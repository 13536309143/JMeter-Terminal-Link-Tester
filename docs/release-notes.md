# JMeter Terminal & Link Tester v1.0.1

This patch includes the complete upstream Paho EDL/EPL license texts alongside the bundled dependency notices. Protocol behavior is unchanged.

Portable terminal simulation and data-chain verification with **MQTT, TCP, UDP and HTTP**.

Download the archive matching your operating system and architecture. Each attached runtime archive includes the application runtime, Java 17, Apache JMeter 5.6.3, the EMQX MQTT plugin, operational profiles and English/Chinese usage guides. No separate Python or Java installation is required.

- `windows-x64.zip`: Windows 10/11 x64
- `macos-arm64.tar.gz`: Apple Silicon Mac
- `macos-x64.tar.gz`: Intel Mac
- Matching `.sha256` files verify each archive.

Extract the full archive, run `jmeter-link-tester doctor`, edit a profile's target address, and run `jmeter-link-tester run profiles/<protocol>.json`. Use `gui` or the included GUI launcher for native JMeter.

Attached runtime archives contain no project regression suites, reference servers, experimental scenarios, execution evidence or testing documentation. Those materials remain in the source repository. GitHub's automatically generated source-code archives represent the full source tree and therefore include its tests.

Current adapters cover MQTT 3.1.1 over TCP, newline-delimited JSON over TCP, JSON datagrams over UDP and JSON HTTP requests/responses. HTTPS/TLS, MQTT 5 and custom binary framing are not included. Applications are unsigned; macOS may show its normal security prompt for downloaded software.

中文：下载对应平台的完整运行包并解压，无需另装 Python 或 Java。先执行 `doctor`，再修改 `profiles` 中的目标地址并运行。源码仓库保留完整测试代码、方法与记录；上传的运行包不含项目测试内容。
