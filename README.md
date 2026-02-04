# SkillPilot：面向 Innovus 的 Skill 驱动自动运行与洞察平台

## 总览（Executive Summary）
SkillPilot 是一个面向 EDA（以 Cadence Innovus 为核心）的 **Skill 驱动智能化自动运行与洞察平台**。用户只需表达意图（例如“看下 XX design 的整体情况”或“对 A/B/C/D 跑 timing health 并对比”），SkillPilot 即可自动完成从 **Design DB 定位、独立 Session 启动、DB 恢复、Skill 执行、输出验收、证据收集、汇总对比** 到 **失败可复现定位** 的全链路闭环。

SkillPilot 的核心不是“跑脚本”，而是把分析能力沉淀为可管理的 **Skill 资产**，把运行过程固化为可审计的 **证据协议**，把失败归因固化为稳定的 **诊断分类**，从而让 Skill **越用越稳、越标准、越可诊断、越可运维**。

---

## 1. 项目目标（Project Goals）
### 1.1 业务目标
- **意图驱动**：用户用自然语言表达“想看什么/想对比什么”，平台自动完成全流程。
- **稳定交付**：每次运行产出标准化报告与结构化汇总，可用于评审、交付、对比。
- **可复现排障**：失败必须输出可复现的最小证据包，支持 CAD/工具/方法学协同定位。
- **资产化沉淀**：把分析方法固化为 Skill（contract + 模板 + 验收 + 版本），形成持续迭代闭环。

### 1.2 工程目标
- **确定性执行链路**：关键决策与执行路径确定、可回归，不依赖大模型“临场规划”。
- **证据优先（Evidence-First）**：所有结论都可追溯到证据文件（manifest/timeline/ack/reports/session）。
- **会话隔离**：每个 design 每次运行一个独立 Innovus Session，避免状态污染，提升可复现性。
- **统一验收**：每个 Skill 都由 contract 驱动输出验收（缺失/为空即失败），确保结果可信可对比。

---

## 2. 项目价值（Why SkillPilot）
### 2.1 对设计团队（Design）
- 从“人肉跑 Innovus + 手工翻日志”升级为“意图 → 证据化洞察”，显著降低反复劳动。
- 结果更稳定：输出有 contract 保障，可自动判定完成度与可信度。
- 更易对比：summary.json 固化结构化指标，天然支持 A/B/C/D 批量运行与对比。

### 2.2 对 CAD/方法学（CAD/Methodology）
- Skill 标准化：把经验变成可版本化、可评审、可回归的资产，而不是散落脚本与口口相传。
- 故障可诊断：稳定的失败分类（taxonomy）+ debug_bundle 证据包，缩短定位链路。
- 运维可控：run_dir 证据目录形成天然审计面，适合纳入持续集成与质量门禁。

### 2.3 对基础设施与运维（Infra/Ops）
- 会话生命周期清晰：dsub -I + supervisor 管理 Innovus，日志与状态都有固定落点。
- 失败可复盘：不依赖“当场复现”，debug_bundle 即可进行离线分析与协助升级。

---

## 3. 总体技术架构（High-Level Architecture）
SkillPilot 采用“**交互前端 + 确定性后端**”分层架构：

### 3.1 Claude Code 前端（意图层）
- 负责与用户交互：澄清 design/skill/对比对象、处理多候选 DB 选择、展示结果与证据路径。
- **不负责关键执行决策**：不自行猜测 DB、不绕过协议执行、不用“模型规划”替代确定性链路。

### 3.2 SkillPilot Runtime 后端（执行与证据层）
- 负责确定性执行：创建 run_dir、定位 DB、启动 Innovus、运行 Skill、验收输出、生成汇总与证据包。
- 负责证据协议：manifest/timeline/request/ack/reports/session/summary/debug_bundle 全量留痕。
- 负责失败归类：稳定 taxonomy，保证同类故障可聚类、可统计、可治理。

### 3.3 Innovus Session（工具层）
- 每个 job 启动一个 Innovus no_gui 常驻 session。
- 通过 queue_processor 在 Innovus 内部执行脚本（白名单 source），并回写 ack 与心跳。

---

## 4. 关键技术组件（Key Components）
### 4.1 Design DB Locator（DB 定位器）
- 输入可为 `name` 或 `path`，定位 `XXX.enc` 与 `XXX.enc.dat`。
- 多候选返回 candidates，**不擅自选择**，由前端交互确认后继续。

