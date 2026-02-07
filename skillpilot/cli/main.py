"""
SkillPilot CLI - Main entry point

Provides commands for:
- run: Execute playbooks
- runner start: Start a Runner session
- runner tail: View runner logs
- runner cancel: Cancel running command
- runner stop: Stop runner session
"""

import argparse
import sys
import os

from skillpilot.runner.core import Runner
from skillpilot.master.core import Master
from skillpilot.runner.adapters import DemoToolAdapter
from skillpilot.protocol import CancelRequest, StopRequest, CancelScope, StopMode, write_atomic_json, get_current_timestamp_ms
from skillpilot.config import (
    load_config,
    get_command,
    get_session_dir,
    get_heartbeat_interval,
    get_lease_enabled,
)


def cmd_run(args):
    """
    Run a playbook.

    Args:
        args: Parsed command line arguments
    """
    from skillpilot.psp.md_loader import PlaybookLoader, SkillLoader

    print(f"Loading playbook: {args.playbook}", file=sys.stderr)

    # Load playbook
    playbook = PlaybookLoader.load(args.playbook)

    # Load skills
    skills_dir = args.skills_dir or "examples/skills"
    skills = SkillLoader.load_from_directory(skills_dir)

    if not skills:
        print(f"No skills found in {skills_dir}", file=sys.stderr)
        return 1

    print(f"Loaded {len(skills)} skills", file=sys.stderr)

    # Create master
    master = Master(
        playbook=playbook,
        skills=skills,
        session_dir=args.session_dir,
    )

    # Run playbook
    try:
        result = master.run()
        if result.status == "ok":
            print(f"Playbook completed successfully", file=sys.stderr)
            return 0
        else:
            print(f"Playbook failed: {result.failure_reason}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_runner_start(args):
    """
    Start a Runner session with configuration file.

    Args:
        args: Parsed command line arguments
    """
    config = load_config(args.config)

    print(f"Starting runner with config: {args.config}", file=sys.stderr)
    print(f"Commands: {list(config.get('commands', {}).keys())}", file=sys.stderr)

    session_dir = args.session_dir or get_session_dir(config)
    heartbeat_interval = args.heartbeat_interval or get_heartbeat_interval(config)
    enable_lease = not args.disable_lease and get_lease_enabled(config)

    tool_name = args.tool or list(config.get('commands', {}).keys())[0] if config.get('commands') else 'demo'
    command = get_command(config, tool_name)

    if not command:
        print(f"Tool command not found: {tool_name}", file=sys.stderr)
        return 1

    print(f"Tool: {tool_name}", file=sys.stderr)
    print(f"Command: {command}", file=sys.stderr)

    if tool_name == "demo":
        adapter = DemoToolAdapter.create(workdir=session_dir)
    else:
        print(f"Tool '{tool_name}' not yet implemented (requires adapter)", file=sys.stderr)
        return 1

    # Create and run runner
    runner = Runner(
        session_dir=session_dir,
        adapter=adapter,
        heartbeat_interval_s=heartbeat_interval,
        enable_lease=enable_lease,
    )

    try:
        runner.run()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_runner_tail(args):
    """
    Tail runner session output.

    Args:
        args: Parsed command line arguments
    """
    session_out_path = os.path.join(args.session_dir, "log", "session.out")

    if not os.path.exists(session_out_path):
        print(f"Session log not found: {session_out_path}", file=sys.stderr)
        return 1

    print(f"Tailing session output: {session_out_path}", file=sys.stderr)

    try:
        import subprocess
        tail_proc = subprocess.Popen(
            ["tail", "-f", session_out_path],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        tail_proc.wait()
        return 0
    except KeyboardInterrupt:
        print("\nTail stopped", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_runner_cancel(args):
    """
    Cancel a running command.

    Args:
        args: Parsed command line arguments
    """
    ctl_dir = os.path.join(args.session_dir, "ctl")
    os.makedirs(ctl_dir, exist_ok=True)

    cancel_path = os.path.join(ctl_dir, "cancel.json")

    from skillpilot.protocol import CancelScope
    cancel = CancelRequest(
        scope=CancelScope.CURRENT if args.all else CancelScope.CMD_ID,
        cmd_id=args.cmd_id if not args.all else None,
        ts=get_current_timestamp_ms(),
    )

    write_atomic_json(cancel_path, cancel.to_dict())

    if args.all:
        print(f"Cancel request written (current command)", file=sys.stderr)
    else:
        print(f"Cancel request written for command: {args.cmd_id}", file=sys.stderr)

    return 0


def cmd_runner_stop(args):
    """
    Stop a runner session.

    Args:
        args: Parsed command line arguments
    """
    ctl_dir = os.path.join(args.session_dir, "ctl")
    os.makedirs(ctl_dir, exist_ok=True)

    stop_path = os.path.join(ctl_dir, "stop.json")

    from skillpilot.protocol import StopMode
    stop = StopRequest(
        mode=StopMode.FORCE if args.force else StopMode.GRACEFUL,
        ts=get_current_timestamp_ms(),
    )

    write_atomic_json(stop_path, stop.to_dict())

    mode = "force" if args.force else "graceful"
    print(f"Stop request written (mode: {mode})", file=sys.stderr)

    return 0


def main():
    """Main entry point for SkillPilot CLI"""

    parser = argparse.ArgumentParser(
        description="SkillPilot - EDA Tool Orchestration System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run a playbook")
    run_parser.add_argument("--playbook", required=True, help="Path to playbook file")
    run_parser.add_argument("--skills-dir", default="examples/skills", help="Directory containing skill files")
    run_parser.add_argument("--session-dir", help="Session directory (default: auto-generated)")
    run_parser.set_defaults(func=cmd_run)

    # runner start command
    runner_start_parser = subparsers.add_parser("runner", help="Runner commands")
    runner_subparsers = runner_start_parser.add_subparsers(dest="runner_command", help="Runner subcommands")

    start_parser = runner_subparsers.add_parser("start", help="Start a Runner session")
    start_parser.add_argument("--config", required=True, help="Path to runner configuration file (YAML)")
    start_parser.add_argument("--tool", help="Tool name from config (default: first tool)")
    start_parser.add_argument("--session-dir", help="Session directory path (overrides config)")
    start_parser.add_argument("--heartbeat-interval", type=float, help="Heartbeat interval (seconds, overrides config)")
    start_parser.add_argument("--disable-lease", action="store_true", help="Disable lease enforcement (overrides config)")
    start_parser.set_defaults(func=cmd_runner_start)

    tail_parser = runner_subparsers.add_parser("tail", help="Tail runner session output")
    tail_parser.add_argument("--session-dir", required=True, help="Session directory path")
    tail_parser.set_defaults(func=cmd_runner_tail)

    cancel_parser = runner_subparsers.add_parser("cancel", help="Cancel running command")
    cancel_parser.add_argument("--session-dir", required=True, help="Session directory path")
    cancel_parser.add_argument("--cmd-id", help="Specific command ID to cancel")
    cancel_parser.add_argument("--all", action="store_true", help="Cancel current command")
    cancel_parser.set_defaults(func=cmd_runner_cancel)

    stop_parser = runner_subparsers.add_parser("stop", help="Stop runner session")
    stop_parser.add_argument("--session-dir", required=True, help="Session directory path")
    stop_parser.add_argument("--force", action="store_true", help="Force stop immediately")
    stop_parser.set_defaults(func=cmd_runner_stop)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "runner" and not args.runner_command:
        start_parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
