# 研究协议与证据模型

## 输入与边界

开始时形成内部研究简报：

```yaml
subject: 研究对象
type: product | company | technology | concept | person | industry | other
as_of: YYYY-MM-DD
focus: 用户特别关注点
geography: 全球或指定市场
audience: 决策者 | 从业者 | 公众 | 其他
deliverables: markdown,pdf,sources,data,visuals,images
```

默认以执行当天为研究截面，以全球为竞品发现范围，再按用户语境缩小。不得把截面日之后才出现的信息写成当时已知事实。

## 来源台账

`sources/sources.json` 使用以下结构。`display_name` 是文末编号参考文献使用的可读简称，不得写 `S001` 之类编号：

```json
{
  "as_of": "2026-07-13",
  "coverage": {
    "attempted_languages": ["zh-CN", "en"],
    "attempted_regions": ["中国", "美国", "欧洲"],
    "attempted_platforms": ["官网", "监管数据库", "arXiv", "GitHub", "Reddit"],
    "successful_source_categories": ["official", "academic", "media", "community"],
    "successful_domains": ["example.com"],
    "blocked_domains": [],
    "network_limitations": [],
    "target_perspective_groups": ["中文/中国大陆", "英文/北美"],
    "balance_exception": null
  },
  "limitations": [
    {
      "scope": "海外用户口碑",
      "cause": "目标论坛不可访问",
      "bias": "更偏向官方与媒体叙事",
      "affected_claims": ["C018"],
      "confidence": "low"
    }
  ],
  "sources": [
    {
      "id": "S001",
      "display_name": "公司 2025 年报",
      "title": "页面或文档完整标题",
      "url": "https://example.com/source",
      "publisher": "发布者",
      "published_at": "2026-06-30",
      "accessed_at": "2026-07-13",
      "language": "en",
      "region": "US",
      "perspective_group": "英文/北美",
      "independence_key": "original-company-filing-2025",
      "tier": 1,
      "type": "official",
      "supports": ["C001", "D001"],
      "notes": "指标口径、归档或访问限制"
    }
  ],
  "claims": [
    {
      "id": "C001",
      "claim": "可核验主张",
      "source_ids": ["S001", "S004"],
      "status": "verified",
      "confidence": "high",
      "counterevidence": []
    }
  ],
  "datasets": [
    {
      "id": "D001",
      "file": "data/revenue.json",
      "unit": "USD million",
      "definition": "财年确认收入",
      "period": "FY2025",
      "geography": "global",
      "source_ids": ["S001"]
    }
  ]
}
```

来源层级：

- Tier 1：官方公告、财报、监管文件、标准、论文、代码仓库、原始数据库；
- Tier 2：有原创采访或原始数据的权威媒体、研究机构；
- Tier 3：可归因的专家、社区讨论和评测；
- Tier 4：聚合、转载、SEO 页面，只能提供线索。

关键主张不能只靠 Tier 4。用户口碑可来自 Tier 3，但必须写平台、观察窗口、样本限制和可能偏差。多家媒体转引同一条通讯社或公告只算一个证据源。

执行时遵循“官方博客/公告/财报/原论文 > 权威媒体原创报道 > 转载/聚合”。每个关键事实都必须能映射到 claim 和来源；搜不到时写“公开信息暂缺”，不得补推。观点必须先陈述事实，再以“我觉得”“我的判断是”或“更可能的解释是”引出，并列证据与反证。

## 文化语言语境平衡

研究开始时声明 2–4 个 `target_perspective_groups`。`perspective_group` 同时表达主要语言和原始发布者所处的地区文化语境；英文北美与英文欧洲可分开，也可在样本较小时合并为“英文/欧美”。每条来源只能属于一个组。

只对最终实际引用、相互独立且属于 Tier 1–3 的来源计算占比。翻译、转载、同一通讯社稿或同一原始文件的镜像使用相同 `independence_key`，只计算一次，并沿用原始发布者的 `perspective_group`；Tier 4 即使出现在文末也不进入比例分母。每个目标组必须占 20%–80%。

若无法满足，在 `coverage.balance_exception` 写入 `cause`、非空 `attempts`、`bias`、非空 `affected_claims` 和 `confidence`（只允许 `low` 或 `medium`），同时在 `limitations` 添加对应记录，并在执行摘要与“研究范围与限制”复述。不得通过重复来源或无关来源凑比例。

文末参考文献按正文、图表、图谱和图注中的首次引用顺序编号。每条写全 `display_name`、`publisher`、`title`、`url`、`published_at` 和 `accessed_at`；构建器将其与内部来源 ID、URL 和首次出现顺序逐项核验。

