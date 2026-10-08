# 跨对象复用与覆盖边界

复用的是研究协议、正文和交付合同。每次研究仍需重定问题、核对来源、选择比较对象和图型，不能把既有案例的事实与判断直接换名使用。纵向演变、横向差异、两轴交汇和原有叙事文风保持不变。

`create_delivery_fixture.py` 提供八类小型教学研究包。对象、来源、日期、数量和图片均为预设虚构内容，没有真实检索，不可当作研究结论或方法效果证据。脚本使用固定数据和 Python 标准库，不联网，也不在运行时调用模型补写 JSON；生成目录必须不存在或为空。

```text
python <skill-dir>/scripts/create_delivery_fixture.py --kind product --destination <新目录>
python <skill-dir>/scripts/build_delivery.py <新目录>/study.json
```

把 `--kind` 改成下表任一类型即可生成另一题材，构建入口无需改代码。每个样例只选择三种与问题有关的组件；这是测试覆盖的取样，不是正式报告的组件数量要求。

| 类型 | 虚构对象与核心问题 | 选择的交互组件 |
|---|---|---|
| `product` | 栖光台灯：局部更换与维护负担 | `images`、`comparison`、`calculator` |
| `industry` | 澄湾循环包装：归还、清洗与调度 | `relationships`、`series`、`scenarios` |
| `company` | 栈桥档案服务社：共享工具与例外处理 | `timeline`、`comparison`、`series` |
| `technology` | 层窗采样：资源节省与漏检边界 | `process`、`evidence`、`calculator` |
| `protocol` | 信笺交换：重发、去重与兼容条件 | `process`、`glossary`、`relationships` |
| `policy` | 澄湾错峰装卸：通行改善与负担转移 | `timeline`、`scenarios`、`evidence` |
| `person` | 林澈的公共档案方法：参与与解释权 | `timeline`、`evidence`、`glossary` |
| `event` | 澄湾步行桥临时关闭：当时信息与事后评价 | `timeline`、`relationships`、`scenarios` |

八类合计覆盖十种交互组件。时间线展示转折与说明；比较表检查相同问题下的差异；过程展示步骤；关系图查看参与者；情景切换条件；证据组件并列支持边界与反方；图片使用热点解释形态；词表保留例子与反例；序列支持查看数值；计算器只计算显式声明的线性假设。交互不会补出缺失证据，计算器也不提供未经验证的预测。

现有静态视觉系统继续支持六类图：`timeline`、`bar`、`line`、`donut`、`matrix`、`knowledge_graph`。它们来自 `data/visuals.json`，由同一场景模型输出 SVG 并绘入 PDF。交互组件中的 `series` 覆盖条形与折线表达，但十种交互组件并不等同于六类静态图的逐项替代。数据不适合绘图时保留定性比较；fixture 不为了覆盖另造六张静态图。

每个研究包用 `study.json` 指向同一份 `report.md`、`sources/sources.json` 与 `data/components.json`，需要静态图时再指定 `visual_spec`。默认交付包含 PDF、离线 HTML、Markdown、组件 CSV、来源与组件 JSON，以及交付清单。PDF 与 HTML 复用正文、来源编号和组件内容；HTML 提供交互，PDF 保留静态表达和参数条件。产品样例中的 PNG 由脚本原生绘制，并标为虚构结构示意；它不能代替正式产品研究中的真实素材核验。

DOCX、PPTX、独立图包或其他格式按用户用途另行组织和验收，当前交付脚本没有专用 DOCX/PPTX renderer，不能因已有 Markdown 或 HTML 就声称这些格式已经交付。

覆盖审计应分别记录：八类 fixture 是否通过来源结构和组件校验，是否完成默认五类格式构建，HTML 交互是否实际操作，PDF 是否逐页检查。固定 fixture 重跑内容应一致，非空目录必须拒绝。结构和构建通过只说明合同可复用；视觉检查、真实原文支持和方法有效性仍需独立验收。仅在实际运行的平台标记实机结果。

2026-10-08 在 Windows 本机完成以下验证：

- 八类样例通过来源结构与组件校验；固定输入在不同目录生成的文件逐字节一致，拒绝覆盖非空目录。
- 八类均由同一个构建入口生成 PDF、离线 HTML、Markdown、CSV 与 JSON，合计 24 个交互组件；原正文块均保留。
- Chromium 实际操作全部十种组件，并检查 32 组桌面、手机与重排布局，以及无 JavaScript 阅读、离线操作、引用、笔记隔离与导入导出；未发现脚本错误或外部请求。200% 检查采用等效宽度重排，未声称已检查浏览器原生缩放。
- 八份 PDF 合计 34 页已提取文字并逐页查看渲染图，未发现缺字、内容裁切或重叠。之后的修改只涉及 HTML 外观；PDF 内容与渲染器未变。
- 产品与行业的整个交付包迁至新目录后可重建；审计阻止读取原目录，实际原目录读取尝试为零。
- 独立执行者仅根据新版 skill 和原始协议研究材料，完成元数据、章节位置与情景配置后生成 HTML 和 5 页 PDF；未修改前端或转换器，也未询问输出格式。
- 组件测试 27 项中 26 项通过、1 项因 Windows 符号链接权限跳过；交付集成测试 10 项通过，包含原有六类静态图的双格式构建。旧 PDF 构建器、初始化脚本和 skill 包检查通过。

公开验证摘要见[版本验收记录](https://github.com/Rolling-Log/orthogonal-research-skill/blob/main/docs/validation/v3.2.0.json)，样例见[在线演示](https://rolling-log.github.io/orthogonal-research-skill/)。使用 `create_delivery_fixture.py` 可在新目录重建对应输入。这些结果证明已覆盖路径的复用与呈现可用，不证明虚构材料的研究有效性。其他操作系统和浏览器尚未实机验证；新增复杂模型仍需有针对性的验收。
