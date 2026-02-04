"""
Pseudo adapters for local testing without real Innovus/dsub
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class SessionHandle:
    """Handle for a session"""
    pid: int
    run_dir: Path
    stop_requested: bool = False


class PseudoSupervisor:
    """Pseudo supervisor - simulates dsub -I + Innovus session"""

    def __init__(self):
        self.sessions: Dict[str, SessionHandle] = {}

    def start(self, run_dir: Path, env: dict) -> SessionHandle:
        """Start a pseudo session"""
        session_dir = run_dir / "session"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create supervisor log
        supervisor_log = session_dir / "supervisor.log"
        with open(supervisor_log, "w") as f:
            f.write("PseudoSupervisor: Starting pseudo session\n")
            f.write(f"run_dir: {run_dir}\n")
            f.write(f"adapter: pseudo\n")
        
        # Create state.json
        state_path = session_dir / "state.json"
        pid = os.getpid()
        state = {
            "pid": pid,
            "start_time": time.time(),
            "exit_code": None,
            "last_heartbeat_ts": None,
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
        
        # Start pseudo session process
        pseudo_session = PseudoSession(run_dir)
        thread = threading.Thread(target=pseudo_session.run, daemon=True)
        thread.start()
        
        handle = SessionHandle(pid=pid, run_dir=run_dir)
        self.sessions[str(run_dir)] = handle
        return handle

    def wait_ready(self, handle: SessionHandle, timeout_s: int = 60) -> bool:
        """Wait for session to be ready"""
        ready_file = handle.run_dir / "session" / "ready"
        start = time.time()
        
        while time.time() - start < timeout_s:
            if ready_file.exists():
                return True
            time.sleep(0.1)
        
        return False

    def stop(self, handle: SessionHandle, reason: str = "") -> None:
        """Stop session"""
        stop_file = handle.run_dir / "session" / "stop"
        with open(stop_file, "w") as f:
            f.write(reason or "stopped_by_supervisor")
        handle.stop_requested = True

    def poll_health(self, handle: SessionHandle) -> Dict[str, Any]:
        """Poll session health"""
        session_dir = handle.run_dir / "session"
        heartbeat_file = session_dir / "heartbeat"
        state_file = session_dir / "state.json"
        
        result = {
            "status": "healthy",
            "heartbeat_age_s": 0,
            "last_heartbeat_ts": None,
        }
        
        # Check heartbeat
        if heartbeat_file.exists():
            heartbeat_time = heartbeat_file.stat().st_mtime
            result["last_heartbeat_ts"] = heartbeat_time
            result["heartbeat_age_s"] = time.time() - heartbeat_time
        else:
            result["status"] = "no_heartbeat"
            return result
        
        # Check state
        if state_file.exists():
            with open(state_file, "r") as f:
                state = json.load(f)
            if state.get("exit_code") is not None:
                result["status"] = "crashed" if state["exit_code"] != 0 else "exited"
        
        # Check if heartbeat is stale
        if result["heartbeat_age_s"] > 30:
            result["status"] = "heartbeat_lost"
        
        return result

    def collect_logs(self, handle: SessionHandle) -> None:
        """Ensure logs are collected (no-op for pseudo)"""
        pass


class PseudoSession:
    """Pseudo session - simulates Innovus queue_processor"""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.running = True

    def run(self):
        """Run pseudo session"""
        session_dir = self.run_dir / "session"
        queue_dir = self.run_dir / "queue"
        ack_dir = self.run_dir / "ack"
        scripts_dir = self.run_dir / "scripts"
        reports_dir = self.run_dir / "reports"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        queue_dir.mkdir(parents=True, exist_ok=True)
        ack_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Write ready file
        ready_file = session_dir / "ready"
        ready_file.write_text("ready")
        
        # Write stdout log
        stdout_log = session_dir / "innovus.stdout.log"
        
        # Check for injection config
        inject_file = session_dir / "inject.json"
        inject_config = {}
        if inject_file.exists():
            with open(inject_file, "r") as f:
                inject_config = json.load(f)
        
        # Main loop
        while self.running:
            try:
                # Update heartbeat
                heartbeat_file = session_dir / "heartbeat"
                heartbeat_file.write_text(str(time.time()))
            except (FileNotFoundError, OSError):
                # Directory was cleaned up, stop running
                self.running = False
                break
            
            # Check for stop signal
            stop_file = session_dir / "stop"
            if stop_file.exists():
                with open(stdout_log, "a") as f:
                    f.write("Session stopped\n")
                break
            
            # Process queue
            for request_file in sorted(queue_dir.glob("*.json")):
                # Check for ack already exists
                request_id = request_file.stem
                ack_file = ack_dir / f"{request_id}.json"
                if ack_file.exists():
                    continue
                
                # Read request
                with open(request_file, "r") as f:
                    request_data = json.load(f)
                
                with open(stdout_log, "a") as f:
                    f.write(f"Processing request: {request_id}\n")
                    f.write(f"  action: {request_data.get('action')}\n")
                    f.write(f"  script: {request_data.get('script')}\n")
                
                # Process request
                ack_data = self._process_request(request_data, scripts_dir, reports_dir, inject_config)
                
                # Write ack
                temp_ack = ack_file.with_suffix(f".tmp.{os.getpid()}")
                with open(temp_ack, "w") as f:
                    json.dump(ack_data, f, indent=2, default=str)
                temp_ack.rename(ack_file)
                
                with open(stdout_log, "a") as f:
                    f.write(f"  result: {ack_data['status']}\n")
            
            # Sleep
            time.sleep(0.1)
        
        # Update state on exit
        state_file = session_dir / "state.json"
        with open(state_file, "r") as f:
            state = json.load(f)
        state["exit_code"] = 0
        state["last_heartbeat_ts"] = time.time()
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _process_request(
        self,
        request: Dict[str, Any],
        scripts_dir: Path,
        reports_dir: Path,
        inject_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a single request"""
        script = request.get("script", "")
        
        # Check for injection
        fail_on_script = inject_config.get("fail_on_script")
        if fail_on_script and fail_on_script in script:
            return {
                "schema_version": "1.0",
                "request_id": request["request_id"],
                "job_id": request["job_id"],
                "status": "FAIL",
                "error_type": "CMD_FAIL",
                "message": f"Injected failure for script: {script}",
                "started_at": request["created_at"],
                "finished_at": time.time(),
            }
        
        # Simulate restore_wrapper
        if "restore_wrapper" in script:
            return {
                "schema_version": "1.0",
                "request_id": request["request_id"],
                "job_id": request["job_id"],
                "status": "PASS",
                "error_type": "OK",
                "message": "Restore completed",
                "started_at": request["created_at"],
                "finished_at": time.time(),
            }
        
        # Simulate subskill execution - generate reports
        if "run_skill" in script or "summary_health" in script:
            self._generate_mock_reports(reports_dir)
            return {
                "schema_version": "1.0",
                "request_id": request["request_id"],
                "job_id": request["job_id"],
                "status": "PASS",
                "error_type": "OK",
                "message": "Skill execution completed",
                "started_at": request["created_at"],
                "finished_at": time.time(),
            }
        
        # Default: PASS
        return {
            "schema_version": "1.0",
            "request_id": request["request_id"],
            "job_id": request["job_id"],
            "status": "PASS",
            "error_type": "OK",
            "message": "Request processed",
            "started_at": request["created_at"],
            "finished_at": time.time(),
        }

    def _generate_mock_reports(self, reports_dir: Path) -> None:
        """Generate mock report files"""
        # Create summary_health.txt
        (reports_dir / "summary_health.txt").write_text("""
Design Health Summary
=====================
Overall Status: HEALTHY
Total Cells: 123456
Utilization: 45.2%
Power: 1.2 W

Timing Analysis
---------------
Setup: PASSED
Hold: PASSED
WNS: 0.45 ns
TNS: 0 ns
""")
        
        # Create timing_health.txt
        (reports_dir / "timing_health.txt").write_text("""
Timing Health Report
====================
Setup WNS: 0.45 ns
Setup TNS: 0 ns
Hold WNS: 0.12 ns
Hold TNS: 0 ns
Critical Path Count: 15
""")
