"""
Summary protocol implementation
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .schema import SCHEMA_VERSION


class Summary:
    """Summary - human and machine readable results"""

    def __init__(
        self,
        job_id: str,
        run_dir: Path,
        enc_path: str,
        enc_dat_path: str,
        skill_name: str,
        skill_version: str,
    ):
        self.schema_version = SCHEMA_VERSION
        self.job_id = job_id
        self.status = "PASS"
        self.error_type = "OK"
        self.design = {
            "enc_path": str(enc_path),
            "enc_dat_path": str(enc_dat_path),
        }
        self.skill = {
            "name": skill_name,
            "version": skill_version,
        }
        self.metrics: Dict[str, Any] = {}
        self.evidence = {
            "run_dir": str(run_dir),
            "summary_md": str(run_dir / "summary.md"),
            "reports_dir": str(run_dir / "reports"),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "status": self.status,
            "error_type": self.error_type,
            "design": self.design,
            "skill": self.skill,
            "metrics": self.metrics,
            "evidence": self.evidence,
        }

    def set_status(self, status: str, error_type: str = "OK") -> None:
        """Set status"""
        self.status = status
        self.error_type = error_type

    def set_metrics(self, metrics: Dict[str, Any]) -> None:
        """Set metrics"""
        self.metrics = metrics

    def write_json(self, run_dir: Path) -> None:
        """Write summary.json atomically"""
        summary_path = run_dir / "summary.json"
        temp_path = summary_path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        temp_path.rename(summary_path)

    def write_md(self, run_dir: Path, findings: str = "", risks: str = "") -> None:
        """Write summary.md"""
        summary_path = run_dir / "summary.md"
        lines = [
            f"# SkillPilot Summary",
            f"",
            f"## Conclusion",
            f"- **Status**: {self.status}",
            f"- **Error Type**: {self.error_type}",
            f"",
        ]
        
        if findings:
            lines.extend([
                f"## Key Findings",
                f"{findings}",
                f"",
            ])
        
        if risks:
            lines.extend([
                f"## Risks / Issues",
                f"{risks}",
                f"",
            ])
        
        lines.extend([
            f"## Evidence Paths",
            f"- **run_dir**: `{run_dir}`",
            f"- **summary.md**: `{summary_path}`",
            f"- **summary.json**: `{run_dir / 'summary.json'}`",
            f"- **reports/**: `{run_dir / 'reports'}`",
            f"- **session/**: `{run_dir / 'session'}`",
        ])
        
        if self.status == "FAIL":
            lines.extend([
                f"- **debug_bundle/**: `{run_dir / 'debug_bundle'}`",
            ])
        
        lines.append("")
        
        with open(summary_path, "w") as f:
            f.write("\n".join(lines))
