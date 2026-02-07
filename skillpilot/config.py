"""
SkillPilot Runner Configuration

Configuration file for EDA tool orchestration with job submission.
Supports multiple tools, servers, and submission systems.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import os
import yaml


class ToolType(str, Enum):
    """Supported EDA tool types"""
    DEMO = "demo"
    INNOVUS = "innovus"
    CADENCE = "cadence"
    SYNOPSYS = "synopsys"
    GENERIC_TCL = "generic_tcl"


class ServerType(str, Enum):
    """Supported EDA server types"""
    LSF = "lsf"
    PBS = "pbs"
    SLURM = "slurm"
    PSEUDO = "pseudo"  # Local mock for testing


class SubmitType(str, Enum):
    """Job submission types"""
    LSF_BSUB = "bsub"
    PBS_QSUB = "qsub"
    SLURM_SRUN = "srun"
    PSEUDO = "pseudo"  # Local mock for testing


@dataclass
class ServerConfig:
    server_type: ServerType
    submit_type: SubmitType = SubmitType.PSEUDO
    host: Optional[str] = None
    user: Optional[str] = None
    queue: Optional[str] = None
    project: Optional[str] = None
    resource_spec: Optional[str] = None
    timeout_hours: int = 24


@dataclass
class ToolConfig:
    """Individual tool configuration"""
    tool_type: ToolType
    name: str
    # Command to start the tool
    startup_command: str
    # Environment setup
    env_vars: Dict[str, str] = field(default_factory=dict)
    # Tool-specific settings
    settings: Dict[str, Any] = field(default_factory=dict)
    # Tcl scripts directory
    tcl_dir: Optional[str] = None


@dataclass
class PseudoSubmitConfig:
    """Pseudo job submission configuration (for testing without DSUB)"""
    enabled: bool = True
    job_dir: str = "jobs"
    # Simulate job queue delay (seconds)
    queue_delay: float = 0.5
    # Simulate job runtime (seconds)
    default_runtime: float = 2.0


@dataclass
class RunnerConfig:
    """Main runner configuration"""
    # Active tool
    tool: ToolConfig
    # Server configuration
    server: ServerConfig
    # Pseudo submission config
    pseudo_submit: PseudoSubmitConfig
    # Session settings
    session_dir: str = "./sessions"
    heartbeat_interval_s: float = 5.0
    enable_lease: bool = True


def load_config(config_path: str) -> RunnerConfig:
    """
    Load runner configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        RunnerConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    # Parse server config
    server_data = data.get('server', {})
    server = ServerConfig(
        server_type=ServerType(server_data.get('type', 'pseudo')),
        host=server_data.get('host'),
        user=server_data.get('user'),
        submit_type=SubmitType(server_data.get('submit_type', 'pseudo')),
        queue=server_data.get('queue'),
        project=server_data.get('project'),
        resource_spec=server_data.get('resource_spec'),
        timeout_hours=server_data.get('timeout_hours', 24),
    )

    # Parse tool config
    tool_data = data.get('tool', {})
    tool = ToolConfig(
        tool_type=ToolType(tool_data.get('type', 'demo')),
        name=tool_data.get('name', 'Default Tool'),
        startup_command=tool_data.get('startup_command', ''),
        env_vars=tool_data.get('env_vars', {}),
        settings=tool_data.get('settings', {}),
        tcl_dir=tool_data.get('tcl_dir'),
    )

    # Parse pseudo submit config
    pseudo_data = data.get('pseudo_submit', {})
    pseudo_submit = PseudoSubmitConfig(
        enabled=pseudo_data.get('enabled', True),
        job_dir=pseudo_data.get('job_dir', 'jobs'),
        queue_delay=pseudo_data.get('queue_delay', 0.5),
        default_runtime=pseudo_data.get('default_runtime', 2.0),
    )

    # Parse runner settings
    runner_data = data.get('runner', {})
    return RunnerConfig(
        tool=tool,
        server=server,
        pseudo_submit=pseudo_submit,
        session_dir=runner_data.get('session_dir', './sessions'),
        heartbeat_interval_s=runner_data.get('heartbeat_interval_s', 5.0),
        enable_lease=runner_data.get('enable_lease', True),
    )


def save_config(config: RunnerConfig, config_path: str) -> None:
    """
    Save runner configuration to YAML file.

    Args:
        config: RunnerConfig object to save
        config_path: Path to save config file
    """
    data = {
        'tool': {
            'type': config.tool.tool_type.value,
            'name': config.tool.name,
            'startup_command': config.tool.startup_command,
            'env_vars': config.tool.env_vars,
            'settings': config.tool.settings,
            'tcl_dir': config.tool.tcl_dir,
        },
        'server': {
            'type': config.server.server_type.value,
            'host': config.server.host,
            'user': config.server.user,
            'submit_type': config.server.submit_type.value,
            'queue': config.server.queue,
            'project': config.server.project,
            'resource_spec': config.server.resource_spec,
            'timeout_hours': config.server.timeout_hours,
        },
        'pseudo_submit': {
            'enabled': config.pseudo_submit.enabled,
            'job_dir': config.pseudo_submit.job_dir,
            'queue_delay': config.pseudo_submit.queue_delay,
            'default_runtime': config.pseudo_submit.default_runtime,
        },
        'runner': {
            'session_dir': config.session_dir,
            'heartbeat_interval_s': config.heartbeat_interval_s,
            'enable_lease': config.enable_lease,
        },
    }

    with open(config_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)
