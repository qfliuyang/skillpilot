# SkillPilot Architecture

This document describes the architecture and design of SkillPilot v1.

## Overview

SkillPilot is an orchestration system for EDA (Electronic Design Automation) tools. It separates concerns into two layers:

1. **Content/Orchestration Layer (PSP)**: Playbook, Skill, Poke definitions
2. **Execution/Governance Layer (Runner)**: PTY-based tool execution with file-based control

### Why This Architecture?

EDA tools (PrimeTime, Innovus, Tempus, etc.) present unique challenges:

| Challenge | Traditional Approach | SkillPilot Approach |
|-----------|-------------------|---------------------|
| Interactive REPL | Direct SSH/Telnet to tool | Runner handles PTY, no direct access |
| Streaming output | Try to parse prompts | Marker-based completion detection |
| Environment complexity | Manual setup per node | File-based control, portable |
| Audit requirements | Manual logging | Automatic logging to files |
| Timeout/Cancel | Manual intervention | Built-in governance |

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                   User / Agent                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  AI Code CLI (Entry Point)                            │
│  - skillpilot run --playbook X                      │
│  - skillpilot runner start --session Y                  │
│  - skillpilot runner tail --session Y                   │
│  - skillpilot runner cancel --session Y --cmd-id Z          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Master (Orchestrator)                                  │
│  ├── PSP Loader (playbook/skill parsing)                │
│  ├── Compiler (steps → commands)                           │
│  ├── Executor (write queue, wait results)                 │
│  └── Summarizer (aggregate results)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │   File Control Plane      │
         │  (Disk-as-API)          │
         ▼                          │
    ┌────────────────────┐              │
    │  Queue/Result/    │              │
    │  CTL/STATE/      │◄───────────┤
    │  LOG/            │              │
    └────────────────────┘              │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Runner (Executor)                                     │
│  ├── PTY Manager (tool process control)                   │
│  ├── Command Processor (read queue, execute)               │
│  ├── Marker Detector (output parsing)                       │
│  ├── Governance (timeout/cancel/stop/lease)               │
│  └── Audit Logger (write session/out, cmd/out)          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Tool Adapter (EDA Tool Interface)                      │
│  - PTY Setup                                        │
│  - Read/Write (stdin/stdout)                          │
│  - Signal Handling (SIGTERM/SIGKILL)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  EDA Tool (PrimeTime/Innovus/Tempus/etc.)            │
│  - Tcl REPL                                          │
│  - Poke Procedures                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. AI Code CLI

**Purpose**: User/agent interface

**Responsibilities**:
- Parse command-line arguments
- Dispatch to Master or Runner
- Provide help and error messages

**Commands**:
```
skillpilot run --playbook X --inputs Y          # Execute playbook
skillpilot runner start --session Y               # Start runner
skillpilot runner tail --session Y                 # View output
skillpilot runner cancel --session Y --cmd-id Z     # Cancel command
skillpilot runner stop --session Y                  # Stop session
```

### 2. Master

**Purpose**: Orchestrate playbook execution

**Responsibilities**:
1. Load PSP definitions (Playbook, Skill)
2. Compile Skill steps to Runner commands
3. Start Runner sessions
4. Write commands to `queue/`
5. Poll `result/` for completion
6. Aggregate results into `playbook_result.json`
7. Handle stop/cancel signals

**Key Design Decisions**:

| Decision | Rationale |
|-----------|------------|
| Separate compilation from execution | Master can start Runner, then batch-write commands |
| Fail-fast by default | Prevents cascading errors from wasting time |
| Auto-generated session dirs | Easy debugging, no manual setup |
| Wait for results synchronously | Simple coordination with Runner |

**State Machine**:
```
idle → compiling → running → (wait for results) → aggregating → done
                      ↓                    ↓
                 error               timeout → failed
```

### 3. Runner

**Purpose**: Execute EDA tool commands safely

**Responsibilities**:
1. Create session directory structure
2. Start tool via PTY
3. Poll `queue/` for commands
4. Execute commands via PTY
5. Detect marker for completion
6. Write outputs to `output/` and `log/`
7. Write results to `result/`
8. Check `ctl/` for stop/cancel
9. Check `state/lease.json` for expiration
10. Handle timeout/cancel/stop

**Key Design Decisions**:

| Decision | Rationale |
|-----------|------------|
| PTY instead of subprocess | EDA tools expect interactive terminals |
| Marker-based completion | Prompts are unreliable, output varies |
| Inflight directory | Prevents double-execution with multiple runners |
| Buffer for chunked output | Marker may span read boundaries |
| Separate phase tracking | Clear state for debugging |

**State Machine**:
```
starting → idle → busy → idle → (repeat)
            ↓        ↓
           error   stopping
```

