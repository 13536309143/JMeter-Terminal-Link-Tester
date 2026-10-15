# JMeter Terminal & Link Tester

[中文使用说明](runtime-guide.zh-CN.md)

This portable application runs terminal simulation and message verification through Apache JMeter. It supports MQTT 3.1.1, TCP, UDP and HTTP. Java, JMeter, the MQTT plugin and the application runtime are included. No Python or Java installation is required.

## Start

Extract the entire archive to a writable folder. Keep the executable, `_internal` and `runtime` folders together.

macOS:

```bash
cd /path/to/jmeter-link-tester
./jmeter-link-tester doctor
./jmeter-link-tester --help
./jmeter-link-tester gui
```

Windows PowerShell:

```powershell
cd D:\jmeter-link-tester
.\jmeter-link-tester.exe doctor
.\jmeter-link-tester.exe --help
.\jmeter-link-tester.exe gui
```

You can also open `JMeter-GUI.command` on macOS or `JMeter-GUI.cmd` on Windows. The command-line application is unsigned; macOS may require approval through its normal security prompt when opening downloaded software.

## Configure a target

Edit a file in `profiles/` and set the target address before running it:

| Profile | Target contract |
| --- | --- |
| `mqtt.json` | MQTT Broker; publish to `<prefix>/<run_id>/up/<device_id>` |
| `tcp.json` | UTF-8 JSON request and JSON response, each terminated by LF |
| `udp.json` | One JSON object per datagram; response preserves `message_id` |
| `http.json` | JSON HTTP endpoint; POST by default; GET/PUT/PATCH/DELETE are also supported |

For TCP/UDP/HTTP, responses must preserve the identity fields and `sent_at_ms` from the request. GET sends the JSON document in the URL-encoded `payload` parameter; other methods send a JSON body. This release uses plain MQTT TCP and HTTP; TLS and custom binary framing need an adapter.

`load.terminals` sets the number of simulated devices. `messages_per_terminal`, `ramp_up_seconds` and `interval_ms` control the workload. Defaults are 5 devices and 10 messages each. `thresholds` controls error rate, delivery rate, request P95 and collection/response P95.

MQTT authentication uses environment variable names in `broker.username_env` and `broker.password_env`. HTTP Bearer authentication uses `http.bearer_token_env`. Set the referenced variables in your shell; do not store passwords or tokens in profiles.

## Run and inspect

```bash
./jmeter-link-tester validate profiles/http.json
./jmeter-link-tester run profiles/http.json
./jmeter-link-tester plan profiles/http.json --output plans/http
./jmeter-link-tester gui plans/http/test-plan.jmx
./jmeter-link-tester runs
```

On Windows replace `./jmeter-link-tester` with `.\jmeter-link-tester.exe`.

Each run writes an isolated folder under `results/runs/`. Open `report.html` for the summary and acceptance gates, or `dashboard/index.html` for the native JMeter dashboard. `summary.json`, `samples.jtl` and `collected.jsonl` retain machine-readable evidence. A nonzero exit code means an execution problem or failed acceptance gate; inspect the run's logs.

| Exit code | Meaning |
| --- | --- |
| 0 | Completed and accepted |
| 1 | Environment or execution error |
| 2 | Invalid configuration |
| 3 | Acceptance gate failed |
| 4 | Execution timeout |
| 130 | Cancelled |

`LINKLAB_HEAP=2g` can increase Java's maximum heap. On Windows set `$env:LINKLAB_HEAP="2g"` before starting the program. Save results outside the application folder if you intend to replace that folder during upgrades.

MQTT publish time is distinct from collection delay. TCP/UDP/HTTP response delay is a round-trip measurement, including server processing. Results describe the configured workload and target; they are not platform-wide capacity or availability certifications.
