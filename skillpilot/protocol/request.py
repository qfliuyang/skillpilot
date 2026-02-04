"""
Request protocol implementation
"""

import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from .schema import SCHEMA_VERSION


class Request:
    """Request to Innovus queue_processor"""

    def __init__(
        self,
        job_id: str,
        action: str = "SOURCE_TCL",
        script: str = "",
        timeout_s: Optional[int] = None,
    ):
        self.schema_version = SCHEMA_VERSION
        self.request_id = f"{job_id}_source_{uuid.uuid4().hex[:8]}"
        self.job_id = job_id
        self.action = action
        self.script = script
        self.timeout_s = timeout_s
        self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        d = {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "job_id": self.job_id,
            "action": self.action,
            "created_at": self.created_at,
        }
        if self.script:
            d["script"] = self.script
        if self.timeout_s is not None:
            d["timeout_s"] = self.timeout_s
        return d

    def write_atomic(self, run_dir: Path) -> Path:
        """Atomically write request to queue directory"""
        queue_dir = run_dir / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        request_path = queue_dir / f"{self.request_id}.json"
        
        if request_path.exists():
            raise FileExistsError(f"Request {self.request_id} already exists")
        
        temp_path = request_path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        temp_path.rename(request_path)
        return request_path
