# docs/ARCHITECTURE.md

## 总览（Architecture at a Glance）
SkillPilot 是一个面向 EDA（以 Innovus 为核心）的 **Skill 驱动自动运行与洞察平台**。其架构核心是“**意图层弱依赖、执行层强确定性、证据层可审计**”：

- **意图层（Claude Code）**：负责用户交互与意图澄清，不承担关键执行决策。
- **执行层（Runtime）**：以确定性状态机驱动 Job，从 DB 定位到 Innovus 执行与验收，严格遵循协议（见 `docs/PROTOCOLS.md`）。
- **工具层（Innovus Session）**：每 Job 独立会话，由 Innovus 内执行器（queue_processor）以 request/ack 闭环执行脚本并产出心跳。
- **证据层（run_dir）**：所有事实落在 run_dir（manifest/timeline/ack/reports/session/summary/debug_bundle），保证可复现诊断与长期治理。

---

## 1. 项目架构目标与非目标

### 1.1 架构目标（MUST）
1. **确定性**：Runtime 的关键行为（选择、执行、验收、归因）必须确定，可回归。
2. **证据优先**：任何结论必须可追溯到 run_dir 的证据文件；文本输出不是事实源。
3. **会话隔离**：每个 Job 独立 Innovus Session，避免状态污染，提升可复现性。
4. **安全边界**：Innovus 只允许 source run_dir/scripts（白名单），restore 例外必须被 wrapper 收敛并审计。
5. **可诊断性**：失败必须稳定归类（taxonomy）并输出 debug_bundle 以支持离线复盘。

### 1.2 非目标（WON’T）
- 不把大模型当作调度器/执行器：不允许“模型临场规划”决定执行细节。
- 不提供绕过协议的“便捷执行通道”（例如直接在对话里执行任意 TCL）。
- 不把工具输出“看起来像成功”当作成功：必须通过 contract 验收输出。

---

## 2. 分层与组件边界（职责清晰、可替换、可测试）

### 2.1 Claude Code Frontend（意图层：交互与呈现）
**职责**
- 获取用户意图（skill、design 列表、对比需求）。
- DB 多候选时与用户交互选择（Runtime 不擅自决定）。
- 展示结果：读取 `summary.md/json`，返回证据路径（run_dir、reports、debug_bundle）。

**不做**
- 不猜 DB、不猜 enc/dat。
- 不绕过协议执行。
- 不用“解析零散日志”替代 summary（summary 才是可对比事实出口）。

---

### 2.2 Orchestrator（执行层：确定性状态机）
**职责**
- 驱动 Job 生命周期状态机（见第 4 节）。
- 统一写入 `job_manifest.json` 与 `job_timeline.jsonl`（SSOT）。
- 调用 Locator / Supervisor / Kernel / Contract Validator 等组件。
- 统一失败归类并触发 debug_bundle 生成。

**接口（概念）**
- `run_job(intent_resolved_params) -> run_dir`
- `resume_job(job_id, user_selection)`（用于多候选选择后继续）

---

### 2.3 DB Locator（执行层：DB 定位器）
**职责**
- 输入 query（名称或显式路径），定位：
  - `<name>.enc`
  - `<name>.enc.dat`
- 多候选返回 candidates；**不自动选择**。
- 将选择过程写入 manifest 的 locator 字段（含 selection_reason）。

**可测试性**
- Locator 必须纯确定性、可离线单测（不依赖 Innovus、dsub）。

---

### 2.4 Session Supervisor（执行层：会话监督器 / dsub -I 适配器）
**职责**
- 通过 `dsub -I` 启动 Innovus no_gui session。
- 负责会话生命周期管理：启动、ready 判定、日志采集、退出码记录。
- 监控 Innovus 内心跳 `session/heartbeat`：
  - 心跳超时判定 `HEARTBEAT_LOST`
  - 进程异常退出判定 `INNOVUS_CRASH`

**产物（协议要求）**
- `session/supervisor.log`
- `session/state.json`
- `session/innovus.stdout/stderr.log`（若可分离）
- `session/heartbeat`

---

