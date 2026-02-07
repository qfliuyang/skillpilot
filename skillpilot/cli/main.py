"""
SkillPilot CLI - Main entry point

Provides commands for:
- run: Execute playbooks
- search: Search for skills or playbooks
- validate: Validate playbook structure
- list skills: List available skills
- list playbooks: List available playbooks
- runner start: Start a Runner session
- runner tail: View runner logs
- runner cancel: Cancel running command
- runner stop: Stop runner session
- session list: List all active sessions
- session current: Show session details
- session delete: Delete a completed session
"""

import argparse
import sys
import os
import traceback
from pathlib import Path
from skillpilot.runner.core import Runner
from skillpilot.runner.adapters import DemoToolAdapter
from skillpilot.psp.md_loader import PlaybookLoader, SkillLoader
from skillpilot.protocol import CancelRequest, StopRequest, write_atomic_json, get_current_timestamp_ms
from skillpilot.config import (
    load_config,
    get_command,
    get_session_dir,
    get_heartbeat_interval,
    get_lease_enabled,
)

# Discovery and validation commands

def cmd_search(args):
    """Search for skills or playbooks matching a pattern"""
    pattern = args.pattern
    print(f"🔍 Searching for: {pattern}", file=sys.stderr)
    
    # Use glob to find files
    from pathlib import Path
    search_paths = [
        "examples/skills",
        "examples/playbooks",
        args.skills_dir if hasattr(args, 'skills_dir') else "examples/skills"
    ]
    
    results = []
    for search_path in search_paths:
        search_dir = Path(search_path)
        if not search_dir.exists():
            continue

        for file_path in search_dir.rglob("*.md"):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if pattern.lower() in content.lower():
                    results.append({
                        'type': 'skill' if 'skill' in str(search_dir).lower() else 'playbook',
                        'name': file_path.stem,
                        'path': str(file_path),
                        'matches': content.count(pattern.lower()),
                    })
    
    
    if results:
        print(f"\n📊 Found {len(results)} match(es):", file=sys.stderr)
        for i, result in enumerate(results, 1):
            print(f"  {i}. [{result['type']}] {result['name']}", file=sys.stderr)
            if result.get('path'):
                print(f"    Path: {result['path']}", file=sys.stderr)
            print(f"    Matches: {result.get('matches', 0)}", file=sys.stderr)
    else:
        print(f"\n❌ No matches found for: {pattern}", file=sys.stderr)
        print(f"💡 Tip: Try a broader search term or check the directories", file=sys.stderr)
    
    return 0


