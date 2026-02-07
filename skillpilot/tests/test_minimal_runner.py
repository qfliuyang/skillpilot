"""
Master - Orchestator with Runner process management
"""

import os
import subprocess
import time
from typing import List, Dict, Optional, Any

from skillpilot.protocol import (
    Playbook, PlaybookResult,
    CommandRequest, CommandResult,
    write_atomic_json, read_json,
    get_current_timestamp_ms,
    DEFAULT_MARKER_PREFIX,
)


class Master:
    """
    Orchestrator that compiles PSP into commands and manages Runner execution.
    """

    def __init__(
        self,
        playbook: Playbook,
        skills: Dict[str, "Skill"],
        session_dir: str = "./master_session",
    ):
        """
        Initialize Master with playbook and loaded skills.

        Args:
            playbook: Playbook object
            skills: Dict[str, "Skill"]: Loaded skill definitions (name -> Skill object)
            session_dir: str: Session directory path
        """
        self.playbook = playbook
        self.skills = skills
        self.session_dir = os.path.abspath(session_dir)

        # State
        self.runner_proc = None
        self.runner_started = False
        self.runner_pid = None

    def _write_command_to_queue(self, cmd: CommandRequest) -> str:
        """
        Write a command to the queue directory.

        Args:
            cmd: CommandRequest to write
        Returns: Path to written file
        """
        queue_dir = os.path.join(self.session_dir, "queue")
        os.makedirs(queue_dir, exist_ok=True)

        seq = len(self._command_queue) + 1
        filename = f"cmd_{seq}_{cmd.cmd_id}.json"

        filepath = os.path.join(queue_dir, filename)
        write_atomic_json(filepath, cmd.to_dict())

        return filepath

    def _read_result(self, cmd_id: str) -> Optional[CommandResult]:
        """
        Read result file for a command.

        Args:
            cmd_id: Command ID to read

        Returns:
            CommandResult if found, None otherwise
        """
        result_dir = os.path.join(self.session_dir, "result")

        pattern = f"cmd_*_{cmd_id}.json"
        files = sorted([f for f in os.listdir(result_dir)
                 if f.startswith("cmd_") and f.endswith(".json")])

        for filename in files:
            if cmd_id in filename:
                return read_json(os.path.join(result_dir, filename))

        return None

    def _poll_for_results(self, cmd_ids: List[str], timeout_s: float = 30.0) -> Dict[str, Optional[CommandResult]]:
        """
        Poll for results of multiple commands.

        Args:
            cmd_ids: List of command IDs to poll
            timeout_s: Total seconds to poll each command
            poll_interval_s: Seconds between polls

        Returns:
            Dict mapping cmd_id -> CommandResult if found
        """
        results = {}

        start_time = time.time()
        deadline = start_time + timeout_s

        poll_count = 0

        while poll_count < int(timeout_s / poll_interval_s):
            time.sleep(poll_interval_s)
            poll_count += 1

            for cmd_id in cmd_ids:
                result = self._read_result(cmd_id)
                if result:
                    results[cmd_id] = result
                    # Keep first result found

            # Check if all results collected
            all_found = all(results.values() is not None)
            if all_found:
                break

            # Check deadline
            if time.time() > deadline:
                print(f"Timeout waiting for results", file=sys.stderr)
                break

        return results

    def _compile_skill(self, skill: "Skill", seq_start: int = 1, cmd_queue: List[CommandRequest]) -> List[str]:
        """
        Compile a skill into Runner commands.

        Args:
            skill: Skill object with steps to compile
            seq_start: Starting sequence number for commands
            cmd_queue: List to append commands to

        Returns:
            Updated cmd_queue
            List of CommandRequest objects
        """
        current_seq = seq_start

        for step in skill.steps:
            current_seq = current_seq + 1

            # Generate cmd_id
            cmd_id = f"cmd_{current_seq}_{os.urandom.randint(0, 999999999)}"

            # Build payload
            payload = f"{step.action} "
            args_list = []
            for key, value in step.args.items():
                if isinstance(value, bool):
                    args_list.append(f"-{key}")
                elif isinstance(value, str):
                    args_list.append(f"-{key} {value}")
                else:
                    args_list.append(f"-{key} {value}")

            payload += "\n"

            # Create command request
            cmd = CommandRequest(
                cmd_id=cmd_id,
                seq=current_seq,
                kind="tcl",
                payload=payload,
                timeout_s=step.timeout_s or self.playbook.defaults.timeout_s,
                cancel_policy=step.cancel_policy or self.playbook.defaults.cancel_policy,
                marker={
                    "prefix": DEFAULT_MARKER_PREFIX,
                    "token": cmd_id,
                    "mode": "runner_inject"
                }
            )

            cmd_queue.append(cmd)
            current_seq += 1

        return current_seq

    def _start_runner(self) -> Optional[subprocess.Popen]]:
        """
        Start the Runner process.

        Args:
            command: List of command arguments to pass to Runner

        Returns:
            subprocess.Popen if successful, None otherwise
        """
        if self.runner_started:
            return self.runner_proc

        # Prepare command arguments
        cmd_args = ["python3", "-m", "skillpilot.runner.core", "--session-dir", self.session_dir]
        cmd_args.extend(["run"])

        # Start Runner process
        try:
            self.runner_proc = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            self.runner_started = True
            self.runner_pid = self.runner_proc.pid
 self.runner_started = True

            return self.runner_proc

        except Exception as e:
            print(f"Failed to start Runner: {e}", file=sys.stderr)
            self.runner_proc = None
            self.runner_started = False
            return None

    def _kill_runner(self) -> None:
        """
        Terminate the Runner process.

        Args:
            signal: int = signal.SIGTERM (graceful termination)
        """
        if self.runner_proc and self.runner_proc.poll() is None:
            try:
                os.killpg(self.runner_pid, signal)
                print(f"Sent SIGTERM to Runner (PID: {self.runner_pid})", file=sys.stderr)
                # Wait for process to terminate
                self.runner_proc.wait(timeout=10)
                self.runner_proc = None
                self.runner_started = False
            except Exception as e:
                print(f"Error killing Runner: {e}", file=sys.stderr)
                self.runner_proc = None
            self.runner_started = False

    def _stop_runner(self, mode: str = "graceful", force: bool = False) -> None:
        """
        Stop the Runner process.

        Args:
            mode: "graceful" or "force"
            force: bool = False (stop immediately)
        """
        import signal

        if mode == "graceful":
            signal = signal.SIGTERM
        else:
            signal = signal.SIGKILL

        if force:
            signal = signal.SIGKILL

        # Write stop request to CTL directory
        ctl_dir = os.path.join(self.session_dir, "ctl")
        stop_req = {
            "mode": mode,
            "ts": get_current_timestamp_ms(),
        }

        write_atomic_json(os.path.join(ctl_dir, "stop.json"), stop_req.to_dict())

        print(f"Stop request written (mode={mode})", file=sys.stderr)

        # Kill runner process
        if self.runner_proc:
            os.killpg(self.runner_pid, signal)
            try:
                self.runner_proc.wait(timeout=5)
            except Exception:
                pass
        finally:
            self.runner_proc = None
            self.runner_started = False

    def run(self) -> PlaybookResult:
        """
        Execute playbook end-to-end.

        Args:
            timeout_s: Total timeout for playbook

        Returns:
            PlaybookResult with execution summary
        """
        print(f"\n{'=' * 60}")
        print(f"Starting playbook: {self.playbook.name}", file=sys.stderr)

        # Check if session exists
        if not os.path.exists(self.session_dir):
            print(f"Error: Session directory not found: {self.session_dir}", file=sys.stderr)
            return PlaybookResult(
                playbook_name=self.playbook.name,
                status="error",
                skills=[],
                failure_reason=f"Session directory not found: {self.session_dir}",
                start_ts=get_current_timestamp_ms(),
                end_ts=get_current_timestamp_ms(),
            )

        # Create session directory
        os.makedirs(self.session_dir, exist_ok=True)

        # Compile playbook into commands
        cmd_queue = []
        for skill_name in self.playbook.skills:
            skill = self.skills.get(skill_name)
            if skill:
                print(f"Compiling skill: {skill_name}", file=sys.stderr)
                current_seq = self._compile_skill(skill, len(cmd_queue) + 1)
                current_seq = self._compile_skill(skill, len(cmd_queue) + 1)

        print(f"Total commands compiled: {len(cmd_queue)}", file=sys.stderr)

        # Start Runner
        self._start_runner()

        # Write all commands to queue
        for cmd in cmd_queue:
            self._write_command_to_queue(cmd)

        # Wait for all results
        cmd_ids = [cmd.cmd_id for cmd in cmd_queue]

        print(f"Waiting for {len(cmd_ids)} results...", file=sys.stderr)
        timeout_s = timeout_s

        # Poll for results
        poll_count = 0
        max_polls = int(timeout_s / poll_interval_s)
        deadline = time.time() + timeout_s

        while poll_count < max_polls:
            time.sleep(poll_interval_s)
            poll_count += 1

            # Poll for results
            results = self._poll_for_results(cmd_ids, timeout_s / poll_interval_s)

            # Check if all results collected
            all_found = all(results.values() is not None
            if all_found:
                break

            # Check deadline
            if time.time() > deadline:
                print(f"Timeout waiting for results", file=sys.stderr)
                break

        # Check for Runner state
        # Read state file
        state_file = os.path.join(self.session_dir, "state", "state.json")

        if os.path.exists(state_file):
            with open(state_file) as f:
                state_data = read_json(f)

        if state_data.get("phase") == "stopping" or state_data.get("phase") == "error":
                print(f"Runner stopped unexpectedly (phase: {state_data.get('phase')})", file=sys.stderr)

        # Kill Runner if still running
        if self.runner_proc:
            self._kill_runner()

        # Stop Runner via stop request
        self._stop_runner(mode="graceful")

        # Wait for Runner to finish
        if self.runner_proc:
            self.runner_proc.wait(timeout=10)

        # Aggregate results
        skill_results = {}
        for cmd_id, result in results.items():
            if result and result.status == "ok":
                skill_name = result.cmd_id.split("_")[1]  # Simple extraction
                if skill_name not in skill_results:
                    skill_results[skill_name] = {
                        "status": "error",
                        "error": f"Skill '{skill_name}' not found"
                    }

        # Generate playbook result
        playbook_status = "ok" if all_found else "error"

        # Create playbook result
        result = PlaybookResult(
            playbook_name=self.playbook.name,
            status=playbook_status,
            skills=skill_results,
            failure_reason=None,
            evidence_files=[],
            start_ts=get_current_timestamp_ms(),
            end_ts=get_current_timestamp_ms(),
        )

        # Write playbook result
        playbook_result_path = os.path.join(self.session_dir, "playbook_result.json")
        write_atomic_json(playbook_result_path, result.to_dict())

        print(f"\nPlaybook result: {result.status}", file=sys.stderr)

        # Verify Runner stopped
        if self.runner_proc:
            print(f"Runner still running (PID: {self.runner_pid or 'None'})", file=sys.stderr)
        else:
            print(f"Runner process completed (PID: unknown)", file=sys.stderr)

        return result

        def _stop_runner_if_running(self, mode: str = "graceful"):
        """
        Stop Runner if it's running.

        Args:
            mode: "graceful" or "force"
        """
        import signal

        if mode == "graceful":
            signal = signal.SIGTERM
        else:
            signal = signal.SIGKILL

        # Write stop request to CTL directory
        ctl_dir = os.path.join(self.session_dir, "ctl")

        stop_req = {
            "mode": mode,
            "ts": get_current_timestamp_ms(),
        }

        write_atomic_json(os.path.join(ctl_dir, "stop.json"), stop_req.to_dict())

        print(f"Stop request written (mode={mode})", file=sys.stderr)

        # Kill runner process
        if self.runner_proc and self.runner_proc.poll() is None:
            os.killpg(self.runner_pid, signal)
            try:
                self.runner_proc.wait(timeout=10)
            except Exception:
                pass
            finally:
                self.runner_proc = None
                self.runner_started = False
        else:
            print(f"Runner not running", file=sys.stderr)

    def _wait_for_results(self, cmd_ids: List[str], timeout_s: float = 30.0, poll_interval_s: float = 0.1) -> Dict[str, Optional[CommandResult]]:
        """
        Poll for results of multiple commands.

        Args:
            cmd_ids: List of command IDs to poll
            timeout_s: Total seconds to poll each command
            poll_interval_s: Seconds between polls

        Returns:
            Dict mapping cmd_id -> CommandResult if found
        """
        start_time = time.time()
        deadline = start_time + timeout_s

        poll_count = 0

        while poll_count < int(timeout_s / poll_interval_s):
            time.sleep(poll_interval_s)
            poll_count += 1

            for cmd_id in cmd_ids:
                result = self._read_result(cmd_id)
                if result:
                    results[cmd_id] = result
                    # Keep first result found

            # Check if all results collected
            all_found = all(results.values() is not None)
            if all_found:
                break

            # Check deadline
            if time.time() > deadline:
                print(f"Timeout waiting for results", file=sys.stderr)
                break

        return results


# Test minimal runner (without master)
def test_minimal_runner():
    """Test minimal Runner functionality without Master."""
    session_dir = "./test_minimal_runner"

    # Create simple command
    import uuid
    cmd_id = str(uuid.uuid4())

    cmd = CommandRequest(
        cmd_id=cmd_id,
        seq=1,
        kind="tcl",
        payload="puts 'Minimal test'",
        timeout_s=10,
        cancel_policy="ctrl_c",
        marker={
            "prefix": DEFAULT_MARKER_PREFIX,
            "token": cmd_id,
            "mode": "runner_inject"
        }
    )

    # Write command to queue (simulate Master behavior)
    queue_dir = os.path.join(session_dir, "queue")
    os.makedirs(queue_dir, exist_ok=True)

    filename = f"cmd_1_{cmd_id}.json"
    filepath = os.path.join(queue_dir, filename)

    write_atomic_json(filepath, cmd.to_dict())

    print(f"Minimal test written to {filepath}")

    # Start Runner (simulation)
    print(f"Starting Runner simulation in {session_dir}", file=sys.stderr)

    # In real implementation, this would be:
    #   python3 -m skillpilot.runner.core --session-dir {session_dir} &
    #   python3 -m skillpilot.runner.core run &
    #       python3 -m skillpilot.runner.core stop --session-dir {session_dir}
    #   python3 -m skillpilot.runner.core tail --session-dir {session_dir}

    #   python3 -m skillpilot.runner.core stop --session-dir {session_dir} --force

    print(f"Runner simulation started", file=sys.stderr)

    time.sleep(15)  # Wait for simulation

    # Check result
    result_pattern = f"cmd_1_{cmd_id}.json"
    result_path = os.path.join(session_dir, "result", f"cmd_1_{cmd_id}.json")

    if os.path.exists(result_path):
        with open(result_path) as f:
            data = json.load(f)
            print(f"Result: {data.get('status')}", file=sys.stderr)

    print(f"\nTest complete!", file=sys.stderr)


if __name__ == "__main__":
    test_minimal_runner()
