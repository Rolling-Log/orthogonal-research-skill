# 同一研究的可复用交付

完整研究默认 PDF 与 HTML 同时交付；用户明确只要一种时用 `--format pdf` 或 `--format html`。简单问答不启动完整交付。原有中文表达、纵横研究方法和 PDF 版式保持不变。

## 先选择理解任务，再选组件

阅读正文需要的目录、搜索、引用、来源详情、笔记、收藏、导出与响应布局已有实现；不要每次重新生成 CSS 和 JavaScript。页面随对象类型采用克制的编辑配色；有明确品牌色资料时可在 theme 中提供颜色和出处。无实体对象不强行放实物图。

用以下命令读取小型目录，只查看确实要用的协议：

```text
python <skill-dir>/scripts/report_components.py --list
python <skill-dir>/scripts/report_components.py --describe process
```

| 需要解决的问题 | 可复用组件 |
| --- | --- |
| 发生顺序、重要转折、后来补充了什么 | timeline |
| 在相同口径下比较路线、对象或方案 | comparison |
| 一件事如何一步步发生 | process |
| 谁依赖谁、资源或信息经过哪里 | relationships |
| 条件不同，结果和限制怎样改变 | scenarios |
| 材料支持什么、哪些判断仍有边界 | evidence |
| 检查可取得的实物、界面或文档图片 | images |
| 分清术语、例子与反例 | glossary |
| 比较数量或随时间变化，保留缺失与口径 | series |
| 在明确线性假设下调整输入 | calculator |

已有六类静态 SVG（timeline、bar、line、donut、matrix、knowledge_graph）继续由 `visuals.json` 生成，并同时进入 PDF 与网页。交互组件与这些静态图可组合使用。

组件不是章节清单，不要求每份报告全部使用。先写好必要论证；仅在操作能帮助理解、比较或核查时加入组件。AI、比特币等对象可同时涉及技术、行业、公司或制度，按问题组合，不能因一个类型标签缩窄研究边界。具体字段见 [report-components.md](report-components.md)；跨对象覆盖与边界见 [reuse-coverage.md](reuse-coverage.md)。

## 一份输入，两种正式阅读形式

初始化会生成 `study.json`、`report.md`、来源台账及空的 `data/components.json`。在当前项目内初始化，或显式提供 `--destination`。不要把开发资料散落到桌面。

`study.json` 的版本、对象 ID 和路径示例：

```json
{
  "version": 1,
  "id": "research-example-2026",
  "title": "研究对象：具体问题",
  "subject_type": "technology",
  "as_of": "2026-10-08",
  "report": "report.md",
  "sources": "sources/sources.json",
  "components": "data/components.json"
}
```

`subject_type` 用于编辑配色，可用 product、industry、company、technology、protocol、policy、person、event 或其他描述；不决定正文研究范围。`id` 使用字母开头的 ASCII slug，同一报告保持稳定，和研究截面共同隔离阅读记录。`as_of` 必须与来源台账一致。有静态图时增加 `visual_spec`，指定已有规范文件；可选 `theme: {"accent":"#0066cc","source":"编辑配色依据或真实出处"}`。文件路径相对 study.json 所在目录，不读取远程文件或包外图片。

`components.json` 结构为 `{"version":1,"components":[]}`。允许没有交互；不能为填满模板编造数据。组件的 `source_ids` 指向既有台账；`after_heading` 可指定正文内唯一的完整标题，将交互放在相关论证旁。省略时置于正文末的图解区域。语义审查仍需核对每项解释与原始材料，字段校验不能证明结论正确。

```text
python <skill-dir>/scripts/build_delivery.py <workspace>/study.json --check-only
python <skill-dir>/scripts/build_delivery.py <workspace>/study.json
```

默认写入研究包的 `delivery/`，可通过 `--output` 指定另一个交付目录。检查输入、构建到临时目录都成功后才替换正式产物；已有交付必须属于同一报告，且其受管理文件没有手工修改。若用户已修改导出文件，使用新的交付目录，不能覆盖其工作。

| 产物 | 用途 |
| --- | --- |
| report.pdf / report.html | 同一研究的静态和交互阅读 |
| report.md | 含组件全部静态解释的完整可编辑稿 |
| source.md / study.json | 保留正文作为重建入口；可把整个交付包搬到新目录重建 |
| sources.json / components.json | 共用证据与交互数据 |
| report.json | 带稳定块编号、结构和来源 ID 的内容，供其他文档或演示转换器复用 |
| data/*.csv / data/raw/ | 表格导出和引用的本地原始数据 |
| visuals/ / media/ | 静态图和实际使用的本地图片 |
| manifest.json / build/ | 文件哈希、生成范围、实际构建结果；语义和视觉审查分别记录 |

HTML 图片、样式和脚本内嵌，可单文件离线阅读；访问外部原文仍需联网。PDF 由原构建器生成，保留原字体、分页与引用风格；不是把交互页面简单截成 PDF。所有预设情景、机制步骤、材料边界、系列数据、图片说明都展开进入 PDF。连续计算保留公式、假设、默认结果与声明输入范围下的上下界，不穷举所有输入。

编译不改写原 `report.md`，不再检索或调用模型。新研究仍需撰写和核验内容，必要的交互规则也仍需作者提供。节省的是重复实现与转换，不承诺无依据的 token 比例。

## 其他交付与真正的扩展

需要可编辑 Word、演示文稿、原生表格或出版级图时，从同一 report.json、Markdown、CSV、数据与图像交给环境已提供的相应工具；沿用它们的模板和渲染检查，不为每个研究重新写格式转换器。当前本 skill 内置交付是 PDF、HTML、Markdown、CSV、JSON 和已有 SVG，未内置原生 DOCX、PPTX、XLSX 作者工具，也不把 HTML 改后缀当成原生文件。

交互图谱不代表因果已证实；证据勾选只改变查看材料，不自动计算可信度；预设情景不是预测；线性计算器不是通用金融或科学仿真。复杂空间地图、真实 3D、音视频标注、专门实验或非线性模型若有实际需要，复用合适的现成工具或增加一个有明确输入输出的新组件，保留对应静态解释和验证。不要把所有可能能力预装到每份报告。

## 验证

源台账检查、PDF 渲染检查、浏览器交互检查各司其职。使用虚构 fixture 验证功能时，明确标记虚构，不把它当作领域研究。

```text
python <skill-dir>/scripts/create_delivery_fixture.py --kind industry --destination <temporary-study>
python <skill-dir>/scripts/build_delivery.py <temporary-study>/study.json
python <skill-dir>/scripts/test_report_components.py
python <skill-dir>/scripts/test_delivery.py
python <skill-dir>/scripts/check_package.py
```

正式交付前逐页检查 PDF，并检查 HTML 的桌面/手机布局、主要交互、来源、无 JS 可读性、离线使用、笔记隔离及页面底部可达性。只声明实际运行过的环境；Windows/Chromium 通过不代表其他系统或浏览器已实测。