## 检索矩阵与三轮关键词

每种语言对每条轴至少运行三组不同意图的关键词：

| 研究轴 | 第一组：起点/现状 | 第二组：变化/争议 | 第三组：反证/用户 |
|---|---|---|---|
| 纵向 | 创立、首次发布、提出者、前身；founded, launch, origin | 版本、融资、转型、收购、危机；release, pivot, acquisition, controversy | 失败、退出、投诉、反思；failure, shutdown, criticism, postmortem |
| 横向 | 替代、竞品、份额、定价；alternatives, competitors, share, pricing | 对比、迁移、监管、路线；versus, migration, regulation, architecture | 用户评价、问题、退款、锁定；reviews, issues, complaints, lock-in |
| 交汇 | 早期选择、路径依赖；early decision, path dependence | 优势根源、历史包袱；root cause, legacy constraint | 情景、预警、反证；scenario, warning signal, falsifier |

主要海外玩家再以当地语言检索“公司名 + 官网/财报/监管/评价”。先找当前官方入口，再沿引用、版本记录、存档和监管文档反向追溯早期资料。数字同时检索指标名、年份、地域和原始发布机构。

学术对象按顺序检查：原论文或预印本页面、会议/期刊正式版本、作者/实验室页面、复现代码与 issue、独立复现实验。不得把后来的二手解读当原论文结论。

## 饱和与最低覆盖

建立“轮次—查询—新增实体—新增事件—新增数据—新增反证”的搜索日志。连续两轮四类新增均为空，才可视为接近饱和。全球性报告默认目标：

- 独立来源 ≥20；
- Tier 1 来源 ≥8；
- 海外来源 ≥5；
- 每个主要竞品同时有官方、独立、社区三类视角；
- 每个高影响结论至少两个独立来源，或明确说明为何只有一个。

这些是研究目标，不是编造配额。达不到时在 `coverage` 与 `limitations` 记录尝试、失败、替代来源、受影响结论和置信度，并在报告执行摘要和研究限制中复述。

## 事实、争议、推断与假设

将材料标记为：

- `F` 事实：来源直接支持；
- `Q` 争议：来源冲突或口径不一；
- `I` 推断：多个事实归纳出的解释；
- `H` 假设：用于未来剧本，尚不可验证。

`F` 可直接陈述；`Q` 并列说法并解释时间、定义或利益立场；`I` 使用“我的判断是/更可能的解释是”并给证据链；`H` 使用“若……则……”并列触发与反证。

因果判断至少检查：时间先后、可能机制、替代解释、反事实、跨来源一致性。只满足相关性时用“伴随”“同期出现”，不能写成“导致”。

## 纵向阶段卡

每个阶段建立一张内部卡片：

```text
阶段名称与时间
外部环境与内部约束
关键人物和可选方案
实际选择及证据
短期结果
形成的新能力/新债务
进入下一阶段的触发事件
主要反证或资料缺口
```

阶段划分必须由战略、技术、组织或市场机制的改变驱动，不能机械按年份等分。

## 竞品选择与口径

先建候选池，再按三项评分选 3–5 个代表对象：

1. 需求重叠：是否完成相同用户任务；
2. 资源竞争：是否争夺同一预算、渠道、人才或注意力；
3. 战略参照：是否代表不同路线、间接替代或未来威胁。

明确区分直接竞品、间接替代和上一代方案。统一地区、币种、税费、套餐档位、统计期、活跃/注册/付费用户定义和版本。无法统一时不得强行排名。

## 三个未来剧本

每个剧本包括：

```text
剧本名与概率区间（避免伪精确点估计）
核心机制与历史根源
时间范围
3–5 个触发信号
至少 2 个反证信号
受影响对象
可监测指标与更新频率
```

基准剧本允许趋势延续中的摩擦；最危险剧本聚焦最脆弱的路径依赖；最乐观剧本要求出现可观察的能力、渠道或市场突破。

## 图片和数据台账

每个数据点记录值、单位、币种、时间、地域、样本、定义和来源 ID。只有可比数据才能同图。

`images/manifest.json` 推荐结构：

```json
{
  "images": [{
    "file": "images/fig_01_launch.jpg",
    "title": "首次发布现场",
    "creator": "机构或摄影者",
    "source_url": "https://example.com",
    "license": "official press asset / CC BY 4.0 / screenshot",
    "accessed_at": "2026-07-13"
  }]
}
```

删除不必要的敏感 EXIF；不可通过裁剪、重绘或生成式修改改变图片的事实含义。
