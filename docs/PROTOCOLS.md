# docs/PROTOCOLS.md

## 总览（Single Source of Truth）
本文件定义 SkillPilot 的**文件协议、证据结构、执行边界与失败分类**，是项目的 **SSOT（Single Source of Truth）**。  
任何实现（Claude Code 前端、Runtime、Innovus 内执行器、Subskill、测试与运维工具）都必须遵循本协议。若实现与本文冲突，以本文为准。

本协议的目标是把“意图驱动运行”落到工程上可长期运维的形态：
- **确定性执行**：关键决策不依赖模型；执行链路可回归。
- **证据优先**：结论必须能追溯到 run_dir 中的证据文件。
- **可复现诊断**：失败必须有稳定 error_type + 最小复盘材料（debug_bundle）。
- **资产化迭代**：Skill/subskill 以 contract 驱动输出验收，越用越标准、越可诊断。

---

## 1. 术语与基本约束

### 1.1 术语
- **CWD**：用户启动入口（Claude Code）的当前工作目录，通常是设计目录。
- **Job**：一次完整运行（定位 DB → 启动 Session → restore → 运行 skill/subskills → 验收 → 汇总 → 证据）。
- **run_dir**：Job 的证据目录，落在 CWD 下，保存所有事实源与产物。
- **Session**：一个 Innovus no_gui 常驻进程实例（每个 job 独立一个）。
- **request**：Runtime 投递给 Innovus 内执行器的执行请求（文件协议）。
- **ack**：Innovus 内执行器对 request 的回执（PASS/FAIL + 分类 + 信息）。
- **Skill / Subskill**：能力资产。Subskill 是最小可复用单元，由 contract + templates + tests + docs 组成。

