# 操作手册与配置字典

运行包使用 `jmeter-link-tester`，源码环境也提供同名入口；Windows 为 `.exe` 或源码环境 `.cmd`。源码中的 `linklab` 是开发入口，额外提供本地参考服务与实验矩阵，运行包不包含这些开发功能。

## 工作流程

先运行 `doctor`；复制对应协议配置，修改对端地址；执行 `validate`；小负载 `run`；查看门禁与原始证据；再逐步调整并发和上报频率。`plan --output <目录>` 生成可编辑 JMX。

```bash
./jmeter-link-tester doctor
./jmeter-link-tester validate scenarios/http-baseline.yaml
./jmeter-link-tester run scenarios/http-baseline.yaml
./jmeter-link-tester plan scenarios/http-baseline.yaml --output build/http
./jmeter-link-tester gui build/http/test-plan.jmx
./jmeter-link-tester runs
```

MQTT 对端为 Broker；TCP/UDP/HTTP 对端必须遵守[消息契约](architecture.md)。默认 `run` 不启动对端服务，连接实际目标前应确认地址、协议与测试窗口。

## 场景字段

YAML 与 JSON 都支持，未知字段、重复 YAML 键、非有限数字、错误类型、非法终端清单会失败。版本字段为 `version: 1`。

| 字段 | 默认值与含义 |
| --- | --- |
| `name` | ASCII 场景标识，1–64 字符，字母/数字/下划线/连字符 |
| `protocol` | `mqtt`；可选 `mqtt/tcp/udp/http` |
| `description` | 场景说明，可用中文 |
| `load.terminals` | 5；单次 1–10,000 个配置终端 |
| `load.messages_per_terminal` | 10；预期总消息数为两者乘积，最多 1,000,000 |
| `load.ramp_up_seconds` | 1；整数秒，逐步启动线程 |
| `load.interval_ms` | 100；每次业务请求前的等待时间，不计入发送时间戳后的链路延迟 |
| `data.devices_csv` | 空时生成终端；否则相对场景文件解析 CSV 路径 |
| `data.seed` | 2025；固定随机种子，生成温度数据 |
| `data.padding_bytes` | 0；追加 ASCII `x` 的数量，最多 32768 |
| `execution.timeout_seconds` | 120；JMeter 进程运行上限，超时终止整个进程组 |
| `execution.html_dashboard` | true；生成原生仪表盘 |

CSV 列必须且只能为 `device_id,device_type,site`。使用前 N 行，一线程一个终端；标识与分类值使用 1–48 个 ASCII 字母、数字、下划线或连字符。生成数据仅用于终端模拟。

## 协议字段

| 协议 | 配置 |
| --- | --- |
| MQTT | `broker.host/port` 默认 127.0.0.1:1883；`username_env/password_env` 为认证环境变量名；`mqtt.qos` 为 0/1/2；`topic_prefix` 默认 `linklab/dongguan` |
| TCP/UDP | `network.host/port` 默认 127.0.0.1:9000；`connect_timeout_ms` 默认 3000；`response_timeout_ms` 默认 1000，UDP 使用后者 |
| HTTP | `http.host/port` 默认 127.0.0.1:8080；`path` 默认 `/telemetry`；`method` 默认 POST；支持 GET/PUT/PATCH/DELETE；`expected_status` 默认 200；连接/响应超时默认 3000/1000ms |

HTTP `bearer_token_env` 指定 Bearer Token 的环境变量名。GET 使用 URL 编码的 `payload` 参数，其他方法使用 JSON 请求体。不会自动跟随重定向。当前只封装明文 HTTP；HTTPS 需另行适配证书验证策略。

MQTT `collection.topic_stage` 默认为 `up`，直接验证 Broker 侧消息；设置为 `persisted` 则订阅提交后回执。`drain_seconds` 默认 3 秒；`max_payload_bytes` 默认 65536。MQTT 订阅探针始终观察上行 Topic，独立校验器观察配置的阶段。

## 门禁与退出码

| 门禁字段 | 默认阈值 |
| --- | ---: |
| `max_error_rate_pct` | 0 |
| `min_delivery_rate_pct` | 100 |
| `max_request_p95_ms` | 3000 |
| `max_e2e_p95_ms` | 3000 |
| `max_duplicates` | 0 |
| `max_out_of_order` | 0 |

以上字段放在 `thresholds` 下。还固定检查进程正常退出、消息采样总数、非法数据为零、采集健康和仪表盘生成；MQTT 检查终端连接/断开数量与订阅探针证据。无有效数据的延迟不是零，相关门禁不会通过。

退出码：0 通过；1 环境或执行异常；2 配置错误；3 门禁失败；4 执行超时；130 操作员取消。`report` 可从已存在的 `summary.json` 重建 HTML/Markdown；`compare` 比较两次结果。

## JMeter 图形界面调试

源码环境可先在另一个终端运行 `./linklab broker --port 1883`，或 `./linklab serve scenarios/tcp-baseline.yaml`，HTTP 使用 `scenarios/http-baseline.yaml`。再生成计划并打开 GUI。

在测试计划上右键添加“查看结果树”或“汇总报告”，用小负载检查请求与断言。GUI 的监听器主要用于调试；正式执行使用 CLI，以保存独立采集、门禁和统一报告。手工修改生成的 JMX 不会自动反向更新 YAML；需固化到编译器或场景配置后重新生成。

## 开发环境故障选项

这些选项用来复现实验，参考服务只在源码中提供。`invalid_every` 每 N 条构造非法温度；MQTT `drop_every` 在采集处理阶段主动丢弃；`processing_delay_ms` 注入处理延迟。TCP/UDP/HTTP 的 `response_drop_every`、`response_invalid_every`、`response_wrong_id_every` 分别控制响应丢失、非法 JSON 和错误 ID。

UDP 使用 `udp_duplicate_every`、`udp_reorder_pairs`；TCP 使用 `tcp_fragment_bytes`、`tcp_close_every`；HTTP 使用 `http_error_every`。协议不匹配的故障选项会被拒绝。上述响应故障由本地参考服务实现，不会改变外部现场服务的行为。
