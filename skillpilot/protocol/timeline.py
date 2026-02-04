"""
Timeline protocol implementation
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from .schema import SCHEMA_VERSION


class Event:
    """Timeline event"""

    def __init__(
        self,
        job_id: str,
        level: str,
        event: str,
        message: str = "",
        state: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.schema_version = SCHEMA_VERSION
        self.ts = datetime.utcnow().isoformat() + "Z"
        self.job_id = job_id
        self.level = level
        self.event = event
        self.message = message
        self.state = state
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        d = {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "job_id": self.job_id,
            "level": self.level,
            "event": self.event,
        }
        if self.message:
            d["message"] = self.message
        if self.state:
            d["state"] = self.state
        if self.data:
            d["data"] = self.data
        return d


class Timeline:
    """Timeline - append-only audit log"""

    LEVELS = ["INFO", "WARN", "ERROR"]
    EVENTS = {
        "STATE_ENTER",
        "STATE_EXIT",
        "ACTION",
        "DONE",
        "FAIL",
    }

    def __init__(self, job_id: str, run_dir: Path):
        self.job_id = job_id
        self.path = run_dir / "job_timeline.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> None:
        """Append event to timeline"""
        with open(self.path, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def state_enter(self, state: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record state enter"""
        self.append(
            Event(
                job_id=self.job_id,
                level="INFO",
                event="STATE_ENTER",
                state=state,
                data=data,
            )
        )

    def state_exit(self, state: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record state exit"""
        self.append(
            Event(
                job_id=self.job_id,
                level="INFO",
                event="STATE_EXIT",
                state=state,
                data=data,
            )
        )

    def action(
        self, action: str, message: str = "", data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record action"""
        self.append(
            Event(
                job_id=self.job_id,
                level="INFO",
                event="ACTION",
                message=message,
                data={"action": action, **(data or {})},
            )
        )

    def done(self, message: str = "") -> None:
        """Record DONE"""
        self.append(
            Event(
                job_id=self.job_id,
                level="INFO",
                event="DONE",
                message=message,
            )
        )

    def fail(self, error_type: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Record FAIL"""
        self.append(
            Event(
                job_id=self.job_id,
                level="ERROR",
                event="FAIL",
                message=message,
                data={"error_type": error_type, **(data or {})},
            )
        )
