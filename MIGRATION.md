# SkillPilot Migration Plan

This guide covers migrating from local development to a real EDA server environment.

## Overview

SkillPilot v1 is designed to work in any environment. For real EDA server deployment:
- Install skillpilot system-wide on EDA server
- Configure tool aliases and adapters
- Store playbooks and skills in workspace directories
- Use from AI Code CLI or local terminal

## Phase 1: Installation

### 1.1 System-wide Install

On your EDA server:

```bash
# Create installation directory
sudo mkdir -p /opt/skillpilot
cd /opt/skillpilot

# Copy or install skillpilot package
cp -r /path/to/skillpilot /opt/skillpilot/

# Install dependencies
pip3 install -r /opt/skillpilot

# Verify installation
python3 -m skillpilot --version
```

### 1.2 Environment Variables

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export SKILLPILOT_HOME=/opt/skillpilot
export SKILLPILOT_WORKSPACE=$HOME/skillpilot_workspaces
export PATH=$PATH:$SKILLPILOT_HOME
```

## Phase 2: Directory Structure

### 2.1 Server Layout

```
/opt/skillpilot/           # SkillPilot installation
├── skillpilot/          # Main package
└── config/
    ├── adapter.yaml        # EDA tool configuration
    └── site.yaml          # Site-specific settings

~/skillpilot_workspaces/    # User workspace
├── playbooks/           # User playbooks (Markdown)
├── skills/             # User skills (Markdown)
└── inputs/             # Input parameters (JSON)
```

### 2.2 Adapter Configuration

Create `adapter.yaml` for your EDA tools:

```yaml
tools:
  - name: primetime
    command: ["pt_shell", "-mode", "gui"]
    boot_tcl: "source /tools/primetime/poke.tcl"
    
  - name: innovus
    command: ["innovus"]
    boot_tcl: "source /tools/innovus/poke.tcl"
    
  - name: tempus
    command: ["tempus"]
    boot_tcl: "source /tools/tempus/poke.tcl"

  - name: demo
    command: ["python3", "/opt/skillpilot/examples/tools/demo_tool.py"]
    boot_tcl: "source /opt/skillpilot/examples/poke/poke.tcl"
```

### 2.3 Site Configuration

Create `site.yaml` for site-specific overrides:

```yaml
# Tool paths
tool_paths:
  primetime: /tools/eda/primetime/2023.12
  innovus: /tools/eda/innovus/v2.2.5
  tempus: /tools/eda/tempus/v23.09

# Session directories
session_base: /tmp/skillpilot_sessions
shared_storage: /shared/skillpilot_results

# Tool aliases
aliases:
  pt: pt_shell
  inv: innovus
  tmp: tempus
```

## Phase 3: Tool Aliases

Configure shell aliases for common EDA tools:

```bash
# In /opt/skillpilot/config/aliases.sh or add to global profile
alias pt='skillpilot runner start --adapter primetime --session-dir'
alias inv='skillpilot runner start --adapter innovus --session-dir'
alias tmp='skillpilot runner start --adapter tempus --session-dir'
```

## Phase 4: Donau/LSF Integration

### 4.1 Submitting SkillPilot as Job

```bash
# Example Donau job submission
dsub -q -n skillpilot -R "rusage[mem=4GB] span[hosts=1]" \
  -cwd $SKILLPILOT_WORKSPACE \
  skillpilot run --playbook timing_check.md

# Example with session directory on shared filesystem
dsub -q -n skillpilot -R "rusage[mem=4GB]" \
  skillpilot run --playbook ~/workspaces/my_playbook.md \
  --session-dir /shared/skillpilot/session_$(date +%s)
```

### 4.2 Tool Adapter for Donau

Create `skillpilot/master/donau_adapter.py`:

```python
"""
Donau/LSF adapter for submitting SkillPilot jobs
"""
import subprocess
import os

class DonauAdapter:
    def __init__(self, config):
        self.queue = config.get("queue", "normal")
        self.resources = config.get("resources", "rusage[mem=4GB]")
    
    def submit_job(self, session_dir, playbook_path):
        """Submit SkillPilot as a Donau job"""
        cmd = [
            "dsub", "-q", "-n", "skillpilot",
            "-R", self.resources,
            "-cwd", session_dir,
            "skillpilot", "run", "--playbook", playbook_path
        ]
        subprocess.run(cmd, check=True)
```

## Phase 5: User Workflow

### 5.1 Creating Skills

Skills are now simple Markdown files:

```markdown
# My Timing Check

**Steps:**
1. Generate timing report
   - Action: poke::report_timing
   - Args: -out "timing.txt" -worst 10
   - Timeout: 60s

2. Check constraints
   - Action: poke::check_paths
   - Args: -paths 100
   - Timeout: 60s
```

Save as `~/skillpilot_workspaces/skills/timing_check.md`

### 5.2 Creating Playbooks

```markdown
# My Verification Flow

**Skills:**
- timing_check
- power_check

**Defaults:**
- timeout_s: 120
- fail_fast: false
- session_mode: shared
```

Save as `~/skillpilot_workspaces/playbooks/verification.md`

### 5.3 Running from Terminal

```bash
# Simple playbook run
skillpilot run --playbook ~/workspaces/playbooks/verification.md

# With explicit session directory
skillpilot run --playbook timing.md --session-dir /tmp/my_session
```

### 5.4 Running from AI Code CLI

When using AI Code CLI (Claude/Opencode):

```bash
# AI Code CLI creates playbook on-the-fly and runs it
# No changes needed - just ensure SKILLPILOT_HOME is set

