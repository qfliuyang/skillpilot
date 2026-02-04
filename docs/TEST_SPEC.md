# docs/TEST_SPEC.md

## 总览（测试的目标：让 Skill 越用越稳、越标准、越可诊断）
SkillPilot 的测试体系围绕三条主线建立，并以协议证据为唯一判定依据（见 `docs/PROTOCOLS.md`）：

1. **确定性**：关键逻辑（定位、协议读写、验收、失败归类、debug_bundle）必须可离线回归。  
2. **证据化**：测试不验证“对话文本”，只验证 run_dir 的协议产物与可复盘性。  
3. **可诊断性**：失败用例必须验证 error_type 稳定、debug_bundle 完整，确保可离线定位与协同支持。

---

## 1. 测试分层（Test Pyramid）

### 1.1 L0：协议与静态合规测试（No Innovus）
目标：保证协议 SSOT 不被破坏，任何运行都能产出可解析、可审计的 run_dir。

覆盖范围（MUST）：
- run_dir 结构：必备文件/目录齐全
- schema_version：manifest/timeline/request/ack/summary/contract/index 必须存在
- 原子写行为：不会出现半写 JSON（可通过“写入失败注入/中断”模拟或工具验证）
- contract 合规：outputs.required >= 1，且路径必须在 `reports/`
- request 合规：只允许 `scripts/*.tcl` 且不含 `..`、不为绝对路径

输出判定：
- 只看协议文件与结构，不依赖工具运行

---

### 1.2 L1：Mock 单元/组件测试（No Innovus）
目标：把 80% 逻辑压在可离线回归范围内，减少对 EDA 环境的依赖。

覆盖范围（MUST）：
- Locator：
  - explicit_path / cwd_scan / 多候选 / 缺 enc.dat
- Contract Validator：
  - 合法性校验与错误归类（CONTRACT_INVALID）
- validate_outputs：
  - glob 命中、缺失、为空、多个文件
- request/ack 等待逻辑：
  - 正常 ack、超时 QUEUE_TIMEOUT、FAIL 透传
- debug_bundle 生成：
  - 任意失败均能输出 index.json + 最小证据集合
- Orchestrator 终态收敛：
  - 任意阶段失败 => manifest/timeline/summary/error_type/debug_bundle 一致

Mock 策略（SHOULD）：
- 通过写入 fake ack 文件模拟 Innovus 返回
- 通过虚拟 session/heartbeat 文件模拟心跳与失活

---

### 1.3 L2：集成测试（Needs Innovus + dsub -I）
目标：验证真正的工具链闭环与环境耦合点，确保“可跑、可控、可诊断”。

覆盖范围（MUST）：
- `dsub -I` 启动 Innovus no_gui 成功
- queue_processor ready 判定可靠（ready 文件或首次 heartbeat）
- request → ack 的闭环可用且稳定（含失败分类）
- restore_wrapper 规则生效（cd 到 enc 目录 + source）
- subskill 执行产出 reports，并能通过 contract 验收
- 失败注入：restore fail、输出缺失、心跳丢失、innovus crash、request 超时

注意：
- 集成测试不追求覆盖全部逻辑，追求“关键路径可用 + 失败可诊断”。

---

## 2. 发布门槛（Quality Gates）

### Gate A：协议 Gate（MUST）
任何提交（CI 或 merge）必须通过：
- run_dir 结构完整
- 必备协议文件 schema_version 存在且可解析
- timeline 至少包含 INIT、关键 ACTION、终态 DONE/FAIL
- FAIL 必有 debug_bundle/index.json 且 pointers 指向关键证据
- validate_outputs 的错误归类稳定（OUTPUT_MISSING/OUTPUT_EMPTY）

### Gate B：离线能力 Gate（MUST）
必须通过 L1 Mock 测试中：
- Locator 全覆盖
- Contract 合规与非法覆盖
- validate_outputs 覆盖
- debug_bundle 覆盖
- Orchestrator 终态一致性覆盖

