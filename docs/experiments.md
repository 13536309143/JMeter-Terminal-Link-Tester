# 实验方法与实测记录

2026-10-15 在 macOS ARM64 上，以真实 JMeter 5.6.3 和回环参考服务执行。环境见 [environment.json](evidence/environment.json)。所有终端、设备和消息都是合成数据；这些测量用于验证实现，不推断现场系统容量。

## 复现方法

先按[部署手册](deployment.md)安装源码环境，再执行：

```bash
LINKLAB_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
./linklab experiments --protocol all
./linklab pipeline-demo
```

Windows PowerShell：

```powershell
$env:LINKLAB_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\linklab.cmd experiments --protocol all
.\linklab.cmd pipeline-demo
```

自动测试共 34 项，启用集成开关后全部通过；[完整执行日志](evidence/automated-tests.log)包含真实 JMeter 子运行。集成覆盖 MQTT QoS 0/2、TCP、UDP 和 HTTP；矩阵 MQTT 默认 QoS 1。无开关时两个真实 JMeter 测试跳过，不能把这种运行描述为完整集成通过。

矩阵先启动回环服务，等待就绪，再调用生产执行器。正向场景要求全部门禁通过；反向场景要求业务门禁失败，且缺失、非法、延迟、重复或乱序等指定信号出现，避免把启动错误误判为故障验证成功。33 项全部符合预期，详见[机器可读矩阵](evidence/experiment-matrix.json)。每项链接保留配置、JMX、JTL、JSONL、资源数据、事件与报告；仅省略体积较大的 JMeter dashboard 目录，`jmeter.log` 本机主机标识行作了脱敏。原始测量文件未改写，文件摘要见 [SHA256SUMS.json](evidence/SHA256SUMS.json)。

## 实验结果

“通过/未通过”指业务验收；反向实验的“未通过”是预期行为。末列表示实验是否正确揭示预期结果与信号。