### 4.2 Session Supervisor（会话监督器）
- 以 `dsub -I` 启动 Innovus，采集 stdout/stderr，维护 session/state。
- 监控 heartbeat，判定会话失活（HEARTBEAT_LOST）与崩溃（INNOVUS_CRASH）。

### 4.3 Innovus queue_processor（工具内执行器）
- Innovus 内常驻轮询 queue，执行 request 中声明的脚本。
- 严格白名单：只允许 source `run_dir/scripts/` 下脚本，防止不可审计执行。
- 每次执行生成 ack（PASS/FAIL + error_type + message + evidence_paths），并周期性写 heartbeat。

### 4.4 Skill（能力资产）
- 每个 Skill 由以下组成：
  - `contract.yaml`：输入/输出/验收与排障提示（debug_hints）
  - `templates/run.tcl`：执行模板（输出必须落到 reports）
  - `tests/mock/`：不依赖 Innovus 的回归夹具与说明
- Skill 可组合：一个“意图”可触发多个 Skill 或对多个 design 批量执行，最终汇总对比。

### 4.5 Contract Validator（验收器）
- 对 required outputs 做强制验收（存在/非空/路径约束），保证“跑完 ≠ 合格”，合格必须可证据化。

### 4.6 Evidence Bundle（证据体系）
- run_dir 是本次运行的事实源（SSOT）。
- debug_bundle 是失败最小可复盘材料，适合跨团队/跨时区交付支持。

---

## 5. 可行性依据（Feasibility & Engineering Rationale）
- Innovus 的 no_gui 模式天然适合自动化运行，且脚本可控、输出可落盘。
- dsub -I 与现有 CAD 环境契合：能继承企业队列/资源/许可治理方式，便于运维对接。
- “每个 job 独立 session + 证据目录”是 EDA 自动化领域可复现性的最有效工程实践之一：
  - 避免 session 污染
  - 保留最小可诊断上下文
  - 支持回归与质量门禁

---

## 6. 关键实现方式（How It Works）
### 6.1 核心执行流水线（确定性状态机）
1. 初始化 run_dir（固定落 CWD/.skillpilot/runs/<job_id>/）
2. 定位 DB（enc + enc.dat）
3. 启动 Innovus session（dsub -I + no_gui + bootstrap）
4. restore DB（通过 restore_wrapper.tcl）
5. 执行 Skill（通过 request/ack 将 scripts 送入 Innovus）
6. contract 验收 outputs（缺失/为空即失败）
7. 生成 summary.json + summary.md（结构化 + 人类可读）
8. 失败则生成 debug_bundle（最小复盘材料）

### 6.2 restore 的工程约束（关键稳定性点）
为避免 enc 相对路径依赖导致的现场不稳定，restore_wrapper 强制：
- `cd` 到 enc 所在目录
- 再 `source enc`

这条规则固定写入协议与落地实现，作为全平台稳定性基线。

### 6.3 “对比”与“批量”的实现策略
- 对 A/B/C/D 批量运行：并发由 orchestrator 控制（max_parallel），每个 design 独立 run_dir 与 session。
- 对比输出：各 run_dir 生成结构化 summary.json，前端可聚合显示差异；后端保持确定性，不在运行期“猜对比逻辑”。

---

## 7. 使用场景（Typical Use Cases）
### 7.1 单 design 健康检查
- “看下 XX design 的整体情况”
- 输出：summary_health 报告、关键告警、证据路径

### 7.2 批量 timing health 与对比
- “对 A/B/C/D 跑 timing health 并对比”
- 输出：每个 design 的 run_dir + 汇总对比表（结构化指标差分）

### 7.3 回归与质量门禁（CAD）
- nightly 对关键 block 运行固定 Skill 集合
- 以 summary.json 聚合趋势，任何失败必须携带 debug_bundle，可自动派单/归因统计

### 7.4 Skill 迭代闭环
- 发现某类失败高发 → 通过 taxonomy 聚类 → 改进 wrapper/脚本/contract → mock 回归 + 集成回归 → 稳定性提升

---

