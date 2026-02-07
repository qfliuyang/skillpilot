# SkillPilot File Control Plane Protocol

This document describes the file-based API protocol used between Master and Runner.

## Overview

SkillPilot uses a **file control plane** protocol (Disk-as-API) where:
- Master writes command requests to `queue/`
- Runner reads commands, executes them, and writes results to `result/`
- Control signals (cancel, stop) are written to `ctl/`
- State tracking happens via `state/`
- All logs go to `log/`

**Key Principle**: All file writes must be atomic using `tmp + rename` pattern.

## Session Directory Structure

```
session_dir/
├── queue/              # Command requests from Master
│   ├── cmd_1_<uuid>.json
│   ├── cmd_2_<uuid>.json
│   └── ...
├── result/             # Command results from Runner
│   ├── cmd_1_<uuid>.json
│   ├── cmd_2_<uuid>.json
│   └── ...
├── output/             # Command output (stdout/stderr)
│   ├── cmd_1_<uuid>.out
│   ├── cmd_2_<uuid>.out
│   └── ...
├── log/               # Session and command logs
│   ├── session.out        # Full session output (append-only)
│   ├── meta.log         # Structured event log (optional)
│   └── last_n_lines.txt  # Recent output (optional)
├── ctl/               # Control signals
│   ├── cancel.json        # Cancel request
│   └── stop.json         # Stop request
├── state/             # Runner state and heartbeat
│   ├── state.json        # Current runner phase, PIDs
│   ├── heartbeat.json    # Liveness indicator
│   └── lease.json        # Lease expiration (optional)
└── inflight/          # Commands being executed (idempotency)
    └── cmd_<seq>_<uuid>.json
```

## File Formats

### 1. Command Request (`queue/cmd_<seq>_<cmd_id>.json`)

Written by: Master
Read by: Runner

```json
{
  "cmd_id": "550e8400-e29b-41d4-a716-446655440000",
  "seq": 1,
  "kind": "tcl",
  "payload": "puts 'Hello World'\n",
  "timeout_s": 60,
  "cancel_policy": "ctrl_c",
  "marker": {
    "prefix": "__SP_DONE__",
    "token": "550e8400-e29b-41d4-a716-446655440000",
    "mode": "runner_inject"
  }
}
```

**Fields**:
- `cmd_id` (string, required): Unique command ID (UUID recommended)
- `seq` (int, required): Sequence number for ordering
- `kind` (string, required): Command kind (v1 only supports `"tcl"`)
- `payload` (string, required): Tcl code to execute
- `timeout_s` (int, optional): Timeout in seconds (default: from playbook)
- `cancel_policy` (string, required): How to handle cancellation
  - `"ctrl_c"`: Send Ctrl-C (default, v1 minimum)
  - `"terminate_tool"`: Terminate tool process
  - `"terminate_session"`: Terminate entire session
- `marker` (object, required): Completion detection
  - `prefix` (string): Marker prefix (default: `"__SP_DONE__"`)
  - `token` (string): Unique token (default: cmd_id)
  - `mode` (string): Marker mode
    - `"runner_inject"`: Runner appends marker (v1 default)
    - `"payload_contains"`: Author includes marker in payload

### 2. Command Result (`result/cmd_<seq>_<cmd_id>.json`)

Written by: Runner
Read by: Master

```json
{
  "cmd_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ok",
  "start_ts": "1707221123456",
  "end_ts": "1707221187654",
  "exit_reason": "marker_seen",
  "output_path": "session_dir/output/cmd_1_550e8400.out",
  "tail_path": "session_dir/log/last_n_lines.txt",
  "stats": {
    "bytes": 1024,
    "lines": 42,
    "duration_ms": 63298
  }
}
```

**Fields**:
- `cmd_id` (string, required): Matches command request
- `status` (string, required): Execution status
  - `"ok"`: Command completed successfully
  - `"error"`: Command failed
  - `"timeout"`: Command timed out
  - `"cancelled"`: Command was cancelled
