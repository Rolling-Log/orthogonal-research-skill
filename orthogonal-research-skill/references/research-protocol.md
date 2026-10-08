# 研究协议与证据模型

## 输入、范围与重要未知

形成内部研究简报，放在既有 `sources/research-log.json`，不要求使用者填写整张表：

```yaml
subject: 研究对象
type: product | company | technology | concept | person | industry | other
as_of: YYYY-MM-DD
purpose: 工作或探索目的；附用户明说/合理推定/暂缺
focus: 用户特别关注点
questions: 领域扫描后校正的必答问题及优先理由
geography: 全球或指定市场
prior_knowledge: 只记录用户明示；未给则按入门解释
reading_budget: 用户给出则记录，未给不编造
deliverables: markdown,pdf,sources,data,visuals,images
```

默认执行当天为研究截面，先全球发现相关路线，再尊重用户市场范围。回顾历史可以使用后发材料，但要区分它解释的事件期、材料发布日期和“当时已知”的信息。访问日不能冒充观测日；不能把截面之后出现的变化写成截面时已发生。

先提取请求，不重复问已有信息。只有不同答案会实质改变对象、边界或解释重心时问 1–2 个简短问题。缺知识水平或阅读预算通常不阻断；探索者不清楚用途时采用“定义—机制—演变—现状路线—争议与未知”的入门路径。用户明确要求 grill me 才开展详细访谈，不让新人提供他尚不懂的领域答案。

深挖前扫定义和易混概念、必要机制、关键转折、主要参与者与直接/间接/历史替代、争议及潜在遗漏。记录会改变理解的新问题、优先级变化及不展开的理由；不得因用户只提一个卖点而跳过必要机制。第一性原理在这里落实为待解释/实现的目标、必要机制、硬约束、可行路线及检验观察。

## 来源台账与技术兼容

`sources/sources.json` 是唯一来源与主张台账；数据实体用 `datasets` 连接 `data/` 中文件。保留 S/C/D 稳定 ID 和旧键。以下是**虚构结构演示**，example.com 和定位文字不是真实证据，不能复制为实际研究：

```json
{
  "method_version": "3",
  "as_of": "2026-07-13",
  "coverage": {
    "balance_policy": "diagnostic",
    "attempted_languages": ["zh-CN", "en"],
    "attempted_regions": ["中国", "美国"],
    "attempted_platforms": ["官网", "原始测试"],
    "successful_source_categories": ["official"],
    "successful_domains": ["example.com"],
    "blocked_domains": [],
    "network_limitations": [],
    "target_perspective_groups": ["中文/中国大陆", "英文/北美"],
    "balance_exception": null
  },
  "limitations": [],
  "sources": [{
    "id": "S001",
    "display_name": "模板产品说明",
    "title": "模板产品说明（虚构）",
    "url": "https://example.com/manual",
    "publisher": "模板机构",
    "published_at": "2026-06-30",
    "accessed_at": "2026-07-13",
    "language": "zh-CN",
    "region": "CN",
    "perspective_group": "中文/中国大陆",
    "independence_key": "template-manual",
    "tier": 1,
    "type": "official",
    "supports": ["C001"],
    "notes": "仅作字段示意，无真实原文。"
  }],
  "claims": [{
    "id": "C001",
    "claim": "模板机构公布了模块复用方案（虚构）。",
    "source_ids": ["S001"],
    "status": "provisional",
    "confidence": "low",
    "counterevidence": []
  }],
  "datasets": []
}
```

`supports` 与 claim/dataset 的 `source_ids` 双向对应，不存在的 ID 和错误方向都须修复；背景来源可 `supports: []`，不能为了填字段编造主张。文献只列实际在正文、表图或图注使用的来源。来源的 `display_name` 是可读简称，不能填内部编号。

日期使用 ISO 日 `YYYY-MM-DD`。发布日期确实不可得时写 `published_at: "unknown"` 并在 `notes` 说明，文献也显示 unknown；不造日期。截面、访问日和显式事件日期需保持各自含义。

