# SkillPilot Testing Guide

## Overview

This guide covers testing practices for SkillPilot, including the current test suite and how to extend it.

---

## Test Structure

```
tests/
├── unit/                # L0/L1 tests (protocol + components)
│   └── test_l0_protocol.py
│   └── test_l1_components.py
├── pseudo/              # L1.5 tests (pseudo integration)
│   ├── test_integration.py
│   └── test_additional.py
└── conftest.py          # Pytest configuration
```

---

## Test Layers

### L0: Protocol and Static Compliance Tests

Tests that validate the protocol layer without any external dependencies.

**Coverage:**
- Schema version validation
- run_dir structure
- Timeline events
- Atomic write behavior
- Contract security constraints

**Run:**
```bash
pytest tests/unit/test_l0_protocol.py -v
```

### L1: Mock Unit Tests

Tests that validate individual components using mocks and fixtures.

**Coverage:**
- Locator (explicit_path, cwd_scan, multi-candidate, missing enc/dat)
- Contract validator (valid, empty required, path escape)
- Output validation (missing, empty, valid, glob patterns)
- Debug bundle generation

**Run:**
```bash
pytest tests/unit/test_l1_components.py -v
```

### L1.5: Pseudo Integration Tests

End-to-end tests using PseudoSupervisor/PseudoSession (no real Innovus).

**Coverage:**
- Pseudo session lifecycle
- Request/ack roundtrip
- Failure injection (fail on script)
- Happy path integration
- Locator fail integration
- Multi-candidate integration
- Glob pattern outputs
- Partial empty glob outputs
- Deep scan locator
- Deep scan limit
- Multiple runs in same CWD
- Summary content validation
- Timeline completeness
- Debug bundle for locator fail

**Run:**
```bash
pytest tests/pseudo/ -v
```

### L2: Real Integration Tests (Future)

Tests that require real Innovus and dsub -I. These are not yet implemented.

---

## Current Test Status

```
Total: 37 tests
Passed: 37
Failed: 0
```

### Test Breakdown

| Layer | Module | Tests | Status |
|-------|---------|--------|--------|
| L0 | Protocol | 6 | ✅ All passing |
| L1 | Components | 10 | ✅ All passing |
| L1.5 | Integration | 21 | ✅ All passing |

---

## Running Tests

### All Tests

```bash
pytest tests/ -v
```

### Specific Test File

```bash
pytest tests/unit/test_l0_protocol.py -v
```

### Specific Test

```bash
pytest tests/unit/test_l0_protocol.py::test_protocol_schema_versions -v
```

### With Coverage

```bash
pytest tests/ --cov=skillpilot --cov-report=html
```

---

## Adding New Tests

### Adding a Unit Test

1. Create test in appropriate file:
   - Protocol tests → `tests/unit/test_l0_protocol.py`
   - Component tests → `tests/unit/test_l1_components.py`

2. Follow naming convention:
   ```python
   def test_<component>_<scenario>():
       """L<layer>: <description>"""
       # Arrange
       # Act
       # Assert
   ```

3. Add docstring explaining the test purpose and layer.

Example:
```python
def test_locator_enc_with_spaces():
    """L1: handle enc filename with spaces"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        
        enc_path = run_dir / "test design.enc"
        enc_path.write_text("# Mock enc")
        
        locator = Locator(cwd=run_dir)
        result = locator.locate("./test design.enc")
        
        assert result.is_success()
```

### Adding an Integration Test

1. Add to `tests/pseudo/test_integration.py` or create new file.

2. Use Orchestrator for full job execution:

```python
def test_new_scenario():
    """L1.5: <description>"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)
        
        # Setup: Create mock DB
        enc_path = cwd / "test.enc"
        enc_dat_path = cwd / "test.enc.dat"
        enc_path.write_text("# Mock enc")
        enc_dat_path.write_text("")
        
        skill_root = Path(__file__).parent.parent.parent / "subskills"
        
        # Act: Run job
        orchestrator = Orchestrator(cwd=cwd, skill_root=skill_root)
        result = orchestrator.run_job(
            design_query="./test.enc",
            skill_name="summary_health_mock",
        )
        
        # Assert
        assert result.status == "PASS"
```

---

## Test Fixtures

### Design DB Fixtures

```python
# Single DB
enc_path = run_dir / "test.enc"
enc_dat_path = run_dir / "test.enc.dat"
enc_path.write_text("# Mock enc")
enc_dat_path.write_text("")

# Multiple DBs for multi-candidate
(run_dir / "block1" / "AAA.enc").parent.mkdir(parents=True)
(run_dir / "block2" / "AAA.enc").parent.mkdir(parents=True)
```