### 4. Tool Adapter

**Purpose**: Abstract EDA tool interactions

**Responsibilities**:
- Start tool with PTY
- Write to tool stdin
- Read from tool stdout/stderr
- Send signals (SIGTERM, SIGKILL)
- Detect process death

**Design**: Interface pattern allows different EDA tools:

```python
class ToolAdapter:
    def start(self) -> int:       # Start tool, return PID
    def write(self, data: str):   # Write to stdin
    def read(self, timeout: float) -> bytes:  # Read from stdout
    def send_signal(self, signal: int):  # Send signal
    def terminate(self):              # Graceful shutdown
    def kill(self):                  # Force kill
    def is_alive(self) -> bool:     # Check running
    def close(self):                 # Cleanup
```

**Adapters**:
- `DemoToolAdapter`: Mock tool for testing
- (v2): `PrimeTimeAdapter`, `InnovusAdapter`, etc.

### 5. PSP (Playbook/Skill/Poke)

**Purpose**: Knowledge encoding layer

**Components**:

#### Playbook
- Orchestrates skills
- Defines default policies (timeout, cancel, fail_fast)
- Example: 2 skills, shared session

#### Skill
- Defines a task's steps
- Each step calls a poke procedure
- Example: 2 steps (generate report, check constraints)

#### Poke
- Tcl procedures in EDA tool
- Produce artifacts (reports, logs)
- Example: `report_timing`, `check_paths`

**Why PSP?**
- **Knowledge Sharing**: Experts write once, used by many
- **Human Readable**: Easy to understand and modify
- **AI-Executable**: Playbooks guide automated execution
- **Version Control**: Track changes in expertise

## Data Flow

### Execution Flow

```
1. CLI: Parse "skillpilot run --playbook X"
   ↓
2. Master: Load playbook.yaml
   ↓
3. Master: Load skills/*.yaml
   ↓
4. Master: Compile to commands (4 cmd)
   ↓
5. Master: Create session directory
   ↓
6. Master: Start Runner (subprocess)
   ↓
7. Master: Write cmd_1.json, cmd_2.json, ... to queue/
   ↓
8. Runner: Read cmd_1.json
   ↓
9. Runner: Execute via PTY
   ↓
10. Runner: Detect marker
    ↓
11. Runner: Write result/cmd_1.json, output/cmd_1.out
    ↓
12. Master: Read result/cmd_1.json
   ↓
13. [Repeat 8-12 for all commands]
   ↓
14. Master: Aggregate results
   ↓
15. Master: Write playbook_result.json
   ↓
16. CLI: Exit with status
```

### Error Flow

```
Runner detects error (tool died, timeout)
   ↓
Runner: Write result with status="error"
   ↓
Master: Read error result
   ↓
Master: Check fail_fast
   ↓
if fail_fast:
   Master: Write stop.json
   ↓
   Master: Stop remaining commands
   ↓
   CLI: Return failure
```

### Cancel Flow

```
User requests cancel
   ↓
CLI: Write ctl/cancel.json
   ↓
Runner: Detect cancel.json
   ↓
Runner: Execute cancel_policy
   ├─ ctrl_c: Send \x03 to PTY
   ├─ terminate_tool: SIGTERM
   └─ terminate_session: SIGKILL
   ↓
Runner: Write result with status="cancelled"
   ↓
Master: Read cancelled result
   ↓
[Fail-fast or user cancel] → Stop or continue
```

## Concurrency Model

### v1: Single Runner per Session

```
Session_001/
├── Runner (PID 1001)  ← Only one Runner per session
└── Master (PID 1002)
    └── Commands queued
        └── Runner executes one at a time
```

**Coordination**:
- Master writes all commands to queue
- Runner processes serially
- Results written as they complete
- Master polls for results

### Future: Multiple Sessions

Potential v2:
- Per-skill sessions (in parallel)
- Session pools
- Load balancing

## Security Model

### File System Isolation

- Session dirs are separate
- No path traversal outside session_dir
- Atomic writes prevent corruption

### No Inbound Network

- v1 has no HTTP/RPC server
- All control via file system
- Safe for restricted network environments

### Process Isolation

- Runner and tool in separate process groups
- Signals can target tool specifically
- Master cannot directly kill tool

## Reliability Features

### 1. Audit Trail

Every action is logged:
- `log/session.out`: Complete output stream
- `log/meta.log`: Structured events (optional)
- `output/cmd_*.out`: Per-command output

### 2. Recovery

Runner restart handling:
- Existing `result/cmd_*.json`: Skip execution
- `inflight/` dir: Prevents double-run
- `state/state.json`: Preserves session state

### 3. Idempotency

Safe to re-run Master:
- Commands with results skipped
- No duplicate execution
- Same final result

### 4. Timeout Protection

