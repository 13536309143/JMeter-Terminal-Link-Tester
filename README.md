# JMeter Terminal & Link Tester

English | [简体中文](README.zh-CN.md)

**Simulate terminals. Verify delivery. Measure the complete link.**

A command-line toolkit built on Apache JMeter for **MQTT, TCP, UDP and HTTP** terminal simulation and data-collection link testing. Configure a workload, run native JMeter samplers, validate individual messages, and retain the measurements behind every acceptance decision. The native JMeter GUI remains available for inspection and further development.

Created for the terminal communication and collection-link workstream of the China Unicom Guangdong Dongguan pilot verification center project. [Scope and requirements mapping](docs/requirements.md) distinguish this deliverable from the wider platform described in the reference documents.

## Download and run

Get a complete runtime from [Releases](https://github.com/13536309143/jmeter/releases/latest):

| Your computer | Download |
| --- | --- |
| Windows x64 | `jmeter-link-tester-1.0.1-windows-x64.zip` |
| Mac with Apple Silicon | `jmeter-link-tester-1.0.1-macos-arm64.tar.gz` |
| Mac with Intel | `jmeter-link-tester-1.0.1-macos-x64.tar.gz` |

Each runtime includes the application, Java 17, JMeter 5.6.3, and the EMQX MQTT plugin. **No separate Python or Java installation is required.** Extract the entire archive into a writable directory. Runtime attachments contain operational profiles and documentation; tests, fixtures and experimental evidence live in this repository. GitHub's automatic *Source code* archives contain the complete source tree, including tests.

macOS:

```bash
tar -xzf jmeter-link-tester-1.0.1-macos-arm64.tar.gz
cd jmeter-link-tester
./jmeter-link-tester doctor
# Edit profiles/http.json to point at your target first.
./jmeter-link-tester run profiles/http.json
./jmeter-link-tester gui
```

Windows PowerShell:

```powershell
Expand-Archive .\jmeter-link-tester-1.0.1-windows-x64.zip -DestinationPath .\tools
cd .\tools\jmeter-link-tester
.\jmeter-link-tester.exe doctor
# Edit profiles\http.json to point at your target first.
.\jmeter-link-tester.exe run profiles\http.json
.\jmeter-link-tester.exe gui
```

A reachable target endpoint is required for `run`. Read the bundled [English runtime guide](docs/runtime-guide.en.md) or [中文运行指南](docs/runtime-guide.zh-CN.md) for endpoint contracts, environment-based credentials, outputs and exit codes. Mac applications are unsigned; follow your organization's normal software approval procedure.

## What it does

| Capability | Implementation |
| --- | --- |
| Terminal workloads | One JMeter thread per terminal; configurable count, Ramp-up, message count and pacing; observed peak active terminals |
| MQTT 3.1.1 | EMQX Connect, Publish, Subscribe and Disconnect samplers; QoS 0/1/2; subscription readiness barrier; independent Paho collector |
| TCP | Native TCP sampler; UTF-8 JSON delimited by LF; reusable terminal connections; correlated responses |
| UDP | Bounded Groovy datagram sampler; connected peer; message-ID matching; duplicate, late and reordered receipt accounting |
| HTTP | Native HTTP sampler; GET/POST/PUT/PATCH/DELETE; JSON, status assertions, message-ID checks and optional Bearer token from environment |
| Data validation | Run/device/message identity, sequence, timestamp and value checks; unique delivery, missing, invalid, duplicate and out-of-order counts |
| Performance | Mean/P50/P95/P99 request time, throughput and error rate; collection/response latency; process resource samples |
| Audit trail | Scenario, CSV, generated JMX, JTL, JSONL receipts, events, provenance hashes, JSON/Markdown/HTML reports |
| Experiments | Real loopback services and deterministic fault injection; MQTT → SQLite commit → MQTT receipt reference pipeline |

**Sampler success and valid delivery are separate measurements.** A successful MQTT publish alone does not prove collection. TCP/UDP/HTTP replies must also satisfy the payload contract. Empty results, missing samples, process failures and timeouts cannot pass acceptance. Response latency includes server processing and must not be interpreted as one-way network latency. [Metric definitions](docs/architecture.md) explain the calculation windows.

## Develop and reproduce

Source prerequisites: Python **3.11+** (3.12 recommended), network access on first setup, and approximately 2 GB free space. Setup creates a local virtual environment and downloads checksum-pinned JMeter/plugin components. It provisions Corretto 17 when no `JAVA_HOME` is configured. Windows x64 and both Mac architectures are supported.

```bash
git clone https://github.com/13536309143/jmeter.git
cd jmeter
bash scripts/setup-macos.sh
./linklab doctor
./linklab demo --protocol mqtt
./linklab demo --protocol tcp
./linklab demo --protocol udp
./linklab demo --protocol http
./linklab pipeline-demo
```

Windows:

```powershell
git clone https://github.com/13536309143/jmeter.git
cd jmeter
.\scripts\setup-windows.cmd
.\linklab.cmd doctor
.\linklab.cmd demo --protocol http
```

`linklab` is the developer entry point and includes temporary loopback services. `jmeter-link-tester` is the production entry point. Each demo starts a local service, executes **real JMeter**, writes an isolated report directory, and shuts the service down. Docker and external broker accounts are unnecessary for these demos.

For a real target, edit a scenario and run:

```bash
./linklab validate scenarios/http-baseline.yaml
./linklab plan scenarios/http-baseline.yaml --output results/http-plan
./linklab run scenarios/http-baseline.yaml
./linklab gui results/http-plan/test-plan.jmx
```

Reports open locally without a web service. Compare runs using `./linklab compare BASELINE_DIR CANDIDATE_DIR`. Authentication secrets come from environment variables and are not written into generated JMX. [Usage and protocol contracts](docs/usage.md) cover parameterization, thresholds and configuration.

## Tests and recorded experiments

The repository retains test code, reproducible procedures and measured evidence:

- **34 automated tests passed**, including enabled native JMeter integration for MQTT QoS 0/2, TCP, UDP and HTTP.
- **33 protocol experiments matched their expected outcomes**: MQTT 5, TCP 8, UDP 9, HTTP 11. Negative experiments must expose the intended fault signal as well as fail acceptance.
- Each protocol's 50-terminal workload delivered **1,000/1,000 valid unique messages**, with an observed peak of **50 active terminals** on the recorded local run.
- The extracted Mac ARM runtime passed four protocol checks and an HTTP failure check with deliberately invalid system Java/JMeter settings.

These are synthetic loopback measurements, not production capacity claims. Native Windows x64, Mac ARM64 and Mac Intel runtime verification passed all five checks per platform. Source CI also passed on Windows/macOS with Python 3.11 and 3.12. See [test methods, environment and raw evidence](docs/experiments.md).

```bash
.venv/bin/python -m unittest discover -s tests -v
LINKLAB_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
./linklab experiments --protocol all
```

```powershell
$env:LINKLAB_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\linklab.cmd experiments --protocol all
```

## Project layout

```text
src/linklab/       Configuration, JMX generation, execution, validation, reporting
scenarios/        Reproducible workload and fault configurations
data/             Synthetic terminal CSV
scripts/          Setup, source packaging, frozen release and verification
runtime/          Local JMeter and JDK after setup (not committed)
source/           Unmodified upstream Apache JMeter 5.6.3 source
tests/            Automated tests
docs/evidence/    Recorded synthetic experiments and verification logs
deployments/      Artifact locks, licenses and optional local broker
.github/          Native Windows/macOS verification and release workflows
```

## Documentation

- [Windows/macOS setup and offline preparation](docs/deployment.md)
- [Configuration, commands and endpoint contracts](docs/usage.md)
- [Architecture, data flow and metric definitions](docs/architecture.md)
- [Test methods and evidence](docs/experiments.md)
- [Operations and troubleshooting](docs/operations.md)
- [Secondary development and release process](docs/development.md)
- [Requirements mapping and delivery boundaries](docs/requirements.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

The current release implements clear-text MQTT/TCP/UDP/HTTP workflows. TLS/HTTPS, distributed load coordination and production ingestion adapters require additional implementation and validation. Reference services are development fixtures. Original customer requirement documents and credentials are not distributed. Apache JMeter and bundled dependencies retain their own licenses and notices; no Apache/EMQX affiliation is implied.
