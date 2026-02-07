# Multi-Tool, Multi-Server Configuration

SkillPilot supports multiple EDA tools and server types through flexible configuration.

## Overview

SkillPilot's configuration system allows you to:

1. **Configure multiple EDA tools** - Switch between Innovus, Cadence, Synopsys, or generic Tcl tools
2. **Configure job submission** - Use pseudo-DSUB for local testing, or real LSF/PBS/Slurm servers
3. **Move between EDA servers** - Change server configuration without code changes

## Quick Start

### 1. Choose or Create a Config File

Copy and modify one of the example configurations in `config_examples/`:

```bash
# Use demo tool with local pseudo-submit
cp config_examples/demo_config.yaml my_config.yaml

# Use Innovus with LSF server
cp config_examples/innovus_config.yaml my_config.yaml

# Use Cadence with PBS server
cp config_examples/cadence_config.yaml my_config.yaml

# Use Synopsys with Slurm server
cp config_examples/synopsys_config.yaml my_config.yaml
```

### 2. Start Runner with Config

```bash
# Start runner with your config file
python3 -m skillpilot.cli.main runner start --config my_config.yaml

# Override session directory
python3 -m skillpilot.cli.main runner start --config my_config.yaml --session-dir ./my_session

# Override heartbeat interval
python3 -m skillpilot.cli.main runner start --config my_config.yaml --heartbeat-interval 10.0

# Disable lease enforcement
python3 -m skillpilot.cli.main runner start --config my_config.yaml --disable-lease
```

## Configuration Format

### Tool Section

Configures the EDA tool to use:

```yaml
tool:
  type: demo|innovus|cadence|synopsys|generic_tcl
  name: "Tool Name"
  startup_command: "command_to_start_tool"
  env_vars:
    ENV_VAR: "value"
    MORE_ENV: "another_value"
  settings:
    tool_specific_setting: value
    threads: 4
    memory: 16G
  tcl_dir: "/path/to/tcl/scripts"
```

#### Tool Types

| Type | Description | Example |
|-------|-------------|---------|
| demo | Mock tool for testing | `examples/tools/demo_tool.py` |
| innovus | Innovus tools (Genus, Olympus) | `genus` |
| cadence | Cadence tools (Virtuoso, Spectre) | `virtuoso -mode batch` |
| synopsys | Synopsys tools (VCS, Custom Compiler) | `vcs -mode batch` |
| generic_tcl | Any Tcl-based tool | `tclsh` |

### Server Section

Configures job submission server:

```yaml
server:
  type: lsf|pbs|slurm|pseudo
  host: "server.company.com"
  user: "username"
  submit_type: lsf_bsub|pbs_qsub|slurm_srun|pseudo
  queue: "queue_name"
  project: "project_name"
  resource_spec: "resource_specification"
  timeout_hours: 24
```

#### Server Types

| Type | Submit Command | Example Queue Spec |
|-------|---------------|------------------|
| lsf | `bsub` | `select[mem>16G] rusage[mem=16G]` |
| pbs | `qsub` | `-l mem=32G -l ncpus=4` |
| slurm | `srun` | `--mem=64G --cpus-per-task=8` |
| pseudo | Local subprocess | None |

### Pseudo-Submit Section

Configures local job submission (for testing without DSUB):

```yaml
pseudo_submit:
  enabled: true|false
  job_dir: "./jobs"
  queue_delay: 0.5
  default_runtime: 2.0
```

When `enabled: true`, SkillPilot runs jobs locally using subprocess.
When `enabled: false`, the real job submission server (LSF/PBS/Slurm) is used.

### Runner Section

Configures runner behavior:

```yaml
runner:
  session_dir: "./sessions"
  heartbeat_interval_s: 5.0
  enable_lease: true
```

## Example Configurations

### Demo Tool (Local Testing)

`config_examples/demo_config.yaml` - Uses demo tool with local pseudo-submit:

```yaml
tool:
  type: demo
  name: "Demo Tool"
  startup_command: "python3 examples/tools/demo_tool.py"

server:
  type: pseudo  # Local mock
  submit_type: pseudo

pseudo_submit:
  enabled: true
  job_dir: "./jobs"
```

