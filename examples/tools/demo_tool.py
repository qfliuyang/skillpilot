#!/usr/bin/env python3
"""
Demo Tool - Mock EDA Tool for Testing

A Tcl-like REPL that simulates EDA tool behavior.
Supports:
- Reading commands from stdin
- puts command for output
- sleep command to simulate long-running operations
- echo command to test basic I/O
- Special commands to test marker detection across chunks
"""

import sys
import time
import re


def puts(text: str) -> None:
    """Emulate Tcl puts command"""
    print(text, flush=True)


def echo(text: str) -> None:
    """Echo text back"""
    print(f"echo: {text}", flush=True)


def sleep_cmd(duration: float) -> None:
    """Simulate long-running operation"""
    print(f"sleeping for {duration}s...", flush=True)
    time.sleep(duration)
    print(f"done sleeping", flush=True)


def slow_puts(text: str, chunk_size: int = 5, delay: float = 0.1) -> None:
    """
    Output text in chunks to simulate streaming and test marker detection.
    This is useful for testing that marker detection works across chunks.
    """
    print(f"slow_puts: {text}", flush=True)
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        sys.stdout.write(chunk)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def error(msg: str) -> None:
    """Simulate error output"""
    print(f"ERROR: {msg}", flush=True)


def help_cmd() -> None:
    """Show available commands"""
    help_text = """
Demo Tool v1.0 - Mock EDA Tool
Available commands:
  puts <text>              - Print text to stdout
  echo <text>              - Echo text back
  sleep <seconds>          - Sleep for specified seconds
  slow_puts <text>        - Print text slowly in chunks (tests marker detection)
  error <msg>              - Print error message
  help                     - Show this help
  exit                     - Exit the tool

Note: This tool simulates a Tcl-like REPL for testing SkillPilot Runner.
"""
    puts(help_text)


def process_command(line: str) -> bool:
    """
    Process a command line.
    Returns True to continue, False to exit.
    """
    line = line.strip()

    if not line:
        return True

    if line.lower() in ["exit", "quit"]:
        puts("Goodbye!")
        return False

    if line.lower() == "help":
        help_cmd()
        return True

    # Parse command
    parts = re.split(r'\s+', line, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "puts":
        puts(args)
    elif cmd == "echo":
        echo(args)
    elif cmd == "sleep":
        try:
            duration = float(args)
            sleep_cmd(duration)
        except ValueError:
            error(f"Invalid sleep duration: {args}")
    elif cmd == "slow_puts":
        slow_puts(args)
    elif cmd == "error":
        error(args)
    else:
        error(f"Unknown command: {cmd}")
        help_cmd()

    return True


def main():
    """Main REPL loop"""
    print("Demo Tool v1.0 - Mock EDA Tool")
    print("Type 'help' for available commands, 'exit' to quit")
    print("Ready.", flush=True)

    try:
        while True:
            try:
                # Read from stdin with timeout
                import select
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        print("\nEOF received, exiting...", flush=True)
                        break
                    if not process_command(line):
                        break
            except KeyboardInterrupt:
                print("\nInterrupted by Ctrl-C", flush=True)
                break
            except Exception as e:
                error(f"Error: {e}")
    finally:
        print("Demo tool shutting down...", flush=True)


if __name__ == "__main__":
    main()