### Report File Fixtures

```python
# Non-empty report
(reports_dir / "report.txt").write_text("content")

# Empty report
(reports_dir / "empty.txt").write_text("")

# Multiple reports for glob
for i in range(3):
    (reports_dir / f"report{i}.txt").write_text(f"content {i}")
```

---

## Failure Injection

PseudoSession supports failure injection via `session/inject.json`:

```python
# Inject fail on restore_wrapper
inject_config = {"fail_on_script": "restore_wrapper"}
(session_dir / "inject.json").write_text(json.dumps(inject_config))

# Result: RESTORE_FAIL
```

Supported injection options:
- `fail_on_script`: Script name that should fail
- `crash_after_s`: Crash session after N seconds
- `heartbeat_stop_after_s`: Stop heartbeat after N seconds
- `delay_ack_s`: Delay ack by N seconds

---

## Common Test Patterns

### Verifying Protocol Compliance

```python
# Verify schema_version
assert hasattr(obj, 'schema_version')
assert obj.schema_version == "1.0"

# Verify atomic write
Manifest.write_atomic(path, data)
assert path.exists()
with open(path, "r") as f:
    loaded_data = json.load(f)
assert loaded_data == data
```

### Verifying Error Types

```python
# Verify specific error_type
assert result.status == "FAIL"
assert result.error_type == "LOCATOR_FAIL"

# Verify debug bundle exists
assert (run_dir / "debug_bundle").exists()
```

### Verifying Timeline Events

```python
# Read timeline
with open(timeline_path, "r") as f:
    events = [json.loads(line) for line in f]

# Check for specific events
event_types = [e["event"] for e in events]
assert "DONE" in event_types
assert "FAIL" not in event_types
```

---

## Test Gates

### Gate A: Protocol Gate

All L0 tests must pass:
- Schema versions present
- run_dir structure valid
- Timeline events correct
- Atomic writes work

### Gate B: Offline Capability Gate

All L1 tests must pass:
- Locator scenarios covered
- Contract validation covered
- Output validation covered
- Debug bundle generation covered

### Gate C: Integration Gate

At least these L1.5 tests must pass:
- Happy path integration
- One failure injection test
- One edge case test

---

## Continuous Integration

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run tests before commit
pytest tests/ -v --tb=short
if [ $? -ne 0 ]; then
    echo "Tests failed. Aborting commit."
    exit 1
fi
```

### GitHub Actions

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: |
          pip install pytest pyyaml
      - name: Run tests
        run: |
          pytest tests/ -v
```

---

## Debugging Tests

### Run with Verbose Output

```bash
pytest tests/ -vv --tb=long
```

### Stop on First Failure

```bash
pytest tests/ -x
```

### Run Specific Test with Debugger

```bash
pytest tests/unit/test_l0_protocol.py::test_protocol_schema_versions --pdb
```

### Print Test Names Only

```bash
pytest tests/ --collect-only
```

---

## Test Data

### Pseudo Environment Fixtures

Located in `subskills/summary_health_mock/`:
- `contract.yaml`: Test skill contract
- `templates/run.tcl`: Test skill template
- `tests/mock/`: Mock data for offline tests

### Real Environment Fixtures (Future)

When implementing L2 tests, you'll need:
- Real design DBs (minimized for testing)
- Real Innovus installation
- Valid licenses

---

## Best Practices

1. **Isolate Tests**: Each test should be independent
2. **Use Fixtures**: Reuse common setup/teardown
3. **Clear Naming**: Test names should describe what they test
4. **Assert on Evidence**: Verify run_dir artifacts, not internal state
5. **Test Both Paths**: Happy path AND failure cases
6. **Validate Contracts**: Always verify contract requirements
7. **Check Debug Bundles**: FAIL tests should verify debug_bundle content

---

## Future Test Plans

### L2: Real Integration Tests

- [ ] Real Innovus session startup
- [ ] Real queue_processor behavior
- [ ] Real TCL script execution
- [ ] Real dsub queue submission
- [ ] Resource cleanup validation

### Performance Tests

- [ ] Concurrent job execution (max_parallel=2/4/8)
- [ ] Large DB handling
- [ ] Long-running skills
- [ ] Memory usage monitoring

### Regression Tests

- [ ] Version compatibility tests
- [ ] Historical run_dir parsing
- [ ] Schema upgrade paths
