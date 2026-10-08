# 示例与图像来源

## V3.2 主页与演示

本版使用本项目生成的虚构教学样例。对象、数字、日期与来源均为预设，内容用于演示版式、交互与双格式交付。

- `images/hero.svg`、`images/research-method.svg`、`images/delivery-flow.svg`：本项目原生绘制的标题、研究方法与交付结构图。
- `images/web-overview.png`、`images/web-mobile.png`：产品样例的真实 Chromium 桌面/手机视口截图。
- `images/web-images.png`、`images/web-calculator.png`、`images/web-series.png`、`images/web-process.png`：2026-10-08 对相应 HTML 组件实际操作后截取的界面。计算器截图中把示意通道数改为 8。
- `images/pdf-reading.png`：技术样例实际 PDF 第三页（正文页码 2）的渲染图。
- `demos/product/`、`demos/industry/`、`demos/technology/`、`demos/protocol/`：由 V3.2 公共交付构建器生成的离线 HTML 与 PDF。HTML 的本地图片内嵌于页面；其中台灯图为脚本绘制的虚构结构示意。

上述素材没有使用第三方品牌照片。可用 `orthogonal-research-skill/scripts/create_delivery_fixture.py` 生成对应教学输入，再用 `build_delivery.py` 生成报告；具体命令见[复用覆盖说明](../orthogonal-research-skill/references/reuse-coverage.md)。

## 早期版式素材

以下为 V3.1 已保留的历史展示素材，本版主页不使用其中的品牌照片。


`hero.svg`、`workflow.svg` 和 `versions.svg` 为本项目绘制的方法与版本示意。

`sample-page-*.png` 是内置虚构样例的实际 PDF 渲染，用于展示格式；其中示例对象、数值与来源均不可当作真实研究结论。

`representative-example.png` 展示 V3.1 的代表图片排版。三个商品照片来自 BIRKENSTOCK 官方商品页，访问于 2026-10-08，依次为：

- [Arizona Birko-Flor 黑色](https://www.birkenstock.com/us/arizona-birko-flor/arizona-core-birkoflor-0-eva-u_1.html)
- [Boston Soft Footbed 绒面皮黑色](https://www.birkenstock.com/us/boston-soft-footbed-suede-leather/boston-suede-suedeleather-softfootbed-eva-u_49.html)
- [Arizona Essentials EVA 黑色](https://www.birkenstock.com/us/arizona-eva/arizona-eva-eva-0-eva-u_3716.html)

照片只作研究排版和形态辨认示例，按原比例缩放。图片及商标权利属于原权利人，未宣称开放许可，也不属于本项目的 MIT 授权。主页示例不代表 BIRKENSTOCK 认可或赞助本项目。
