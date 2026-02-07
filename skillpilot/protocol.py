"""
Core protocol types for SkillPilot file-based control plane.

All file writes must be atomic using tmp + rename pattern.
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


# Default marker prefix for completion detection
DEFAULT_MARKER_PREFIX = "__SP_DONE__"


class CommandStatus(str, Enum):
    """Status of a command execution"""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class RunnerPhase(str, Enum):
    """Runner state machine phases"""
    STARTING = "starting"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPING = "stopping"


class CancelScope(str, Enum):
    """Scope for cancel requests"""
    CURRENT = "current"
    CMD_ID = "cmd_id"


class CancelPolicy(str, Enum):
    """Policy for handling cancellation"""
    CTRL_C = "ctrl_c"
    TERMINATE_TOOL = "terminate_tool"
    TERMINATE_SESSION = "terminate_session"


class StopMode(str, Enum):
    """Mode for stop requests"""
    GRACEFUL = "graceful"
    FORCE = "force"


class MarkerMode(str, Enum):
    """How marker is provided"""
    RUNNER_INJECT = "runner_inject"
    PAYLOAD_CONTAINS = "payload_contains"


@dataclass
class Marker:
    """Marker configuration for command completion detection"""
    prefix: str = DEFAULT_MARKER_PREFIX
    token: str = ""  # Defaults to cmd_id if empty
    mode: MarkerMode = MarkerMode.RUNNER_INJECT


@dataclass
class CommandRequest:
    """
    Command request file: queue/cmd_<seq>_<cmd_id>.json

    Runner reads this to execute commands.
    """
    cmd_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    seq: int = 0
    kind: str = "tcl"
    payload: str = ""
    timeout_s: Optional[int] = None
    cancel_policy: CancelPolicy = CancelPolicy.CTRL_C
    marker: Marker = field(default_factory=Marker)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandRequest":
        marker_data = data.get("marker", {})
        marker = Marker(**marker_data)

        return cls(
            cmd_id=data.get("cmd_id", str(uuid.uuid4())),
            seq=data.get("seq", 0),
            kind=data.get("kind", "tcl"),
            payload=data.get("payload", ""),
            timeout_s=data.get("timeout_s"),
            cancel_policy=CancelPolicy(data.get("cancel_policy", "ctrl_c")),
            marker=marker,
        )


@dataclass
class CommandResult:
    """
    Result file: result/cmd_<seq>_<cmd_id>.json

    Runner writes this after command completion.
    """
    cmd_id: str
    status: CommandStatus
    start_ts: str  # ISO8601 or epoch_ms (must be consistent)
    end_ts: str
    exit_reason: str
    output_path: Optional[str] = None
    tail_path: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandResult":
        return cls(
            cmd_id=data["cmd_id"],
            status=CommandStatus(data["status"]),
            start_ts=data["start_ts"],
            end_ts=data["end_ts"],
            exit_reason=data["exit_reason"],
            output_path=data.get("output_path"),
            tail_path=data.get("tail_path"),
            stats=data.get("stats"),
        )


@dataclass
class SessionState:
    """
    State file: state/state.json

    Runner writes this to track its phase and current operation.
    """
    phase: RunnerPhase
    session_id: str
    runner_pid: int
    tool_pid: Optional[int] = None
    current_cmd_id: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        return cls(
            phase=RunnerPhase(data["phase"]),
            session_id=data["session_id"],
            runner_pid=data["runner_pid"],
            tool_pid=data.get("tool_pid"),
            current_cmd_id=data.get("current_cmd_id"),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat() + "Z"),
        )


@dataclass
class Heartbeat:
    """
    Heartbeat file: state/heartbeat.json

    Runner writes this periodically to show liveness.
    """
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Heartbeat":
        return cls(timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"))


@dataclass
class LeaseInfo:
    """
    Lease file: state/lease.json

    Master writes this to keep Runner alive.
    """
    lease_id: str
    expires_at: str  # ISO8601 or epoch_ms
    owner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeaseInfo":
        return cls(
            lease_id=data["lease_id"],
            expires_at=data["expires_at"],
            owner=data.get("owner"),
        )

    def is_expired(self) -> bool:
        """Check if lease has expired (assuming epoch_ms format)"""
        try:
            expires_ms = float(self.expires_at)
            current_ms = datetime.utcnow().timestamp() * 1000
            return current_ms >= expires_ms
        except (ValueError, TypeError):
            # If not epoch_ms, try ISO8601
            try:
                expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
                return datetime.utcnow() >= expires
            except ValueError:
                return True  # Treat as expired if parsing fails


@dataclass
class CancelRequest:
    """
    Cancel request file: ctl/cancel.json

    Master writes this to cancel a running command.
    """
    scope: CancelScope
    cmd_id: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CancelRequest":
        return cls(
            scope=CancelScope(data["scope"]),
            cmd_id=data.get("cmd_id"),
            ts=data.get("ts", datetime.utcnow().isoformat() + "Z"),
        )


@dataclass
class StopRequest:
    """
    Stop request file: ctl/stop.json

    Master writes this to stop the session.
    """
    mode: StopMode
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "StopRequest":
        return cls(
            mode=StopMode(data["mode"]),
            ts=data.get("ts", datetime.utcnow().isoformat() + "Z"),
        )


@dataclass
class PlaybookResult:
    """
    Playbook execution result (written by Master)
    """
    playbook_name: str
    status: str
    skills: List[Dict[str, Any]]
    failure_reason: Optional[str] = None
    evidence_files: List[str] = field(default_factory=list)
    start_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    end_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Atomic file write utilities
def write_atomic_json(filepath: str, data: Dict[str, Any]) -> None:
    """
    Write JSON file atomically using tmp + rename pattern.

    Args:
        filepath: Target file path
        data: Data to write (must be JSON-serializable)
    """
    # Create parent directories if needed
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Write to temp file
    tmp_path = f"{filepath}.tmp.{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)

    # Atomic rename
    os.rename(tmp_path, filepath)


def read_json(filepath: str, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Read JSON file if it exists.

    Args:
        filepath: File path to read
        default: Default value if file doesn't exist

    Returns:
        Parsed JSON data or default
    """
    if not os.path.exists(filepath):
        return default

    with open(filepath, "r") as f:
        return json.load(f)


def get_current_timestamp_ms() -> str:
    """Get current timestamp as milliseconds since epoch"""
    return str(int(datetime.utcnow().timestamp() * 1000))


def get_current_timestamp_iso() -> str:
    """Get current timestamp in ISO8601 format"""
    return datetime.utcnow().isoformat() + "Z"