### 1.2 强制约束（MUST）
- run_dir 必须位于：`CWD/.skillpilot/runs/<job_id>/`
- 所有协议文件必须包含：`schema_version`
- Innovus 执行动作必须通过 **request/ack** 闭环完成
- Innovus 只允许 `source` run_dir 的 **scripts/** 目录下脚本（白名单）
- 唯一例外：**restore_wrapper.tcl** 内允许 `source <enc_path>`（外部输入），且必须审计记录
- request/ack/manifest/summary 必须**原子写入**（临时文件 + rename）
- FAIL 必须生成 **debug_bundle**（最小复盘材料）

---

## 2. run_dir 规范（证据目录）

### 2.1 根路径（MUST）
`CWD/.skillpilot/runs/<job_id>/`

### 2.2 job_id 规则（MUST / SHOULD）
- MUST：在同一 CWD 下唯一，不得复用
- SHOULD：可排序、可读，建议：`YYYYMMDD_HHMMSS_<pid>_<rand4>`

### 2.3 目录布局（MUST）
run_dir 必须包含以下项（目录/文件名固定）：

- `job_manifest.json`（MUST）  
- `job_timeline.jsonl`（MUST，JSON Lines 追加写）
- `scripts/`（MUST，Innovus 白名单 source 目录）
- `queue/`（MUST，request 投递目录）
- `ack/`（MUST，ack 回执目录）
- `reports/`（MUST，subskill 输出证据目录）
- `session/`（MUST，会话日志与状态）
- `summary.json`（MUST）
- `summary.md`（MUST）
- `debug_bundle/`（MUST if FAIL；MAY if PASS）

> 说明：任何“事实”必须在 run_dir 中有落点；Claude Code 的对话内容不作为事实源。

---

## 3. job_manifest.json（事实源清单）

### 3.1 设计目标
manifest 是 Job 的**事实总表**（输入、选择、版本、运行环境、最终状态、关键证据指针）。  
要求：字段稳定、可机器解析、可对比、可做长期治理统计。

### 3.2 顶层字段（MUST）
- `schema_version`: string（例如 `"1.0"`）
- `job_id`: string
- `created_at`: ISO8601 string
- `status`: `"RUNNING" | "PASS" | "FAIL"`（终态必须更新）
- `error_type`: `"OK"` 或 Failure Taxonomy（终态必须写入）
- `runtime`: object（MUST）
- `design`: object（MUST）
- `skill`: object（MUST）
- `artifacts`: object（SHOULD）
- `versions`: object（SHOULD）
- `checksums`: object（MAY，若需要产物校验）

### 3.3 runtime（MUST）
- `cwd`: string（建议绝对路径）
- `run_dir`: string（绝对路径）
- `adapter`: string（当前固定 `"dsub-i"`）
- `user`: string（MAY）
- `host`: string（MAY）
- `env_summary`: object（MAY，必须脱敏；严禁写入敏感 token/口令）

### 3.4 design（MUST）
- `enc_path`: string（建议绝对路径）
- `enc_dat_path`: string（建议绝对路径）
- `locator`: object（MUST）
  - `mode`: `"explicit_path" | "cwd_scan"`
  - `query`: string（用户输入原始查询：`AAA` 或 `./AAA.enc`）
  - `candidates`: array（MUST if 多候选；否则 MAY）
    - item:
      - `path`: string
      - `mtime`: string（ISO8601，推荐）或 number（epoch，允许但需一致）
      - `size`: number
  - `selected`: object（MUST in 最终执行态；未选择前可缺省）
    - `enc_path`: string
    - `enc_dat_path`: string
  - `selection_reason`: string（例如：`direct_match | unique_scan_result | user_selected`）

### 3.5 skill（MUST）
- `name`: string（例如 `summary_health`）
- `version`: string（例如 `1.2.0`，开发阶段可用 `dev` 但必须存在）
- `subskill_path`: string（加载来源路径，便于复盘）

### 3.6 artifacts（SHOULD）
用于快速定位证据，不要求包含所有文件，但推荐至少：
- `timeline`: string（路径）
- `summary_json`: string
- `summary_md`: string
- `reports_dir`: string
- `session_dir`: string
- `debug_bundle_dir`: string（MUST if FAIL）

---

## 4. job_timeline.jsonl（状态机事件流）

### 4.1 设计目标
timeline 是 Job 的**追加型审计日志**，用于：
- 还原状态机转移与关键动作
- 定位在哪一步失败、耗时在哪里
- 支持运维统计（失败分布、时延分布）

### 4.2 格式（MUST）
- 文件为 JSON Lines：每行一个完整 JSON 对象
- MUST 只追加写，不做就地修改（除了极端修复工具）
- MUST 每行包含字段：

事件字段（MUST）：
- `schema_version`: string
- `ts`: ISO8601
- `job_id`: string
- `level`: `"INFO" | "WARN" | "ERROR"`
- `event`: string（事件名）
- `state`: string（MAY；如属于某状态）
- `message`: string（MAY）
- `data`: object（MAY；结构化上下文）

### 4.3 最小事件集合（MUST）
- `STATE_ENTER`（每个状态至少一次）
- `STATE_EXIT`（每个状态至少一次）
- `ACTION`（至少包含以下 action 之一或多项）
  - `locate_db`
  - `start_session`
  - `submit_request`
  - `receive_ack`
  - `validate_outputs`
  - `summarize`
- 终态事件（必须二选一）
  - PASS：`DONE`
  - FAIL：`FAIL`（且 level=ERROR）

---

## 5. request / ack / heartbeat（执行闭环协议）

### 5.1 Request（queue/<request_id>.json）

#### 5.1.1 命名（MUST）
`queue/<request_id>.json`

#### 5.1.2 request_id（MUST）
- MUST：全局唯一（至少在该 run_dir 内唯一）
- SHOULD：可读可追踪，建议：
  `<job_id>_<seq4>_<action_tag>`
  - 例：`20260204_170301_18452_a3f9_0003_restore`

#### 5.1.3 字段（MUST）
- `schema_version`: `"1.0"`
- `request_id`: string
- `job_id`: string
- `action`: string（当前 MUST 为 `"SOURCE_TCL"`）
- `script`: string（MUST 形如 `scripts/<name>.tcl`）
- `timeout_s`: number（MAY；若缺省由 runtime 默认）
- `created_at`: ISO8601

#### 5.1.4 原子写（MUST）
- MUST：写入临时文件（同目录）后 rename 为目标文件名
- MUST：禁止覆盖已有 request 文件（避免重复执行语义混乱）

---

### 5.2 Ack（ack/<request_id>.json）

#### 5.2.1 命名（MUST）
`ack/<request_id>.json`

#### 5.2.2 字段（MUST）
- `schema_version`: `"1.0"`
- `request_id`: string
- `job_id`: string
- `status`: `"PASS" | "FAIL"`
- `error_type`: `"OK"` 或 Failure Taxonomy
- `message`: string（FAIL MUST 有简短、可操作的原因）
- `started_at`: ISO8601（SHOULD）
- `finished_at`: ISO8601（SHOULD）
- `duration_ms`: number（MAY）
- `evidence_paths`: array<string>（MAY，指向关键日志/输出）

#### 5.2.3 原子写与唯一性（MUST）
- MUST 原子写
- MUST 每个 request_id 仅允许生成一个最终 ack（避免重复执行或覆盖）

---

### 5.3 Heartbeat（session/heartbeat）

#### 5.3.1 语义（MUST）
- queue_processor MUST 周期性更新 `session/heartbeat`（touch 或写入时间戳）
- Supervisor/Runtime MUST 根据 heartbeat 判定会话健康：
  - 超过阈值未更新 => `HEARTBEAT_LOST`

---

## 6. 安全边界（执行白名单与审计）

### 6.1 脚本白名单（MUST）
queue_processor 对 request MUST 做如下校验：
- `action` MUST 等于 `"SOURCE_TCL"`
- `script` MUST 是相对路径，且 MUST 以 `scripts/` 开头
- `script` MUST NOT 包含 `..`
- `script` MUST NOT 是绝对路径
- MUST 做 realpath 校验：  
  `realpath(run_dir/script)` 必须以 `realpath(run_dir/scripts)` 为前缀  
  以阻止符号链接逃逸与路径穿越

违反安全边界的处理（MUST）：
- ack.status=FAIL
- error_type=`CMD_FAIL` 或 `INTERNAL_ERROR`（实现可选择其一，但必须稳定一致）
- message 必须明确说明 “security violation / invalid script path”

---

### 6.2 restore 例外（唯一允许 source 外部文件，MUST）
- 外部 `enc_path` 的 `source` 仅允许在 `scripts/restore_wrapper.tcl` 内发生
- restore_wrapper MUST 执行：
  1) `cd [file dirname $enc_path]`
  2) `source $enc_path`
- Runtime MUST 在 manifest 与 timeline 中记录：
  - enc_path、enc_dat_path
  - restore_wrapper 路径
  - restore request_id 与对应 ack

---

## 7. Subskill Contract 协议（能力资产声明）

### 7.1 contract 文件位置（MUST）
`subskills/<name>/contract.yaml`（序列化格式允许 YAML；runtime 内部可转为结构化对象）

### 7.2 contract.yaml 字段（MUST）
- `schema_version`: string
- `name`: string
- `version`: string
- `tool`: MUST 为 `"innovus"`
- `description`: string（SHOULD）
- `scripts`: array（MUST，至少 1 项）
  - item:
    - `name`: string（例如 `run`）
    - `entry`: string（例如 `templates/run.tcl`）
- `outputs`: object（MUST）
  - `required`: array（MUST，至少 1 项）
    - item:
      - `path`: string（MUST 位于 `reports/` 下，可含 glob）
      - `non_empty`: boolean（SHOULD；默认建议 true）
      - `description`: string（MAY）
- `debug_hints`: array<string>（MUST，至少 2 条）

### 7.3 contract 安全约束（MUST）
- required.path MUST 指向 `reports/` 下（禁止 `../`、禁止绝对路径、禁止指向 run_dir 外部）
- required.path 若为 glob，glob 展开后仍 MUST 都落在 `reports/` 下

---

## 8. validate_outputs（验收协议）

### 8.1 验收规则（MUST）
对 `outputs.required` 逐条校验：
1) glob 展开后 MUST 命中至少 1 个文件，否则 `OUTPUT_MISSING`
2) 若 `non_empty=true`，命中文件 MUST `size > 0`，否则 `OUTPUT_EMPTY`

任意 required 失败：
- Job MUST FAIL
- manifest.status=FAIL
- error_type 写为对应分类（OUTPUT_MISSING / OUTPUT_EMPTY）
- debug_bundle MUST 生成，并包含缺失/为空的文件清单与 contract 指针

---

## 9. Summary 协议（对用户与对比友好）

### 9.1 summary.json（MUST）
- `schema_version`: string
- `job_id`: string
- `status`: `"PASS" | "FAIL"`
- `error_type`: string
- `design`: object（至少包含可追溯信息）
  - `enc_path`: string（可为 basename，但建议保留可追溯路径或哈希）
  - `enc_dat_path`: string
- `skill`: object
  - `name`: string
  - `version`: string
- `metrics`: object（由 subskill 定义；字段应稳定以支持对比）
- `evidence`: object（MUST）
  - `run_dir`: string
  - `summary_md`: string
  - `reports_dir`: string
  - `debug_bundle_dir`: string（MUST if FAIL）

### 9.2 summary.md（MUST）
必须包含以下段落（标题可变但语义必须存在）：
- 结论：PASS/FAIL + error_type
- 关键发现（PASS 时）
- 风险点/异常点（若有）
- 证据路径：reports、关键日志、debug_bundle（若 FAIL）

---

## 10. Failure Taxonomy（稳定失败分类，MUST）
`error_type` MUST 取以下枚举之一：

- `OK`（仅 PASS）
- `LOCATOR_FAIL`（找不到 enc/enc.dat、多候选未选择、不可读）
- `SESSION_START_FAIL`（dsub/innovus 启动失败或 ready 超时）
- `INNOVUS_CRASH`（进程异常退出）
- `HEARTBEAT_LOST`（心跳超时）
- `QUEUE_TIMEOUT`（request 超时未获 ack）
- `RESTORE_FAIL`（restore_wrapper 或 enc restoreDesign 报错）
- `CMD_FAIL`（非 restore 的脚本执行失败）
- `CONTRACT_INVALID`（contract 本身不合法）
- `OUTPUT_MISSING`（required 缺失）
- `OUTPUT_EMPTY`（required 为空）
- `INTERNAL_ERROR`（runtime 自身异常或未分类错误）

要求：
- 同类问题 MUST 映射到同一 error_type（稳定性对治理非常关键）
- message MUST 简短、可操作；详细上下文应在 logs/ack/evidence 中体现

---

## 11. debug_bundle（FAIL 的最小可复盘交付）

### 11.1 生成原则（MUST）
- 任意 FAIL（包括 LOCATOR_FAIL）都 MUST 生成 debug_bundle
- debug_bundle MUST 能在**脱离现场环境**的情况下支持基础定位（至少知道失败点、错误分类、关键日志尾部、输入选择）

### 11.2 必须内容（MUST）
`debug_bundle/` MUST 包含：
- `index.json`（推荐名；MUST）
- `job_manifest.json`（复制或指针，MUST）
- `job_timeline.jsonl`（可截断但必须覆盖 FAIL 前后，MUST）
- `ack/`（至少包含最后一个 FAIL ack，MUST）
- `session/` 日志 tail（若存在 session；MUST if 有 session）
  - `supervisor.log` tail
  - `innovus stdout/stderr` tail（若可用）
  - `state.json`（建议包含 last_heartbeat）
- `reports_inventory.json` 或 `reports_inventory.txt`（MUST：文件名/大小/mtime 清单）
- `contract.yaml` 或其路径指针（MUST if 涉及 subskill 执行/验收）
- `notes.txt`（MAY：额外说明/复现建议）

### 11.3 index.json 推荐字段（SHOULD）
- `schema_version`
- `job_id`
- `error_type`
- `summary`: string（1～3 行）
- `pointers`: object（相对路径）
  - `manifest`
  - `timeline`
  - `last_fail_ack`
  - `session_logs`
  - `reports_inventory`
  - `contract`
- `next_actions`: array<string>（给用户/运维的下一步建议）

---

## 12. Schema Versioning（版本演进规则）

### 12.1 适用范围（MUST）
以下文件 MUST 包含 `schema_version`：
- manifest / timeline / request / ack / summary / contract / debug_bundle index

### 12.2 升级规则（MUST）
- 任何字段语义变化、必填变更、结构变更 => MUST 提升 schema_version（至少次版本）
- MUST 尽量向后兼容：旧字段仍可解析，或提供迁移工具（不破坏历史 run_dir 可读性）
- Runtime SHOULD 在 manifest.versions 记录自身版本、subskill 版本、工具版本（便于治理）

---

## 总结（协议验收口径）
- **run_dir 是事实源**：任何结论必须能通过 run_dir 内的协议文件复盘；Claude Code 文本不作为事实。  
- **执行必须闭环**：任何 Innovus 内动作必须有 request/ack；任何关键阶段必须在 timeline 有事件。  
- **失败必须可交付复盘**：FAIL 必有稳定 error_type + debug_bundle（最小材料）。  
- **Skill 必须可验收**：contract 定义 required outputs，validate_outputs 严格执行，确保“跑完”与“合格”一致。
