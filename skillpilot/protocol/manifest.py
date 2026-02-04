"""
Manifest protocol implementation
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from .schema import SCHEMA_VERSION


class Manifest:
    """Job manifest - SSOT for job input, selection, version, and final state"""

    def __init__(
        self,
        job_id: str,
        cwd: str,
        run_dir: str,
        adapter: str = "pseudo",
    ):
        self.schema_version = SCHEMA_VERSION
        self.job_id = job_id
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.status = "RUNNING"
        self.error_type = "OK"
        self.runtime = {
            "cwd": cwd,
            "run_dir": run_dir,
            "adapter": adapter,
        }
        self.design: Dict[str, Any] = {}
        self.skill: Dict[str, Any] = {}
        self.artifacts: Dict[str, Any] = {}
        self.versions: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "status": self.status,
            "error_type": self.error_type,
            "runtime": self.runtime,
            "design": self.design,
            "skill": self.skill,
            "artifacts": self.artifacts,
            "versions": self.versions,
        }

    def set_status(self, status: str, error_type: str = "OK") -> None:
        """Set final status"""
        self.status = status
        self.error_type = error_type

    def set_design(
        self,
        enc_path: str,
        enc_dat_path: str,
        locator_mode: str,
        query: str,
        candidates: Optional[list] = None,
        selection_reason: str = "",
    ) -> None:
        """Set design information"""
        locator = {
            "mode": locator_mode,
            "query": query,
            "selection_reason": selection_reason,
        }
        if candidates:
            locator["candidates"] = candidates
        if selection_reason:
            locator["selected"] = {
                "enc_path": enc_path,
                "enc_dat_path": enc_dat_path,
            }

        self.design = {
            "enc_path": enc_path,
            "enc_dat_path": enc_dat_path,
            "locator": locator,
        }

    def set_skill(self, name: str, version: str, subskill_path: str) -> None:
        """Set skill information"""
        self.skill = {
            "name": name,
            "version": version,
            "subskill_path": subskill_path,
        }

    def set_artifacts(self, run_dir: Path, has_debug_bundle: bool = False) -> None:
        """Set artifact pointers"""
        self.artifacts = {
            "timeline": str(run_dir / "job_timeline.jsonl"),
            "summary_json": str(run_dir / "summary.json"),
            "summary_md": str(run_dir / "summary.md"),
            "reports_dir": str(run_dir / "reports"),
            "session_dir": str(run_dir / "session"),
        }
        if has_debug_bundle:
            self.artifacts["debug_bundle_dir"] = str(run_dir / "debug_bundle")

    @staticmethod
    def write_atomic(path: Path, data: Dict[str, Any]) -> None:
        """Atomically write manifest to file"""
        temp_path = path.with_suffix(f".tmp.{id(path.parent)}")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        temp_path.rename(path)
