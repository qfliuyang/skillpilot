"""
Debug bundle protocol implementation
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from .schema import SCHEMA_VERSION


class DebugBundle:
    """Debug bundle - minimal reproducible materials for FAIL cases"""

    def __init__(self, run_dir: Path, job_id: str, error_type: str, summary: str):
        self.run_dir = run_dir
        self.job_id = job_id
        self.error_type = error_type
        self.summary = summary
        self.bundle_dir = run_dir / "debug_bundle"
        self.schema_version = SCHEMA_VERSION

    def generate(
        self,
        manifest_path: Path,
        timeline_path: Path,
        last_fail_ack_path: Optional[Path] = None,
        session_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
        contract_path: Optional[Path] = None,
        notes: str = "",
    ) -> None:
        """Generate debug bundle"""
        self.bundle_dir.mkdir(parents=True, exist_ok=True)

        index = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "error_type": self.error_type,
            "summary": self.summary,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "pointers": {},
            "next_actions": self._get_next_actions(),
        }

        # Copy manifest
        if manifest_path.exists():
            shutil.copy2(manifest_path, self.bundle_dir / "job_manifest.json")
            index["pointers"]["manifest"] = "job_manifest.json"

        # Copy timeline (can truncate but must cover FAIL events)
        if timeline_path.exists():
            shutil.copy2(timeline_path, self.bundle_dir / "job_timeline.jsonl")
            index["pointers"]["timeline"] = "job_timeline.jsonl"

        # Copy last fail ack
        if last_fail_ack_path and last_fail_ack_path.exists():
            ack_dir = self.bundle_dir / "ack"
            ack_dir.mkdir(exist_ok=True)
            shutil.copy2(last_fail_ack_path, ack_dir / last_fail_ack_path.name)
            index["pointers"]["last_fail_ack"] = f"ack/{last_fail_ack_path.name}"

        # Copy session logs tail
        if session_dir and session_dir.exists():
            session_bundle_dir = self.bundle_dir / "session"
            session_bundle_dir.mkdir(exist_ok=True)
            
            # Copy state.json
            state_file = session_dir / "state.json"
            if state_file.exists():
                shutil.copy2(state_file, session_bundle_dir / "state.json")
            
            # Copy log tails (last 2000 lines)
            for log_name in ["supervisor.log", "innovus.stdout.log", "innovus.stderr.log"]:
                log_path = session_dir / log_name
                if log_path.exists():
                    tail_path = session_bundle_dir / f"{log_name}.tail"
                    self._tail_file(log_path, tail_path, lines=2000)
            
            index["pointers"]["session_logs"] = "session/"

        # Generate reports inventory
        if reports_dir and reports_dir.exists():
            inventory_path = self.bundle_dir / "reports_inventory.json"
            self._generate_inventory(reports_dir, inventory_path)
            index["pointers"]["reports_inventory"] = "reports_inventory.json"

        # Copy contract
        if contract_path and contract_path.exists():
            shutil.copy2(contract_path, self.bundle_dir / "contract.yaml")
            index["pointers"]["contract"] = "contract.yaml"

        # Write notes
        if notes:
            notes_path = self.bundle_dir / "notes.txt"
            with open(notes_path, "w") as f:
                f.write(notes)
            index["pointers"]["notes"] = "notes.txt"

        # Write index
        index_path = self.bundle_dir / "index.json"
        temp_path = index_path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "w") as f:
            json.dump(index, f, indent=2, default=str)
        temp_path.rename(index_path)

    def _tail_file(self, src: Path, dst: Path, lines: int = 2000) -> None:
        """Copy last N lines of file"""
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        with open(dst, "w", encoding="utf-8") as f:
            f.writelines(tail_lines)

    def _generate_inventory(self, reports_dir: Path, inventory_path: Path) -> None:
        """Generate reports inventory"""
        inventory = []
        for path in sorted(reports_dir.rglob("*")):
            if path.is_file():
                stat = path.stat()
                inventory.append({
                    "path": str(path.relative_to(reports_dir)),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        
        with open(inventory_path, "w") as f:
            json.dump(inventory, f, indent=2, default=str)

    def _get_next_actions(self) -> List[str]:
        """Get suggested next actions based on error_type"""
        actions_map = {
            "LOCATOR_FAIL": [
                "Check if enc/enc.dat exist and are readable",
                "Try explicit path: ./path/to/design.enc",
                "Check permissions and mount points",
            ],
            "SESSION_START_FAIL": [
                "Check session/supervisor.log for dsub errors",
                "Verify Innovus installation and license",
                "Check queue availability and resources",
            ],
            "INNOVUS_CRASH": [
                "Check session/state.json for exit code",
                "Review innovus stdout/stderr tail",
                "Check if design DB is corrupted",
            ],
            "HEARTBEAT_LOST": [
                "Check session/heartbeat last update time",
                "Verify if Innovus process is still running",
                "Check system resources and queue status",
            ],
            "QUEUE_TIMEOUT": [
                "Check if heartbeat is still updating",
                "Review script execution logs",
                "Check for infinite loops or long operations",
            ],
            "RESTORE_FAIL": [
                "Review ack message and Innovus log tail",
                "Check if enc contains relative path dependencies",
                "Verify enc.dat compatibility",
            ],
            "CMD_FAIL": [
                "Check ack message for script error",
                "Review script in scripts/",
                "Check for TCL syntax errors",
            ],
            "CONTRACT_INVALID": [
                "Review contract.yaml",
                "Ensure required outputs are specified",
                "Check path constraints",
            ],
            "OUTPUT_MISSING": [
                "Check reports_inventory.json",
                "Verify script generated required outputs",
                "Check contract.yaml requirements",
            ],
            "OUTPUT_EMPTY": [
                "Check report file sizes in reports/",
                "Verify script produced non-empty outputs",
                "Review script logic",
            ],
        }
        return actions_map.get(self.error_type, ["Review debug_bundle contents for details"])
