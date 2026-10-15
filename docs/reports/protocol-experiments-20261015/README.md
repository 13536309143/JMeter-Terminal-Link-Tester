# JMeter 四协议实验技术报告资料

主要文件：

- `JMeter四协议终端模拟与采集链路实验技术报告.docx`：22 页中文正式报告，嵌入 14 张实际页面截图。
- `report.zh-CN.html`：可在浏览器离线阅读的完整报告。
- `report.zh-CN.md`：便于维护的 Markdown 文本。
- `screenshots/`：独立截图原图，已裁去无关浏览器界面和空白，未改写页面数据。
- `views/`：本次截图所用的只读证据页面，数据来自实际运行产物，不是 JMeter 原生 GUI。
- `evidence/runs/`：本次 33 项矩阵实验的 JMX、场景、JTL、JSONL、日志、资源与 HTML 报告。
- `evidence/integration-runs/`：本次自动化测试中 5 次真实 JMeter 子运行。
- `evidence/pipeline-runs/`：SQLite 提交后回执链路与数据库。
- `evidence/prior-release/`：报告中引用的既有跨平台工程验收副本；其原项目路径为 `docs/evidence/`。

浏览器可直接打开 `report.zh-CN.html`；图片使用相对路径，移动或交接时请保留整个资料目录。数据索引为 `evidence/run-index.json`，每个条目使用本资料目录下的相对路径；原始 provenance 和日志中的绝对路径保留用于追溯，在其他机器运行时应重新生成 JMX。

本次结果：33 项实验全部符合预期，其中 14 项正向通过业务验收、19 项反向触发预期失败信号；34 项完整自动化测试通过；MQTT 提交后回执参考链路交付 50 条。四协议 50 终端实验均为 1000/1000 条有效唯一交付，实际活跃峰值为 50。

证据摘要见 `evidence/SHA256SUMS.json`，键相对于本资料根目录。截图来源、时间、裁剪范围与原始截图摘要见 `evidence/screenshot-manifest.json`。浏览器完整窗口原始截图仅作为本机内部取证留存，资料截图只裁去无关界面。

这些是回环与合成终端实验，不代表现场设备、跨网性能或整个平台容量验收。当前资料是实验交接资料，包含测试内容，不属于可直接运行的软件发行包。