### 2.5 Innovus queue_processor（工具层：Innovus 内执行器）
**职责**
- 常驻轮询 `run_dir/queue`，处理 request。
- 只允许执行 `SOURCE_TCL` 且脚本必须在 `run_dir/scripts/`（白名单 + realpath 校验）。
- 执行脚本并捕获 TCL 错误，生成 ack：
  - `ack/<request_id>.json`
- 定期更新 `session/heartbeat`。

**关键属性**
- 执行器是“受控的工具内内核”：把所有工具内动作收敛到可审计的 request/ack。

---

### 2.6 Execution Kernel（执行层：原子操作集合）
**职责**
- 初始化 run_dir 结构与协议文件。
- 渲染/生成 scripts（restore_wrapper、subskill run 脚本）。
- 投递 request（原子写）、等待 ack（超时策略）。
- 执行 contract 验收（validate_outputs）。
- 生成 summary（json + md）。
- FAIL 时生成 debug_bundle（最小复盘包）。

**实现原则**
- Kernel 尽量“可 mock”：例如 ack 等待可用 fake ack 文件替代 Innovus。

---

### 2.7 Contract Validator（执行层：验收与合规）
**职责**
- 校验 contract 合法性（CONTRACT_INVALID）：
  - required outputs 至少 1 项
  - required 路径必须在 reports/ 下（禁止绝对路径/`..`）
- 验收 required outputs（OUTPUT_MISSING / OUTPUT_EMPTY）。

---

## 3. 证据与数据流（Evidence-First Dataflow）

### 3.1 SSOT 证据集合
run_dir 中以下对象是事实源（见 `docs/PROTOCOLS.md`）：
- `job_manifest.json`：输入、选择、版本、终态
- `job_timeline.jsonl`：状态机事件流（追加写）
- `queue/*.json`：request（执行输入）
- `ack/*.json`：ack（执行输出）
- `scripts/*.tcl`：实际执行脚本快照（可审计、可复盘）
- `reports/*`：Skill 输出证据（验收对象）
- `session/*`：会话与日志、心跳、状态
- `summary.json/md`：结果出口（对比与呈现）
- `debug_bundle/*`：FAIL 最小复盘材料

### 3.2 “证据优先”的工程意义
- 结果稳定：summary 输出可版本化、可聚合对比。
- 排障稳定：失败不依赖“现场复现”，靠 debug_bundle 离线定位。
- 治理可行：可按 error_type / tool_version / skill_version / design 统计失败与波动。

---

## 4. Job 状态机（确定性执行骨架）

### 4.1 状态定义（建议最小集）
- `INIT`
- `PREPARE_RUNDIR`
- `LOCATE_DB`
- `START_SESSION`
- `RESTORE_DB`
- `RUN_SKILL`
- `VALIDATE_OUTPUTS`
- `SUMMARIZE`
- `DONE`
- `FAIL`

> 状态名可实现为枚举，但必须能在 timeline 中稳定记录。

### 4.2 状态转移（MUST）
- `LOCATE_DB` 成功才允许进入 `START_SESSION`
- `START_SESSION` 成功才允许进入 `RESTORE_DB`
- `RESTORE_DB` PASS 才允许进入 `RUN_SKILL`
- `RUN_SKILL` PASS 才允许进入 `VALIDATE_OUTPUTS`
- `VALIDATE_OUTPUTS` PASS 才允许进入 `SUMMARIZE`
- `SUMMARIZE` 成功后进入 `DONE`

任意状态发生错误：
- 进入 `FAIL`
- 写入 timeline：`FAIL` 事件（level=ERROR）
- manifest 写终态：`status=FAIL` + `error_type`
- 生成 `debug_bundle/`

### 4.3 多候选 DB 的“可恢复停顿点”
当 Locator 发现 candidates>1：
- Job 不应直接 FAIL
- Orchestrator 进入“等待选择”分支（可表现为在 `LOCATE_DB` 内输出 candidates 并暂停）
- 前端回传 user selection 后继续（写 selection_reason=`user_selected`）

---

## 5. 关键机制（影响稳定性与可诊断性的核心设计）

