"""
SkillPilot Runner - Core implementation

The Runner is the session-based executor that manages EDA tool PTY sessions.
It reads commands from the queue, executes them via PTY, and writes results.
"""

import os
import sys
import time
import uuid
import select
import signal
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from skillpilot.protocol import (
    CommandRequest,
    CommandResult,
    SessionState,
    RunnerPhase,
    CommandStatus,
    CancelRequest,
    StopRequest,
    LeaseInfo,
    write_atomic_json,
    read_json,
    get_current_timestamp_ms,
    DEFAULT_MARKER_PREFIX,
)
from skillpilot.runner.adapters import ToolAdapter, AdapterConfig


class Runner:
    """
    SkillPilot Runner - PTY-based EDA tool executor.

    The Runner:
    1. Creates session directory structure
    2. Starts tool process with PTY
    3. Polls queue for commands
    4. Executes commands via PTY with marker detection
    5. Writes results, outputs, and logs
    6. Handles cancel/stop requests (M2)
    7. Manages timeout/lease (M2)
    """

    # Session directory structure
    DIR_QUEUE = "queue"
    DIR_RESULT = "result"
    DIR_OUTPUT = "output"
    DIR_LOG = "log"
    DIR_CTL = "ctl"
    DIR_STATE = "state"
    DIR_INFLIGHT = "inflight"  # For idempotency (M2)

    # File names
    FILE_SESSION_OUT = "session.out"
    FILE_META_LOG = "meta.log"
    FILE_STATE = "state.json"
    FILE_HEARTBEAT = "heartbeat.json"
    FILE_LEASE = "lease.json"
    FILE_CANCEL = "cancel.json"
    FILE_STOP = "stop.json"

    def __init__(
        self,
        session_dir: str,
        adapter: ToolAdapter,
        heartbeat_interval_s: float = 5.0,
        enable_lease: bool = True,
    ):
        """
        Initialize Runner.

        Args:
            session_dir: Path to session directory (will be created if needed)
            adapter: Tool adapter to manage PTY connection
            heartbeat_interval_s: Interval for heartbeat updates
            enable_lease: Whether to enforce lease expiration
        """
        self.session_dir = os.path.abspath(session_dir)
        self.adapter = adapter
        self.heartbeat_interval_s = heartbeat_interval_s
        self.enable_lease = enable_lease

        self.session_id: str = str(uuid.uuid4())
        self.runner_pid: int = os.getpid()
        self.state: Optional[SessionState] = None
        self.stopping: bool = False

        # Output buffer for marker detection (supports chunks)
        self.output_buffer: List[bytes] = []

        # Session log file handle
        self.session_log_file = None

        # Command execution state (for M2 governance)
        self.current_cmd: Optional[CommandRequest] = None
        self.cancel_requested: bool = False
        self.cancel_handled: bool = False

    def _get_path(self, *parts: str) -> str:
        """Get path within session directory"""
        return os.path.join(self.session_dir, *parts)

    def _create_session_dir(self) -> None:
        """Create session directory structure"""
        dirs = [
            self.DIR_QUEUE,
            self.DIR_RESULT,
            self.DIR_OUTPUT,
            self.DIR_LOG,
            self.DIR_CTL,
            self.DIR_STATE,
            self.DIR_INFLIGHT,  # M2: inflight tracking
        ]
        for d in dirs:
            os.makedirs(self._get_path(d), exist_ok=True)

    def _write_state(self, phase: RunnerPhase, current_cmd_id: Optional[str] = None) -> None:
        """Write current state to state file"""
        state = SessionState(
            phase=phase,
            session_id=self.session_id,
            runner_pid=self.runner_pid,
            tool_pid=self.adapter.pid,
            current_cmd_id=current_cmd_id,
            updated_at=get_current_timestamp_ms(),
        )
        write_atomic_json(self._get_path(self.DIR_STATE, self.FILE_STATE), state.to_dict())
        self.state = state

    def _write_heartbeat(self) -> None:
        """Write heartbeat file"""
        heartbeat = {"timestamp": get_current_timestamp_ms()}
        write_atomic_json(
            self._get_path(self.DIR_STATE, self.FILE_HEARTBEAT),
            heartbeat
        )

    def _append_session_log(self, data: bytes) -> None:
        """Append data to session.out log file"""
        if self.session_log_file is None:
            self.session_log_file = open(
                self._get_path(self.DIR_LOG, self.FILE_SESSION_OUT),
                "ab"
            )
        self.session_log_file.write(data)
        self.session_log_file.flush()

    def _scan_queue(self) -> List[CommandRequest]:
        """
        Scan queue directory for command files.

        Returns:
            List of pending commands sorted by filename
        """
        queue_dir = self._get_path(self.DIR_QUEUE)
        if not os.path.exists(queue_dir):
            return []

        commands = []
        for filename in sorted(os.listdir(queue_dir)):
            if filename.startswith("cmd_") and filename.endswith(".json"):
                filepath = os.path.join(queue_dir, filename)
                try:
                    data = read_json(filepath)
                    if data:
                        cmd = CommandRequest.from_dict(data)
                        commands.append(cmd)
                except Exception as e:
                    # Log error but continue
                    print(f"Error reading {filename}: {e}", file=sys.stderr)

        return commands

    def _check_result_exists(self, cmd_id: str) -> bool:
        """
        Check if result file exists for a command.

        Args:
            cmd_id: Command ID to check

        Returns:
            True if result file exists
        """
        result_dir = self._get_path(self.DIR_RESULT)
        for filename in os.listdir(result_dir) if os.path.exists(result_dir) else []:
            if filename.endswith(".json") and cmd_id in filename:
                return True
        return False

    def _check_control_files(self) -> tuple[Optional[CancelRequest], Optional[StopRequest], Optional[LeaseInfo]]:
        """
        Check for control files (cancel, stop, lease).

        Returns:
            Tuple of (cancel_req, stop_req, lease_info)
        """
        cancel = None
        stop = None
        lease = None

        # Check cancel.json
        cancel_path = self._get_path(self.DIR_CTL, self.FILE_CANCEL)
        if os.path.exists(cancel_path):
            try:
                data = read_json(cancel_path)
                if data:
                    cancel = CancelRequest.from_dict(data)
            except Exception:
                pass

        # Check stop.json
        stop_path = self._get_path(self.DIR_CTL, self.FILE_STOP)
        if os.path.exists(stop_path):
            try:
                data = read_json(stop_path)
                if data:
                    stop = StopRequest.from_dict(data)
            except Exception:
                pass

        # Check lease.json
        lease_path = self._get_path(self.DIR_STATE, self.FILE_LEASE)
        if os.path.exists(lease_path):
            try:
                data = read_json(lease_path)
                if data:
                    lease = LeaseInfo.from_dict(data)
            except Exception:
                pass

        return cancel, stop, lease

    def _execute_command(
        self,
        cmd: CommandRequest,
        output_path: str,
    ) -> CommandResult:
        """
        Execute a single command via PTY.

        Args:
            cmd: Command request to execute
            output_path: Path to write command output

        Returns:
            Command result with status and metadata
        """
        start_ts = get_current_timestamp_ms()
        self.current_cmd = cmd
        self.cancel_requested = False
        self.cancel_handled = False

        # Open output file
        output_file = open(output_path, "wb")

        # Reset output buffer
        self.output_buffer = []

        # Write payload to PTY
        payload = cmd.payload

        # Inject marker if in runner_inject mode
        marker_text = ""
        if cmd.marker.mode == "runner_inject":
            marker_text = f'puts "{cmd.marker.prefix} {cmd.marker.token}"\n'
            payload += marker_text

        self.adapter.write(payload)

        # Read output until marker detected or timeout
        marker_pattern = f"{cmd.marker.prefix} {cmd.marker.token}".encode('utf-8')
        marker_found = False
        buffer = b""

        start_time = time.time()
        timeout = cmd.timeout_s or 300  # Default 5 minutes

        while not marker_found and not self.stopping:
            # Check timeout
            if time.time() - start_time > timeout:
                output_file.close()
                self.current_cmd = None
                return CommandResult(
                    cmd_id=cmd.cmd_id,
                    status=CommandStatus.TIMEOUT,
                    start_ts=start_ts,
                    end_ts=get_current_timestamp_ms(),
                    exit_reason="timeout",
                    output_path=output_path,
                )

            # Check control files periodically (M2)
            cancel, stop, lease = self._check_control_files()

            # Handle stop
            if stop is not None:
                self.stopping = True
                break

            # Handle lease expiration
            if self.enable_lease and lease is not None and lease.is_expired():
                print("Lease expired during command execution", file=sys.stderr)
                self.stopping = True
                break

            # Handle cancel request (M2 - full implementation)
            if cancel is not None:
                # Check if this command should be cancelled
                if cancel.scope == "current" or cancel.cmd_id == cmd.cmd_id:
                    if not self.cancel_requested:
                        self.cancel_requested = True
                        print(f"Cancel requested for command {cmd.cmd_id}", file=sys.stderr)

                        # Execute cancel policy
                        if cmd.cancel_policy == "ctrl_c":
                            # Send Ctrl-C (\x03)
                            self.adapter.write("\x03")
                            self.cancel_handled = True
                            # Give it time to react, then break
                            time.sleep(0.5)
                            break
                        elif cmd.cancel_policy == "terminate_tool":
                            self.adapter.terminate()
                            time.sleep(1)
                            break
                        elif cmd.cancel_policy == "terminate_session":
                            self.adapter.kill()
                            self.stopping = True
                            break

            # Read from PTY
            try:
                data = self.adapter.read(timeout=0.1, size=4096)
                if data:
                    output_file.write(data)
                    output_file.flush()

                    # Append to session log
                    self._append_session_log(data)

                    # Check for marker (may span chunks)
                    buffer += data
                    if marker_pattern in buffer:
                        marker_found = True
                        break

                    # Keep buffer limited
                    if len(buffer) > 8192:
                        buffer = buffer[-8192:]

            except OSError as e:
                # Tool likely died
                output_file.close()
                self.current_cmd = None
                return CommandResult(
                    cmd_id=cmd.cmd_id,
                    status=CommandStatus.ERROR,
                    start_ts=start_ts,
                    end_ts=get_current_timestamp_ms(),
                    exit_reason=f"tool_died: {e}",
                    output_path=output_path,
                )

        output_file.close()
        end_ts = get_current_timestamp_ms()
        self.current_cmd = None

        if marker_found:
            exit_reason = "marker_seen"
            status = CommandStatus.OK
        elif self.cancel_requested:
            exit_reason = "ctrl_c"
            status = CommandStatus.CANCELLED
        else:
            exit_reason = "stop_requested"
            status = CommandStatus.CANCELLED

        return CommandResult(
            cmd_id=cmd.cmd_id,
            status=status,
            start_ts=start_ts,
            end_ts=end_ts,
            exit_reason=exit_reason,
            output_path=output_path,
        )

    def _move_to_inflight(self, cmd: CommandRequest) -> str:
        """
        Move command file to inflight directory.

        Args:
            cmd: Command to move

        Returns:
            Path to inflight file
        """
        src_filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.json"
        src_path = self._get_path(self.DIR_QUEUE, src_filename)
        inflight_path = self._get_path(self.DIR_INFLIGHT, src_filename)
        os.rename(src_path, inflight_path)
        return inflight_path

    def _remove_from_inflight(self, cmd: CommandRequest) -> None:
        """
        Remove command from inflight after completion.

        Args:
            cmd: Command to remove
        """
        filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.json"
        inflight_path = self._get_path(self.DIR_INFLIGHT, filename)
        try:
            os.remove(inflight_path)
        except OSError:
            pass

    def run(self) -> None:
        """
        Main runner loop.

        This method:
        1. Creates session directory
        2. Starts tool adapter
        3. Enters main loop:
           - Poll queue for commands
           - Execute commands (idempotent - skip if result exists)
           - Write results
           - Check control files (cancel/stop)
           - Update heartbeat
        """
        # Starting phase
        print(f"Starting Runner session: {self.session_id}", file=sys.stderr)
        print(f"Session directory: {self.session_dir}", file=sys.stderr)

        self._create_session_dir()
        self._write_state(RunnerPhase.STARTING)

        # Start tool
        tool_pid = self.adapter.start()
        print(f"Tool started with PID: {tool_pid}", file=sys.stderr)

        self._write_state(RunnerPhase.IDLE)

        # Main loop
        last_heartbeat = time.time()

        try:
            while not self.stopping:
                current_time = time.time()

                # Update heartbeat periodically
                if current_time - last_heartbeat >= self.heartbeat_interval_s:
                    self._write_heartbeat()
                    last_heartbeat = current_time

                # Check control files
                cancel, stop, lease = self._check_control_files()

                # Handle stop (M2 - proper mode handling)
                if stop is not None:
                    print(f"Stop requested: {stop.mode}", file=sys.stderr)
                    if stop.mode == "force":
                        # Force: terminate immediately
                        print("Force stop - terminating tool...", file=sys.stderr)
                        self.stopping = True
                        break
                    else:
                        # Graceful: wait for current command to finish
                        if self.state and self.state.phase == RunnerPhase.BUSY:
                            print("Graceful stop - waiting for current command...", file=sys.stderr)
                            # Don't break yet, let current command finish
                        else:
                            self.stopping = True
                            break

                # Handle lease expiration (M2 - basic check)
                if lease is not None and lease.is_expired():
                    print("Lease expired, stopping...", file=sys.stderr)
                    # If no command running (IDLE), stop immediately
                    if not self.state or self.state.phase != RunnerPhase.BUSY:
                        self.stopping = True
                        break
                    # If command running (BUSY), let it finish gracefully
                    else:
                        self.stopping = True
                        break

                # Scan queue for commands
                commands = self._scan_queue()

                if commands:
                    # Process next command
                    cmd = commands[0]

                    # Check if result already exists (idempotent)
                    if not self._check_result_exists(cmd.cmd_id):
                        print(f"Executing command: {cmd.cmd_id}", file=sys.stderr)
                        self._write_state(RunnerPhase.BUSY, cmd.cmd_id)

                        # M2: Move to inflight (prevents duplicate execution)
                        inflight_path = self._move_to_inflight(cmd)

                        # Prepare output path
                        output_filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.out"
                        output_path = self._get_path(self.DIR_OUTPUT, output_filename)

                        try:
                            # Execute command
                            result = self._execute_command(cmd, output_path)

                            # Write result file
                            result_filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.json"
                            result_path = self._get_path(self.DIR_RESULT, result_filename)
                            write_atomic_json(result_path, result.to_dict())

                            print(f"Command {cmd.cmd_id} completed: {result.status}", file=sys.stderr)
                        finally:
                            self._remove_from_inflight(cmd)

                    self._write_state(RunnerPhase.IDLE)

                # Small sleep to avoid busy polling
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nInterrupted by Ctrl-C, stopping...", file=sys.stderr)
            self.stopping = True
        except Exception as e:
            print(f"Error in runner loop: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self._write_state(RunnerPhase.ERROR)
            raise
        finally:
            # Cleanup
            print("Runner stopping...", file=sys.stderr)
            self._write_state(RunnerPhase.STOPPING)

            # Close session log
            if self.session_log_file:
                self.session_log_file.close()

            # Terminate tool
            self.adapter.terminate()
            self.adapter.close()

            print("Runner stopped", file=sys.stderr)


def main():
    """Entry point for running runner directly"""
    import argparse

    parser = argparse.ArgumentParser(description="SkillPilot Runner")
    parser.add_argument(
        "--session-dir",
        required=True,
        help="Session directory path"
    )
    parser.add_argument(
        "--adapter",
        default="demo",
        choices=["demo"],
        help="Tool adapter to use"
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=5.0,
        help="Heartbeat interval in seconds"
    )
    parser.add_argument(
        "--disable-lease",
        action="store_true",
        help="Disable lease enforcement (for testing)"
    )

    args = parser.parse_args()

    # Create adapter
    if args.adapter == "demo":
        from skillpilot.runner.adapters import DemoToolAdapter
        adapter = DemoToolAdapter.create(workdir=args.session_dir)
    else:
        raise ValueError(f"Unknown adapter: {args.adapter}")

    # Create and run runner
    runner = Runner(
        session_dir=args.session_dir,
        adapter=adapter,
        heartbeat_interval_s=args.heartbeat_interval,
        enable_lease=not args.disable_lease,
    )
    runner.run()


if __name__ == "__main__":
    main()