| 实验 | 预期业务验收 | 实际业务验收 | 完整率 % | 实际峰值终端 | 采集/响应 P95 ms | 符合预期 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| [mqtt-baseline](evidence/runs/mqtt-baseline-bc60f20474454c2a/report.md) | 通过 | 通过 | 100.0 | 5 | 7 | 是 |
| [mqtt-concurrent-50](evidence/runs/mqtt-concurrent-50-bd7ee27e1cc24923/report.md) | 通过 | 通过 | 100.0 | 50 | 9 | 是 |
| [mqtt-invalid-payload](evidence/runs/mqtt-invalid-payload-fc4cf46b7d614763/report.md) | 未通过 | 未通过 | 70.0 | 5 | 8 | 是 |
| [mqtt-collection-drop](evidence/runs/mqtt-collection-drop-e978b559afe84548/report.md) | 未通过 | 未通过 | 80.0 | 5 | 2 | 是 |
| [mqtt-processing-delay](evidence/runs/mqtt-processing-delay-43aa86b5e39c4f93/report.md) | 未通过 | 未通过 | 100.0 | 2 | 345 | 是 |
| [tcp-baseline](evidence/runs/tcp-baseline-481f906731424709/report.md) | 通过 | 通过 | 100.0 | 5 | 1 | 是 |
| [tcp-concurrent-50](evidence/runs/tcp-concurrent-50-e39bfed29d334a7b/report.md) | 通过 | 通过 | 100.0 | 50 | 1 | 是 |
| [tcp-invalid-response](evidence/runs/tcp-invalid-response-52c82799cafc4da2/report.md) | 未通过 | 未通过 | 50.0 | 2 | 50 | 是 |
| [tcp-wrong-message-id](evidence/runs/tcp-wrong-message-id-2c712ba4d84d4657/report.md) | 未通过 | 未通过 | 50.0 | 2 | 56 | 是 |
| [tcp-response-loss](evidence/runs/tcp-response-loss-667e52a8599c4715/report.md) | 未通过 | 未通过 | 50.0 | 2 | 50 | 是 |
| [tcp-processing-delay](evidence/runs/tcp-processing-delay-51b716ded5774971/report.md) | 未通过 | 未通过 | 100.0 | 2 | 180 | 是 |
| [udp-baseline](evidence/runs/udp-baseline-bd8f4dd916e74e22/report.md) | 通过 | 通过 | 100.0 | 5 | 1 | 是 |
| [udp-concurrent-50](evidence/runs/udp-concurrent-50-bab65e3499504f9d/report.md) | 通过 | 通过 | 100.0 | 50 | 1 | 是 |
| [udp-invalid-response](evidence/runs/udp-invalid-response-22e11df1c7ab498f/report.md) | 未通过 | 未通过 | 50.0 | 2 | 73 | 是 |
| [udp-wrong-message-id](evidence/runs/udp-wrong-message-id-daf4c457cabf4267/report.md) | 未通过 | 未通过 | 50.0 | 2 | 119 | 是 |
| [udp-response-loss](evidence/runs/udp-response-loss-f4fdbf97c8994ccb/report.md) | 未通过 | 未通过 | 50.0 | 2 | 84 | 是 |
| [udp-processing-delay](evidence/runs/udp-processing-delay-0ec017003faa41c4/report.md) | 未通过 | 未通过 | 100.0 | 2 | 183 | 是 |
| [tcp-fragmented](evidence/runs/tcp-fragmented-c1e034e40c67433f/report.md) | 通过 | 通过 | 100.0 | 2 | 90 | 是 |
| [tcp-abrupt-close](evidence/runs/tcp-abrupt-close-8e487389f6084f75/report.md) | 未通过 | 未通过 | 33.33333333333333 | 2 | 48 | 是 |
| [udp-duplicates](evidence/runs/udp-duplicates-d5d8d14c89f6412f/report.md) | 未通过 | 未通过 | 100.0 | 2 | 95 | 是 |
| [udp-reordered](evidence/runs/udp-reordered-a786f5a5750a4e1f/report.md) | 未通过 | 未通过 | 100.0 | 2 | 276 | 是 |
| [udp-large-payload](evidence/runs/udp-large-payload-5744ae9c8fd149f4/report.md) | 通过 | 通过 | 100.0 | 2 | 73 | 是 |
| [http-baseline](evidence/runs/http-baseline-f7b26a53bda84e19/report.md) | 通过 | 通过 | 100.0 | 5 | 3 | 是 |
| [http-concurrent-50](evidence/runs/http-concurrent-50-c203d48fa1984dda/report.md) | 通过 | 通过 | 100.0 | 50 | 2 | 是 |
| [http-invalid-response](evidence/runs/http-invalid-response-52418b9cdbfc49e3/report.md) | 未通过 | 未通过 | 50.0 | 2 | 80 | 是 |
| [http-wrong-message-id](evidence/runs/http-wrong-message-id-230dfb6f57a74ed5/report.md) | 未通过 | 未通过 | 50.0 | 2 | 87 | 是 |
| [http-response-loss](evidence/runs/http-response-loss-061651c8a9ff40b2/report.md) | 未通过 | 未通过 | 50.0 | 2 | 78 | 是 |
| [http-processing-delay](evidence/runs/http-processing-delay-69e29174d3ee47af/report.md) | 未通过 | 未通过 | 100.0 | 2 | 185 | 是 |
| [http-get](evidence/runs/http-get-485858d473954afa/report.md) | 通过 | 通过 | 100.0 | 2 | 84 | 是 |
| [http-put](evidence/runs/http-put-39fecea5f0284670/report.md) | 通过 | 通过 | 100.0 | 2 | 87 | 是 |
| [http-patch](evidence/runs/http-patch-341ddfbedf724f8f/report.md) | 通过 | 通过 | 100.0 | 2 | 81 | 是 |
| [http-delete](evidence/runs/http-delete-3d7b376d52db475c/report.md) | 通过 | 通过 | 100.0 | 2 | 82 | 是 |
| [http-error-status](evidence/runs/http-error-status-c2ebd121d1ec4b55/report.md) | 未通过 | 未通过 | 50.0 | 2 | 78 | 是 |

## 并发、数据链路与离线验证

四协议的 `concurrent-50` 场景使用 50 终端、每终端 20 条消息、1 秒 Ramp-up、100 ms 间隔。JTL 中业务采样的 `grpThreads` 峰值为 50，四场景均交付 1,000 条有效唯一消息。吞吐量采用整个 JMeter 采样区间，包含连接、Ramp-up 和收尾；不能用配置终端数替代观测并发。

[SQLite 链路摘要](evidence/persistence-summary.json)记录 50 条消息全部通过；[SQLite 数据库](evidence/persistence.sqlite3)保留提交结果。该实验从 MQTT 上报到事务提交后发送回执，再由独立订阅者验证，证明参考实现这一阶段的消息交付。

[冷启动离线日志](evidence/offline-cold-install.log)来自新目录、新运行时和新虚拟环境，使用已下载组件及本机 wheelhouse，执行 `bootstrap.py --offline` 后通过环境检查。离线材料必须匹配目标操作系统、架构和 Python 版本。

## 可发行包验证

```bash
.venv/bin/python -m pip install pyinstaller==6.16.0
.venv/bin/python scripts/release_bundle.py
.venv/bin/python scripts/verify_release.py build/release/macos-arm64/jmeter-link-tester
```