- `start_ts` (string, required): Start timestamp (ISO8601 or epoch_ms)
- `end_ts` (string, required): End timestamp (same format as start_ts)
- `exit_reason` (string, required): Why command ended
  - `"marker_seen"`: Marker detected in output
  - `"tool_exit"`: Tool process exited
  - `"ctrl_c"`: Ctrl-C was sent
  - `"lease_expired"`: Lease timed out
  - `"tool_died"`: Tool crashed (OSError)
- `output_path` (string, optional): Path to output file
- `tail_path` (string, optional): Path to recent output
- `stats` (object, optional): Execution statistics
  - `bytes`: Output size in bytes
  - `lines`: Number of output lines
  - `duration_ms`: Execution time

### 3. Session State (`state/state.json`)

Written by: Runner
Read by: Master (optional, for debugging)

```json
{
  "phase": "idle",
  "session_id": "session_20240206_143025_a1b2c3d4",
  "runner_pid": 12345,
  "tool_pid": 12346,
  "current_cmd_id": null,
  "updated_at": "1707221123456"
}
```

**Fields**:
- `phase` (string, required): Current runner phase
  - `"starting"`: Initializing session
  - `"idle"`: Waiting for commands
  - `"busy"`: Executing a command
  - `"error"`: Error state
  - `"stopping"`: Cleaning up and exiting
- `session_id` (string, required): Unique session identifier
- `runner_pid` (int, required): Runner process ID
- `tool_pid` (int, optional): EDA tool process ID
- `current_cmd_id` (string/null): Currently executing command (or null)
- `updated_at` (string, required): Last update timestamp

### 4. Heartbeat (`state/heartbeat.json`)

Written by: Runner (periodically)
Read by: Master (optional, for liveness check)

```json
{
  "timestamp": "1707221123456"
}
```

**Fields**:
- `timestamp` (string, required): Current timestamp

### 5. Lease (`state/lease.json`)

Written by: Master (to keep Runner alive)
Read by: Runner (enforces expiration)

```json
{
  "lease_id": "lease_12345",
  "expires_at": "1707221123456",
  "owner": "master_process"
}
```

**Fields**:
- `lease_id` (string, required): Unique lease identifier
- `expires_at` (string, required): Expiration timestamp
- `owner` (string, optional): Master identifier

**Behavior**:
- Runner checks lease periodically
- When lease expires, Runner enters `stopping` phase
- Master can extend lease by updating `expires_at`

### 6. Cancel Request (`ctl/cancel.json`)

Written by: Master
Read by: Runner

```json
{
  "scope": "current",
  "cmd_id": null,
  "ts": "1707221123456"
}
```

**Fields**:
- `scope` (string, required): Cancellation scope
  - `"current"`: Cancel currently executing command
  - `"cmd_id"`: Cancel specific command
- `cmd_id` (string/null): Command ID (required if scope="cmd_id")
- `ts` (string, required): Request timestamp

**Behavior**:
- Runner checks cancel file periodically
- On detection, executes cancel_policy from command request
- After handling, cancel file should be removed

### 7. Stop Request (`ctl/stop.json`)

Written by: Master
Read by: Runner

```json
{
  "mode": "graceful",
  "ts": "1707221123456"
}
```

**Fields**:
- `mode` (string, required): Stop mode
  - `"graceful"`: Wait for current command to finish
  - `"force"`: Terminate immediately
- `ts` (string, required): Request timestamp

**Behavior**:
- Runner checks stop file periodically
- `graceful`: Let current command complete, then stop
- `force`: Terminate tool/session immediately
- On detection, Runner enters `stopping` phase

## Execution Flow

### Normal Execution

```
Master                          Runner
  |                               |
  |-- write cmd_1.json --------> |
  |                               |-- Read cmd_1.json
  |                               |-- Execute payload via PTY
  |                               |-- Detect marker
  |                               |
  |  <-- cmd_1_result.json ------|-- Write result
  |                               |
  |-- write cmd_2.json --------> |
  |                               |-- Read cmd_2.json
  |                               |-- Execute payload
  |                               |-- Detect marker
  |                               |
  |  <-- cmd_2_result.json ------|-- Write result
  |                               |
  ...                             ...
```

