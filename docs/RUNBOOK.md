# docs/RUNBOOK.md

## 总览（Runbook 的定位：怎么跑、怎么交付、怎么排障）
本手册面向三类角色：**设计工程师（Design）**、**CAD/方法学（CAD）**、**基础设施/运维（Infra/Ops）**。它描述 SkillPilot 在真实项目环境中的标准运行方式、结果交付口径与失败排障路径。

SkillPilot 的核心承诺是：
- 用户只表达意图，平台完成从 DB 定位到 Skill 运行与洞察输出；
- 任意一次运行都有 **run_dir 证据目录**；
- 任意一次失败都有 **debug_bundle 最小可复现材料**；
- 结论来自证据（manifest/timeline/ack/reports/session/summary），不是对话文本。

---

## 1. 快速运行（面向 Design 用户）

### 1.1 运行前准备（你需要确认）
在你的设计目录（CWD）中，确认你要分析的 DB 满足：
- 存在 `XXX.enc`
- 存在 `XXX.enc.dat`（固定命名规则：`<enc_path>.dat`）

建议：
- 尽量在包含 DB 的目录作为 CWD 运行，便于 locator 快速定位与证据就地归档。

### 1.2 你如何发起一次分析（意图表达）
在 Claude Code 中直接描述意图，例如：
- “看下 XX design 的整体情况（用 summary_health）”
- “对 A/B/C/D 跑 timing health 并对比”
- “对 ./blockA.enc 跑 summary_health，给我证据路径和结论”

如果 locator 扫描到多个候选 DB：
- Claude Code 会列出 candidates（路径/时间/大小）
- 你只需选择正确的那个（这一步不由系统擅自决定）

### 1.3 运行结果在哪里（你只需要记住一条路径）
每次运行都会生成一个证据目录：
- `CWD/.skillpilot/runs/<job_id>/`

你最常用的三个入口：
- `summary.md`：面向人的结论与证据路径
- `reports/`：Skill 输出报告（验收对象）
- `debug_bundle/`：失败最小复盘材料（仅 FAIL 必有）

---

## 2. 结果交付口径（怎么把结果发给别人）

### 2.1 PASS 交付（推荐方式）
你可以直接交付：
- `summary.md`
- `reports/` 下关键报告（按 summary.md 中引用的证据路径）

若对方需要完整审计：
- 打包整个 `run_dir`

### 2.2 FAIL 交付（标准方式）
FAIL 时优先交付：
- `debug_bundle/`（最小材料，跨团队协作最友好）

只有在对方明确要求完整上下文时，再交付：
- 整个 `run_dir`

> 原则：debug_bundle 是“最小可复盘交付”，run_dir 是“完整证据归档”。

---

## 3. 你该如何阅读一次运行（从 summary 到证据）

### 3.1 先看 summary.md（必须）
summary.md 必须包含：
- 结论：PASS/FAIL + error_type
- 关键发现/风险点
- 证据路径（reports / session logs / debug_bundle）

你只要按 summary.md 的“证据路径”点击/打开，就能定位到事实源。

### 3.2 再看 summary.json（对比/自动化用）
当你需要对比 A/B/C/D 或做趋势统计时：
- 使用 `summary.json` 的 `metrics` 字段作为机器可读指标来源
- 不建议直接解析工具原生日志（脆弱且不可维护）

---

## 4. 标准排障流程（Design/CAD 通用）

### 4.1 最短排障路径（3 步）
1. 打开 `summary.md`：确认 `error_type` 与失败阶段  
2. 打开 `debug_bundle/index.json`：确认最小材料指针与 next_actions  
3. 打开 `ack/<last_request_id>.json` 与 `session/*log` tail：看第一条真实报错上下文

### 4.2 关键证据文件你应当会找
- `job_manifest.json`：本次输入、DB 选择、skill 版本、最终状态
- `job_timeline.jsonl`：在哪一步失败、每步耗时
- `ack/*.json`：工具内执行是否成功、失败分类与 message
- `session/*`：dsub/innovus 日志、心跳与退出码
- `reports/*`：skill 输出与验收对象
- `debug_bundle/*`：失败最小复盘材料

---

## 5. 常见 error_type 与处理指引（按 Taxonomy 稳定路由）

> error_type 定义见 `docs/PROTOCOLS.md`，本节只给处理动作。

### 5.1 LOCATOR_FAIL（DB 定位失败）
**含义**
- 找不到 enc / enc.dat
- 多候选但未选择
- 路径不可读/权限问题

**你做什么**
- 优先用显式路径重试：`./path/to/XXX.enc`
- 检查 `XXX.enc.dat` 是否存在且命名正确
- 若权限/挂载问题，将 debug_bundle 发给 Infra/Ops

---

### 5.2 SESSION_START_FAIL（会话启动失败）
**含义**
- dsub -I 启动失败、资源/队列问题、license 问题、ready 超时

**你做什么**
- 看 `session/supervisor.log` 的第一处错误
- 将 debug_bundle 发给 CAD/Infra（包含 dsub 输出与命令）

---

### 5.3 INNOVUS_CRASH（工具崩溃）
**含义**
- Innovus 异常退出（exit_code 非预期）

**你做什么**
- 提供 debug_bundle（重点：state.json、innovus stdout/stderr tail）
- 若是特定 DB/特定版本高发，CAD 可据此做版本相关性统计

---

### 5.4 HEARTBEAT_LOST（心跳丢失）
**含义**
- Innovus 卡死、被 kill、queue_processor 未运行或停止更新 heartbeat

