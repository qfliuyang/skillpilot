"""
SkillPilot Master - PSP orchestrator and compiler

The Master:
1. Loads Playbook and Skill definitions
2. Compiles skill steps into Runner commands
3. Starts Runner sessions
4. Writes commands to queue
5. Waits for results
6. Aggregates results into playbook_result.json
"""

import os
import sys
import time
import uuid
from typing import Dict, List, Optional
from datetime import datetime

from skillpilot.psp.schema import Playbook, Skill, PlaybookDefaults
from skillpilot.protocol import (
    CommandRequest,
    CommandResult,
    PlaybookResult,
    CancelPolicy,
    write_atomic_json,
    read_json,
    get_current_timestamp_ms,
    DEFAULT_MARKER_PREFIX,
)


class Master:
    """
    SkillPilot Master - Orchestrates Playbook execution via Runner.

    The Master manages the lifecycle of playbook execution:
    - Loads PSP definitions
    - Compiles to Runner commands
    - Starts Runner session
    - Monitors execution
    - Aggregates results
    """

    def __init__(
        self,
        playbook: Playbook,
        skills: Dict[str, Skill],
        session_dir: Optional[str] = None,
    ):
        """
        Initialize Master.

        Args:
            playbook: Playbook to execute
            skills: Dictionary of loaded skills
            session_dir: Session directory (default: ./sessions/<timestamp>)
        """
        self.playbook = playbook
        self.skills = skills
        self.session_dir = session_dir or self._create_session_dir()
        self.session_id: str = os.path.basename(self.session_dir)

        # Track execution state
        self.cmd_seq: int = 0
        self.results: Dict[str, CommandResult] = {}
        self.skill_results: Dict[str, Dict] = {}
        self.stopping: bool = False

    def _create_session_dir(self) -> str:
        """Create a new session directory"""
        base_dir = os.path.join(os.getcwd(), "sessions")
        os.makedirs(base_dir, exist_ok=True)

        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        session_dir = os.path.join(base_dir, session_name)
        os.makedirs(session_dir, exist_ok=True)

        return session_dir

    def _compile_skill(self, skill: Skill) -> List[CommandRequest]:
        """
        Compile a skill into Runner commands.

        Args:
            skill: Skill to compile

        Returns:
            List of CommandRequest objects
        """
        commands = []

        for step in skill.steps:
            self.cmd_seq += 1
            cmd_id = str(uuid.uuid4())

            # Build Tcl payload
            # Format: poke::<action> <args...>
            args_str = ""
            for key, value in step.args.items():
                if isinstance(value, str):
                    args_str += f' -{key} "{value}"'
                elif isinstance(value, bool):
                    if value:
                        args_str += f' -{key}'
                else:
                    args_str += f' -{key} {value}'

            payload = f'poke::{step.action}{args_str}\n'

            # Create command request
            from skillpilot.protocol import Marker, MarkerMode

            cmd = CommandRequest(
                cmd_id=cmd_id,
                seq=self.cmd_seq,
                kind="tcl",
                payload=payload,
                timeout_s=step.timeout_s or self.playbook.defaults.timeout_s,
                cancel_policy=CancelPolicy(self.playbook.defaults.cancel_policy),
                marker=Marker(prefix=DEFAULT_MARKER_PREFIX, token=cmd_id, mode=MarkerMode.RUNNER_INJECT),
            )

            commands.append(cmd)

        return commands

    def _write_command(self, cmd: CommandRequest) -> str:
        """
        Write command file to queue.

        Args:
            cmd: Command to write

        Returns:
            Path to written file
        """
        queue_dir = os.path.join(self.session_dir, "queue")
        os.makedirs(queue_dir, exist_ok=True)

        filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.json"
        filepath = os.path.join(queue_dir, filename)
        write_atomic_json(filepath, cmd.to_dict())

        return filepath

    def _read_result(self, cmd: CommandRequest) -> Optional[CommandResult]:
        """
        Read result file for a command.

        Args:
            cmd: Command to read result for

        Returns:
            CommandResult if found, None otherwise
        """
        result_dir = os.path.join(self.session_dir, "result")
        filename = f"cmd_{cmd.seq}_{cmd.cmd_id}.json"
        filepath = os.path.join(result_dir, filename)

        if not os.path.exists(filepath):
            return None

        data = read_json(filepath)
        if data:
            return CommandResult.from_dict(data)
        return None

    def _wait_for_result(self, cmd: CommandRequest, timeout_s: int = 3600) -> Optional[CommandResult]:
        """
        Wait for result file to appear.

        Args:
            cmd: Command to wait for
            timeout_s: Maximum time to wait (default 1 hour)

        Returns:
            CommandResult if completed, None if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout_s:
            result = self._read_result(cmd)
            if result:
                return result

            time.sleep(0.5)

        return None

    def _run_skill(self, skill_name: str) -> Dict:
        """
        Execute a single skill.

        Args:
            skill_name: Name of skill to run

        Returns:
            Dictionary with skill execution results
        """
        if skill_name not in self.skills:
            return {
                "name": skill_name,
                "status": "error",
                "error": f"Skill not found: {skill_name}",
            }

        skill = self.skills[skill_name]

        print(f"Compiling skill: {skill_name}", file=sys.stderr)

        # Compile skill to commands
        commands = self._compile_skill(skill)

        print(f"  -> Generated {len(commands)} commands", file=sys.stderr)

        # Write commands to queue
        for cmd in commands:
            self._write_command(cmd)

        # Wait for all commands to complete
        skill_results = []
        all_ok = True

        for cmd in commands:
            print(f"  -> Waiting for command: {cmd.cmd_id}", file=sys.stderr)
            result = self._wait_for_result(cmd)

            if not result:
                skill_results.append({
                    "cmd_id": cmd.cmd_id,
                    "status": "timeout",
                    "error": "Command timed out",
                })
                all_ok = False
            elif result.status == "ok":
                self.results[cmd.cmd_id] = result
                skill_results.append({
                    "cmd_id": cmd.cmd_id,
                    "status": result.status,
                    "output_path": result.output_path,
                })
            else:
                self.results[cmd.cmd_id] = result
                skill_results.append({
                    "cmd_id": cmd.cmd_id,
                    "status": result.status,
                    "error": result.exit_reason,
                })
                all_ok = False

        return {
            "name": skill_name,
            "status": "ok" if all_ok else "error",
            "commands": skill_results,
        }

    def run(self) -> PlaybookResult:
        """
        Execute the playbook.

        Returns:
            PlaybookResult with execution summary
        """
        start_ts = get_current_timestamp_ms()

        print(f"Starting playbook execution: {self.playbook.name}", file=sys.stderr)
        print(f"Session directory: {self.session_dir}", file=sys.stderr)

        try:
            # Execute each skill
            for skill_name in self.playbook.skills:
                if self.stopping:
                    break

                print(f"\nRunning skill: {skill_name}", file=sys.stderr)
                result = self._run_skill(skill_name)
                self.skill_results[skill_name] = result

                # Fail-fast if enabled
                if self.playbook.defaults.fail_fast and result["status"] != "ok":
                    print(f"Skill {skill_name} failed, stopping (fail_fast=True)", file=sys.stderr)
                    break

            # Generate playbook result
            end_ts = get_current_timestamp_ms()
            status = self._determine_playbook_status()

            # Collect evidence files
            evidence_files = self._collect_evidence()

            playbook_result = PlaybookResult(
                playbook_name=self.playbook.name,
                status=status,
                skills=list(self.skill_results.values()),
                failure_reason=self._get_failure_reason(),
                evidence_files=evidence_files,
                start_ts=start_ts,
                end_ts=end_ts,
            )

            # Write playbook result
            result_path = os.path.join(self.session_dir, "playbook_result.json")
            write_atomic_json(result_path, playbook_result.to_dict())

            print(f"\nPlaybook execution completed: {status}", file=sys.stderr)
            print(f"Result file: {result_path}", file=sys.stderr)

            return playbook_result

        except Exception as e:
            print(f"Error during playbook execution: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

            return PlaybookResult(
                playbook_name=self.playbook.name,
                status="error",
                skills=list(self.skill_results.values()),
                failure_reason=str(e),
                evidence_files=[],
                start_ts=start_ts,
                end_ts=get_current_timestamp_ms(),
            )

    def _determine_playbook_status(self) -> str:
        """Determine overall playbook status"""
        if self.stopping:
            return "cancelled"

        for skill_result in self.skill_results.values():
            if skill_result.get("status") != "ok":
                return "error"

        return "ok"

    def _get_failure_reason(self) -> Optional[str]:
        """Get failure reason if playbook failed"""
        for skill_name, skill_result in self.skill_results.items():
            if skill_result.get("status") != "ok":
                return f"Skill '{skill_name}' failed: {skill_result.get('error', 'unknown')}"

        return None

    def _collect_evidence(self) -> List[str]:
        """Collect evidence files from outputs"""
        evidence = []
        output_dir = os.path.join(self.session_dir, "output")

        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.endswith(".out"):
                    evidence.append(os.path.join(output_dir, filename))

        return evidence

    def stop(self):
        """Stop playbook execution gracefully"""
        print("Stopping playbook execution...", file=sys.stderr)
        self.stopping = True


def main():
    """Entry point for running master directly"""
    import argparse

    parser = argparse.ArgumentParser(description="SkillPilot Master")
    parser.add_argument(
        "--playbook",
        required=True,
        help="Path to playbook file"
    )
    parser.add_argument(
        "--skills-dir",
        default="examples/skills",
        help="Directory containing skill files"
    )
    parser.add_argument(
        "--session-dir",
        help="Session directory (default: auto-generated)"
    )

    args = parser.parse_args()

    # Load playbook
    from skillpilot.psp.md_loader import PlaybookLoader, SkillLoader
    playbook = PlaybookLoader.load(args.playbook)

    # Load skills
    skills = SkillLoader.load_from_directory(args.skills_dir)

    # Create and run master
    master = Master(
        playbook=playbook,
        skills=skills,
        session_dir=args.session_dir,
    )

    try:
        result = master.run()
        print(f"\nPlaybook result: {result.status}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrupted by Ctrl-C", file=sys.stderr)
        master.stop()