### Gate C：工具闭环 Gate（MUST for release / SHOULD for dev）
- 至少 1 个 Happy Path 集成用例通过
- 至少 2 个失败注入用例通过（推荐：RESTORE_FAIL + HEARTBEAT_LOST）

---

## 3. 测试数据与夹具（Fixtures）

### 3.1 Locator Fixtures（No Innovus）
在临时目录构造以下结构：
- 单候选：
  - `AAA.enc`
  - `AAA.enc.dat`（可为空目录/文件，但必须存在）
- 多候选：
  - `block1/AAA.enc`
  - `block2/AAA.enc`
  - 对应 `.dat` 均存在
- 缺 dat：
  - 只有 `AAA.enc`，无 `AAA.enc.dat`

每个 fixture 应记录：
- path、mtime、size 的可控值（便于 deterministic 断言）

### 3.2 Contract Fixtures（No Innovus）
- 合法 contract：required 在 `reports/`，>=1
- 非法 contract：
  - required 为空
  - required 包含 `../`
  - required 为绝对路径
  - required 指向 `session/` 或 `scripts/`（必须拒绝）

### 3.3 validate_outputs Fixtures（No Innovus）
在 run_dir/reports 构造：
- 存在且非空文件
- 空文件（size=0）
- 多文件匹配 glob（部分为空/全部非空）

### 3.4 集成测试 DB Fixtures（Needs Innovus）
准备至少一个可 restore 的最小 DB：
- `MIN.enc`
- `MIN.enc.dat`
要求：
- restore_wrapper 可以成功 source
- subskill 可以生成 required reports

若无可共享 DB，可采用“企业内部最小示例 DB”作为基准资产，并固定在受控路径（但测试仍需复制到 CWD 或建立只读引用策略）。

---

## 4. Mock 测试用例矩阵（Minimum Viable Suite）

> error_type 必须严格断言（taxonomy 稳定性对长期治理非常关键）。

### 4.1 Locator（L 系列）
- **L1**：explicit_path 正常  
  输入：`./AAA.enc`  
  断言：selected enc_path 与 enc_dat_path 正确；selection_reason=direct_match
- **L2**：cwd_scan 单候选  
  输入：`AAA`  
  断言：unique_scan_result
- **L3**：cwd_scan 多候选  
  输入：`AAA`  
  断言：返回 candidates；不写 selected；Orchestrator 输出“需要选择”
- **L4**：缺 enc 或缺 enc.dat  
  断言：LOCATOR_FAIL + debug_bundle（即使无 session）

### 4.2 Contract（C 系列）
- **C1**：合法 contract  
  断言：通过
- **C2**：required=[]  
  断言：CONTRACT_INVALID
- **C3**：required 路径越界（`../` / 绝对路径）  
  断言：CONTRACT_INVALID

### 4.3 validate_outputs（V 系列）
- **V1**：required 命中且非空  
  断言：PASS
- **V2**：required 缺失  
  断言：OUTPUT_MISSING
- **V3**：required 命中但空文件  
  断言：OUTPUT_EMPTY
- **V4**：glob 命中多个文件  
  断言：若 non_empty=true，则任一为空 => OUTPUT_EMPTY

### 4.4 request/ack（Q 系列，Mock ack）
- **Q1**：收到 PASS ack  
  断言：timeline 含 submit_request/receive_ack；继续后续状态
- **Q2**：超时未收到 ack  
  断言：QUEUE_TIMEOUT + debug_bundle
- **Q3**：收到 FAIL ack（RESTORE_FAIL/CMD_FAIL）  
  断言：job FAIL；manifest.error_type 与 ack.error_type 一致（或按规则映射一致）

### 4.5 debug_bundle（D 系列）
- **D1**：LOCATOR_FAIL 也生成 debug_bundle  
  断言：index.json 存在；包含 manifest/timeline；指明缺失 enc/dat
- **D2**：RESTORE_FAIL 打包最后 FAIL ack + session log tail（若 session 存在）  
  断言：pointers 正确；材料齐全