### 5.1 每 Job 独立 Innovus Session（隔离）
原因：
- Innovus 内部状态复杂（变量、数据库上下文、脚本副作用），共享 session 会导致不可复现与污染。
收益：
- 复盘简单、回归稳定、资源回收清晰。

### 5.2 request/ack 执行闭环（工具内动作可审计）
- Runtime 不直接“把 TCL 打到工具里”，而是通过文件队列投递确定性脚本。
- ack 统一承载执行结果、错误归类与证据路径指针，成为诊断与治理入口。

### 5.3 scripts 白名单 + restore 例外收敛（安全边界）
- 绝大多数执行必须来自 run_dir/scripts（可审计输入快照）。
- restore 唯一例外：enc 是外部输入，必须通过 restore_wrapper 收敛：
  - `cd [file dirname $enc_path]`
  - `source $enc_path`
并在 manifest/timeline 审计记录。

### 5.4 contract 驱动验收（“跑完”不等于“合格”）
- Skill 的完成标准不是命令不报错，而是 required outputs 满足 contract：
  - 存在
  - 非空（如要求）
否则 Job 必须 FAIL，且 error_type 明确（OUTPUT_MISSING/OUTPUT_EMPTY）。

### 5.5 debug_bundle（FAIL 最小复盘交付）
- debug_bundle 是跨团队协作的最小材料（设计↔CAD↔基础设施↔厂商）。
- 其结构固定，保证任何失败都能被稳定路由与定位。

---

## 6. 批量运行与对比（A/B/C/D 场景的架构支持）

### 6.1 并发模型
- Orchestrator 控制并发度（max_parallel）。
- 每个 design/job：
  - 独立 run_dir
  - 独立 session
避免资源抢占导致的互相污染与证据混淆。

### 6.2 对比模型（输出结构化、对比在汇总层）
- 每个 job 产出 `summary.json`（结构化 metrics）。
- 对比逻辑应在汇总/展示层完成（可由前端或独立 aggregator 完成）。
- Runtime 负责“每个 job 的确定性事实”，不负责“对比策略的推理”。

---

## 7. 弱模型/无互联网环境（架构保障）
- 执行关键路径不依赖联网：DB 定位、dsub、Innovus、脚本、验收、证据全在本地完成。
- 模型能力不足时仍可运行：
  - 前端只影响“对话体验”
  - 后端执行与结果由协议与状态机保证
- 未来可替换前端：Web/CLI wrapper/自动调度器均可接入，只要遵循协议与运行 API。

---

## 8. 可演进性与长期维护（工程化落地策略）

### 8.1 协议稳定优先
- 新增能力先扩展 contract/summary metrics，再扩展脚本与解析。
- schema_version 演进必须向后兼容，保证历史 run_dir 可读可比。

### 8.2 Skill 资产治理
- Skill 必须具备：
  - contract（输出与验收）
  - templates（执行脚本）
  - tests/mock（离线回归）
  - SKILL.md（使用说明与指标解释）
- 以 error_type 统计失败分布，反向驱动：
  - wrapper 稳定性工程
  - 输出规范化
  - 诊断信息补齐（evidence_paths、debug_hints）

### 8.3 运维可观测性
建议长期纳入治理的指标（可写入 summary/versions 或外部系统）：
- Job 总耗时、各状态耗时
- error_type 分布
- tool 版本/skill 版本的失败相关性
- heartbeat 丢失与队列超时频次

---

## 总结（架构验收口径）
SkillPilot 的架构是否“专业可长期运行”，取决于以下硬标准是否满足：

1. **确定性**：Runtime 以状态机运行，关键决策可回归。  
2. **证据化**：run_dir 完整、协议文件齐全，任何结论可追溯。  
3. **隔离性**：每 Job 独立 session，避免污染并提升可复现性。  
4. **可诊断**：FAIL 有稳定 error_type 与 debug_bundle，可离线复盘、可路由支持。  
5. **可演进**：Skill 资产化（contract 驱动），schema 可升级且向后兼容。  

> 本架构的落地细则与行为规范以 `docs/PROTOCOLS.md` 为 SSOT；开发实现规范与测试门槛分别见 `docs/DEVELOPMENT_SPEC.md` 与 `docs/TEST_SPEC.md`。
