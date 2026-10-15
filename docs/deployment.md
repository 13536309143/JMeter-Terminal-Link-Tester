# Windows 与 macOS 部署手册

覆盖自动部署、已有 Java、手工部署和离线交付。Python 依赖使用独立 `.venv`；Java 与 JMeter 放在项目 `runtime/`，不需要修改系统 Java 或全局 Python 包。

## 部署前准备

准备 Python 3.11+，新机器建议 3.12，以便直接使用依赖 wheel。建议开发机具备 4 核 CPU、16GB 内存和 2GB 可用空间。高并发实验使用独立负载机，并给结果目录留出空间。Python、JDK 与原生库的 CPU 架构应匹配。

安装器识别 macOS arm64、macOS x86_64、Windows AMD64。其他平台可预装 JDK 17+ 并设置 `JAVA_HOME`。首次联网安装访问 Python 包索引、Apache、Amazon Corretto 与 GitHub Releases。

原始项目 `.docx` 仅作需求参考，不参与安装，不随源码包分发。

## 自动部署

macOS：

```bash
cd /path/to/jmeter
python3 --version
bash scripts/setup-macos.sh
./linklab doctor
./linklab demo --protocol mqtt
./linklab demo --protocol tcp
./linklab demo --protocol udp
./linklab demo --protocol http
```

Windows PowerShell：

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

两个入口均调用 `scripts/bootstrap.py`：准备固定组件、创建或复用 `.venv`、按 `requirements.lock` 安装依赖、执行 `doctor`。校验过的安装包可重复使用，摘要不符的文件不会被解压安装。

PowerShell 辅助入口为 `scripts/setup-windows.ps1`；若本机策略不允许运行 `.ps1`，使用 `.cmd` 或 `py -3 scripts\bootstrap.py`。

## 使用已有 JDK

macOS：

```bash
export JAVA_HOME="/path/to/jdk/Contents/Home"
bash scripts/setup-macos.sh
```

Windows：

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
.\scripts\setup-windows.cmd
```

存在 `JAVA_HOME` 时不额外下载 JDK。Java 选择顺序为 `JAVA_HOME`、项目 `runtime/jdk`、系统 `PATH`。`doctor` 检查 Java 主版本、JMeter 清单版本与插件摘要。

调整 Java 最大堆：macOS 使用 `LINKLAB_HEAP=2g ./linklab run scenarios/baseline.yaml`；Windows 先设置 `$env:LINKLAB_HEAP="2g"`。还需给采集器、Broker 和系统保留内存。

## 手工部署

1. 安装 JDK 17+，设置 `JAVA_HOME`。
2. 从 `deployments/artifacts.lock.json` 指定地址下载 JMeter，校验 SHA-512，解压为 `runtime/apache-jmeter-5.6.3`。
3. 下载 MQTT 插件，核对锁文件的 SHA-256，复制到 JMeter `lib/ext/`；同目录不要同时安装多个版本。
4. 创建 `.venv`，安装依赖与项目。

macOS：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
./linklab doctor
```

Windows：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\linklab.cmd doctor
```

JMeter 与 JDK 摘要来自官方分发记录；MQTT 插件摘要固定了本项目采用的官方 Release 下载产物。摘要锁定用于取得相同文件，不等同于组件签名背书。

## 离线部署

离线材料在**与目标机器相同操作系统、CPU 架构和 Python 主次版本**的联网准备机上制作。不能把 macOS 虚拟环境或原生 wheel 直接复制到 Windows。

先完成联网安装，再准备 wheelhouse：

```bash
.venv/bin/python -m pip wheel -r requirements.lock --wheel-dir downloads/wheels
```

```powershell
.\.venv\Scripts\python.exe -m pip wheel -r requirements.lock --wheel-dir downloads\wheels
```

传入离线机的材料：源码包；锁文件指定的 JMeter、插件、目标平台 JDK 压缩包；`downloads/wheels/`；Python 安装程序或已安装的 Python。已有合适 JDK 时可省略 JDK 包。

```bash
python3 scripts/bootstrap.py --offline
```

```powershell
py -3 scripts\bootstrap.py --offline
```

`--offline` 禁止组件联网下载，pip 使用 `--no-index`。缺包或摘要不符会失败。联网安装若复用了已有运行时，准备离线材料时需按锁文件另行补齐原始压缩包。

## 可选独立 MQTT Broker

已安装 Docker 的机器可运行 Mosquitto：

```bash
docker compose -f deployments/compose.yaml up -d
./linklab run scenarios/baseline.yaml
docker compose -f deployments/compose.yaml down
```

Windows 测试入口换为 `.\linklab.cmd`。Compose 仅映射 `127.0.0.1:1883`。默认实验使用 aMQTT，不依赖 Docker。本机无 Docker，Compose 路径未在本次环境实跑。

## 验收与迁移

依次执行 `doctor`、四协议 `demo`、`pipeline-demo`、自动化测试，保存结果目录和环境记录。Windows 的部署验收需在 Windows 上执行，macOS 实测不能代替。

迁移目录后重新运行安装脚本，重建 editable 引用并重新生成 JMX。旧报告可保留，其中的绝对路径仅供追溯。

下载受代理影响时可设置标准 `HTTPS_PROXY`，或将已校验文件手工放入 `downloads/`。不要关闭证书校验来解决下载错误。

## 官方资料

- [JMeter](https://jmeter.apache.org/download_jmeter.cgi)
- [EMQX MQTT 插件](https://github.com/emqx/mqtt-jmeter/releases/tag/v2.0.2)
- [Corretto 17](https://docs.aws.amazon.com/corretto/latest/corretto-17-ug/downloads-list.html)
- [Python](https://www.python.org/downloads/)
- [Mosquitto 镜像](https://hub.docker.com/_/eclipse-mosquitto)