### Cancel Flow

```
Master                          Runner
  |                               |
  |-- write cmd.json ----------> | (busy)
  |                               |-- Executing...
  |                               |
  |-- write cancel.json ------> |-- Detect cancel
  |                               |-- Execute cancel_policy
  |                               |-- Write result (cancelled)
  |                               |
  |  <-- result.json ------------|-- Master sees cancelled
```

### Stop Flow

```
Master                          Runner
  |                               |
  |-- write stop.json ---------> |-- Detect stop
  |                               |-- Handle per mode
  |                               |  - graceful: Wait for cmd
  |                               |  - force: Terminate now
  |                               |-- Enter stopping
  |                               |-- Cleanup
  |                               |-- Write state (stopping)
```

## Marker Detection

Runner uses marker to determine when a command completes. This is critical because EDA tools:
- Have unpredictable output
- May pause or prompt
- Can't reliably detect completion via prompt/exit code

### Marker Format

Default marker format: `__SP_DONE__ <token>`

Example in tool output:
```
Timing analysis complete
__SP_DONE__ 550e8400-e29b-41d4-a716-446655440000
```

### Chunked Output

Output may be read in chunks. Runner handles this:

```python
buffer = b""
while not done:
    chunk = read_from_pty(4096)
    buffer += chunk

    # Check for marker (may span chunks)
    if marker_pattern in buffer:
        done = True
        break

    # Keep buffer bounded
    if len(buffer) > 8192:
        buffer = buffer[-8192:]
```

## Idempotency

Runner must not re-execute completed commands:

### 1. Result File Check

Before executing a command, Runner checks if `result/cmd_<seq>_<cmd_id>.json` exists:
- If exists: Skip execution (already done)
- If not exists: Execute normally

### 2. Inflight Directory (v1)

To prevent double-execution when multiple Runners are running:

```
Before execution:
  - Move queue/cmd_*.json → inflight/cmd_*.json

After execution:
  - Remove inflight/cmd_*.json
```

This ensures only one Runner processes a command.

## Atomic File Writes

All writes must use `tmp + rename` pattern:

```python
def write_atomic(filepath, data):
    tmp_path = f"{filepath}.tmp.{os.getpid()}"
    with open(tmp_path, "w") as f:
        f.write(data)
    os.rename(tmp_path, filepath)  # Atomic on same filesystem
```

**Why?**:
- Prevents partial writes from being read
- Ensures readers see complete file or old version
- Avoids race conditions

## Error Handling

### Tool Death

If tool dies unexpectedly:
```
OSError during PTY read → Write result with status="error"
                               exit_reason="tool_died: <error>"
```

### Lease Expiration

When lease expires:
```
Check lease.is_expired() → Write result (if cmd running) with status="cancelled"
                              exit_reason="lease_expired"
                              → Enter stopping phase
```

### Cancel Handling

Per `cancel_policy`:
- `ctrl_c`: Send `\x03` to PTY
- `terminate_tool`: `SIGTERM` to tool process
- `terminate_session`: `SIGKILL` to entire session group

## Security Considerations

### Path Restrictions

- All paths must be within `session_dir`
- No `../` or absolute paths outside session
- Prevents directory traversal attacks

### Permissions

- `session_dir` should have proper permissions (700 or 750)
- Control files should be writable by Master

## Compatibility Notes

### v1 Constraints

- Only supports `"tcl"` commands
- Marker mode defaults to `"runner_inject"`
- Cancel policy minimum: `"ctrl_c"`
- Single session mode (shared session)

### Future Extensions

Potential v2 features:
- Additional command kinds (Python, shell, etc.)
- Per-skill session mode
- Multi-tool sessions
- Streaming output API (in addition to file-based)

## Testing

Test protocol compliance using integration tests:

```bash
python -m skillpilot.tests.integration_tests
```

This verifies:
1. E2E execution flow
2. Marker detection across chunks
3. Timeout handling
4. Cancel behavior
5. Lease expiration
6. Recovery and idempotency
7. Audit logging
