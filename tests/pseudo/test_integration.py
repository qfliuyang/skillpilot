"""
L1.5: Pseudo integration tests with PseudoSupervisor/PseudoSession
"""

import json
import tempfile
import time
from pathlib import Path

from skillpilot.orchestrator import Orchestrator
from skillpilot.adapters import PseudoSupervisor, SessionHandle


def test_pseudo_session_lifecycle():
    """Test PseudoSession lifecycle"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        supervisor = PseudoSupervisor()
        
        # Start session
        handle = supervisor.start(run_dir, env={})
        assert isinstance(handle, SessionHandle)
        
        # Wait for ready
        ready = supervisor.wait_ready(handle, timeout_s=10)
        assert ready
        
        # Check health
        health = supervisor.poll_health(handle)
        assert health["status"] in ["healthy", "no_heartbeat"]
        
        # Stop session
        supervisor.stop(handle, reason="test_complete")
        
        # Check health again (should show stopped/exited)
        time.sleep(0.5)
        health = supervisor.poll_health(handle)
        assert health["status"] in ["exited", "heartbeat_lost"]


def test_request_ack_roundtrip():
    """Test request -> ack roundtrip"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        supervisor = PseudoSupervisor()
        
        # Start session
        handle = supervisor.start(run_dir, env={})
        supervisor.wait_ready(handle, timeout_s=10)
        
        # Submit request via kernel
        from skillpilot.kernel import ExecutionKernel
        kernel = ExecutionKernel(run_dir=run_dir)
        request_id = kernel.submit_request(job_id="test", script="scripts/test.tcl")
        
        # Wait for ack
        from skillpilot.protocol.ack import Ack
        ack = kernel.wait_for_ack(request_id)
        
        assert ack is not None
        assert ack.request_id == request_id
        assert ack.status == "PASS"
        
        supervisor.stop(handle)


def test_injection_fail_on_script():
    """Test failure injection via inject.json"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create injection config
        session_dir = run_dir / "session"
        session_dir.mkdir(parents=True)
        inject_config = {"fail_on_script": "restore_wrapper"}
        (session_dir / "inject.json").write_text(json.dumps(inject_config))
        
        # Start session
        supervisor = PseudoSupervisor()
        handle = supervisor.start(run_dir, env={})
        supervisor.wait_ready(handle, timeout_s=10)
        
        # Submit request that should fail
        from skillpilot.kernel import ExecutionKernel
        kernel = ExecutionKernel(run_dir=run_dir)
        request_id = kernel.submit_request(job_id="test", script="scripts/restore_wrapper.tcl")
        
        # Wait for ack - should be FAIL
        ack = kernel.wait_for_ack(request_id)
        
        assert ack.status == "FAIL"
        assert ack.error_type == "CMD_FAIL"
        
        supervisor.stop(handle)


def test_happy_path_integration():
    """I1: Full happy path integration test"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)
        
        # Create mock design DB
        enc_path = cwd / "test_design.enc"
        enc_dat_path = cwd / "test_design.enc.dat"
        enc_path.write_text("# Mock enc\n# RESTORE_OK")
        enc_dat_path.write_text("")
        
        # Setup skill root
        skill_root = Path(__file__).parent.parent.parent / "subskills"
        
        # Run job
        orchestrator = Orchestrator(cwd=cwd, skill_root=skill_root)
        result = orchestrator.run_job(
            design_query="./test_design.enc",
            skill_name="summary_health_mock",
        )
        
        # Verify result
        assert result.status == "PASS"
        assert result.error_type == "OK"
        assert result.run_dir.exists()
        
        # Verify run_dir structure
        run_dir = result.run_dir
        assert (run_dir / "job_manifest.json").exists()
        assert (run_dir / "job_timeline.jsonl").exists()
        assert (run_dir / "summary.json").exists()
        assert (run_dir / "summary.md").exists()
        assert (run_dir / "reports").exists()
        assert (run_dir / "session").exists()
        
        # Verify reports
        reports_dir = run_dir / "reports"
        assert (reports_dir / "summary_health.txt").exists()
        assert (reports_dir / "timing_health.txt").exists()
        
        # Verify manifest
        with open(run_dir / "job_manifest.json", "r") as f:
            manifest = json.load(f)
        assert manifest["status"] == "PASS"
        assert manifest["error_type"] == "OK"
        # Compare resolved paths for macOS compatibility
        assert Path(manifest["design"]["enc_path"]).resolve() == enc_path.resolve()
        assert Path(manifest["design"]["enc_dat_path"]).resolve() == enc_dat_path.resolve()
        
        # Verify timeline has DONE event
        with open(run_dir / "job_timeline.jsonl", "r") as f:
            events = [json.loads(line) for line in f]
        done_events = [e for e in events if e["event"] == "DONE"]
        assert len(done_events) == 1


def test_locator_fail_integration():
    """Test LOCATOR_FAIL integration"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)
        
        # Setup skill root
        skill_root = Path(__file__).parent.parent.parent / "subskills"
        
        # Run job with non-existent design
        orchestrator = Orchestrator(cwd=cwd, skill_root=skill_root)
        result = orchestrator.run_job(
            design_query="./nonexistent.enc",
            skill_name="summary_health_mock",
        )
        
        # Verify result
        assert result.status == "FAIL"
        assert result.error_type == "LOCATOR_FAIL"
        assert result.run_dir.exists()
        
        # Verify debug bundle exists
        debug_bundle_dir = result.run_dir / "debug_bundle"
        assert debug_bundle_dir.exists()
        assert (debug_bundle_dir / "index.json").exists()


def test_multi_candidate_integration():
    """Test multi-candidate DB selection"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)
        
        # Create multiple design DBs
        block1_dir = cwd / "block1"
        block2_dir = cwd / "block2"
        block1_dir.mkdir()
        block2_dir.mkdir()
        
        (block1_dir / "AAA.enc").write_text("# Block1")
        (block1_dir / "AAA.enc.dat").write_text("")
        (block2_dir / "AAA.enc").write_text("# Block2")
        (block2_dir / "AAA.enc.dat").write_text("")
        
        # Setup skill root
        skill_root = Path(__file__).parent.parent.parent / "subskills"
        
        # Run job without selection
        orchestrator = Orchestrator(cwd=cwd, skill_root=skill_root)
        result = orchestrator.run_job(
            design_query="AAA",
            skill_name="summary_health_mock",
        )
        
        # Verify result needs selection
        assert result.status == "NEEDS_SELECTION"
        assert result.needs_user_selection
        assert len(result.candidates) == 2
        
        # Resume with selection
        result2 = orchestrator.run_job(
            design_query="AAA",
            skill_name="summary_health_mock",
            user_selection={
                "enc_path": str(block1_dir / "AAA.enc"),
                "enc_dat_path": str(block1_dir / "AAA.enc.dat"),
            },
        )
        
        assert result2.status == "PASS"
        assert result2.error_type == "OK"
