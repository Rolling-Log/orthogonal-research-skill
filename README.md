# orthogonal-research-skill

一个面向 Codex 的中文深度研究 skill，使用“纵向演进 + 横向竞争 + 交汇判断”的方法，产出可审计的研究报告。它包含来源台账、全球检索要求、证据约束、可视化、知识图谱、PDF 构建和交付前验收流程。

## 包含内容

- orthogonal-research-skill/SKILL.md：skill 本体和触发描述
- orthogonal-research-skill/references/：研究协议、报告规范、视觉系统、对抗审查和回归矩阵
- orthogonal-research-skill/scripts/：工作区初始化、可视化渲染、PDF 构建和包校验
- orthogonal-research-skill/assets/：字体、许可证、示例素材和 PDF 样式
- orthogonal-research-skill/vendor/reportlab/：PDF 构建所需的精简 ReportLab 代码及其许可证

## 安装

推荐在 Codex 中使用 skill 安装器，并指定仓库里的 skill 子目录：

~~~text
使用 $skill-installer 从
https://github.com/Rolling-Log/orthogonal-research-skill/tree/main/orthogonal-research-skill
安装这个 skill。
~~~

手动安装时，先克隆仓库，再把仓库中的 orthogonal-research-skill 子目录复制到：

~~~text
<CODEX_HOME>/skills/orthogonal-research-skill/
~~~

安装后的目录中应直接包含 SKILL.md、agents/、assets/、references/、scripts/ 和 vendor/。
## 使用

在 Codex 中提出系统性研究请求，例如：

~~~text
使用 $orthogonal-research-skill 研究某产品的起源、竞品、用户口碑和未来风险，并交付中文 PDF 报告。
~~~

skill 会先创建带时间戳的研究工作区，再按来源记录、纵向分析、横向分析、交汇洞察、可视化、写作和 PDF 验收顺序执行。联网工具、浏览器和图片素材由运行环境提供；skill 不内置凭据，也不会关闭 TLS 校验或绕过访问控制。

## 本地自检

在仓库根目录执行：

~~~bash
python orthogonal-research-skill/scripts/check_package.py
python orthogonal-research-skill/scripts/init_workspace.py --self-test
python orthogonal-research-skill/scripts/build_report.py --self-test
~~~

当前仓库的 GitHub Actions 会在 macOS 和 Windows 上使用 Python 3.9 与 3.12 运行这些检查。

## 许可证

本仓库原创内容使用 MIT License。内置字体和 ReportLab 代码保留各自上游许可证，详见：

- LICENSE
- THIRD_PARTY_NOTICES.md
- orthogonal-research-skill/assets/licenses/

研究报告中的外部网页、图片和数据仍由各自权利人负责，使用时请记录来源、许可和访问日期。