**你做什么**
- 看 `session/heartbeat` 最后更新时间、`session/state.json`
- 把 debug_bundle 给 Infra/Ops（关注队列/资源/节点稳定性）

---

### 5.5 QUEUE_TIMEOUT（request 等待 ack 超时）
**含义**
- request 投递成功，但在超时内没有收到 ack
- 常见原因：脚本卡住、queue_processor 故障、会话异常但未立刻退出

**你做什么**
- 看 heartbeat 是否仍在更新：
  - 有 heartbeat：脚本卡住概率高（看最后一个 request 对应脚本与 innovus tail）
  - 无 heartbeat：会话失活概率高（HEARTBEAT_LOST/INNOVUS_CRASH 方向排查）
- 将 debug_bundle 发给 CAD（脚本/方法学）或 Infra（会话稳定性）

---

### 5.6 RESTORE_FAIL（DB 恢复失败）
**含义**
- restore_wrapper source enc 报错或 restoreDesign 失败
- 可能与 enc 内部相对路径依赖、缺失文件、版本不兼容相关

**你做什么**
- 先看 `ack/<restore_request_id>.json` 的 message
- 再看 innovus log tail 中第一条 TCL error
- 将 debug_bundle 发给 CAD/设计方法学（恢复链路问题通常需要他们定位）

---

### 5.7 CMD_FAIL（Skill 脚本执行失败）
**含义**
- 非 restore 的脚本 source 失败或 TCL 运行错误

**你做什么**
- 查看 fail ack 的 evidence_paths（若提供）
- 查看 `scripts/` 中实际执行脚本快照
- 将 debug_bundle 发给 subskill 开发者或 CAD

---

### 5.8 CONTRACT_INVALID（Skill 资产声明不合法）
**含义**
- contract.yaml 不符合规范（required 为空、路径越界等）

**你做什么**
- 这类问题属于工程质量问题：直接发给 subskill 维护者
- debug_bundle 中应包含 contract 或指针

---

### 5.9 OUTPUT_MISSING / OUTPUT_EMPTY（验收失败）
**含义**
- subskill 没按 contract 产出 required outputs，或输出为空

**你做什么**
- 打开 summary.md 查看缺失项
- 打开 reports 目录清单（debug_bundle 中 inventory）
- 发给 subskill 维护者：他们需要修脚本或修 contract

---

### 5.10 INTERNAL_ERROR（系统自身错误）
**含义**
- runtime bug、未处理异常、协议破坏等

**你做什么**
- 直接交付 debug_bundle 给 runtime 维护者
- 附上你触发的意图与 CWD（但事实仍以 run_dir 为准）

---

## 6. CAD/方法学：Skill 迭代闭环与治理入口

### 6.1 你如何判断一个 Skill 是否“工程化合格”
合格必须满足：
- contract 有 required outputs（>=1）且在 `reports/`
- validate_outputs 可严格判定质量
- FAIL 能输出 debug_bundle，且能离线复盘失败原因
- summary.json metrics 字段稳定可比（为对比与趋势治理服务）

### 6.2 失败聚类与治理（推荐实践）
使用以下维度聚类：
- `error_type`
- `skill.name/version`
- `tool version`（若写入 manifest.versions）
- `design`（block、分支、策略）

治理输出：
- 高发 RESTORE_FAIL：多半是 restore 输入不规范/相对路径/版本兼容，优先治理 wrapper 与输入规范
- 高发 OUTPUT_*：多半是 contract 与脚本不一致，优先治理 Skill 资产规范
- 高发 HEARTBEAT/CRASH：偏 infra 或工具稳定性，推动环境与资源治理

---

## 7. Infra/Ops：会话与资源排障入口

### 7.1 dsub 相关（首要入口）
查看：
- `session/supervisor.log`

关注：
- 队列资源不足、排队时间异常
- 运行节点不可用/挂载失败
- license 获取失败
- module/环境变量不一致

### 7.2 会话健康（心跳与退出码）
查看：
- `session/heartbeat` 最后更新时间
- `session/state.json`（pid/exit_code/last_heartbeat_ts）
- Innovus stdout/stderr tail

判定方向：
- heartbeat 停止且 exit_code 异常：INNOVUS_CRASH
- heartbeat 停止但 exit_code 未知/无：HEARTBEAT_LOST（可能被 kill 或卡死）
- heartbeat 正常但 queue timeout：脚本卡住或执行器异常

---

## 8. 标准化“问题上报模板”（推荐复制粘贴）

当你需要请求 CAD/Infra/Skill 维护者支持，推荐提供：

- 结论：PASS/FAIL + error_type（来自 summary.md）
- run_dir 路径：
  - `CWD/.skillpilot/runs/<job_id>/`
- debug_bundle 路径（FAIL 必有）：
  - `.../debug_bundle/`
- 最后一个失败 ack：
  - `.../ack/<request_id>.json`
- 关键日志（若需要）：
  - `.../session/supervisor.log`（tail）
  - `.../session/innovus.*.log`（tail）
- 你运行时的意图描述（可选，辅助理解）

> 原则：不要只贴日志截图；提供 debug_bundle 才能保证“离线可复盘”。

---

## 总结（运行与协作的硬标准）
- 运行只认 run_dir：**summary/reports/debug_bundle** 是你的三个入口。  
- 交付优先 debug_bundle：FAIL 必须可离线复盘、可稳定路由支持团队。  
- 排障从 error_type 入手：taxonomy 稳定，协作成本才会持续下降。  
- Skill 迭代以 contract/验收/证据为闭环：这决定了平台能否“越用越稳”。