## 8. 弱模型、无互联网的设计考虑（Weak-Model / Air-Gapped）
SkillPilot 将“大模型能力”限定在 **交互与表述**，将“关键决策与执行”压到 **确定性后端**，因此在弱模型或无互联网环境仍能稳定工作：

- **无互联网**：runtime 不依赖联网，所有输入来自本地 DB 与 subskill 资产；证据落本地 run_dir。
- **弱模型**：即便模型能力不足，仍可通过确定性 API/参数触发同样的执行流水线；模型最多影响“解释文本”，不影响结果正确性。
- **可替代前端**：Claude Code 只是默认入口；未来可接入其它 UI（Web/Slack/CLI wrapper），协议与后端不变。

---

## 9. 能力长期演进与维护（Evolution & Operations）
### 9.1 长期演进路线
- Skill 资产库持续扩展：从 health、timing、congestion、power/IR、DRC 相关分析逐步覆盖。
- 对比维度增强：跨版本、跨 PVT、跨 floorplan、跨策略参数的结构化指标对比。
- 质量治理闭环：按 error_type、design、skill、工具版本维度统计失败与波动，推动稳定性工程化治理。

### 9.2 可维护性原则
- 协议先行：任何新增能力先定义 contract/outputs/证据，再实现脚本。
- 向后兼容：所有关键文件带 schema_version，升级必须可解析历史 run_dir。
- 可诊断优先：FAIL 必出 debug_bundle；日志与证据路径要“可交付给别人就能定位”。

---

## 10. 名称与术语（Glossary）
- **Skill**：面向某一类洞察的标准化能力包（contract + templates + tests + docs）。
- **Job**：对某个 design DB 执行一次（restore + skill + validate + summarize）的完整运行。
- **run_dir**：该 job 的证据目录，包含事实源文件与所有产物。
- **Session**：一个独立 Innovus no_gui 进程实例。
- **request/ack**：runtime 与 Innovus 内执行器之间的文件队列协议。
- **contract**：对 Skill 的输入/输出/验收/排障提示的正式声明。
- **debug_bundle**：失败最小复盘材料包，用于离线定位与协同支持。
- **taxonomy**：稳定的失败分类体系（用于统计、治理与快速路由支持团队）。

---

## 总结（What Makes This Project “Professional”）
SkillPilot 把 EDA 自动化中最难的三件事工程化落地：  
1) **确定性执行**（不靠“模型规划”来赌稳定性）  
2) **证据化交付**（每次运行都能审计与复盘）  
3) **资产化沉淀**（Skill 可版本化、可回归、可迭代）  

这使它不仅能“跑起来”，更能长期“跑得稳、跑得标准、跑得可诊断”。

---

# 文档导航（从理念到落地：开发必读顺序）

> 下列文档用于把上述理念完整落到可开发、可测试、可运维的工程实现。

1. **`docs/PROTOCOLS.md`（SSOT）**  
   定义 run_dir 结构、manifest/timeline/request/ack/summary/contract/debug_bundle 的字段级协议与强制约束。  
   任何实现以此为准。

2. **`docs/ARCHITECTURE.md`**  
   定义系统分层、组件边界、状态机、数据流与关键设计决策（Why + How）。  
   用于指导模块划分与接口设计。

3. **`docs/DEVELOPMENT_SPEC.md`**  
   定义开发落地规范：dsub -I supervisor、Innovus queue_processor、restore wrapper、白名单安全、subskill 资产化、验收与证据产出要求。  
   用于指导“怎么写代码、怎么落地到可运维形态”。

4. **`docs/TEST_SPEC.md`**  
   定义测试分层（协议/Mock/集成）、发布 Gate、用例矩阵、失败注入策略。  
   用于确保“越用越稳”的工程闭环。

5. **`docs/RUNBOOK.md`**  
    定义用户运行方式、常见失败排障路径、debug_bundle 交付口径，以及 CAD/运维的定位入口。  
    用于现场推广与跨团队协作支持。

6. **`docs/MIGRATION_GUIDE.md`**  
    定义从 pseudo 环境迁移到真实生产环境（Innovus + dsub -I）的步骤。  
    包含 `SupervisorDsubI` adapter 实现示例、真实 `bootstrap.tcl` 模板、配置说明和常见问题。

7. **`docs/TESTING_GUIDE.md`**  
    定义测试分层（L0/L1/L1.5）、运行方式、添加新测试的规范。  
    用于确保代码质量与持续集成。

