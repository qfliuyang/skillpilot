# docs/PSEUDO_ENV_DEV_GUIDE.md（非生产环境预开发与测试指南）

## 0. 目标与原则
你当前环境：**非 Linux、无 dsub、无 Innovus、无真实 design DB**。本指南的目标是让你仍然能在本地把 SkillPilot **80% 以上的 Runtime 逻辑**（协议、状态机、定位器、request/ack、验收、失败归类、debug_bundle）开发完成，并能跑通端到端的“伪闭环”。

核心原则：
1. **接口解耦**：把 `Supervisor(dsub)`、`Session(Innovus)`、`queue_processor(Innovus 内执行器)` 抽象成可替换 Adapter；生产环境用真实 adapter，本地用 pseudo adapter。
2. **证据驱动测试**：所有测试只断言 run_dir 证据（manifest/timeline/ack/summary/debug_bundle），而不是工具日志细节。
3. **先做确定性后端**：先把协议与状态机跑通，再接真实工具；避免把“工具不存在”当成架构阻塞点。

---

## 1. 推荐代码结构（为 pseudo 环境做准备）
建议在 Runtime 中显式引入 adapter 层（名字可不同，但职责必须一致）：

- `adapters/`
  - `supervisor_base.py`（接口）
  - `supervisor_pseudo.py`（本地伪实现）
  - `supervisor_dsub_i.py`（生产实现：dsub -I）
- `adapters/innovus_exec_base.py`（可选：若你将 queue_processor 也抽象）
- `protocol/`（manifest/timeline/request/ack/summary/debug_bundle）
- `orchestrator/`（状态机）
- `locator/`
- `contracts/`
- `kernel/`（run_dir 初始化、脚本渲染、投递 request、等待 ack、验收、汇总）

关键点：**Orchestrator/Kernel 不直接调用 dsub 或 Innovus 命令**，只调用 `SupervisorAdapter` 接口。

---

## 2. 生产依赖在架构中的位置（你要替换的点）
生产环境依赖主要集中在两处：

1) **Supervisor：如何启动 Innovus Session**
- 生产：`dsub -I -- innovus -no_gui -init bootstrap.tcl`
- 本地：启动一个 pseudo “session 进程”（实际上是一个 Python/Node 子进程或线程），它负责：
  - 写 `session/ready`
  - 更新 `session/heartbeat`
  - 轮询 `queue/` 并写 `ack/`

2) **queue_processor：在 Innovus 内执行 TCL**
- 生产：Innovus TCL 循环 + source 脚本
- 本地：pseudo queue_processor 解释 request 并模拟执行结果：
  - 对 `scripts/restore_wrapper.tcl`：模拟 restore 成功或失败
  - 对 subskill 脚本：按配置生成 reports 文件（用于 validate_outputs）

因此，本地只需实现一个“**文件队列执行器**”，无需真正解析 TCL——只要保证 request/ack/heartbeat/日志落盘行为与协议一致。

---

## 3. Pseudo 环境总体方案（你在本地跑的是“可替换闭环”）
### 3.1 伪组件清单
你需要实现这些 pseudo 组件：

- **PseudoSupervisor**
  - 模拟 dsub -I 行为：启动/停止 session、产生日志、维护 state.json
- **PseudoSession（进程/线程）**
  - 承担“工具会话”角色：ready/heartbeat
- **PseudoQueueProcessor**
  - 轮询 queue，读取 request，执行“伪动作”，写 ack
  - 生成必要的 reports 以通过 contract 验收
- **PseudoDesignDB（fixtures）**
  - 用文件夹/文本文件模拟 `AAA.enc` 与 `AAA.enc.dat` 的存在性与定位
  - 通过 enc 内容或旁路配置控制“restore 成功/失败”

### 3.2 你将获得的能力覆盖
通过 pseudo 环境，你可以本地完成：
- run_dir 初始化与协议写入（manifest/timeline）
- locator（explicit_path/cwd_scan、多候选）
- request 原子写、ack 等待、超时 QUEUE_TIMEOUT
- restore_wrapper 生成与 restore 流程验证（RESTORE_FAIL）
- subskill contract 校验（CONTRACT_INVALID）
- validate_outputs（OUTPUT_MISSING/OUTPUT_EMPTY）
- summary.json/md 生成
- debug_bundle 生成与材料指针校验
- heartbeat lost / session crash 注入（HEARTBEAT_LOST / INNOVUS_CRASH）

---

## 4. Adapter 接口设计（最关键：解耦点）
### 4.1 SupervisorAdapter（建议最小接口）
建议定义以下接口（伪代码语义）：

- `start(run_dir: Path, env: dict) -> SessionHandle`
  - 启动 session，返回 handle（包含 pid/进程对象/通信信息）
- `wait_ready(handle, timeout_s) -> None | raise SessionStartError`
- `stop(handle, reason) -> None`
- `poll_health(handle) -> HealthStatus`
  - 读取 `session/heartbeat` 与进程状态，返回健康/失活/崩溃
