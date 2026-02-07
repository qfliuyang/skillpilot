"""
Simple Configuration Loader for SkillPilot

Loads command aliases and minimal runner settings from YAML config.
Focus on simplicity - just command aliases and basic settings.
"""

import os
import yaml
from typing import Dict, Optional


def load_config(config_path: str) -> Dict:
    """
    Load configuration from YAML file.

    Simple format:
    commands:
      tool_name: command_to_run
    scheduler:
      type: lsf|pbs|slurm
      queue: queue_name
      project: project_name
    session_dir: ./sessions
    heartbeat_interval_s: 5.0
    enable_lease: true

    Args:
        config_path: Path to YAML config file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_command(config: Dict, tool_name: str) -> Optional[str]:
    """
    Get command for a tool by name.

    Args:
        config: Configuration dictionary
        tool_name: Name of the tool

    Returns:
        Command string, or None if tool not found
    """
    return config.get('commands', {}).get(tool_name)


def get_session_dir(config: Dict) -> str:
    """Get session directory from config (default: ./sessions)"""
    return config.get('session_dir', './sessions')


def get_heartbeat_interval(config: Dict) -> float:
    """Get heartbeat interval from config (default: 5.0)"""
    return config.get('heartbeat_interval_s', 5.0)


def get_lease_enabled(config: Dict) -> bool:
    """Get lease enabled from config (default: true)"""
    return config.get('enable_lease', True)


def get_scheduler_type(config: Dict) -> Optional[str]:
    """Get scheduler type from config (lsf|pbs|slurm|None for local)"""
    scheduler = config.get('scheduler', {})
    return scheduler.get('type') if scheduler else None


def get_scheduler_queue(config: Dict) -> Optional[str]:
    """Get scheduler queue from config"""
    scheduler = config.get('scheduler', {})
    return scheduler.get('queue') if scheduler else None


def get_scheduler_project(config: Dict) -> Optional[str]:
    """Get scheduler project from config"""
    scheduler = config.get('scheduler', {})
    return scheduler.get('project') if scheduler else None


def get_scheduler_resource(config: Dict) -> Optional[str]:
    """Get scheduler resource spec from config"""
    scheduler = config.get('scheduler', {})
    return scheduler.get('resource_spec') if scheduler else None
