"""
Ack protocol implementation
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from .schema import SCHEMA_VERSION


class Ack:
    """Ack from Innovus queue_processor"""

    def __init__(
        self,
        request_id: str,
        job_id: str,
        status: str = "PASS",
        error_type: str = "OK",
        message: str = "",
        evidence_paths: Optional[List[str]] = None,
    ):
        self.schema_version = SCHEMA_VERSION
        self.request_id = request_id
        self.job_id = job_id
        self.status = status
        self.error_type = error_type
        self.message = message
        self.evidence_paths = evidence_paths or []
        self.started_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        d = {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "job_id": self.job_id,
            "status": self.status,
            "error_type": self.error_type,
            "message": self.message,
            "started_at": self.started_at,
        }
        if self.evidence_paths:
            d["evidence_paths"] = self.evidence_paths
        return d

    def finish(self, status: str, error_type: str = "OK", message: str = "", evidence_paths: Optional[List[str]] = None) -> None:
        """Mark ack as finished"""
        self.status = status
        self.error_type = error_type
        self.message = message
        if evidence_paths:
            self.evidence_paths = evidence_paths
        self.finished_at = datetime.utcnow().isoformat() + "Z"

    def write_atomic(self, run_dir: Path) -> Path:
        """Atomically write ack to ack directory"""
        ack_dir = run_dir / "ack"
        ack_dir.mkdir(parents=True, exist_ok=True)
        ack_path = ack_dir / f"{self.request_id}.json"
        
        temp_path = ack_path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        temp_path.rename(ack_path)
        return ack_path

    @staticmethod
    def read(run_dir: Path, request_id: str) -> Optional["Ack"]:
        """Read ack from file"""
        ack_path = run_dir / "ack" / f"{request_id}.json"
        if not ack_path.exists():
            return None
        
        with open(ack_path, "r") as f:
            data = json.load(f)
        
        ack = Ack(
            request_id=data["request_id"],
            job_id=data["job_id"],
            status=data["status"],
            error_type=data["error_type"],
            message=data.get("message", ""),
            evidence_paths=data.get("evidence_paths", []),
        )
        ack.started_at = data["started_at"]
        if "finished_at" in data:
            ack.finished_at = data["finished_at"]
        return ack