- Per-command timeout: Prevents hanging
- Default from playbook: Configurable per task
- Lease expiration: Session-level safety net

### 5. Graceful Degradation

Tool failure handling:
- Status in result file
- Master can aggregate mixed success/failure
- fail_fast configurable

## Performance Considerations

### File I/O

- Atomic writes: `tmp + rename`
- Batch writes: Master writes multiple commands
- Polling: Runner checks queue every 100ms

### Memory

- Buffer bounded: 8KB for marker detection
- Streaming: Output written as received
- No large in-memory structures

### CPU

- Event-driven: Wait for PTY data, not spin loops
- Select-based: Efficient I/O multiplexing
- Minimal polling: Only when idle

## Testing Strategy

### Unit Tests

- Protocol types: JSON serialization/deserialization
- PSP parsing: YAML/JSON loading
- Command compilation: Steps to commands

### Integration Tests

7 acceptance criteria:
1. E2E flow (4 commands)
2. Marker detection (chunks)
3. Timeout
4. Cancel
5. Lease
6. Recovery
7. Audit logging

### Manual Testing

- Real EDA tool: PrimeTime/Innovus adapters
- Complex playbooks: Multi-skill, large outputs
- Edge cases: Timeout, cancel during marker

## Future Extensions (v2+)

### Additional Tools

- PrimeTime adapter
- Innovus adapter
- Tempus adapter
- Custom tool adapter framework

### Multi-Session

- Per-skill sessions (parallel execution)
- Session pools
- Dynamic allocation

### Advanced Governance

- Priority queues
- Resource limits
- Preemption

### Enhanced Logging

- Structured event logs (JSON lines)
- Metrics collection
- Log streaming (WebSocket/gRPC)

### Remote Execution

- Donau integration
- LSF/SLURM integration
- Distributed session management

## Monitoring and Debugging

### Session State

Monitor `state/state.json` to see:
```json
{
  "phase": "busy",
  "current_cmd_id": "550e8400-...",
  "updated_at": "1707221123456"
}
```

### Heartbeat

Check `state/heartbeat.json` for liveness:
```json
{
  "timestamp": "1707221123456"
}
```

If timestamp > 30s old: Runner may be hung.

### Log Tailing

```bash
# View live output
tail -f session_dir/log/session.out

# View structured events
tail -f session_dir/log/meta.log
```

### Result Inspection

```bash
# Check command status
cat session_dir/result/cmd_*.json | jq '.status'

# Find failed commands
cat session_dir/result/cmd_*.json | jq 'select(.status != "ok")'
```

## Dependencies

### Python Libraries

- `pty`: PTY management (built-in)
- `pyyaml`: YAML parsing for PSP
- `dataclasses`: Type-safe data structures (built-in)
- `typing`: Type hints (built-in)

### External Tools

- EDA tool: Provided by user (PrimeTime, Innovus, etc.)
- `tail`: System tool for log viewing
- `dsub`/`bsub`: Job submission (v2, optional)

## Code Organization

```
skillpilot/
├── __init__.py              # Package exports
├── protocol.py               # File control plane types
├── runner/
│   ├── __init__.py
│   ├── core.py            # Main runner logic
│   └── adapters.py        # Tool interfaces
├── master/
│   ├── __init__.py
│   ├── core.py            # Master orchestrator
│   └── md_loader.py       # Markdown PSP parsing
├── psp/
│   ├── __init__.py
│   └── schema.py          # PSP data structures
├── cli/
│   ├── __init__.py
│   └── main.py            # CLI entry point
├── tests/
│   ├── __init__.py
│   └── integration_tests.py # 7 acceptance tests
└── utils/
    └── __init__.py           # Helper functions

examples/
├── tools/
│   └── demo_tool.py      # Mock EDA tool
├── playbooks/
│   └── basic_verification.yaml
├── skills/
│   ├── timing_analysis.yaml
│   ├── power_analysis.yaml
│   └── long_test.yaml
├── poke/
│   └── poke.tcl            # Tcl procedures
└── inputs/
    └── test_inputs.json     # Input parameters
```

## Design Principles

### 1. Separation of Concerns

- PSP doesn't know about Runner
- Runner doesn't understand business logic
- CLI doesn't touch PTY directly

### 2. Fail-Safe

- All writes atomic
- Idempotent by default
- Graceful degradation on errors

### 3. Observable

- Everything logged
- State visible via files
- Easy debugging with standard tools

### 4. Extensible

- Adapter pattern for new tools
- PSP format for new skills
- Plugin architecture for v2 features

## Conclusion

SkillPilot v1 provides a robust, auditable, and governable way to orchestrate EDA tool workflows. The architecture separates concerns clearly, provides safety guarantees, and is ready for real-world use in complex compute environments.
