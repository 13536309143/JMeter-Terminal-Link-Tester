# 四协议实验中文技术报告

本目录收录 JMeter 终端与链路测试工具的 MQTT、TCP、UDP、HTTP 实验过程、截图与实测证据。

- [在线阅读完整中文报告](protocol-experiments-20261015/report.zh-CN.md)
- [下载 Word 正式报告（22 页）](protocol-experiments-20261015/JMeter四协议终端模拟与采集链路实验技术报告.docx)
- [查看 14 张实际页面截图](protocol-experiments-20261015/screenshots/)
- [实验运行索引](protocol-experiments-20261015/evidence/run-index.json)
- [自动化测试过程](protocol-experiments-20261015/evidence/automated-tests.log)
- [本次 GitHub 发布文件摘要清单](publication-manifest.json)

结果为 33 项实验符合预期、34 项自动化测试通过；正向与反向实验的判定口径见正文。截图来自真实执行产物的只读证据页面，并非 JMeter 原生 GUI 截图。实验使用回环网络与合成终端，结果不代表现场容量验收。

## 下载与复现

下载或克隆仓库后，打开 `protocol-experiments-20261015/report.zh-CN.html` 即可离线阅读，保留相邻的 `screenshots/` 目录。复现命令、环境、场景与故障注入方法见报告及[项目实验指南](../experiments.md)。每次运行的 JMX、JTL、独立采集 JSONL、配置、指标和结论均随本次 GitHub 资料保留。

## 发布范围与证据校验

GitHub 保留报告正文、Word、14 张截图、截图来源记录及关键原始运行证据。重复生成的 `dashboard/` 静态资源、包含机器诊断信息的 `jmeter.log` 和完整资料 ZIP 仅保留在本机交接资料中，不纳入此目录的 Git 版本。需要仪表盘时可按报告复跑，或用原始 JTL 重新生成。

资料内 `evidence/SHA256SUMS.json` 对应完整本地资料集，含上述未上传文件；校验 GitHub 中实际发布的文件请使用本目录 `publication-manifest.json`，其路径相对于本目录。这一发布清单记录 SHA-256，原始证据文件不作改写。

这些资料包含实验与测试内容，只发布到源码仓库，不加入可运行软件的 Release 发行包。