---

## 当前实现状态（Current Status）

### ✅ 已完成（Implemented）

- ✅ 协议层（manifest/timeline/request/ack/summary/debug_bundle/contract）
- ✅ Locator（explicit_path/cwd_scan/multi-candidate）
- ✅ PseudoSupervisor + PseudoSession（本地测试适配器）
- ✅ Contract Validator（contract 校验与输出验证）
- ✅ Orchestrator 状态机（完整执行流水线）
- ✅ Debug Bundle 生成（失败最小复盘材料）
- ✅ Mock Subskill（summary_health_mock）
- ✅ 测试套件（37 个测试全部通过）

### 🔄 待实现（To-Do for Production）

- 🔄 `SupervisorDsubI` adapter（真实 dsub -I + Innovus）
- 🔄 真实 `bootstrap.tcl`（Innovus queue_processor）
- 🔄 真实 Skill TCL 脚本（使用 Innovus API）
- 🔄 L2 集成测试（真实环境）

---

## 快速开始（Quick Start）

### 本地测试（Pseudo 环境）

```python
from pathlib import Path
from skillpilot.orchestrator import Orchestrator

# 创建伪设计 DB
(Path("./test.enc")).write_text("# Mock enc")
(Path("./test.enc.dat")).write_text("")

# 运行 Job
orchestrator = Orchestrator(cwd=Path("."), skill_root=Path("./subskills"))
result = orchestrator.run_job(
    design_query="./test.enc",
    skill_name="summary_health_mock",
)

print(f"Status: {result.status}")
print(f"Run dir: {result.run_dir}")
```

### 运行测试

```bash
# 安装依赖
pip install pytest pyyaml

# 运行所有测试
pytest tests/ -v

# 运行特定测试层
pytest tests/unit/test_l0_protocol.py -v  # L0: 协议测试
pytest tests/unit/test_l1_components.py -v  # L1: 组件测试
pytest tests/pseudo/ -v  # L1.5: 伪集成测试
```

---

## 项目结构（Project Structure）

```
skillpilot/
├── skillpilot/              # 核心运行时
│   ├── protocol/            # 协议层
│   ├── adapters/            # 适配器层（pseudo/dsub-i）
│   ├── orchestrator/        # 状态机与作业编排
│   ├── locator/            # DB 定位器
│   ├── contracts/          # 合约验证器
│   ├── kernel/             # 执行内核
│   └── skills/             # Skill 资产库
├── subskills/              # 实现 Skill
│   └── summary_health_mock/
├── tests/                 # 测试套件
│   ├── unit/              # L0/L1 单元测试
│   └── pseudo/            # L1.5 伪集成测试
└── docs/                  # 文档
```

---

## 测试覆盖率（Test Coverage）

| 测试层 | 测试文件 | 测试数量 | 状态 |
|---------|---------|----------|------|
| L0: 协议 | test_l0_protocol.py | 6 | ✅ 全部通过 |
| L1: 组件 | test_l1_components.py | 10 | ✅ 全部通过 |
| L1.5: 伪集成 | test_integration.py + test_additional.py | 21 | ✅ 全部通过 |
| **总计** | | **37** | ✅ **全部通过** |

---

## 迁移到生产环境（Migration）

详细迁移步骤见 `docs/MIGRATION_GUIDE.md`。

简要步骤：

1. 实现 `SupervisorDsubI` adapter
2. 创建真实 `bootstrap.tcl`  
3. 实现真实 Skill TCL 脚本
4. 配置 dsub 队列和资源
5. 运行 L2 集成测试

---

## 文档索引（Documentation Index）

| 文档 | 用途 | 读者 |
|------|------|------|
| PROTOCOLS.md | 协议 SSOT | 所有实现者 |
| ARCHITECTURE.md | 系统架构与设计决策 | 架构师、开发者 |
| DEVELOPMENT_SPEC.md | 开发规范与实现细节 | 开发者 |
| TEST_SPEC.md | 测试标准与发布门槛 | QA、开发者 |
| RUNBOOK.md | 运行手册与排障指南 | 用户、CAD、运维 |
| MIGRATION_GUIDE.md | 生产环境迁移指南 | 开发者、运维 |
| TESTING_GUIDE.md | 测试实践与扩展指南 | QA、开发者 |


