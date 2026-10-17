# 步骤

## 步骤一：

```
我们正在开发「雾歇香薰」个人作品集网站。项目目录是 website/，技术栈是纯静态 HTML/CSS/JS，无构建步骤，绝对不引入任何框架、npm 包、CDN 依赖。

请读取我提供的 Figma 设计稿：<在这里粘贴你刚才复制的链接>

请根据该设计稿，帮我搭建首页的基本骨架。具体任务：

创建 index.html 和 css/style.css。

在 index.html 中按从上到下的顺序写出语义化标签（<header>, <main>, <section id="hero">, <section id="ai-entry">, <section id="brand-story">, <section id="product-series">, <footer>），暂时不用写具体内容，先用占位文字。

在 style.css 中定义 :root CSS 变量（颜色、字体、间距），请从 Figma 中提取实际的颜色值和间距值。

中文文案要克制、温和，不要堆砌感叹号，不要使用 emoji。

先不要做页面细节，先跑通结构。生成后请用一句话说明你改了什么。
```

```
请重新读取 Figma 设计稿（链接：<粘贴链接>），专门查看“产品系列”模块的排版。
目前 HTML 里的产品只是简单的文字堆叠，请帮我用 CSS Grid 把它们改成并排的卡片布局（桌面端一行 3 个）。每个卡片包含：图片占位、产品名、价格。只修改产品系列相关的 HTML 和 CSS。
```

```
我已经在 assets/images/ 文件夹里放好了图片（hero-bg.webp, product-1.webp, product-2.webp 等）。
请修改代码：

给 Hero 模块加上背景图 assets/images/hero-bg.webp，并确保文字在深色背景下依然清晰可读。

把产品卡片里的“图片占位”灰块，替换成真实的 <img src="assets/images/product-1.webp" alt="檀木">。

如果某张图片缺失，先用纯色背景撑住。
```

## 步骤二

```
我们正在开发「雾歇香薰」个人作品集网站，项目目录是 website/。

技术栈：纯静态 HTML/CSS/JS，无构建步骤，绝对不引入任何框架、npm 包、CDN 依赖。
已有文件：index.html、css/style.css、css/tokens.css（如果存在）、assets/。
设计基调：低饱和、东方木质调、克制。标题用系统宋体族，全站配色不超过 3 种。

现在要新增一个页面：AI客服页（文件名为 demo.html）。

请读取我提供的 Figma 设计稿：https://www.figma.com/design/AuQcgLLRaAsIDA2GFh92PH/Untitled?node-id=2-5652&t=PuyUI60HjsUjPnUG-11

具体任务：
1. 创建 demo.html，复用 index.html 中已有的导航栏和页脚结构（直接复制过来，保持链接指向正确）。
2. 根据 Figma 设计稿，搭建 AI 客服页的主体结构：
   - 页面标题与简介区
   - 对话消息列表区（包含 AI 消息气泡、用户消息气泡）
   - 预设问题按钮区
   - 输入框与发送按钮
   - 检索来源展示区（可折叠）
   - 检索过程可视化区（改写 query、向量分/BM25 分等）
3. 所有颜色、字体、间距必须引用 css/tokens.css 或 css/style.css 中已有的 CSS 变量，不要硬编码新颜色。
4. 新增的样式请追加到 css/style.css 中，不要覆盖已有样式。
5. 先只搭骨架，用占位文字（如“AI回答占位”“用户问题占位”），不要写真实交互逻辑。
6. 不要修改 index.html 和已有的 CSS 变量。
7. 中文文案要克制、温和，不要堆砌感叹号，不要使用 emoji。

改完请用一句话说明：改了什么、没改什么。
```
