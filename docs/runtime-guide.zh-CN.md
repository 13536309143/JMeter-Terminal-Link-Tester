# JMeter 终端与链路测试工具

[English guide](runtime-guide.en.md)

本应用通过 Apache JMeter 执行终端模拟与消息校验，支持 MQTT 3.1.1、TCP、UDP、HTTP。发行包内置 Java、JMeter、MQTT 插件和应用运行环境，无需另装 Python 或 Java。

## 启动

完整解压到可写目录，保持可执行文件、`_internal` 和 `runtime` 在一起。

macOS：

```bash
cd /path/to/jmeter-link-tester
./jmeter-link-tester doctor
./jmeter-link-tester --help
./jmeter-link-tester gui
```

Windows PowerShell：

```powershell
cd D:\jmeter-link-tester
.\jmeter-link-tester.exe doctor
.\jmeter-link-tester.exe --help
.\jmeter-link-tester.exe gui
```

也可双击 macOS 的 `JMeter-GUI.command` 或 Windows 的 `JMeter-GUI.cmd`。命令行应用未签署商业开发者证书，macOS 首次打开下载的软件时可能显示常规安全确认提示。

## 配置目标

修改 `profiles/` 中对应文件的目标地址后运行：

| 配置 | 对端约定 |
| --- | --- |
| `mqtt.json` | MQTT Broker；发布到 `<prefix>/<run_id>/up/<device_id>` |
| `tcp.json` | 请求与响应均为 UTF-8 JSON，以 LF 换行结束 |
| `udp.json` | 每个数据报一条 JSON；响应保留 `message_id` |
| `http.json` | 默认 POST JSON；也支持 GET、PUT、PATCH、DELETE |

TCP/UDP/HTTP 响应需保留请求中的消息身份字段与 `sent_at_ms`。GET 将 JSON 放在 URL 编码的 `payload` 参数中，其他方法发送 JSON 请求体。当前封装为明文 MQTT TCP 与 HTTP，TLS 和自定义二进制帧需另行适配。

`load.terminals` 设置终端数量；`messages_per_terminal`、`ramp_up_seconds`、`interval_ms` 设置消息数、启动过渡时间和间隔。默认 5 终端、每终端 10 条消息。`thresholds` 控制错误率、完整率、请求 P95 和采集或响应 P95。

MQTT 的 `broker.username_env`、`broker.password_env` 填写认证环境变量名称；HTTP Bearer 认证使用 `http.bearer_token_env`。在终端设置对应变量，不要把口令写入配置。

## 执行与结果

```bash
./jmeter-link-tester validate profiles/http.json
./jmeter-link-tester run profiles/http.json
./jmeter-link-tester plan profiles/http.json --output plans/http
./jmeter-link-tester gui plans/http/test-plan.jmx
./jmeter-link-tester runs
```

Windows 将入口替换为 `.\jmeter-link-tester.exe`。

每次运行在 `results/runs/` 下生成独立目录。打开 `report.html` 查看汇总和门禁，打开 `dashboard/index.html` 查看 JMeter 仪表盘。`summary.json`、`samples.jtl`、`collected.jsonl` 保留结构化证据。非零退出码表示执行异常或门禁失败，请检查对应目录日志。

| 退出码 | 含义 |
| --- | --- |
| 0 | 完成且通过 |
| 1 | 环境或执行异常 |
| 2 | 配置错误 |
| 3 | 门禁未通过 |
| 4 | 执行超时 |
| 130 | 已取消 |

可用 `LINKLAB_HEAP=2g` 调整 Java 最大堆，Windows 设置 `$env:LINKLAB_HEAP="2g"`。升级替换目录前，应把需要保留的运行结果移到独立位置。

MQTT 发布耗时与采集处理延迟分别统计。TCP/UDP/HTTP 为包含服务端处理的响应往返时间。报告只反映当前目标与负载，不构成整个平台容量或长期可用性的认证。
