"""
SkillPilot - EDA Tool Orchestration System

A system for orchestrating EDA tool interactions via PTY sessions with a
file-based control plane protocol (Disk-as-API).

Core components:
- Runner: PTY-based executor that manages EDA tool sessions
- Master: Orchestrator that compiles Playbook/Skill/Poke into commands
- PSP: Playbook/Skill/Poke definitions
- CLI: Entry point for users and agents
"""

__version__ = "1.0.0"

from skillpilot.protocol import (
    CommandRequest,
    CommandResult,
    SessionState,
    CancelRequest,
    StopRequest,
    LeaseInfo,
    write_atomic_json,
    read_json,
    get_current_timestamp_ms,
    get_current_timestamp_iso,
)

__all__ = [
    "CommandRequest",
    "CommandResult",
    "SessionState",
    "CancelRequest",
    "StopRequest",
    "LeaseInfo",
    "write_atomic_json",
    "read_json",
    "get_current_timestamp_ms",
    "get_current_timestamp_iso",
]
