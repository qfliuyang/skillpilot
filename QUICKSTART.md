# SkillPilot v1 - Quick Start Guide

This guide will get you running with SkillPilot in 5 minutes.

## Prerequisites

- Python 3.8 or higher
- pty library: `pip install pty`
- PyYAML (for playbooks/skills - note: now uses Markdown): `pip install pyyaml`

## Installation

```bash
cd skillpilot
pip install -e .
```

## Quick Start

### 1. Run a demo

The simplest way to try SkillPilot is to run a playbook with the demo tool:

```bash
# Run a basic verification playbook
python -m skillpilot.cli.main run \
  --playbook examples/playbooks/basic_verification.md \
  --skills-dir examples/skills
```

This will:
- Load playbook and skills from Markdown files
- Create a session directory (`sessions/session_*`)
- Start a Runner process
- Execute all commands in the playbook
- Collect results

### 2. Inspect results

After execution completes, check the session directory:

```bash
# Find the latest session
ls -lt sessions/ | head -2

# Check results
cat sessions/session_*/result/cmd_*.json

# View outputs
cat sessions/session_*/output/cmd_*.out

# Check session log
tail -f sessions/session_*/log/session.out
```

### 3. Run integration tests

Verify SkillPilot meets all acceptance criteria:

```bash
python -m skillpilot.tests.integration_tests
```

This runs all 7 tests covering:
1. E2E: Run playbook with 4 commands
2. Marker detection across chunks
3. Timeout handling
4. Cancel via ctrl-c
5. Lease expiration
6. Recovery after restart
7. Audit logging

### 4. Advanced: Start Runner separately

For debugging or testing, you can start Runner manually:

```bash
# Start a runner session in a specific directory
python -m skillpilot.runner.core --session-dir test_session

# In another terminal, write commands to queue
cat > test_session/queue/cmd_1_test.json << 'EOF'
{
  "cmd_id": "test_001",
  "seq": 1,
  "kind": "tcl",
  "payload": "puts 'Hello from queue'",
  "timeout_s": 30,
  "cancel_policy": "ctrl_c",
  "marker": {
    "prefix": "__SP_DONE__",
    "token": "test_001",
    "mode": "runner_inject"
  }
}
EOF

# Tail the session output
python -m skillpilot.cli.main runner tail --session-dir test_session

# Stop the runner
python -m skillpilot.cli.main runner stop --session-dir test_session
```

## Creating Your Own Playbook

### Step 1: Define Poke procedures

Create `poke.tcl` with your EDA tool procedures:

```tcl
namespace eval poke {

    proc report_timing {args} {
        # Parse arguments
        array set opts {-out "timing.txt"}
        foreach {key value} $args {
            if {[info exists opts($key)]} {
                set opts($key) $value
            }
        }

        # Your EDA tool logic here
        puts "Generating timing report..."
        puts "  Output file: $opts(-out)"

        # Write report to file
        set fd [open $opts(-out) w]
        puts $fd "Timing analysis complete"
        close $fd
    }
}
```

### Step 2: Create a Skill

Create a Markdown skill file (`my_skill.md`):

```markdown
# My Analysis Skill

**Inputs:**
- param1: value
- param2: value

**Steps:**
1. Generate timing report
   - Action: poke::report_timing
   - Args: -out "timing_report.txt" -worst 10
   - Timeout: 60s

2. Check results
   - Action: poke::check_results
   - Args: -format "json"
   - Timeout: 30s
```

### Step 3: Create a Playbook

Create a Markdown playbook (`my_playbook.md`):

```markdown
# My Verification Flow

**Skills:**
- my_analysis

**Defaults:**
- timeout_s: 120
- cancel_policy: ctrl_c
- fail_fast: false
- session_mode: shared
```

### Step 4: Run it

```bash
python -m skillpilot.cli.main run \
  --playbook my_playbook.md \
  --skills-dir ./skills
```

## Common Issues

### Tool not found

If you get "Demo tool not found" error, ensure that demo_tool.py is executable:

```bash
chmod +x examples/tools/demo_tool.py
```

### Markdown Format Errors

If you see "Skill not found" errors, check:
1. File ends with `.md` extension
2. File format is correct (see QUICKSTART for examples)
3. Skills are in the specified directory

### Port/Resource conflicts

If you see PTY errors, ensure that:
- Session directory is on a local filesystem
- Proper permissions for file operations

### Tests failing

Tests may fail if:
- System has low resources (memory/CPU)
- Python version < 3.8
- Missing dependencies (pty, pyyaml)

## Next Steps

- Read [PROTOCOL.md](PROTOCOL.md) for file-based API details
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Read [MIGRATION.md](MIGRATION.md) for EDA server deployment guide
- Explore examples in `examples/`

## AI Code CLI Integration

### From Claude/Opencode

Claude can directly use skillpilot commands:

```bash
# Claude creates a skill or playbook
# Then runs it directly
claude: "Create a timing analysis skill and run it"
skillpilot run --playbook ~/workspaces/timing_check.md
```

### From Local Terminal

Just use the normal CLI commands shown above!

## Support

For issues or questions, refer to:
- Integration tests: `skillpilot/tests/integration_tests.py`
- Protocol definitions: `skillpilot/protocol.py`
- Example PSP files: `examples/`
- Migration guide: `MIGRATION.md` (for EDA server deployment)


## Support

For issues or questions, refer to:
- Integration tests: `skillpilot/tests/integration_tests.py`
- Protocol definitions: `skillpilot/protocol.py`
- Example PSP files: `examples/`