### Innovus with LSF

`config_examples/innovus_config.yaml` - Uses Innovus Genus with LSF server:

```yaml
tool:
  type: innovus
  name: "Innovus Genus"
  startup_command: "genus"
  env_vars:
    LM_LICENSE_FILE: "/licenses/genus.lic"
  settings:
    threads: 4

server:
  type: lsf
  host: "eda-server.company.com"
  user: "eda_user"
  submit_type: lsf_bsub
  queue: "eda_queue"
  resource_spec: "select[mem>16G] rusage[mem=16G]"
```

### Cadence with PBS

`config_examples/cadence_config.yaml` - Uses Cadence Virtuoso with PBS server:

```yaml
tool:
  type: cadence
  name: "Cadence Virtuoso"
  startup_command: "virtuoso -mode batch -no_gui"

server:
  type: pbs
  host: "pbs-server.company.com"
  user: "eda_user"
  submit_type: pbs_qsub
  queue: "eda_q"
  resource_spec: "-l mem=32G -l ncpus=4"
```

### Synopsys with Slurm

`config_examples/synopsys_config.yaml` - Uses Synopsys VCS with Slurm server:

```yaml
tool:
  type: synopsys
  name: "Synopsys VCS"
  startup_command: "vcs -mode batch"
  settings:
    num_threads: 8

server:
  type: slurm
  host: "slurm-server.company.com"
  user: "eda_user"
  submit_type: slurm_srun
  queue: "eda_q"
  resource_spec: "--mem=64G --cpus-per-task=8"
```

## Moving Between Servers

To switch EDA servers, update the `server` section in your config:

1. Copy your config to a backup
2. Update server settings (host, user, queue, etc.)
3. Restart runner with new config

No code changes needed - just configuration!

## CLI Override Options

Any server/runner setting can be overridden from command line:

| Config Setting | CLI Override | Example |
|---------------|---------------|---------|
| `server.host` | `--host` (not yet implemented) | Not needed - config-based |
| `runner.session_dir` | `--session-dir` | `--session-dir ./my_session` |
| `runner.heartbeat_interval_s` | `--heartbeat-interval` | `--heartbeat-interval 10.0` |
| `runner.enable_lease` | `--disable-lease` | `--disable-lease` |

## Architecture

```
+-------------------+     +------------------+
|   Playbook/Skill  <---> |     Master       |
+-------------------+     +------------------+
                              |                  |
                              v                  v
+-------------------+     +------------------+
|       Config     <---> |  Config Loader  |
|  - Tool Types      |  - Load YAML      |
|  - Server Types    |  - Override with CLI|
|  - Server Config   |                  |
|  - Submit Config   |                  v
+-------------------+     +------------------+
                              |                  |
                              v                  v
+-------------------+     +------------------+
|     Runner Core   <---> |  Runner (PTY)   |
|  - Load Config      |  - Start Tool      |
|  - Create Adapter    |  - Execute Commands  |
+-------------------+     +------------------+
                              |
                              v
                         +------------------+
                         |     EDA Tool / Job    |
                         +------------------+
```

## File Structure

```
skillpilot/
├── config.py                # Config loading module
├── submission.py            # Pseudo-DSUB implementation
├── runner/core.py           # Updated to use config
├── cli/main.py              # Updated with --config
└── config_examples/
    ├── demo_config.yaml          # Demo tool example
    ├── innovus_config.yaml       # Innovus example
    ├── cadence_config.yaml        # Cadence example
    ├── synopsys_config.yaml       # Synopsys example
    └── generic_tcl_config.yaml     # Generic Tcl example
```

## Next Steps

The configuration system is designed for extensibility:

1. **Add new tool adapters** - Add adapter classes to `adapters.py` for each EDA tool
2. **Add new server types** - Add server implementations for new job schedulers
3. **Extend config options** - Add tool-specific or server-specific options as needed

## See Also

- [PROTOCOL.md](PROTOCOL.md) - File-based API specification
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [README.md](README.md) - Getting started guide