新工作区明确 `method_version: "3"` 和 `coverage.balance_policy: "diagnostic"`。缺政策的旧数据仍执行旧 strict 文化比例规则；未知政策拒绝，不能用删键绕过旧承诺。旧成品技术重建不会自动获得 V3 方法审查状态；重研究应另生成包、说明截面并保留旧产物。

## 来源角色、独立根与覆盖诊断

Tier 用于寻找和追溯材料：1 为原始公告/财报/标准/论文/代码/数据库，2 为原创采访或测量，3 为可归因专家/社区/评测，4 为转载聚合和发现线索。层级不是一刀切真值排序。官方资料适合核验公告和规格，原创测试可能更适合真实效果；前者的动机、后者的方法与样本都要检查。关键主张不能只靠 Tier 4。

`independence_key` 标原始文件、数据、观察或试验根。翻译、转载、镜像沿用同根与原发布语境，不能循环印证。一个域名可有独立试验，多个域名也可共用一个根；缺 key 不自动认定独立。根数不自动决定置信度。直接公告日期可由原公告核验，效果外推或有动机的性能承诺则需要独立检验或限缩。

每条来源保留 `language`、`region`、`perspective_group`。目标语境组按研究对象相关性选择，不强制 2–4 组。实际引用的独立 Tier 1–3 来源按组诊断；20%–80%、来源总数和 Tier 数量只提醒可能偏斜，不是 V3 合格线。不得为凑比例引入无关材料，也不得以比例合格掩盖重要当地玩家缺失。同源组别冲突仍是错误。

`coverage` 记录检索语种、地区、平台、成功类别与域名、受阻域名、替代尝试和证据缺口。真实缺口放在 `limitations`，逐条写 `scope`、`cause`、`bias`、`affected_claims`、`confidence`；报告披露其具体影响。网络失败或来源比例本身不能机械降低全部判断的置信度。

社区材料仅在使用体验、故障、采用或传播问题有关时取得；记录平台、观察窗口、样本与选择偏差。概念机制不因缺消费者口碑而失败，反之产品体验结论不能只拿官方宣传充当用户证据。

## 高影响主张的最小合同

关键事实映射到 claim 和可靠来源。高影响指错误会改变核心机制理解、路线比较、工作风险或行动；不只指摘要中的句子。普通背景沿用基本结构，不给所有句子灌字段。高影响 claim 增：

- `impact_reason`：简述错误会改变什么。
- `kind`：`fact` / `disputed` / `inference` / `hypothesis`。
- `evidence`：与 `source_ids` 对应的证据条目，每条 `source_id`、`locator`、`supported_statement`、`support_boundary`、`time_basis` 均非空。
- 分析性主张的 `review`：`alternative`、`discriminating_evidence`、`change_condition`、`revision` 四个简短字符串。纯日期或原公告事实不必硬造因果反方。

`locator` 使用可复找的网页小标题/锚点/表行、PDF 页或章节、数据表指标；印刷页和文件页有差异时区分。没有精确页码就写可定位章节及局限，不编页码。`supported_statement` 简述来源实际表达；`support_boundary` 写不能推出的部分。`time_basis` 区分事件/观测期、公告期、访问日及版本；后发回顾不等于当时已知。原文不可得、只见搜索摘要时不能填成已读原文。

承重推断的**虚构字段片段**如下，不是另一份完整台账。合入完整台账时把对应 source.supports 同步补上 C002，并遵守原有 ID 双向关系：

