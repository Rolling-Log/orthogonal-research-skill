# 版本记录

默认使用最新版本；旧版本的 skill 保存在独立标签中，原始本地版本文件夹也继续保留。2026-10-08 是本次归档发布日，不代表这些历史版本的最初开发日期。

| 版本 | 内容 | 快照 |
|---|---|---|
| **V3.2.0 · 当前** | 同源 PDF 与交互 HTML、十类复用组件、八类对象验证、按需采集工具、在线演示 | [V3.2](https://github.com/Rolling-Log/orthogonal-research-skill/releases/tag/v3.2.0) |
| V3.1.0 | 定义与摘要之间的代表图片：1–4 张横排、每张 ≤10 字；PDF/HTML 构建与计数；单版本安装包；可视化主页 | [V3.1](https://github.com/Rolling-Log/orthogonal-research-skill/releases/tag/v3.1.0) |
| V3.0.0 | 依据读者用途组织研究；第一性原理、强反方、关键证据与不确定性进入研究和正文 | [V3](https://github.com/Rolling-Log/orthogonal-research-skill/tree/v3.0.0/orthogonal-research-skill) |
| V2.2.0 | 取证、引用、构建、图片与逐页验收可靠性修复 | [V2.2](https://github.com/Rolling-Log/orthogonal-research-skill/tree/v2.2.0/orthogonal-research-skill) |
| V2.1.0 | 封面自动显示全文字数与粗估阅读时间 | [V2.1](https://github.com/Rolling-Log/orthogonal-research-skill/tree/v2.1.0/orthogonal-research-skill) |
| V2.0.0 | 本地升级前基线 | [V2](https://github.com/Rolling-Log/orthogonal-research-skill/tree/v2.0.0/orthogonal-research-skill) |
| V1.0.0 | 仓库原有公开首版，原提交与标签保留 | [V1](https://github.com/Rolling-Log/orthogonal-research-skill/tree/v1.0.0/orthogonal-research-skill) |

## V3.2.0 · 2026-10-08

- 完整研究默认同时交付 PDF 与离线 HTML，共用正文、来源和组件数据；明确要求单一格式时按该格式交付。
- 新增十类通用组件：时间线、比较表、过程、关系、情景、证据、图片热点、术语、数据序列、线性计算器。PDF 保留步骤、情景、假设与静态说明，原有六类图表继续可用。
- 网页增加目录、搜索、引用定位、笔记与收藏、记录导入导出、手机适配和按对象调整的主题色；样式、脚本与图片内嵌，阅读和操作可离线进行。
- 新增 `study.json` 与统一 `build_delivery.py`；导出可编辑正文、表格、结构化数据与重建入口。更换题材通过内容和配置复用组件，构建无需调用模型。
- 加入 Agent-Reach 相关工具的按需发现与调用说明，补充网页、社区、字幕及代码材料的取证路径，继续使用原来源台账。
- 工作目录默认建立在当前项目。中文文风、纵横研究方法、原 PDF 排版及原 `build_report.py` 接口沿用。
- 用产品、行业、公司、技术、协议、政策、人物和事件八类虚构案例验证交付；主页增加实际渲染图和在线交互示例。

详见 [V3.2 验证记录](docs/validation/v3.2.0.json)与 [组件使用说明](orthogonal-research-skill/references/reusable-delivery.md)。

## V3.1.0 · 2026-10-08

- 将勃肯鞋单页测试中的代表图片布局纳入通用 skill；一张足够时只用一张，必要时最多四张，图片与短说明、来源同页。
- 支持 Markdown `representative-images` 容器，PDF / HTML 一致展示；保持比例，后文自然分页，短说明进入字数统计。
- 发布包只有一个 `orthogonal-research-skill/` 文件夹；包含字体、必要的 ReportLab 子集和许可证，不附带旧版或旧 Windows 图片转换二进制。
- 主页展示方法图、流程图、真实渲染样例和代表图片排版示例；固定的“下载最新版”链接始终指向当前发布。

旧版归档用于追溯；同名 skill 不适合同时安装多份。
