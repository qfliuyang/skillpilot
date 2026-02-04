# docs/DEVELOPMENT_SPEC.md

## 总览（开发规范的目标与使用方式）
本规范用于指导 SkillPilot Runtime、Innovus 内执行器（queue_processor）、以及 Subskill（Skill 资产）的**工程化实现**。其核心目标是把“意图驱动运行”落地为长期可运维的系统：**确定性、证据化、可验收、可诊断、可回归**。

阅读与落地顺序建议：
1. 先读 `docs/PROTOCOLS.md`（协议 SSOT）
2. 再读 `docs/ARCHITECTURE.md`（组件边界与状态机）
3. 本文解决“怎么写代码、怎么组织模块、怎么保证稳定性与可诊断性”
4. 最后对照 `docs/TEST_SPEC.md` 通过 Gate

> 术语与协议字段以 `docs/PROTOCOLS.md` 为准；本文不重复定义协议，只强调“必须如何实现”。

---

## 1. 总体开发原则（必须贯彻的工程约束）

### 1.1 确定性优先（MUST）
- Runtime 的行为必须由**明确参数 + 固定规则**决定，不依赖模型推断。
- 任意 job 只要输入相同（design + skill + 版本 + 环境），应生成**可对比**的证据结构（允许报告内容因工具本身差异变化，但协议结构与验收口径必须一致）。

### 1.2 证据优先（MUST）
- 所有关键动作都要写入 timeline（STATE_ENTER/EXIT + ACTION）。
- 所有工具内执行必须有 request/ack。
- PASS/FAIL 的判断必须来自协议与验收（contract），不是“脚本没报错”。

### 1.3 最小权限与可审计（MUST）
- Innovus 仅允许 source `run_dir/scripts/`（白名单 + realpath 校验）。
- restore 的外部 source 仅能发生在 restore_wrapper 内，且必须审计记录。

### 1.4 可诊断性（MUST）
- 失败必须稳定归类到 taxonomy（error_type）。
- FAIL 必须生成 debug_bundle，且能离线复盘（无需现场重跑）。

---

## 2. 推荐工程目录与模块划分（便于长期维护）

> 仅为推荐结构，不强制目录名，但**强制职责边界**。

### 2.1 Runtime 模块建议
- `orchestrator/`
  - 状态机驱动、并发控制、统一异常映射与终态收敛
- `protocol/`
  - manifest/timeline/request/ack/summary/debug_bundle 的读写与 schema 校验
- `locator/`
  - enc/dat 定位逻辑（纯确定性、可单测）
- `supervisor/`
  - dsub -I 启动、ready 判定、日志与 state.json、heartbeat 监控
- `kernel/`
  - run_dir 初始化、脚本渲染、request 提交、ack 等待、validate_outputs、summary 生成
- `contracts/`
  - contract 解析、合法性校验、outputs.required 验收实现
- `skills/` 或 `subskills/`
  - 能力资产仓库（contract + templates + docs + tests）

### 2.2 “可测试边界”要求（MUST）
- locator/contract/validate_outputs/debug_bundle 必须可在**无 Innovus 环境**下单测。
- supervisor 与 queue_processor 的集成测试需要 Innovus，但应尽量把不确定性封装在 supervisor 内。

---

## 3. Orchestrator（状态机与作业生命周期）

### 3.1 单 Job 的执行骨架（MUST）
Orchestrator 必须按以下顺序驱动状态（状态名可实现为枚举，但 timeline 必须可追踪）：
1. `PREPARE_RUNDIR`
2. `LOCATE_DB`
3. `START_SESSION`
4. `RESTORE_DB`
5. `RUN_SKILL`
6. `VALIDATE_OUTPUTS`
7. `SUMMARIZE`
8. `DONE` 或 `FAIL`

要求：
- 每个状态进入/退出必须写 timeline（STATE_ENTER/STATE_EXIT）。
- 每个外部动作必须写 ACTION（例如 locate_db、start_session、submit_request、receive_ack、validate_outputs、summarize）。
- 任意异常必须统一捕获，归类 error_type，进入 FAIL 收敛逻辑（见 3.4）。