- `collect_logs(handle) -> None`
  - 确保 session/ 下日志齐全（pseudo 环境可简化）

生产与本地唯一差别：实现不同，Orchestrator 不应感知差别。

---

## 5. PseudoSupervisor / PseudoSession 设计（可直接开工）
### 5.1 PseudoSession 运行模式
推荐用 **子进程**（Python `subprocess`）实现，跨平台更接近真实“会话进程”语义：

- `pseudo_session.py --run-dir <path> --mode <profile>`
- 进程启动后：
  1. 写 `session/ready`
  2. 周期 touch `session/heartbeat`
  3. 循环扫描 `queue/*.json`，对每个 request 生成 ack
  4. 将执行过程写入 `session/innovus.stdout.log`（伪日志）
  5. 响应停止信号或检测到 `session/stop` 文件

### 5.2 ack 生成逻辑（必须遵守协议）
- request 合法性校验：action/script 路径安全规则（你可以在 pseudo 中实现同样的 realpath 校验）
- 执行结果：
  - 默认 PASS
  - 可按“脚本名/配置文件”触发 FAIL（用于失败注入）
- ack 字段必须完整：status/error_type/message/时间戳

### 5.3 心跳与崩溃注入
为了覆盖 HEARTBEAT_LOST / INNOVUS_CRASH：
- **HEARTBEAT_LOST**：让 pseudo_session 停止更新 heartbeat 但不退出（模拟卡死）
- **INNOVUS_CRASH**：让 pseudo_session 直接退出（非 0 code 或异常退出）

实现方式（任选其一）：
- 读取 `run_dir/session/inject.json`，里面声明：
  - `crash_after_s`
  - `heartbeat_stop_after_s`
  - `fail_on_request_id`
  - `fail_on_script`
  - `delay_ack_s`（用于触发 QUEUE_TIMEOUT）

---

## 6. Pseudo “Innovus 执行语义”（不解析 TCL，只模拟契约）
你不需要解析 TCL，你只需要模拟“执行某脚本产生某些 outputs”。

### 6.1 restore_wrapper 的模拟策略
约定：
- 若 request.script == `scripts/restore_wrapper.tcl`：
  - 检查 manifest 里 enc_path 是否存在
  - 检查 enc_dat_path 是否存在
  - 读取 enc 文件内容，若包含关键字 `RESTORE_FAIL` 则 FAIL（用于注入）
  - 否则 PASS

这样你就能覆盖：
- 正常 restore
- enc 缺失 / enc.dat 缺失（应在 locator 阶段失败，但也可在这里模拟防御）
- restore 失败归类 RESTORE_FAIL

### 6.2 subskill run 的模拟策略
约定：
- 对任意 `scripts/<subskill>.tcl` 或统一 `scripts/run_skill.tcl`：
  - 根据 `run_dir/scripts/` 中脚本名或 `run_dir/job_manifest.json` 的 skill.name
  - 在 `reports/` 目录创建 contract 要求的文件
  - 可按 inject.json 控制：
    - 不生成某个 required 输出（触发 OUTPUT_MISSING）
    - 生成空文件（触发 OUTPUT_EMPTY）
    - 延迟 ack（触发 QUEUE_TIMEOUT）
    - 直接 ack FAIL（CMD_FAIL）

这样 validate_outputs 与 debug_bundle 都能在本地被充分覆盖。

---

## 7. PseudoDesignDB（fixtures）设计：模拟 enc 与 enc.dat
在本地测试目录构造：

```
designs/
  A/
    A.enc
    A.enc.dat/            # 可以是空目录
  B/
    B.enc                 # 内容写 RESTORE_FAIL 触发 restore fail
    B.enc.dat/
  C/
    C.enc                 # 有 enc，但缺 C.enc.dat 触发 LOCATOR_FAIL
```

enc 内容无需真实，只用作“注入开关”，例如：
- `# RESTORE_FAIL`
- `# RESTORE_SLOW 120`（配合 pseudo_session 读取）

---

## 8. 本地端到端“伪闭环”跑法（你应该能在 Claude Code 里反复跑）
### 8.1 运行模式选择
建议 runtime 支持一个开关：
- `SP_ADAPTER=pseudo`（本地）
- `SP_ADAPTER=dsub-i`（生产）

以及一个 profile：
- `SP_PSEUDO_PROFILE=happy|restore_fail|output_missing|heartbeat_lost|crash|queue_timeout`

### 8.2 Happy Path（必须首先跑通）
目标：得到 PASS 的 run_dir，且 contract required outputs 全部生成。
断言：
- manifest.status=PASS, error_type=OK
- summary.json/md 存在
- reports required 非空
- timeline 有 DONE