```json
{
  "id": "C002",
  "claim": "模板中的模块复用可能降低重复工程，但利润影响未定。",
  "source_ids": ["S001"],
  "status": "provisional",
  "confidence": "low",
  "impact_reason": "影响是否把该路线视为成本优势。",
  "kind": "inference",
  "evidence": [{
    "source_id": "S001",
    "locator": "模板示意：模块复用章节，无真实原文",
    "supported_statement": "模板记载核心组件用于两个系列。",
    "support_boundary": "不提供对照成本或利润，不能证明经济净收益。",
    "time_basis": "模板公告期 2026-06-30；非实际观测。"
  }],
  "review": {
    "alternative": "系列复用来自渠道需求，协调成本可能抵消工程节省。",
    "discriminating_evidence": "同条件项目的重复工程与协调成本对照；本例没有。",
    "change_condition": "净成本对照无优势时撤回成本优势，仅保留技术复用事实。",
    "revision": "从必然降成本收窄为可能减少重复工程，利润仍未知。"
  },
  "counterevidence": []
}
```

混合报道对同一主张同时使用公告与原创测量时，在 evidence 标 `mixed_source: true`，显式 `root_keys: ["原始公告根", "独立测试根"]`；只写该主张实际使用的根。单根可继承 source.`independence_key`，无需重复。媒体整篇独立不等于每句独立，未标混合也不能免除独立审查者的溯根检查。

核心证据真实不可得时，允许 `source_ids: []`、`evidence: []`、非空 `support_gap`，并将 `status` 设 unresolved/provisional/hypothesis、`confidence` 设 low/medium；不得写 verified/high。空证据不证明假设成立，必须在正文悬置或限缩。有证据也可能不足，`verified` 仅是作者状态记录，不是脚本语义认证。

事实直接陈述，争议并列说法和口径，推断用“我的判断是/更可能的解释是”说明性质，假设用“若……则……”连触发与反证。置信度描述依据稳固程度，事件概率描述未来可能性，两者不混用；无依据不填概率。

## 检索、阶段与停止

根据当前承重问题选择查询，不机械按每种语言每轴三轮填格。可用起源/前身/提出者、版本/转型/危机、路线/替代/测量、失败/退出/反思、路径依赖/反事实等意图；对主要海外玩家补当地原始资料。数字同时寻找定义、统计期、地域和原发布者。学术对象先原论文与正式版本，再作者资料、复现代码/issue和独立复现实验；后来的讲解不能冒充原论文结论。

日志复用“轮次—问题/查询—新增实体/事件/数据/反证—改变了什么—下一步理由”。早期就检索最強合理反方，优先找能区分解释的证据；双方都预期的证据不能裁决。连续两轮无新增和来源数仅作停止线索，不能替代问题检查。停止时说明：关键问题已支持/限缩/悬置，什么仍未知，继续检索为何不太可能改变主要判断。

纵向阶段卡沿用：

```text
阶段名称与时间
外部环境与内部约束
关键人物及实际可选路线
选择及证据，短期结果
形成的新能力/新债务
下一阶段触发，反证与资料缺口
```

阶段由实际机制转变划分，不强制 3–6 段。横向按需求重叠、资源竞争、路线参照选择代表；明确直接、间接和历史替代，统一版本、地域、币种/税、档位、统计期、样本与定义，不可统一就不强行排名。

未来情景仅在工作问题需要预测时展开，写机制与历史根源、时间、触发、反证、影响对象和可观测指标。数量服从实际分歧，不强制三剧本、3–5 信号或概率区间。

## 图片、数据与结构检查

数据记录值、单位、币种、时间、地域、样本、定义与来源；只同图比较可比数据。`datasets.file` 指向报告包内实际存在的数据文件，不能用不存在路径充数。图片在 `images/manifest.json` 记录 file、title、creator、source_url、license、accessed_at，必要时加截图日。删除不必要敏感 EXIF，不修改事实含义。

写作前运行：

```text
python <skill-dir>/scripts/check_research.py sources/sources.json --output build/research-check.json
```

检查器只处理 ID 关系、日期格式/显式事件时间及高影响记录的可审查性。字段齐全和结构成功不能证明原文支持、因果或完整理解；未标高影响的承重判断由独立审查补查。依据 [adversarial-review.md](adversarial-review.md) 做实质审查，报告只呈现证据、判断、限制和修订结果，不呈现私有推理链。