### 3.2 并发模型（SHOULD）
- 支持多 design 并行（A/B/C/D）：
  - 并发由 Orchestrator 控制 `max_parallel`
  - 每个 job 独立 run_dir + 独立 session
- timeline 必须能单 job 复盘，不允许跨 job 混写。

### 3.3 多候选 DB 的交互停顿（MUST）
当 locator 返回 candidates>1：
- Orchestrator 不应 FAIL
- 应将候选写入 manifest.design.locator.candidates
- 抛出/返回一个“需要用户选择”的可恢复结果（由前端选择后调用 resume 继续）
- 选择后写 selection_reason=`user_selected`

### 3.4 终态收敛（MUST）
- PASS：
  - manifest.status=PASS
  - manifest.error_type=OK
  - timeline 写 `DONE`
- FAIL（任意阶段）：
  - manifest.status=FAIL
  - manifest.error_type=<taxonomy>
  - timeline 写 `FAIL`（level=ERROR）
  - 触发 debug_bundle 生成（即使 locator 失败也要生成）

---

## 4. Protocol I/O（协议文件读写与原子性）

### 4.1 原子写规则（MUST）
对以下文件必须原子写（临时文件 + rename）：
- `job_manifest.json`
- `summary.json`
- `queue/<request_id>.json`
- `ack/<request_id>.json`
- `debug_bundle/index.json`（及其它关键 json）

推荐流程：
1. 写入 `.<name>.tmp.<pid>.<rand>`
2. flush + fsync（可用则做）
3. rename 到目标文件名

### 4.2 timeline 追加写（MUST）
- `job_timeline.jsonl` 只能追加写
- 每行必须是完整 JSON
- 允许实现：
  - 单线程写入（推荐）
  - 或文件锁（flock）保证行级原子

### 4.3 Schema 校验（SHOULD）
- Runtime 启动时可对 contract、request、ack、manifest、summary 做 schema_version 与必填字段校验
- 校验失败归类为 `INTERNAL_ERROR` 或 `CONTRACT_INVALID`（按对象类型）

---

## 5. Locator 实现规范（enc/dat 定位）

### 5.1 输入判定（MUST）
- 若 query 含路径分隔符或以 `.enc` 结尾：视为显式路径（explicit_path）
- 否则：视为名称扫描（cwd_scan）

### 5.2 扫描策略（MUST 可配置）
- 默认扫描根为 CWD
- 默认最大深度 `scan_depth=3`（可配置）
- 仅匹配文件名：`<name>.enc`
- 每个 candidate 记录：path、mtime、size

### 5.3 enc.dat 规则（MUST）
- enc.dat 的判定：`<enc_path>.dat`（即 `AAA.enc.dat`）
- 若 enc 存在但 enc.dat 缺失：返回 `LOCATOR_FAIL`

### 5.4 多候选行为（MUST）
- 返回 candidates 列表，不自动选择
- manifest 必须落 candidates
- 由前端交互选择后继续

---

## 6. Supervisor（dsub -I + Innovus Session 生命周期）

### 6.1 启动命令约束（SHOULD）
建议 Innovus 以 no_gui + init script 启动：
- `innovus -no_gui -init <run_dir>/scripts/bootstrap.tcl`

并由 supervisor 通过 `dsub -I` 启动（具体参数按企业环境封装）。

### 6.2 ready 判定（MUST）
必须提供确定性的 ready 判定机制，并具备超时：
- 方式 A（推荐）：queue_processor 启动后写 `session/ready`
- 方式 B：检测 heartbeat 首次更新

ready 超时：
- error_type = `SESSION_START_FAIL`

### 6.3 会话证据（MUST）
Supervisor 必须写入：
- `session/supervisor.log`：包含 dsub 命令、返回码、关键环境摘要（脱敏）
- `session/state.json`：至少包含
  - `pid`（若可获得）
  - `start_time`
  - `exit_code`（退出后）
  - `last_heartbeat_ts`（由监控更新）
