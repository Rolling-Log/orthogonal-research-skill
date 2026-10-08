# 可复用研究组件协议 v1

组件补充已完成的研究叙事，用于读者查看不同事件、对象、步骤、关系、情景和证据。按研究问题选组件；没有适合交互的问题就用空数组，不要求每份报告集齐十类。此协议只接受下列十种结构，不接收 HTML、JavaScript、任意公式、网络图片或自定义插件。

先按需发现，再填写实际证据：

```text
python <skill-dir>/scripts/report_components.py --list
python <skill-dir>/scripts/report_components.py --describe scenarios
python <skill-dir>/scripts/report_components.py --validate data/components.json --sources sources/sources.json --workspace .
```

`--describe KIND` 只返回该类的可编辑示例和简短说明。示例中的文字、数字和来源占位须替换；图片示例须提供实际本地文件。

## 公共结构

文件为 UTF-8 JSON：

```json
{
  "version": 1,
  "components": [
    {
      "id": "mechanism",
      "kind": "process",
      "title": "解释机制的标题",
      "intro": "读者通过这些步骤能核查什么问题。",
      "source_ids": ["S001"],
      "after_heading": "三、横向分析：竞争图谱",
      "steps": [
        {"id": "input", "title": "输入", "body": "基于真实材料解释输入如何影响后续步骤。"}
      ]
    }
  ]
}
```

`version` 必须是整数 `1`。`components` 可以为空，最多 30 个。每个组件必需 `id`、`kind`、`title`、`intro`、`source_ids`，以及该类型的专用字段；不接受未知字段。

`id` 为 1–64 位 ASCII slug：首位字母，其后只用字母、数字、下划线或连字符。组件 ID 在文件内唯一，事件、步骤等子项 ID 在各自数组内唯一。不同组件可以复用子项 ID。关系连接通过本组件的节点 ID 引用；比较行必须给出全部列 ID，缺失数据填 `null`。

`after_heading` 是可选的原稿标题文字，不带 Markdown 的 `##`。构建入口核查它在原稿中精确且唯一匹配，再将组件放在对应位置。省略时统一放在正文后、文末信息来源章节前。原始研究 Markdown 保持不变；静态组件由构建时临时内容承载。

`source_ids` 至少 1 个、最多 100 个，格式为 `S001`，不得重复，且每个 ID 必须已在来源台账。组件公共导读产生兼容现有编号系统的 `{{@S001,@S002 |}}` 引文，所有列出的来源都会被引用。一个组件使用多项材料时，导读或具体说明应解释材料的支持边界；结构检查不替代研究语义检查。

## 十种有限结构

下表省略公共字段；`?` 表示可省略。除注明例外，数组最多 30 项；默认至少 1 项。所有 `id` 都遵循公共 slug 规则。

| kind | 专用字段 | 适用问题 |
| --- | --- | --- |
| timeline | `events:[{id,date,label,detail,category?}]` | 事件何时发生，转折带来什么变化；`date` 是短文本，可写历史时期或不确定日期，不强造精确日历日期。 |
| comparison | `columns:[{id,label,unit?}], rows:[{id,label,values:{columnId:值},detail?}]` | 对象在同一维度下有何差别；值接受字符串、有限数或 `null`。 |
| process | `steps:[{id,title,body}]` | 机制如何逐步发生；数组顺序就是步骤顺序。 |
| relationships | `nodes:[{id,label,detail}], links:[{from,to,label,kind}]` | 谁和谁如何关联；连接 `kind` 只能为 `fact` 或 `hypothesis`，连接数组可为空，不把假设显示为事实。 |
| scenarios | `cases:[{id,title,when,text,outcomes:[{label,value}],limitation}]` | 在什么条件下出现什么结果；结果值接受字符串、有限数或 `null`，每个情景必须交代限制。 |
| evidence | `items:[{id,title,statement,limit,kind}], conclusion` | 材料究竟支持什么、不能推出什么；`kind` 是短文本材料类型，`conclusion` 由研究者独立写明，筛选材料不自动重新推导结论。 |
| images | `items:[{id,path,alt,caption,points:[{x,y,title,body}]}]` | 图中哪个位置说明什么；标注数组可为空，`x/y` 为距左、距上 0–100 的百分比。 |
| glossary | `items:[{id,term,definition,example?,counterexample?}]` | 一个术语是什么、何时适用、什么不是它。 |
| series | `mode,unit,basis,x:[文本],series:[{id,label,values:[数值或null]}]` | 在共同口径下如何随横轴变化；`mode` 仅 `bar` 或 `line`，最多 12 个序列、120 个横轴位置；每个值数组必须与 `x` 等长。 |
| calculator | `inputs:[{id,label,value,min,max,step,unit}], outputs:[{id,label,unit,base,terms:[{input,coefficient}]}], assumptions` | 明确假设下，改变输入如何改变有限线性结果；详见下段。 |

