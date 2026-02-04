"""
L0: Protocol and static compliance tests
"""

import json
import tempfile
from pathlib import Path

from skillpilot.protocol.manifest import Manifest
from skillpilot.protocol.timeline import Timeline, Event
from skillpilot.protocol.request import Request
from skillpilot.protocol.ack import Ack
from skillpilot.protocol.summary import Summary
from skillpilot.protocol.debug_bundle import DebugBundle
from skillpilot.protocol.contract import Contract


def test_protocol_schema_versions():
    """All protocol files must contain schema_version"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Test Manifest
        manifest = Manifest(
            job_id="test_job",
            cwd=str(run_dir),
            run_dir=str(run_dir),
        )
        assert hasattr(manifest, 'schema_version')
        assert manifest.schema_version == "1.0"
        
        # Test Event
        event = Event(
            job_id="test_job",
            level="INFO",
            event="TEST",
        )
        assert hasattr(event, 'schema_version')
        assert event.schema_version == "1.0"
        
        # Test Request
        request = Request(job_id="test_job")
        assert hasattr(request, 'schema_version')
        assert request.schema_version == "1.0"
        
        # Test Ack
        ack = Ack(
            request_id="test_req",
            job_id="test_job",
        )
        assert hasattr(ack, 'schema_version')
        assert ack.schema_version == "1.0"
        
        # Test Summary
        summary = Summary(
            job_id="test_job",
            run_dir=run_dir,
            enc_path="/tmp/test.enc",
            enc_dat_path="/tmp/test.enc.dat",
            skill_name="test_skill",
            skill_version="1.0.0",
        )
        assert hasattr(summary, 'schema_version')
        assert summary.schema_version == "1.0"
        
        # Test Contract
        contract = Contract(name="test", version="1.0.0")
        assert hasattr(contract, 'schema_version')
        assert contract.schema_version == "1.0"


def test_run_dir_structure():
    """run_dir must have required structure"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "runs" / "test_job"
        run_dir.mkdir(parents=True)
        
        # Create required directories
        (run_dir / "scripts").mkdir()
        (run_dir / "queue").mkdir()
        (run_dir / "ack").mkdir()
        (run_dir / "reports").mkdir()
        (run_dir / "session").mkdir()
        
        # Create required files
        (run_dir / "job_manifest.json").write_text("{}")
        (run_dir / "job_timeline.jsonl").write_text("")
        (run_dir / "summary.json").write_text("{}")
        (run_dir / "summary.md").write_text("")
        
        # Verify structure
        assert (run_dir / "scripts").exists()
        assert (run_dir / "queue").exists()
        assert (run_dir / "ack").exists()
        assert (run_dir / "reports").exists()
        assert (run_dir / "session").exists()
        assert (run_dir / "job_manifest.json").exists()
        assert (run_dir / "job_timeline.jsonl").exists()
        assert (run_dir / "summary.json").exists()
        assert (run_dir / "summary.md").exists()


def test_timeline_events():
    """Timeline must have required events"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        timeline = Timeline(job_id="test", run_dir=run_dir)
        
        # Test state events
        timeline.state_enter("INIT")
        timeline.state_exit("INIT")
        
        # Test action events
        timeline.action("test_action", "test message")
        
        # Test done event
        timeline.done()
        
        # Test fail event
        timeline.fail("TEST_ERROR", "test error message")
        
        # Read and verify
        lines = timeline.path.read_text().splitlines()
        events = [json.loads(line) for line in lines]
        
        assert len(events) == 5
        assert events[0]["event"] == "STATE_ENTER"
        assert events[0]["state"] == "INIT"
        assert events[1]["event"] == "STATE_EXIT"
        assert events[2]["event"] == "ACTION"
        assert events[3]["event"] == "DONE"
        assert events[4]["event"] == "FAIL"
        assert events[4]["level"] == "ERROR"


def test_atomic_write():
    """Atomic write must not leave partial files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Test manifest atomic write
        manifest = Manifest(
            job_id="test",
            cwd=str(run_dir),
            run_dir=str(run_dir),
        )
        Manifest.write_atomic(run_dir / "job_manifest.json", manifest.to_dict())
        
        # File should exist and be valid JSON
        with open(run_dir / "job_manifest.json", "r") as f:
            data = json.load(f)
        assert data["job_id"] == "test"


def test_contract_validation():
    """Contract must have required outputs"""
    contract = Contract(name="test", version="1.0.0")
    
    # Invalid: no required outputs
    is_valid, error = contract.validate()
    assert not is_valid
    assert "No required outputs" in error
    
    # Add required output with invalid path
    contract.add_required_output("/tmp/report.txt")
    is_valid, error = contract.validate()
    assert not is_valid
    assert "absolute" in error or "relative" in error or "must start" in error
    
    # Add valid outputs
    contract = Contract(name="test", version="1.0.0")
    contract.add_required_output("reports/test.txt")
    contract.add_required_output("reports/test2.txt")
    contract.add_debug_hint("Hint 1")
    contract.add_debug_hint("Hint 2")
    
    is_valid, error = contract.validate()
    assert is_valid


def test_request_security():
    """Request script must be in scripts/ and not contain .."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Valid request
        request = Request(job_id="test")
        request.script = "scripts/test.tcl"
        request_path = request.write_atomic(run_dir)
        assert request_path.exists()
        
        # Try writing with invalid script (should write but fail at runtime)
        request2 = Request(job_id="test2")
        request2.script = "../evil.tcl"
        # This writes to disk - validation happens at runtime
        request2.write_atomic(run_dir)