- `session/innovus.stdout.log` / `session/innovus.stderr.log`（可合并但建议分离）

### 6.4 心跳监控（MUST）
- supervisor 或 orchestrator 必须周期检查 heartbeat
- 超过 `heartbeat_timeout_s` 判定 `HEARTBEAT_LOST`
- 若进程退出且非正常终止判定 `INNOVUS_CRASH`

---

## 7. Innovus 内 queue_processor（TCL 执行器）实现规范

### 7.1 必备行为（MUST）
- 启动后进入循环：
  - 更新 `session/heartbeat`
  - 扫描 `queue/*.json`
  - 对每个 request：
    - 解析字段并做安全校验（见 7.2）
    - 执行 `source <script>`
    - 捕获异常并写 ack
- 写 ack 必须原子（同目录临时文件 + rename）

### 7.2 安全校验（MUST）
- `action` 必须为 `"SOURCE_TCL"`
- `script` 必须：
  - 相对路径
  - 以 `scripts/` 开头
  - 不含 `..`
  - realpath 结果必须在 `run_dir/scripts` 下（防符号链接逃逸）

违规处理：
- ack.status=FAIL
- error_type=`CMD_FAIL`（或 `INTERNAL_ERROR`，但必须全局一致）
- message 明确指出非法脚本路径/安全违规

### 7.3 错误归类策略（MUST）
- 执行 `scripts/restore_wrapper.tcl` 失败 => `RESTORE_FAIL`
- 执行其他脚本失败 => `CMD_FAIL`

### 7.4 幂等与重复处理（SHOULD）
防止重复执行同一 request（例如轮询抖动或重启）：
- 若发现 `ack/<request_id>.json` 已存在：
  - SHOULD 跳过执行该 request
- 或实现 processed 标记（例如 `queue/processed/<request_id>`）

---

## 8. restore_wrapper.tcl（稳定性基线，必须实现）

### 8.1 生成位置（MUST）
- `run_dir/scripts/restore_wrapper.tcl`

### 8.2 固定行为（MUST）
restore_wrapper 必须执行：
1. `cd [file dirname $enc_path]`
2. `source $enc_path`

要求：
- enc_path 必须来自 runtime 注入（建议 env 或模板替换）
- 所有错误必须抛出，由 queue_processor 捕获写 FAIL ack
- wrapper 的生成与 enc_path 必须记录到 timeline/manifest（便于复盘）

---

## 9. Subskill（Skill 资产）开发规范

### 9.1 目录结构（MUST）
`subskills/<name>/`
- `contract.yaml`（MUST）
- `templates/run.tcl`（MUST）
- `SKILL.md`（MUST：解释输入前提、输出、指标口径、常见失败）
- `tests/mock/`（MUST：至少 README + fixtures 说明）

### 9.2 contract 规范（MUST）
- `outputs.required` 至少 1 条
- required.path 必须在 `reports/` 下
- 必须提供 `debug_hints`（>=2）

contract 非法：
- error_type = `CONTRACT_INVALID`

### 9.3 模板脚本规范（MUST）
- 所有输出必须写入 `run_dir/reports/`
- 禁止写入 enc 所在目录、用户 home、或任何 run_dir 外部路径
- 推荐由 runtime 注入以下变量/环境（实现任选其一，但要统一）：
  - `SP_RUN_DIR`
  - `SP_SCRIPTS_DIR`
  - `SP_REPORTS_DIR`
  - `SP_JOB_ID`
  - `SP_ENC_PATH`
  - `SP_ENC_DAT_PATH`

### 9.4 输出与指标口径（SHOULD）
- 每个 subskill 输出建议包括：
  - 关键 rpt（人读）
  - 参数与版本快照（复盘用）
  - 可选：结构化 metrics（供 summary.json 聚合）

---

## 10. validate_outputs 与 Summary 生成

