"""
L1: Mock unit tests for components
"""

import json
import tempfile
from pathlib import Path

from skillpilot.locator import Locator
from skillpilot.contracts import ContractValidator
from skillpilot.protocol.contract import Contract


def test_locator_explicit_path():
    """L1: explicit_path should find DB"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create enc and enc.dat
        enc_path = run_dir / "test.enc"
        enc_dat_path = run_dir / "test.enc.dat"
        enc_path.write_text("# Mock enc")
        enc_dat_path.write_text("")
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("./test.enc")
        
        assert result.is_success()
        # Compare resolved paths to handle macOS symlinks
        assert result.enc_path.resolve() == enc_path.resolve()
        assert result.enc_dat_path.resolve() == enc_dat_path.resolve()
        assert result.selection_reason == "direct_match"


def test_locator_missing_enc():
    """L4: missing enc should fail"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("./missing.enc")
        
        assert not result.is_success()
        assert result.selection_reason == "explicit_path_not_found"


def test_locator_missing_enc_dat():
    """L4: missing enc.dat should fail"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create enc without enc.dat
        enc_path = run_dir / "test.enc"
        enc_path.write_text("# Mock enc")
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("./test.enc")
        
        assert not result.is_success()
        assert result.selection_reason == "enc_dat_missing"


def test_locator_cwd_scan_unique():
    """L2: cwd_scan with unique result"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create enc and enc.dat
        enc_path = run_dir / "AAA.enc"
        enc_dat_path = run_dir / "AAA.enc.dat"
        enc_path.write_text("# Mock enc")
        enc_dat_path.write_text("")
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("AAA")
        
        assert result.is_success()
        assert result.selection_reason == "unique_scan_result"


def test_locator_cwd_scan_multiple():
    """L3: cwd_scan with multiple candidates"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create multiple encs
        (run_dir / "block1" / "AAA.enc").parent.mkdir(parents=True)
        (run_dir / "block2" / "AAA.enc").parent.mkdir(parents=True)
        (run_dir / "block1" / "AAA.enc").write_text("# Mock")
        (run_dir / "block1" / "AAA.enc.dat").write_text("")
        (run_dir / "block2" / "AAA.enc").write_text("# Mock")
        (run_dir / "block2" / "AAA.enc.dat").write_text("")
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("AAA")
        
        assert result.needs_selection()
        assert result.selection_reason == "multiple_candidates"
        assert len(result.candidates) == 2


def test_contract_validator_valid():
    """C1: valid contract should pass"""
    contract = Contract(name="test", version="1.0.0")
    contract.add_required_output("reports/test.txt")
    contract.add_required_output("reports/test2.txt")
    contract.add_debug_hint("Hint 1")
    contract.add_debug_hint("Hint 2")
    
    is_valid, error = ContractValidator.validate_contract(contract)
    assert is_valid
    assert error == ""


def test_contract_validator_empty_required():
    """C2: empty required should fail"""
    contract = Contract(name="test", version="1.0.0")
    contract.add_debug_hint("Hint 1")
    contract.add_debug_hint("Hint 2")
    
    is_valid, error = ContractValidator.validate_contract(contract)
    assert not is_valid
    assert "No required outputs" in error


def test_contract_validator_path_escape():
    """C3: path with .. should fail"""
    contract = Contract(name="test", version="1.0.0")
    contract.add_required_output("reports/../evil.txt")
    contract.add_debug_hint("Hint 1")
    contract.add_debug_hint("Hint 2")
    
    is_valid, error = ContractValidator.validate_contract(contract)
    assert not is_valid
    assert ".." in error


def test_validate_outputs_missing():
    """V2: missing output should fail"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        reports_dir = run_dir / "reports"
        reports_dir.mkdir()
        
        contract = Contract(name="test", version="1.0.0")
        contract.add_required_output("reports/missing.txt")
        contract.add_required_output("reports/missing2.txt")
        contract.add_debug_hint("Hint 1")
        contract.add_debug_hint("Hint 2")
        
        is_valid, error_type, results = ContractValidator.validate_outputs(contract, reports_dir)
        assert not is_valid
        assert error_type == "OUTPUT_MISSING"


def test_validate_outputs_empty():
    """V3: empty output should fail"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        reports_dir = run_dir / "reports"
        reports_dir.mkdir()
        
        # Create empty file
        (reports_dir / "empty.txt").write_text("")
        
        contract = Contract(name="test", version="1.0.0")
        contract.add_required_output("reports/empty.txt", non_empty=True)
        contract.add_debug_hint("Hint 1")
        contract.add_debug_hint("Hint 2")
        
        is_valid, error_type, results = ContractValidator.validate_outputs(contract, reports_dir)
        assert not is_valid
        assert error_type == "OUTPUT_EMPTY"


def test_validate_outputs_valid():
    """V1: valid outputs should pass"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        reports_dir = run_dir / "reports"
        reports_dir.mkdir()
        
        # Create files with content
        (reports_dir / "report1.txt").write_text("content 1")
        (reports_dir / "report2.txt").write_text("content 2")
        
        contract = Contract(name="test", version="1.0.0")
        contract.add_required_output("reports/report1.txt")
        contract.add_required_output("reports/report2.txt")
        contract.add_debug_hint("Hint 1")
        contract.add_debug_hint("Hint 2")
        
        # Validate contract first
        is_valid, _ = ContractValidator.validate_contract(contract)
        assert is_valid
        
        is_valid, error_type, results = ContractValidator.validate_outputs(contract, reports_dir)
        assert is_valid
        assert error_type == "OK"
        assert len(results) == 2
        assert all(r["status"] == "OK" for r in results)


def test_debug_bundle_generation():
    """D1: debug bundle should contain required files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        # Create required files
        (run_dir / "job_manifest.json").write_text('{"job_id": "test"}')
        (run_dir / "job_timeline.jsonl").write_text('{"event": "TEST"}')
        (run_dir / "session").mkdir()
        (run_dir / "session" / "state.json").write_text('{"pid": 123}')
        (run_dir / "session" / "supervisor.log").write_text("log line 1\nlog line 2\n")
        
        # Generate debug bundle
        from skillpilot.protocol.debug_bundle import DebugBundle
        debug_bundle = DebugBundle(
            run_dir=run_dir,
            job_id="test",
            error_type="TEST_ERROR",
            summary="Test error",
        )
        debug_bundle.generate(
            manifest_path=run_dir / "job_manifest.json",
            timeline_path=run_dir / "job_timeline.jsonl",
            session_dir=run_dir / "session",
        )
        
        # Verify bundle contents
        bundle_dir = run_dir / "debug_bundle"
        assert bundle_dir.exists()
        assert (bundle_dir / "index.json").exists()
        assert (bundle_dir / "job_manifest.json").exists()
        assert (bundle_dir / "job_timeline.jsonl").exists()
        assert (bundle_dir / "session" / "state.json").exists()
        assert (bundle_dir / "session" / "supervisor.log.tail").exists()
        
        # Check index
        with open(bundle_dir / "index.json", "r") as f:
            index = json.load(f)
        assert index["error_type"] == "TEST_ERROR"
        assert "manifest" in index["pointers"]
        assert "timeline" in index["pointers"]
        assert "session_logs" in index["pointers"]
