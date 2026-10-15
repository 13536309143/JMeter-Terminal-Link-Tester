# JMeter 终端与链路测试工具

[English](README.md) | 简体中文

**JMeter Terminal & Link Tester** · MQTT / TCP / UDP / HTTP

[下载完整运行包](https://github.com/13536309143/jmeter/releases/latest)。Windows x64、macOS Apple Silicon 和 Intel 分别提供内置 Java、JMeter、Python 应用运行环境的发行包，解压后使用 `jmeter-link-tester`，无需先安装 Python 或 Java。发行包仅含运行内容，测试代码、场景和实验记录保留在本仓库。

基于 **Apache JMeter + EMQX MQTT 插件**封装的测试工具，面向中国联通广东产互东莞中试验证中心项目的终端通信与采集链路验证。支持 **MQTT、TCP、UDP、HTTP**，提供参数化终端、自动执行、数据完整性校验和可追溯报告，操作入口为命令行和 JMeter 原生图形界面。

本仓库交付原平台中的终端通信与采集链路测试能力。原项目文件涉及的数字孪生、AI 模型评估、私有云门户等能力，以及整个平台的用户并发、长期可用性和第三方测评指标，见[需求对应与交付边界](docs/requirements.md)。

## 先运行一个实验

完成下方源码安装后，在项目目录执行（本次本地目录为 `/Volumes/OUT/jmeter`）：

```bash
cd /Volumes/OUT/jmeter
./linklab doctor
./linklab demo --protocol mqtt
./linklab demo --protocol tcp
./linklab demo --protocol udp
./linklab demo --protocol http
./linklab pipeline-demo
```

`demo` 自动启动回环服务，运行真实 JMeter 测试并生成报告；`pipeline-demo` 验证 **MQTT 上报 → SQLite 提交 → MQTT 回执 → 独立校验**。临时服务在实验结束后关闭。默认实验不需要 Docker、外部 Broker 或现场账号。

每次运行输出独立结果目录和验收结论。打开目录中的 `report.html` 查看报告；`summary.json` 用于自动化系统读取。失败实验返回非零退出码，并保留原始证据。

## 能力与验证口径

| 能力 | 实现与产物 |
| --- | --- |
| 多终端模拟 | 一线程对应一个终端；数量、Ramp-up、循环数、间隔可配置；记录实际峰值活跃终端数 |
| MQTT | EMQX Connect、Pub、Sub、Disconnect 原生采样器；MQTT 3.1.1，QoS 0/1/2；SUBACK 就绪屏障 |
| HTTP | JMeter 原生 HTTP Sampler；GET/POST/PUT/PATCH/DELETE；JSON 与状态码、消息 ID 校验 |
| TCP | JMeter 原生 TCP Sampler；UTF-8 JSON + LF 分帧；复用终端连接；校验响应消息 ID |
| UDP | JSR223/Groovy 数据报采样器；限定对端；按消息 ID 匹配响应；超时有界；记录重复、迟到与乱序 |
| 参数与数据 | YAML/JSON 场景、CSV 终端清单、固定随机种子；运行 ID、终端 ID、序列号、发送时间戳 |
| 链路校验 | 有效唯一消息完整率、非法、缺失、重复、乱序、队列溢出；SQLite 提交后回执参考链路 |
| 性能评估 | 请求平均值与 P50/P95/P99、错误率、吞吐量、MQTT 采集处理延迟、TCP/UDP/HTTP 响应往返延迟 |
| 故障实验 | 非法负载、采集丢弃、处理延迟、响应丢失、错误消息 ID、TCP 分段与断连、UDP 重复与乱序 |
| 结果追溯 | JMX、配置、CSV、JTL、JSONL、事件日志、资源采样、摘要与 HTML/Markdown 报告 |
| 工程交付 | Windows/macOS 安装、组件摘要锁定、离线流程、自动化测试、跨平台 CI、源码打包 |

**完整率与成功率分别统计。** MQTT 发布成功仍需核对独立采集记录；TCP/UDP/HTTP 收到响应后仍需核对内容与消息标识。空结果、少发消息、执行超时和错误退出不会被当作成功。

## 环境准备与安装

| 组件 | 固定版本或要求 | 安装方式 |
| --- | --- | --- |
| Python | 3.11+，新环境建议 3.12 | 预先安装，依赖放入项目 `.venv` |
| Java | JDK 17+；默认 Corretto 17.0.20.12.1 | 自动下载，或使用已有 `JAVA_HOME` |
| JMeter | 5.6.3 | 自动下载并校验 SHA-512 |
| EMQX MQTT 插件 | mqtt-xmeter 2.0.2 | 固定地址与 SHA-256，安装至 `lib/ext` |
| 开发机 | 建议 4 核、16GB 内存，预留 2GB 空间 | 并发负载另按目标吞吐量评估 |
| Docker | 可选 | 仅 Mosquitto Compose 实验需要 |

### macOS

支持 Apple Silicon 与 Intel Mac。源码解压后执行：

```bash
cd /path/to/jmeter
python3 --version
bash scripts/setup-macos.sh
./linklab doctor
./linklab demo --protocol mqtt
```

### Windows

支持 Windows 10/11 x64，建议使用简短目录，如 `D:\jmeter`。先安装 Python 3.12，再在 PowerShell 执行：

```powershell
cd D:\jmeter
py -3 --version
.\scripts\setup-windows.cmd
.\linklab.cmd doctor
.\linklab.cmd demo --protocol mqtt
.\linklab.cmd demo --protocol tcp
.\linklab.cmd demo --protocol udp
.\linklab.cmd demo --protocol http
```

也可运行 `py -3 scripts\bootstrap.py`，无需激活虚拟环境。PowerShell 辅助入口为 `scripts/setup-windows.ps1`。Windows ARM64 的自动 JDK 安装不在当前安装器范围内。

手工部署、已有 Java、离线交付、代理与迁移步骤见[部署手册](docs/deployment.md)。

## 使用场景文件

以下配置表示 5 个 TCP 终端，每终端请求 10 次，1 秒内逐步启动，每次请求前等待 100ms：

```yaml
version: 1
name: tcp-baseline
protocol: tcp
network:
  host: 127.0.0.1
  port: 9000
  response_timeout_ms: 1000
load:
  terminals: 5
  messages_per_terminal: 10
  ramp_up_seconds: 1
  interval_ms: 100
thresholds:
  max_error_rate_pct: 0
  min_delivery_rate_pct: 100
  max_request_p95_ms: 3000
  max_e2e_p95_ms: 3000
```

```bash
# 校验参数和 CSV，生成可编辑的原生测试计划
./linklab validate scenarios/tcp-baseline.yaml
./linklab plan scenarios/tcp-baseline.yaml --output build/tcp-debug
./linklab gui build/tcp-debug/test-plan.jmx

# demo 自动启动参考服务；run 连接已经启动的现场服务
./linklab demo --scenario scenarios/tcp-baseline.yaml
./linklab run scenarios/tcp-baseline.yaml
```

Windows 入口为 `.\linklab.cmd`，子命令与参数一致。`run` 要求目标服务已启动；`demo` 自动建立本地实验环境并替换场景中的目标地址。

MQTT 现场接入使用 `scenarios/site.example.yaml`。账号密码通过 `LINKLAB_MQTT_USERNAME` 和 `LINKLAB_MQTT_PASSWORD` 环境变量传入，场景文件与命令行不保存密码。CSV 路径相对于场景文件解析。详见[操作手册与配置字典](docs/usage.md)。

## JMeter 原生图形界面

`linklab plan` 生成的 `.jmx` 可直接检查线程组、定时器、采样器和断言。文件包含本机 CSV 与证据目录的绝对路径，迁移主机后应重新生成。

GUI 用于编写和调试；完整的独立采集、门禁与报告流程通过 `linklab run` 执行。GUI 操作、监听器与手工服务启动方式见[操作手册](docs/usage.md#jmeter-图形界面调试)。

## 实验测试

```bash
# 单元与本地协议服务测试
.venv/bin/python -m unittest discover -s tests -v

# 真实 JMeter 集成：MQTT QoS 0/2、TCP、UDP、HTTP
LINKLAB_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -p test_integration.py -v

# 33 个正常、并发和故障场景，也可选择 mqtt / tcp / udp / http
./linklab experiments --protocol all
```

Windows：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:LINKLAB_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_integration.py -v
.\linklab.cmd experiments --protocol all
```

故障场景的业务验收应为“未通过”；矩阵检查缺失、非法、重复、乱序或超限信号是否符合预期，符合才算实验通过。50 终端实验使用 1 秒 Ramp-up、每终端 20 条消息，并检查**实际峰值活跃终端数达到 50**。

本机环境、参数、实测结果与验证限制见[实验报告](docs/experiments.md)。Windows/macOS CI 工作流已提供，跨平台发行流水线在 Windows、macOS ARM 与 Intel 上验证便携应用，结果保存在 GitHub Actions。

## 报告与结果对比

每次运行使用独立 ID 和目录，避免串入历史消息、复用客户端 ID 或覆盖旧结果：

```text
results/runs/<场景名>-<run_id>/
├── scenario.json       场景快照
├── devices.csv         终端参数
├── test-plan.jmx       实际执行脚本
├── provenance.json     版本、执行命令与输入摘要
├── samples.jtl         JMeter 原始采样
├── collected.jsonl     独立采集或响应验证记录
├── resources.csv       JMeter 进程与本机资源采样
├── console.log         控制台日志
├── jmeter.log          JMeter 日志
├── events.jsonl        生命周期事件
├── summary.json        结构化结论与门禁
├── report.html         离线报告
├── report.md           Markdown 摘要
└── dashboard/          JMeter 原生 HTML 仪表盘
```

```bash
./linklab runs
./linklab report results/runs/<运行目录>
./linklab compare results/runs/<基线目录> results/runs/<候选目录> --output comparison.json
```

比较结果标记负载、协议和采集阶段是否一致。跨环境结论还需核对硬件、目标服务、QoS 和消息大小；零值或无数据不会被计算成虚假的变化百分比。公式见[架构与指标说明](docs/architecture.md)。

## 项目结构与二次开发

```text
src/linklab/        场景模型、JMX 编译、执行器、采集器、TCP/UDP/HTTP、SQLite 参考链路、报告、CLI
scenarios/          正常、并发、故障和现场接入模板
data/               终端 CSV 示例
deployments/        组件摘要锁定与可选 Broker Compose
scripts/            安装、环境、验证与打包脚本
tests/              单元、协议服务和真实 JMeter 集成测试
docs/               部署、使用、设计、需求、实验、运维与实测证据
runtime/            本机 Java、JMeter 与插件，不进入源码包
source/             初次部署时准备的 JMeter 官方源码
```

常规扩展从 `src/linklab` 开始，无须修改 JMeter 核心。新增终端字段、协议、门禁和落库适配器的入口见[开发指南](docs/development.md)。

```bash
# 生成交接源码包；不含客户原始文档、密码、运行时和大体积原始结果
.venv/bin/python scripts/package.py
```

## 适用范围

当前协议契约为 MQTT 3.1.1 over TCP、TCP 按行 JSON、UDP JSON 请求/响应、HTTP JSON。TCP/UDP/HTTP 对端应保留消息标识与发送时间戳；自定义二进制帧或专有协议需编写适配器。HTTPS/TLS、MQTT 5、WebSocket、集群负载发生器与多用户服务端尚未封装。

内置 Broker 和 TCP/UDP/HTTP 服务仅监听 `127.0.0.1`，用于实验。SQLite 服务是采集参考实现，不提供生产级高可用和持久化 MQTT Outbox。现场系统可在提交数据后，按相同消息契约向 `persisted` Topic 发送回执，以接入独立验证。

单次本地任务上限为 10,000 个配置终端、1,000,000 条预期消息，不代表本机已达到对应承载能力。长稳、吞吐极限和现场验收应在专用环境按[运维手册](docs/operations.md)执行。

## 文档导航

- [部署与离线交付](docs/deployment.md)
- [使用流程与配置字典](docs/usage.md)
- [架构、消息契约与指标口径](docs/architecture.md)
- [需求对应与交付边界](docs/requirements.md)
- [实验步骤与本机实测报告](docs/experiments.md)
- [运维、故障排查与验收步骤](docs/operations.md)
- [二次开发与持续集成](docs/development.md)
- [第三方组件与来源](THIRD_PARTY_NOTICES.md)
