"""
Orchestrator - state machine driven job execution
"""

import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from skillpilot.protocol.manifest import Manifest
from skillpilot.protocol.timeline import Timeline
from skillpilot.protocol.summary import Summary
from skillpilot.protocol.debug_bundle import DebugBundle
from skillpilot.locator import Locator, LocatorResult
from skillpilot.contracts import ContractValidator
from skillpilot.adapters import PseudoSupervisor, SessionHandle
from skillpilot.kernel import ExecutionKernel


class JobResult:
    """Result of job execution"""
    
    def __init__(
        self,
        status: str,
        error_type: str,
        run_dir: Path,
        needs_user_selection: bool = False,
        candidates: Optional[list] = None,
    ):
        self.status = status
        self.error_type = error_type
        self.run_dir = run_dir
        self.needs_user_selection = needs_user_selection
        self.candidates = candidates


class Orchestrator:
    """Orchestrator - state machine driven job execution"""

    def __init__(self, cwd: Path, skill_root: Path):
        self.cwd = cwd
        self.skill_root = skill_root
        self.supervisor = PseudoSupervisor()

    def create_run_dir(self) -> Path:
        """Create run directory"""
        skillpilot_dir = self.cwd / ".skillpilot"
        skillpilot_dir.mkdir(parents=True, exist_ok=True)
        runs_dir = skillpilot_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        rand = str(uuid.uuid4())[:4]
        job_id = f"{timestamp}_{rand}"
        
        run_dir = runs_dir / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def run_job(
        self,
        design_query: str,
        skill_name: str,
        user_selection: Optional[Dict[str, str]] = None,
    ) -> JobResult:
        """
        Run a job
        
        Args:
            design_query: Design name or explicit path
            skill_name: Name of skill to run
            user_selection: Optional user selection for multi-candidate DB
            
        Returns:
            JobResult
        """
        run_dir = self.create_run_dir()
        job_id = run_dir.name
        
        # Initialize manifest and timeline
        manifest = Manifest(
            job_id=job_id,
            cwd=str(self.cwd),
            run_dir=str(run_dir),
            adapter="pseudo",
        )
        timeline = Timeline(job_id=job_id, run_dir=run_dir)
        kernel = ExecutionKernel(run_dir=run_dir)
        
        # Write initial manifest
        Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
        
        # PREPARE_RUNDIR state
        timeline.state_enter("PREPARE_RUNDIR")
        timeline.state_exit("PREPARE_RUNDIR")
        
        # LOCATE_DB state
        timeline.state_enter("LOCATE_DB")
        locator = Locator(cwd=self.cwd)
        result = locator.locate(design_query)
        
        if result.needs_selection():
            if user_selection:
                # User made selection
                enc_path = Path(user_selection["enc_path"])
                enc_dat_path = Path(user_selection["enc_dat_path"])
                manifest.set_design(
                    enc_path=str(enc_path),
                    enc_dat_path=str(enc_dat_path),
                    locator_mode="cwd_scan",
                    query=design_query,
                    candidates=result.candidates,
                    selection_reason="user_selected",
                )
            else:
                # Need user to select
                return JobResult(
                    status="NEEDS_SELECTION",
                    error_type="OK",
                    run_dir=run_dir,
                    needs_user_selection=True,
                    candidates=result.candidates,
                )
        elif result.is_success():
            manifest.set_design(
                enc_path=str(result.enc_path),
                enc_dat_path=str(result.enc_dat_path),
                locator_mode="explicit_path" if "/" in design_query or design_query.endswith(".enc") else "cwd_scan",
                query=design_query,
                selection_reason=result.selection_reason,
            )
        else:
            # Locator failed
            error_type = "LOCATOR_FAIL"
            timeline.fail(error_type, result.selection_reason)
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                summary=f"DB locator failed: {result.selection_reason}",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        
        timeline.state_exit("LOCATE_DB")
        
        # Load contract
        contract_path = self.skill_root / skill_name / "contract.yaml"
        from skillpilot.protocol.contract import Contract
        try:
            contract = Contract.load(contract_path)
            manifest.set_skill(
                name=contract.name,
                version=contract.version,
                subskill_path=str(contract_path),
            )
        except Exception as e:
            error_type = "CONTRACT_INVALID"
            timeline.fail(error_type, str(e))
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                contract_path=contract_path,
                summary=f"Contract load failed: {e}",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        
        # Validate contract
        is_valid, error_msg = ContractValidator.validate_contract(contract)
        if not is_valid:
            error_type = "CONTRACT_INVALID"
            timeline.fail(error_type, error_msg)
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                contract_path=contract_path,
                summary=f"Contract invalid: {error_msg}",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        
        # START_SESSION state
        timeline.state_enter("START_SESSION")
        try:
            handle = self.supervisor.start(run_dir, env={})
            if not self.supervisor.wait_ready(handle, timeout_s=30):
                error_type = "SESSION_START_FAIL"
                timeline.fail(error_type, "Session ready timeout")
                manifest.set_status("FAIL", error_type)
                self._generate_debug_bundle(
                    run_dir=run_dir,
                    job_id=job_id,
                    error_type=error_type,
                    timeline_path=run_dir / "job_timeline.jsonl",
                    manifest_path=run_dir / "job_manifest.json",
                    session_dir=run_dir / "session",
                    summary="Session start failed: ready timeout",
                )
                Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
                return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        except Exception as e:
            error_type = "SESSION_START_FAIL"
            timeline.fail(error_type, str(e))
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                session_dir=run_dir / "session",
                summary=f"Session start failed: {e}",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        timeline.state_exit("START_SESSION")
        
        # RESTORE_DB state
        timeline.state_enter("RESTORE_DB")
        kernel.write_restore_wrapper(Path(manifest.design["enc_path"]))
        timeline.action("submit_request", "restore_wrapper")
        restore_request_id = kernel.submit_request(job_id, "scripts/restore_wrapper.tcl")
        timeline.action("receive_ack", "restore_wrapper")
        
        try:
            ack = kernel.wait_for_ack(restore_request_id)
            if ack.status != "PASS":
                error_type = ack.error_type
                timeline.fail(error_type, ack.message)
                manifest.set_status("FAIL", error_type)
                self._generate_debug_bundle(
                    run_dir=run_dir,
                    job_id=job_id,
                    error_type=error_type,
                    timeline_path=run_dir / "job_timeline.jsonl",
                    manifest_path=run_dir / "job_manifest.json",
                    session_dir=run_dir / "session",
                    last_fail_ack_path=run_dir / "ack" / f"{restore_request_id}.json",
                    summary=f"Restore failed: {ack.message}",
                )
                Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
                self.supervisor.stop(handle)
                return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        except TimeoutError:
            error_type = "QUEUE_TIMEOUT"
            timeline.fail(error_type, "Restore request timeout")
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                session_dir=run_dir / "session",
                summary="Restore request timeout",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            self.supervisor.stop(handle)
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        timeline.state_exit("RESTORE_DB")
        
        # RUN_SKILL state
        timeline.state_enter("RUN_SKILL")
        kernel.write_run_skill_script(skill_name)
        timeline.action("submit_request", f"run_{skill_name}")
        skill_request_id = kernel.submit_request(job_id, f"scripts/run_{skill_name}.tcl")
        timeline.action("receive_ack", f"run_{skill_name}")
        
        try:
            ack = kernel.wait_for_ack(skill_request_id)
            if ack.status != "PASS":
                error_type = ack.error_type
                timeline.fail(error_type, ack.message)
                manifest.set_status("FAIL", error_type)
                self._generate_debug_bundle(
                    run_dir=run_dir,
                    job_id=job_id,
                    error_type=error_type,
                    timeline_path=run_dir / "job_timeline.jsonl",
                    manifest_path=run_dir / "job_manifest.json",
                    session_dir=run_dir / "session",
                    last_fail_ack_path=run_dir / "ack" / f"{skill_request_id}.json",
                    summary=f"Skill execution failed: {ack.message}",
                )
                Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
                self.supervisor.stop(handle)
                return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        except TimeoutError:
            error_type = "QUEUE_TIMEOUT"
            timeline.fail(error_type, "Skill request timeout")
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                session_dir=run_dir / "session",
                summary="Skill request timeout",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            self.supervisor.stop(handle)
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        timeline.state_exit("RUN_SKILL")
        
        # VALIDATE_OUTPUTS state
        timeline.state_enter("VALIDATE_OUTPUTS")
        is_valid, error_type, validation_results = ContractValidator.validate_outputs(
            contract, run_dir / "reports"
        )
        
        if not is_valid:
            timeline.fail(error_type, str(validation_results))
            manifest.set_status("FAIL", error_type)
            self._generate_debug_bundle(
                run_dir=run_dir,
                job_id=job_id,
                error_type=error_type,
                timeline_path=run_dir / "job_timeline.jsonl",
                manifest_path=run_dir / "job_manifest.json",
                session_dir=run_dir / "session",
                reports_dir=run_dir / "reports",
                contract_path=contract_path,
                summary=f"Output validation failed: {error_type}",
            )
            Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
            self.supervisor.stop(handle)
            return JobResult(status="FAIL", error_type=error_type, run_dir=run_dir)
        timeline.state_exit("VALIDATE_OUTPUTS")
        
        # SUMMARIZE state
        timeline.state_enter("SUMMARIZE")
        summary = Summary(
            job_id=job_id,
            run_dir=run_dir,
            enc_path=manifest.design["enc_path"],
            enc_dat_path=manifest.design["enc_dat_path"],
            skill_name=manifest.skill["name"],
            skill_version=manifest.skill["version"],
        )
        summary.set_metrics({"total_outputs": len(validation_results)})
        summary.write_json(run_dir)
        summary.write_md(run_dir, findings="Analysis completed successfully", risks="None")
        timeline.state_exit("SUMMARIZE")
        
        # DONE
        timeline.done()
        manifest.set_status("PASS", "OK")
        manifest.set_artifacts(run_dir, has_debug_bundle=False)
        Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
        
        # Stop session
        self.supervisor.stop(handle)
        
        return JobResult(status="PASS", error_type="OK", run_dir=run_dir)

    def _generate_debug_bundle(
        self,
        run_dir: Path,
        job_id: str,
        error_type: str,
        timeline_path: Path,
        manifest_path: Path,
        session_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
        contract_path: Optional[Path] = None,
        last_fail_ack_path: Optional[Path] = None,
        summary: str = "",
    ) -> None:
        """Generate debug bundle"""
        debug_bundle = DebugBundle(
            run_dir=run_dir,
            job_id=job_id,
            error_type=error_type,
            summary=summary,
        )
        debug_bundle.generate(
            manifest_path=manifest_path,
            timeline_path=timeline_path,
            session_dir=session_dir,
            reports_dir=reports_dir,
            contract_path=contract_path,
            last_fail_ack_path=last_fail_ack_path,
        )
