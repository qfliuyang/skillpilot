#!/usr/bin/env python3
"""
SkillPilot CLI Wrapper Script

This script provides convenient shortcuts to SkillPilot commands
without needing to type the full python3 -m skillpilot.cli.main prefix.

Usage:
    skillpilot run <playbook> [options]
    skillpilot runner start <config> [options]
    skillpilot runner tail <session-dir>
    skillpilot runner cancel <session-dir> [options]
    skillpilot runner stop <session-dir> [--force]
"""

import sys
import os
import subprocess

# Add skillpilot root to Python path for imports
SKILLPILOT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SKILLPILOT_ROOT)

from skillpilot.cli import main as skillpilot_main


def main():
    if len(sys.argv) < 2:
        print("Usage: skillpilot <command> [args]")
        print()
        print("Commands:")
        print("  run <playbook> [options]")
        print("  runner start <config> [options]")
        print("  runner tail <session-dir>")
        print("  runner cancel <session-dir> [options]")
        print("  runner stop <session-dir> [--force]")
        print()
        print("Examples:")
        print("  # Run a playbook")
        print("  skillpilot run examples/playbooks/basic_verification.md")
        print()
        print("  # Start a runner session")
        print("  skillpilot runner start config_examples/demo_config.yaml")
        print()
        print("  # Tail session logs")
        print("  skillpilot runner tail ./sessions/session_xxx")
        print()
        print("  # Cancel a command")
        print("  skillpilot runner cancel ./sessions/session_xxx")
        print()
        print("  # Stop a session")
        print("  skillpilot runner stop ./sessions/session_xxx --force")
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    # Map to actual SkillPilot CLI
    skillpilot_main([command, *args])


if __name__ == "__main__":
    main()
