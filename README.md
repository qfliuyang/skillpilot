# SkillPilot - EDA Tool Orchestration System

A system for orchestrating EDA tools via PTY sessions with file-based control plane.

## What is SkillPilot?

SkillPilot separates EDA tool automation into two layers:
- **PSP (Playbook/Skill/Poke)**: Human-readable domain knowledge in Markdown
- **Runner/Master**: Executes playbooks and manages EDA tool sessions

## Quick Start

### Prerequisites
- Python 3.8 or higher
- pty: `pip install pty`

### Installation

```bash
pip install -e .
```

### Run a Playbook

```bash
# Basic execution
python -m skillpilot.cli.main run \
  --playbook examples/playbooks/basic_verification.md \
  --skills-dir examples/skills

# With custom session directory
python -m skillpilot.cli.main run \
  --playbook examples/playbooks/basic_verification.md \
  --session-dir ./my_session
```

### Inspect Results

```bash
# View session state
cat sessions/session_*/state/state.json

# Check command results
cat sessions/session_*/result/cmd_*.json

# View command outputs
cat sessions/session_*/output/cmd_*.out

# Follow session log
tail -f sessions/session_*/log/session.out
```

### Integration Tests

```bash
# Run all 7 acceptance criteria tests
python -m skillpilot.tests.integration_tests
```

### Advanced Usage

```bash
# Start runner manually
python -m skillpilot.runner.core --session-dir ./test_session

# Write custom command
cat > test_session/queue/cmd_1.json << 'EOF'
{
  "cmd_id": "custom_001",
  "seq": 1,
  "kind": "tcl",
  "payload": "puts 'Custom command'",
  "timeout_s": 60,
  "cancel_policy": "ctrl_c",
  "marker": {
    "prefix": "__SP_DONE__",
    "token": "custom_001",
    "mode": "runner_inject"
  }
}
EOF

# Tail session output
python -m skillpilot.cli.main runner tail --session-dir ./test_session

# Cancel running command
python -m skillpilot.cli.main runner cancel --session-dir ./test_session --all

# Stop session
python -m skillpilot.cli.main runner stop --session-dir ./test_session --force
```

## PSP Format

### Skill File Format
Skills are Markdown files (.md) with this structure:

```markdown
# Timing Analysis

**Inputs:**
- report_file: timing_report.txt
- worst_paths: 10
- total_paths: 100

**Steps:**
1. Generate timing report
   - Action: poke::report_timing
   - Args: -out "timing_report.txt" -worst 10 -paths 100
   - Timeout: 30s

2. Check slack violations
   - Action: poke::report_constraints
   - Args: -out "constraints_report.txt"
   - Timeout: 30s
```

### Playbook File Format
Playbooks are Markdown files (.md) with this structure:

```markdown
# Basic Verification

**Skills:**
- timing_analysis
- power_analysis

**Defaults:**
- timeout_s: 60
- cancel_policy: ctrl_c
- fail_fast: true
- session_mode: shared
```

### Playbook File Format
Playbooks are Markdown files (.md) with this structure:

```markdown
# My Playbook Name

Skills:
- skill_name_1
- skill_name_2

Defaults:
- timeout_s: 60
- cancel_policy: ctrl_c
- fail_fast: true
- session_mode: shared
```

## Architecture

```
User/Agent
      |
      |      |
      |      |
CLI (Entry Point) | Master |      |
Compiles PSP          | to commands | Runner (PTY Executor) | EDA Tool (Tcl REPL)
File Control Plane     |      |      |
```

## Key Features

- Markdown PSP: Skills/Playbooks in human-readable Markdown
- AI Code CLI Compatible: Works with Claude/OpenCode and similar tools
- File-based Control Plane: No inbound network required
- PTY-based Execution: Handles interactive EDA tools
- Marker Detection: Reliable command completion
- Governance: Timeout, cancel, stop, lease management
- Audit Logging: Complete command and session logs
- Idempotent: Safe to restart/re-run
- Real EDA Server Ready: See MIGRATION.md for deployment

## Examples

See examples directory for:
- Skills: examples/skills/*.md
- Playbooks: examples/playbooks/*.md
- Poke procedures: examples/poke/poke.tcl
- Demo tool: examples/tools/demo_tool.py

## Documentation

- Protocol: PROTOCOL.md - File-based API specification
- Architecture: ARCHITECTURE.md - System design
- Migration: MIGRATION.md - EDA server deployment guide
- Quick Start: QUICKSTART.md - Quick start guide

## Support

For issues or questions:
- Integration tests: skillpilot/tests/integration_tests.py
- Report issues with reproduction steps