def cmd_validate(args):
    """Validate playbook structure before execution"""
    playbook_path = args.playbook
    
    if not os.path.exists(playbook_path):
        print(f"❌ Playbook not found: {playbook_path}", file=sys.stderr)
        print(f"💡 Tip: Use 'skillpilot list playbooks' to see available playbooks", file=sys.stderr)
        return 1
    
    print(f"🔍 Validating: {playbook_path}", file=sys.stderr)
    
    try:
        # Load and parse playbook
        playbook = PlaybookLoader.load(playbook_path)
        
        # Check for required sections
        has_skills = bool(playbook.skills)
        has_defaults = playbook.defaults is not None
        
        skill_count = len(playbook.skills) if has_skills else 0
        defaults_count = 1 if has_defaults else 0
        
        if not has_skills and not has_defaults:
            print(f"⚠️  Warning: Playbook has no **Skills** or **Defaults** section", file=sys.stderr)
            print(f"💡 Tip: A playbook should define at least one skill or set defaults", file=sys.stderr)
        
        # Validate skill references
        if has_skills:
            skills_dir = args.skills_dir if hasattr(args, 'skills_dir') else "examples/skills"
            for skill_name in playbook.skills:
                skill_file = os.path.join(skills_dir, f"{skill_name}.md")
                if not os.path.exists(skill_file):
                    print(f"❌ Skill file not found: {skill_file}", file=sys.stderr)
                    print(f"💡 Tip: Use 'skillpilot list skills' to see available skills", file=sys.stderr)
                    return 1
        
        print(f"✅ Playbook validation: {playbook_path}", file=sys.stderr)
        print(f"   Skills: {skill_count}", file=sys.stderr)
        print(f"   Defaults: {defaults_count}", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"❌ Error validating playbook: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def cmd_list_skills(args):
    """List all available skills"""
    skills_dir = args.skills_dir if hasattr(args, 'skills_dir') else "examples/skills"
    
    if not os.path.exists(skills_dir):
        print(f"❌ Skills directory not found: {skills_dir}", file=sys.stderr)
        return 1
    
    try:
        skills = SkillLoader.load_from_directory(skills_dir)
        
        print(f"\n📚 Available skills ({len(skills)} found):", file=sys.stderr)
        for skill_name, skill in skills.items():
            print(f"  • {skill.name}", file=sys.stderr)
            if skill.inputs_schema:
                print(f"    Inputs: {', '.join(skill.inputs_schema.keys())}", file=sys.stderr)
        
        print(f"\n💡 Tip: View skill details with 'skillpilot validate <skill_name>'", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"❌ Error loading skills: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def cmd_list_playbooks(args):
    """List all available playbooks"""
    playbooks_dir = args.playbooks_dir if hasattr(args, 'playbooks_dir') else "examples/playbooks"
    
    if not os.path.exists(playbooks_dir):
        print(f"❌ Playbooks directory not found: {playbooks_dir}", file=sys.stderr)
        return 1
    
    try:
        playbooks = [f for f in os.listdir(playbooks_dir) if f.endswith('.md')]
        
        print(f"\n📚 Available playbooks ({len(playbooks)} found):", file=sys.stderr)
        for playbook_name in playbooks:
            print(f"  • {playbook_name}", file=sys.stderr)
        
        print(f"\n💡 Tip: Use 'skillpilot validate <playbook>' to check playbook structure", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"❌ Error loading playbooks: {e}", file=sys.stderr)
        return 1


def cmd_run(args):
    """Run a playbook"""
    from skillpilot.master.core import Master
    
    playbook_path = args.playbook
    skills_dir = args.skills_dir
    session_dir = args.session_dir
    
    if not os.path.exists(playbook_path):
        print(f"❌ Playbook not found: {playbook_path}", file=sys.stderr)
        return 1
    
    try:
        playbook = PlaybookLoader.load(playbook_path)
    except Exception as e:
        print(f"❌ Error loading playbook: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    
    try:
        skills = SkillLoader.load_from_directory(skills_dir)
    except Exception as e:
        print(f"❌ Error loading skills: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    
    print(f"Loaded {len(skills)} skills", file=sys.stderr)

    # Create master
    master = Master(
        playbook=playbook,
        skills=skills,
        session_dir=session_dir,
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


def cmd_session_list(args):
    """List all active sessions"""
    session_dir = args.session_dir or "sessions"
    
    if not os.path.exists(session_dir):
        print(f"❌ Session directory not found: {session_dir}", file=sys.stderr)
        return 1
    
    try:
        sessions = [d for d in os.listdir(session_dir) if d.startswith("session_")]
        
        if not sessions:
            print(f"📭 No active sessions found in {session_dir}", file=sys.stderr)
            return 0
        
        print(f"\n📋 Active sessions ({len(sessions)} found):", file=sys.stderr)
        for session_id in sorted(sessions):
            session_path = os.path.join(session_dir, session_id)
            state_file = os.path.join(session_path, "state", "state.json")
            
            if os.path.exists(state_file):
                import json
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    status = state.get('status', 'unknown')
                    print(f"  • {session_id} - Status: {status}", file=sys.stderr)
            else:
                print(f"  • {session_id} - Status: incomplete", file=sys.stderr)
        
        print(f"\n💡 Tip: Use 'skillpilot session current <session_id>' for details", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"❌ Error listing sessions: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def cmd_session_current(args):
    """Show info about current session"""
    session_dir = args.session_dir or "sessions"
    session_id = args.session_id
    
    if not session_id:
        print(f"❌ Session ID required", file=sys.stderr)
        print(f"💡 Tip: Use 'skillpilot session list' to see available sessions", file=sys.stderr)
        return 1
    
    session_path = os.path.join(session_dir, session_id)
    
    if not os.path.exists(session_path):
        print(f"❌ Session not found: {session_path}", file=sys.stderr)
        return 1
    
    try:
        state_file = os.path.join(session_path, "state", "state.json")
        
        if not os.path.exists(state_file):
            print(f"⚠️  Session state file not found: {state_file}", file=sys.stderr)
            return 1
        
        import json
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        print(f"\n📊 Session: {session_id}", file=sys.stderr)
        print(f"   Status: {state.get('status', 'unknown')}", file=sys.stderr)
        print(f"   Path: {session_path}", file=sys.stderr)
        
        queue_dir = os.path.join(session_path, "queue")
        if os.path.exists(queue_dir):
            commands = [f for f in os.listdir(queue_dir) if f.startswith("cmd_")]
            print(f"   Commands in queue: {len(commands)}", file=sys.stderr)
        
        result_dir = os.path.join(session_path, "result")
        if os.path.exists(result_dir):
            results = [f for f in os.listdir(result_dir) if f.startswith("cmd_")]
            completed = sum(1 for r in results if r.endswith(".json"))
            print(f"   Commands completed: {completed}", file=sys.stderr)
        
        return 0
    
    except Exception as e:
        print(f"❌ Error reading session: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


def cmd_session_delete(args):
    """Delete a completed session by ID"""
    session_dir = args.session_dir or "sessions"
    session_id = args.session_id
    
    if not session_id:
        print(f"❌ Session ID required", file=sys.stderr)
        print(f"💡 Tip: Use 'skillpilot session list' to see available sessions", file=sys.stderr)
        return 1
    
    session_path = os.path.join(session_dir, session_id)
    
    if not os.path.exists(session_path):
        print(f"❌ Session not found: {session_path}", file=sys.stderr)
        return 1
    
    if args.force or input(f"⚠️  Delete session {session_id}? (yes/no): ").lower() == "yes":
        import shutil
        try:
            shutil.rmtree(session_path)
            print(f"✅ Session deleted: {session_id}", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"❌ Error deleting session: {e}", file=sys.stderr)
            traceback.print_exc()
            return 1
    else:
        print(f"❌ Deletion cancelled", file=sys.stderr)
        return 1


def main():
    """Main entry point for SkillPilot CLI"""

    parser = argparse.ArgumentParser(
        description="SkillPilot - EDA Tool Orchestration System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    list_parser = subparsers.add_parser("list", help="List available items")
    list_subparsers = list_parser.add_subparsers(dest="list_command", help="List subcommands")

    list_skills_parser = list_subparsers.add_parser("skills", help="List available skills")
    list_skills_parser.add_argument("--skills-dir", default="examples/skills", help="Directory containing skill files")
    list_skills_parser.set_defaults(func=cmd_list_skills)

    list_playbooks_parser = list_subparsers.add_parser("playbooks", help="List available playbooks")
    list_playbooks_parser.add_argument("--playbooks-dir", default="examples/playbooks", help="Directory containing playbook files")
    list_playbooks_parser.set_defaults(func=cmd_list_playbooks)

    search_parser = subparsers.add_parser("search", help="Search for skills or playbooks")
    search_parser.add_argument("pattern", help="Search pattern to match")
    search_parser.add_argument("--skills-dir", default="examples/skills", help="Directory containing skill files")
    search_parser.set_defaults(func=cmd_search)

    validate_parser = subparsers.add_parser("validate", help="Validate playbook structure")
    validate_parser.add_argument("playbook", help="Path to playbook file")
    validate_parser.add_argument("--skills-dir", default="examples/skills", help="Directory containing skill files")
    validate_parser.set_defaults(func=cmd_validate)

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

    session_parser = subparsers.add_parser("session", help="Session management commands")
    session_subparsers = session_parser.add_subparsers(dest="session_command", help="Session subcommands")

    session_list_parser = session_subparsers.add_parser("list", help="List all active sessions")
    session_list_parser.add_argument("--session-dir", help="Session directory path (default: ./sessions)")
    session_list_parser.set_defaults(func=cmd_session_list)

    session_current_parser = session_subparsers.add_parser("current", help="Show info about current session")
    session_current_parser.add_argument("session_id", help="Session ID to inspect")
    session_current_parser.add_argument("--session-dir", help="Session directory path (default: ./sessions)")
    session_current_parser.set_defaults(func=cmd_session_current)

    session_delete_parser = session_subparsers.add_parser("delete", help="Delete a completed session")
    session_delete_parser.add_argument("session_id", help="Session ID to delete")
    session_delete_parser.add_argument("--session-dir", help="Session directory path (default: ./sessions)")
    session_delete_parser.add_argument("--force", action="store_true", help="Skip confirmation")
    session_delete_parser.set_defaults(func=cmd_session_delete)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "runner" and not args.runner_command:
        start_parser.print_help()
        return 1

    if args.command == "session" and not args.session_command:
        session_parser.print_help()
        return 1

    if args.command == "list" and not args.list_command:
        list_parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