### 8.3 失败注入（每个都要能稳定复现）
- restore_fail：最终 RESTORE_FAIL + debug_bundle
- output_missing：OUTPUT_MISSING + debug_bundle（含 reports_inventory + contract）
- output_empty：OUTPUT_EMPTY
- queue_timeout：QUEUE_TIMEOUT
- heartbeat_lost：HEARTBEAT_LOST
- crash：INNOVUS_CRASH
- contract_invalid：CONTRACT_INVALID（无需 session）

---

## 9. 单元测试与集成测试划分（在无工具环境下也能做到很像 CI）
### 9.1 L0：协议静态测试（不需要 pseudo session）
- run_dir 初始化结构
- manifest/timeline/summary schema_version 存在
- contract 校验

### 9.2 L1：Mock 组件测试（不需要 pseudo session）
- locator 多候选/缺 dat
- validate_outputs missing/empty
- debug_bundle 生成

### 9.3 L1.5：Pseudo 集成测试（需要 pseudo session，但不需要 Innovus）
这是你本地最重要的“集成层”：
- orchestrator + kernel + pseudo supervisor + pseudo queue_processor 全链路
- 覆盖 request/ack/heartbeat/超时/崩溃

> 等你接入真实 dsub/Innovus 后，再把 L2 真实集成测试加上。

---

## 10. 关键实现细节（跨平台注意点）
### 10.1 路径与原子写
- Windows/macOS rename 语义与 Linux 略不同，但“临时文件同目录 + rename”仍是最可靠方案。
- 统一使用 `pathlib`/标准库路径 API，避免手写路径拼接。
- realpath 校验要注意符号链接处理（macOS 同样适用）。

### 10.2 文件锁（可选）
如果 timeline 追加写可能被并发写入：
- 本地可先采用单线程写 timeline（推荐）
- 或使用跨平台锁库（Python 可用 portalocker 等；但若你不想引入依赖，先单线程）

### 10.3 子进程管理
- PseudoSession 用子进程可模拟真实“会话崩溃/退出码/卡死”
- stop 机制建议用 `session/stop` 文件或发送 SIGTERM（Windows 兼容性更复杂，文件方式更稳）

---

## 11. 最小可实现清单（MVP 开发顺序）
建议按以下顺序开发，每步都有可验证产物：

1) **protocol 层**：manifest/timeline/request/ack/summary/debug_bundle 的读写 + 原子写工具  
2) **run_dir 初始化**：固定结构生成  
3) **locator**：explicit_path/cwd_scan + 多候选输出  
4) **contract + validate_outputs**：missing/empty 覆盖  
5) **orchestrator 状态机**：能在 locator fail 时生成 debug_bundle  
6) **pseudo supervisor + pseudo session**：能写 ready/heartbeat、能处理 queue→ack  
7) **restore_wrapper 生成 + request/ack 闭环**：RESTORE_DB 状态可 PASS/FAIL  
8) **subskill 执行模拟**：生成 reports，跑通 PASS  
9) **失败注入覆盖**：queue_timeout/heartbeat_lost/crash/output_missing/output_empty  
10) **pseudo 集成测试套件**：把上述场景固化成可回归用例

---

## 12. 你接入生产环境时要改什么（迁移最小化）
当未来有 Linux + dsub + Innovus：
- 保持 Orchestrator/Kernel/Protocol/Contract/Locator **不变**
- 只新增/完善：
  - `SupervisorDsubI`（生产 adapter）
  - 真实 `bootstrap.tcl` 与 `queue_processor.tcl`
  - 真实 subskill templates（TCL）
- 将同一套测试分层扩展：
  - 现有 L0/L1/L1.5 继续跑
  - 新增 L2（真实集成）用例

这就是“预开发最大化复用”的关键收益：**把不可得的生产依赖变成可替换 adapter**。

---

## 13. 附：PseudoSession 的最小行为规范（建议你实现时照着做）
PseudoSession 启动后必须在 run_dir/session 下生成/维护：
- `ready`（启动成功标志）
- `heartbeat`（周期更新）
- `innovus.stdout.log`（伪日志，可写处理 request 的摘要）
- `state.json`（pid/start_time/exit_code/last_heartbeat_ts）

处理 request 时：
- 读取 `queue/<request_id>.json`
- 校验 script 路径安全
- 执行“伪动作”（见第 6 节）
- 写 `ack/<request_id>.json`（原子写）
- 可选：将已处理 request 移动到 `queue/processed/` 或仅依赖 ack 存在跳过

---

## 14. 你需要我补齐的内容（可选，但会显著加速你开工）
如果你告诉我你准备使用的实现语言（Python/Node/Go/Rust）与项目骨架（比如你打算用哪种测试框架），我可以进一步给出：
- `SupervisorAdapter` 的接口定义代码模板
- `pseudo_session` 的可运行最小实现
- 一套可直接跑的 pseudo 集成测试用例（happy + 6 个失败注入）
- 一个最小 subskill（例如 `summary_health_mock`）的 contract+模板+fixtures

这样你在 Claude Code 里可以直接复制成第一版可运行工程。