Windows 将解释器替换为 `.venv\Scripts\python.exe`、平台目录替换为 `windows-x64`；Intel Mac 为 `macos-x64`。验证服务由源码侧启动，不进入发行包。

本机提取后的 Mac ARM 发行应用通过 MQTT/TCP/UDP/HTTP 四项正向运行及 HTTP 错误状态反向运行，共 5 项，见[摘要](evidence/portable-verification.json)与[日志](evidence/portable-verification.log)。验证明确移除 `PYTHONPATH`，设置无效系统 `JAVA_HOME/JMETER_HOME`，应用仍使用自身运行环境。

[发布流水线](../.github/workflows/release.yml)在 Windows x64、Mac ARM 和 Mac Intel 原生 runner 上分别构建、审计和执行同样的 5 项验证，通过后才上传运行包到 Release；每个平台完整证据保存在对应 Actions 的 `verification-*` artifact。本地历史证据不替代跨平台流水线的实际状态。

## 跨平台发行验收记录

源码 CI 在 Windows/macOS × Python 3.11/3.12 共 4 个原生环境通过，[状态快照](evidence/source-ci.json)关联到发布代码提交。便携发行验收每平台包含四协议正向运行和 HTTP 错误状态反向运行，共 15 项：

| 平台 | 检查数 | 结果与原始运行记录 |
| --- | ---: | --- |
| Windows x64 | 5 | [verification.json](evidence/platforms/windows-x64/verification.json) · [运行证据](evidence/platforms/windows-x64/runs/) |
| Mac Apple Silicon | 5 | [verification.json](evidence/platforms/macos-arm64/verification.json) · [运行证据](evidence/platforms/macos-arm64/runs/) |
| Mac Intel | 5 | [verification.json](evidence/platforms/macos-x64/verification.json) · [运行证据](evidence/platforms/macos-x64/runs/) |

[原生发行流水线](https://github.com/13536309143/jmeter/actions/runs/38694408421)将证据保存在 Actions；本仓库另存各平台配置、JMX、JTL、响应 JSONL、日志和门禁结果，避免仅依赖 artifact 保留期。每个平台的 `CI.json` 记录代码提交和 artifact ID。与本机矩阵相同，仅省略生成的 JMeter dashboard 静态目录。

已发布附件的下载、SHA-256 与内容审计结果见 [published-release.json](evidence/published-release.json)。运行压缩包包含四种协议配置及运行环境，不含项目测试目录、参考服务、实验场景和实验记录。GitHub 自动生成的源码附件保留测试。

下载后的本地校验：

```bash
shasum -a 256 -c jmeter-link-tester-1.0.1-macos-arm64.tar.gz.sha256
```

```powershell
Get-FileHash .\jmeter-link-tester-1.0.1-windows-x64.zip -Algorithm SHA256
Get-Content .\jmeter-link-tester-1.0.1-windows-x64.zip.sha256
```

## 调试过程中的修正

- **MQTT 订阅就绪**：独立采集器等待 SUBACK；JMeter 观察订阅也设置就绪屏障，发布端在订阅建立后开始发送，避免启动顺序引起的漏收。
- **延迟口径**：将业务消息时间戳生成移至发送间隔之后，避免把人为设置的定时间隔计入端到端观测延迟。
- **UDP 超时计算**：用 `TimeUnit.NANOSECONDS.toMillis` 转换剩余时间，消除 Groovy 数值类型造成的方法重载歧义，并保留明确超时边界。
- **并发参考服务**：扩大 TCP/HTTP 回环服务的监听队列，消除 50 终端同时建连时参考服务自身造成的首请求失败；并发验收同时检查 JTL 实际活跃终端峰值。
- **Windows 中文编码**：首轮 Windows CI 揭示测试脚本默认使用 cp1252 读取 UTF-8 报告/JMX 的问题，已将读取显式设为 UTF-8，并统一 CLI 输出。后续两版本 Python 的 Windows 源码 CI 与便携验证全部通过。

正式下载的 1.0.1 Mac ARM 包还在本次部署机器上完成了相同的 5 项运行验证，[结果](evidence/downloaded-runtime-local.json)和[日志](evidence/downloaded-runtime-local.log)另存。该验证使用实际从 Release 下载并通过 SHA-256 校验的附件。

## 限制与现场实验建议

当前测量没有外部网络、真实设备或生产 Broker 干扰；未进行长期稳定性、TLS、分布式压测或硬件承载极限验收。Docker 路径在本机未实跑。现场复测应固定机器与版本、隔离负载发生器和被测服务、校准时钟，逐级增加负载并保存服务端监控。跨机器 MQTT 时间戳延迟依赖时钟同步；TCP/UDP/HTTP 当前值为带处理时间的响应往返观测。负向故障属于显式参考服务实验，不应在现场误配置启用。