- **D3**：OUTPUT_MISSING 打包 reports_inventory + contract 指针  
  断言：inventory 列出实际文件；contract 可定位

---

## 5. 集成测试用例（Innovus + dsub -I）

### 5.1 I1：Happy Path（最小闭环）
步骤：
1. 在 CWD 放置 `MIN.enc` 与 `MIN.enc.dat`
2. 启动 job：skill=`summary_health`（或最小 subskill）
3. supervisor 启动 Innovus，queue_processor ready
4. restore_wrapper PASS
5. run_skill PASS
6. validate_outputs PASS
7. summary 生成

断言（MUST）：
- manifest.status=PASS，error_type=OK
- reports/ 下 required outputs 存在且非空
- summary.json/md 存在
- timeline 包含 DONE

### 5.2 I2：RESTORE_FAIL 注入
构造：
- 使用一个故意失败的 enc（例如引用缺失文件/错误命令）
断言：
- restore ack FAIL，error_type=RESTORE_FAIL
- job FAIL
- debug_bundle 包含 fail ack + innovus tail + restore_wrapper 脚本快照

### 5.3 I3：HEARTBEAT_LOST 注入
构造（任选其一）：
- 启动后 kill Innovus
- 或停止 queue_processor 更新 heartbeat（可通过测试脚本故意卡死在不更新心跳的循环，视实现能力）
断言：
- error_type=HEARTBEAT_LOST 或 INNOVUS_CRASH（按真实观测与规则）
- debug_bundle 包含 session/state.json 与最后心跳信息

### 5.4 I4：OUTPUT_MISSING 注入
构造：
- subskill 脚本不生成 required outputs
断言：
- validate_outputs FAIL：OUTPUT_MISSING
- debug_bundle 包含 reports_inventory + contract

### 5.5 I5：QUEUE_TIMEOUT 注入（可选但强烈建议）
构造：
- 投递一个会卡死的脚本（例如永不返回或长时间 sleep）
- 或让 queue_processor 不处理 queue（模拟执行器故障）
断言：
- error_type=QUEUE_TIMEOUT
- debug_bundle 指向最后 request 与 session 日志

---

## 6. 稳定性与回归策略（Regression Strategy）

### 6.1 版本回归（MUST for releases）
对以下组合至少做一次回归：
- runtime version × subskill version × tool version（若可获取）
把版本写入 manifest.versions，便于定位回归引入。

### 6.2 并发回归（SHOULD）
- max_parallel=2/4 做 A/B 并发
- 断言：
  - 各 run_dir 不互相污染
  - request/ack 不串扰
  - 任一 job FAIL 不影响其它 job 完成

### 6.3 历史可读性回归（SHOULD）
- 使用历史 run_dir 样例作为输入，验证当前解析器仍能读旧 schema_version（或明确报出迁移提示）
- 防止协议升级破坏长期治理数据。

---

## 7. 测试判定标准（Pass/Fail Criteria）

### 7.1 必须断言的“硬结果”
- manifest.status 与 error_type
- summary.status 与 error_type
- timeline 是否包含关键事件与终态事件
- FAIL 是否生成 debug_bundle 且 index pointers 可用
- contract required 输出验收结果（存在/非空）

### 7.2 不作为判定标准的内容（避免脆弱性）
- Innovus 日志中的具体行号/时间戳
- Claude Code 的自然语言措辞
- 报告中可能随工具版本变化的非关键字段（除非你们锁定了口径）

---

## 总结（测试体系的专业落点）
SkillPilot 的测试不是“跑一遍看看”，而是以协议与证据为中心的工程闭环：

- L0/L1 确保绝大部分逻辑可离线回归，支撑“越用越稳”。  
- L2 只验证工具闭环与环境耦合点，确保“可跑且可诊断”。  
- Gate A/B/C 把协议稳定性、失败可复盘、以及关键路径可用性变成发布门槛。  

> 当你新增或修改任何 subskill：必须同时新增/更新其 contract 校验用例、validate_outputs 用例，以及至少一个集成 Happy Path（或复用统一的最小 subskill 集成用例）。