### 10.1 validate_outputs（MUST）
- 读取 contract.outputs.required
- glob 展开并验证：
  - 无命中 => `OUTPUT_MISSING`
  - non_empty=true 且 size=0 => `OUTPUT_EMPTY`
- 任一失败 => Job FAIL，必须生成 debug_bundle

### 10.2 summary 生成（MUST）
- `summary.json`：写入 status/error_type/skill/design/metrics/evidence
- `summary.md`：必须包含
  - 结论（PASS/FAIL + error_type）
  - 关键发现或失败原因
  - 证据路径（reports/session/debug_bundle）

---

## 11. debug_bundle 生成规范（FAIL 必须）

### 11.1 触发点（MUST）
任意 FAIL 都必须生成 debug_bundle，包括：
- LOCATOR_FAIL（无 session 也要生成最小材料）
- SESSION_START_FAIL / HEARTBEAT_LOST / INNOVUS_CRASH
- RESTORE_FAIL / CMD_FAIL
- CONTRACT_INVALID / OUTPUT_MISSING / OUTPUT_EMPTY
- INTERNAL_ERROR

### 11.2 生成内容（MUST）
详见 `docs/PROTOCOLS.md` 的 debug_bundle 章节；实现时必须保证：
- 有 `index.json`
- 有 manifest/timeline
- 有最后 FAIL 的 ack（如存在 request）
- 有 session 日志 tail（如存在 session）
- 有 reports 清单
- 若与 contract/验收相关，包含 contract 或其指针

### 11.3 “tail 策略”（SHOULD）
为控制体积但保留诊断价值：
- supervisor/innovus 日志取最后 N 行（例如 2000 行）
- timeline 可截断但必须包含 FAIL 前后关键事件（建议保留全量，体积通常可控）

---

## 12. 错误处理与 error_type 映射（统一口径）

### 12.1 归类优先级（MUST）
当多个异常同时出现时，最终 error_type 应遵循“最贴近根因”的优先级，建议：
1. CONTRACT_INVALID（静态错误优先）
2. LOCATOR_FAIL
3. SESSION_START_FAIL
4. INNOVUS_CRASH
5. HEARTBEAT_LOST
6. QUEUE_TIMEOUT
7. RESTORE_FAIL
8. CMD_FAIL
9. OUTPUT_MISSING / OUTPUT_EMPTY（验收失败）
10. INTERNAL_ERROR（兜底）

> 实现可调整，但必须写入开发说明并在测试中锁定行为，保证统计治理稳定。

### 12.2 message 编写规范（MUST）
- 必须简短、可执行（例如“missing AAA.enc.dat”而不是堆栈）
- 详细堆栈与上下文留在 logs/ack/evidence_paths

---

## 13. 开发完成的质量门槛（Definition of Done）

### 13.1 Runtime DoD（MUST）
- 满足协议：run_dir 结构、manifest/timeline/request/ack/summary/debug_bundle
- 满足安全边界：scripts 白名单 + restore 例外收敛
- 满足失败可复盘：任意 FAIL 生成 debug_bundle 且 index 指向关键证据
- 满足测试：通过 `docs/TEST_SPEC.md` 的 Gate A/B（以及至少 1 个集成 Happy Path）

### 13.2 Subskill DoD（MUST）
- contract 合法且 required>=1
- 输出全部在 reports/ 且能通过 validate_outputs
- SKILL.md 说明指标口径、输入前提与常见失败
- tests/mock 可指导他人离线验证 contract 与输出验收逻辑

---

## 总结（落地抓手）
SkillPilot 的“专业性”最终落在以下可执行抓手上：
1. **状态机驱动 + 协议留痕**：任何一次运行都可复盘、可回归。  
2. **request/ack + scripts 白名单**：工具内动作可审计、可控、可诊断。  
3. **contract 驱动验收**：输出质量有硬标准，避免“跑完即交付”的不确定性。  
4. **debug_bundle 兜底**：失败必可交付复盘材料，形成跨团队协作与稳定性治理闭环。  

> 对应测试门槛与用例矩阵见 `docs/TEST_SPEC.md`。