`title`、标签、日期、单位等短文本最多 300 字符；正文、定义、边界等最多 20,000 字符。正文不按此上限凑长度；超过单页的表格单元格由现有 PDF 构建器明确报错，应把长解释拆回叙事，不能静默截断。`unit` 可以为空；其他必需文本不能为空。`null` 保持“缺失”，不得自动转成零。

## 计算与数值边界

计算器只实现 `输出 = base + Σ(输入 × coefficient)`，不解析表达式、不执行 `eval`。输入要求有限数值、`min < max`、默认值在区间内、`0 < step <= max-min`；默认值须落在 `min + 整数 × step` 的步长格点上，允许通常二进制小数误差，避免网页初始输入即被浏览器判定无效。每个输出最多引用同一输入一次；需要合并系数时先完成合并。`terms` 可为空，表示常数输出。输入之间按独立区间处理，不支持隐含关联约束。

所有数值拒绝布尔值、NaN、Infinity 和浮点转换溢出。计算器另检查默认结果、每个端点乘积、整体区间上下界；有限输入仍可能产生无穷乘积，这类输入明确拒绝。PDF 保留默认值、输入上下界、步长、完整公式和各输出的精确线性区间，不只保存网页初始画面。输出区间是给定独立输入范围的计算边界，不声称是实测或预测区间。

## 文本、图片与输出安全

所有内容字段为纯文本。HTML 渲染器负责 HTML 转义；静态 Markdown 转换只负责自己的语法边界，避免双重转义。尖括号与普通反斜杠可以作为原文；常规竖线在表格中转义。会被既有 PDF 行内解析器解释的 Markdown 格式、反引号、链接、引用标记和 `\|` 字面序列明确拒绝；引用统一通过 `source_ids` 生成。换行和制表在静态行内内容中折叠为空格，不接受其他控制字符。组件文本不能承担 Markdown 富文本编辑器的职责。

`images.path` 相对研究包根目录，允许 PNG、JPG、JPEG；文件须存在且签名匹配。绝对路径、URL、网络共享路径、父目录穿越、指向包外的符号链接都拒绝。不会读取网络。规范 SVG 继续交由原有 `visuals.json` 管线处理；GIF、WebP 不在本协议的 PDF 图片支持范围。路径归一为正斜杠；生成 Markdown 时编码空格等路径字符。图像标注在 PDF 中完整展开为位置和说明表。

数据导出使用带 UTF-8 BOM 的 CSV，文件名为 `component-<id>.csv` 或 `component-<id>.<子表>.csv`。每行包含组件 ID、标题、来源 ID；关系分别导出节点与连接，图片另导出标注，计算器分别导出输入、输出与系数，比较另导出列定义。`null` 导出为空单元格；数值零保持 `0`。可能被电子表格解释为公式的文本以单引号保护；数值保持数值。导出不会沿现存文件符号链接写到目标数据目录外。

## 构建接口与验证边界

`scripts/report_components.py` 只依赖 Python 标准库：

```python
checked = validate_components(spec, source_ids, workspace)
static_md = components_markdown(checked)
csv_paths = export_tables(checked, output_directory)
```

校验返回独立副本，不修改输入对象。`workspace` 是现存研究包目录；传给 PDF 的 Markdown 图片基准目录须与它一致。`components_markdown` 不添加固定总章节标题，可传单组件数组供入口按标题插入；它展开所有条目、情景、证据边界、图注、反例和数值，不截成默认选项。`evaluate_calculator` 可对已校验组件计算默认或指定范围内输入，`calculator_ranges` 返回输出独立区间。

单元测试：`python <skill-dir>/scripts/test_report_components.py`。它覆盖十种协议、缺失值、引用、导出、数值边界、路径隔离及失效输入。通过表示协议和转换正常，不表示来源内容真实、判断有效或 PDF 外观已经审核。