# AI can call skillpilot commands directly
skillpilot run --playbook <playbook_path>
```

## Phase 6: Tool Integration

### 6.1 Poke Libraries

Ensure your EDA tools have poke libraries:

```tcl
# Example poke.tcl structure
namespace eval poke {

    proc report_timing {args} {
        # Your EDA tool logic here
    }
}
```

Install poke libraries in tools directory:
```
/tools/eda/primetime/poke.tcl
/tools/eda/innovus/poke.tcl
/tools/eda/tempus/poke.tcl
```

### 6.2 Demo Tool on Server

For testing on real EDA server, demo_tool.py can run locally:

```bash
# Start demo tool directly
python3 /opt/skillpilot/examples/tools/demo_tool.py

# Or via skillpilot
skillpilot runner start --session-dir ./test_demo
```

## Phase 7: Troubleshooting

### 7.1 Permission Issues

```bash
# Fix permissions
chmod +x /opt/skillpilot/examples/tools/demo_tool.py
chmod 755 $SKILLPILOT_WORKSPACE
```

### 7.2 Session Directory Conflicts

```bash
# Clean up stale sessions
find /tmp/skillpilot_sessions -type d -mtime +1d -exec rm -rf {} \;

# Or use unique session names
skillpilot run --session-dir /tmp/skillpilot_$(date +%s%N)
```

### 7.3 Tool Path Issues

```bash
# Verify tool in PATH
which pt_shell
which innovus

# Check adapter configuration
cat /opt/skillpilot/config/adapter.yaml
```

### 7.4 Debug Mode

```bash
# Enable verbose logging
export SKILLPILOT_DEBUG=1

# View session logs
skillpilot runner tail --session-dir <session_dir>

# Check state
cat <session_dir>/state/state.json
```

## Phase 8: Rollback Plan

If you need to revert changes:

```bash
# 1. Restore previous configuration
git checkout <commit_hash>

# 3. Reinstall
pip3 uninstall skillpilot
pip3 install /path/to/old/version
```

## Phase 9: Advanced Configuration

### 9.1 Multi-Tool Sessions

For advanced use cases, configure session_mode:

```markdown
# Advanced playbook with per-skill sessions
# My Multi-Tool Playbook

**Defaults:**
- session_mode: per_skill
- parallel: true

**Skills:**
- timing_check (use primetime)
- power_check (use innovus)
```

### 9.2 Resource Limits

Configure resource constraints:

```yaml
# In site.yaml
resources:
  max_sessions: 10
  max_memory_per_session: "8GB"
  session_timeout: 3600
```

## Phase 10: Training

### 10.1 EDA Scenario Cheatsheet

Create `EDA_CHEATSHEET.md`:

```markdown
# EDA Tool Cheatsheet for SkillPilot

## Available Skills

### Timing Analysis
- **poke::report_timing**: Generate timing report
- **poke::check_paths**: Verify path connectivity
- **poke::report_slack**: Check timing violations

### Power Analysis
- **poke::report_power**: Generate power analysis
- **poke::check_leakage**: Verify no leakage paths

### Constraints
- **poke::report_constraints**: Check design constraints
- **poke::check_setup**: Verify timing setup

## Common Patterns

### Report Generation
```markdown
# Timing Report Skill

**Steps:**
1. Read setup file
   - Action: poke::read_setup
   - Args: -file "setup.json"

2. Generate report
   - Action: poke::report_timing
   - Args: -out "report.txt" -worst 10
```

### Data Extraction
```markdown
# Data Collection Skill

**Steps:**
1. Check timing violations
   - Action: poke::report_timing
   - Args: -out "timing.txt"
   
2. Extract violations
   - Action: poke::extract_data
   - Args: -format "json" -field "violations"
```

## Quick Templates

### Basic Playbook Template
```markdown
# My Playbook

**Skills:**
- skill1
- skill2

**Defaults:**
- timeout_s: 300
- cancel_policy: ctrl_c
```

### Single Step Skill
```markdown
# Quick Check

**Steps:**
1. Quick verification
   - Action: poke::quick_check
   - Args: -mode "fast"
```
```

Save to `~/skillpilot_workspaces/CHEATSHEET.md`

## Phase 11: Version Management

### 11.1 Tracking Changes

```bash
# Check version
python3 -m skillpilot --version

# View configuration
cat /opt/skillpilot/config/adapter.yaml
```

### 11.2 Update Strategy

```bash
# For major updates
1. Backup current installation
2. Test new version in staging
3. Update system-wide installation
4. Migrate workspaces
5. Verify with playbooks

# For minor updates
# Skills can be updated without reinstalling
# Playbooks can reference updated skills
```

## Summary

This migration plan provides:
- ✅ Complete installation guide
- ✅ Directory structure recommendations
- ✅ Tool alias configuration
- ✅ Donau/LSF integration example
- ✅ User workflow documentation
- ✅ Tool integration guidelines
- ✅ Troubleshooting procedures
- ✅ Rollback strategy
- ✅ Advanced configuration options
- ✅ Training materials (cheatsheet)
- ✅ Version management

Next steps after this plan:
1. Install skillpilot system-wide on EDA server
2. Configure adapters and aliases
3. Create first test skill/playbook
4. Run via Donau or local terminal
5. Verify end-to-end workflow
