"""Self-contained HTML/Markdown reports with escaped data and no remote resources."""
from __future__ import annotations

import html
import json
from pathlib import Path


def display(value):
    if value is None:
        return "无有效数据"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def write_report(output: Path, result: dict):
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    escape = lambda v: html.escape(display(v), quote=True)
    jtl, collection = result["jmeter"], result["collection"]
    protocol = result.get("protocol", "mqtt")
    sample_label = {"mqtt": "MQTT Publish", "tcp": "TCP Request", "udp": "UDP Request", "http": "HTTP Request"}[protocol]
    publish = jtl["labels"].get(sample_label, {})
    status = "通过" if result["acceptance"]["passed"] else "未通过"
    timing_note = ("MQTT Publish 耗时由 EMQX 插件测量；QoS 0 不等待 PUBACK。MQTT Subscribe 是批次探针，时间不能作为端到端延迟。独立采集器以发送时间戳计算传输观测延迟和采集处理延迟。"
                   if protocol == "mqtt" else
                   "TCP 按 LF 字节分帧，UDP 与 HTTP 通过 message_id 关联响应。请求耗时来自 JMeter；响应往返延迟以请求发送时间戳到客户端收到响应的时间计算，包含服务端处理时间。它不能解释为单向网络延迟。")
    cards = [("预期消息", result["expected_messages"]), ("有效唯一消息", collection.get("valid_unique", 0)),
             ("完整率 %", collection.get("delivery_rate_pct")), ("采样错误率 %", jtl["error_rate_pct"]),
             ("业务请求 P95 ms", publish.get("p95_ms")), ("采集处理 P95 ms" if protocol == "mqtt" else "响应往返 P95 ms", collection.get("e2e", {}).get("p95_ms"))]
    card_html = "".join(f'<div class="card"><span>{escape(k)}</span><strong>{escape(v)}</strong></div>' for k, v in cards)
    gates = "".join(f'<tr><td>{escape(g["name"])}</td><td>{escape(g["actual"])}</td><td>{escape(g["operator"])} {escape(g["expected"])}</td><td class="{"ok" if g["passed"] else "fail"}">{"通过" if g["passed"] else "未通过"}</td></tr>' for g in result["acceptance"]["gates"])
    labels = "".join(f'<tr><td>{escape(k)}</td>' + "".join(f'<td>{escape(v.get(f))}</td>' for f in ("count", "errors", "mean_ms", "p95_ms", "p99_ms")) + "</tr>" for k, v in jtl["labels"].items())
    error_rows = "".join(f'<li>{escape(k)} × {escape(v)}</li>' for k, v in jtl["errors_by_message"].items()) or "<li>无采样错误</li>"
    invalid_rows = "".join(f'<li>{escape(k)} × {escape(v)}</li>' for k, v in collection.get("invalid_reasons", {}).items()) or "<li>无非法数据</li>"
    trend = jtl["series"]
    if trend:
        max_y = max(1, max(p["samples"] for p in trend))
        first_second = trend[0]["timestamp_seconds"]
        span = max(1, trend[-1]["timestamp_seconds"] - first_second)
        points = " ".join(f'{30 + (p["timestamp_seconds"] - first_second) * 840 / span:.1f},{160 - p["samples"] * 130 / max_y:.1f}' for p in trend)
        chart = f'<svg viewBox="0 0 900 190" role="img" aria-label="发布采样每秒分布"><path d="M30 20V160H880" fill="none" stroke="#b6c5d4"/><polyline points="{points}" fill="none" stroke="#1767b2" stroke-width="3"/><text x="30" y="183" fill="#526579">每个点对应一个有采样的秒桶，最大 {max_y} 条/秒</text></svg>'
    else:
        chart = "<p>无发布采样</p>"
    failure = f'<p class="fail">执行异常：{escape(result["error"])}</p>' if result.get("error") else ""
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JMeter 终端与链路测试报告 · {escape(result['scenario_name'])}</title>
<style>body{{font:15px/1.7 system-ui,-apple-system,'Microsoft YaHei',sans-serif;color:#203247;background:#f3f6fa;margin:0}}main{{max-width:1100px;margin:40px auto;padding:0 24px 48px}}h1{{font-size:30px;letter-spacing:-.5px;margin-bottom:8px}}h2{{font-size:21px;margin-top:32px}}.eyebrow{{color:#526579;font-size:13px;letter-spacing:2px}}.meta{{color:#526579;overflow-wrap:anywhere}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:28px}}.card,section{{background:white;border:1px solid #dce4ed;border-radius:10px;padding:20px}}.card span{{display:block;color:#526579}}.card strong{{font-size:29px}}section{{margin-top:16px;overflow:auto}}table{{border-collapse:collapse;width:100%;text-align:left}}th,td{{padding:10px 12px;border-bottom:1px solid #e3e9f0}}th{{background:#f3f6fa}}.ok{{color:#087a55}}.fail{{color:#b72c37}}svg{{width:100%;max-height:230px}}code{{background:#edf2f7;padding:2px 5px}}a{{color:#1767b2}}@media(max-width:640px){{.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}h1{{font-size:25px}}}}@media print{{body{{background:white}}main{{margin:0}}section,.card{{break-inside:avoid}}}}</style>
<main><div class="eyebrow">JMETER TERMINAL & LINK TESTER</div><h1>终端模拟与采集链路测试报告</h1>
<p class="meta">{escape(result['scenario_name'])} · {protocol.upper()} · 运行 {escape(result['run_id'])}<br>{escape(result['started_at'])} · 状态 {escape(result['status'])} · 验收 <b class="{'ok' if status == '通过' else 'fail'}">{status}</b></p>{failure}
<div class="cards">{card_html}</div><h2>验收门禁</h2><section><table><tr><th>检查项</th><th>实际值</th><th>阈值</th><th>结论</th></tr>{gates}</table></section>
<h2>分操作采样</h2><section><table><tr><th>操作</th><th>采样数</th><th>错误数</th><th>平均 ms</th><th>P95 ms</th><th>P99 ms</th></tr>{labels}</table>
<p>{timing_note}</p></section>
<h2>业务采样分布</h2><section>{chart}<p>业务消息吞吐量：{escape(result.get('message_throughput_per_second', result.get('publish_throughput_per_second')))} 条/秒。统计区间采用整个 JMeter 执行采样区间，包含连接、Ramp-up 和收尾。实测峰值活跃终端数：{escape(jtl.get('peak_active_terminals'))}。</p></section>
<h2>数据质量与异常</h2><section><p>缺失 {escape(collection.get('missing', 0))} · 重复 {escape(collection.get('duplicates', 0))} · 乱序 {escape(collection.get('out_of_order', 0))} · 注入丢弃 {escape(collection.get('injected_drops', 0))} · 队列溢出 {escape(collection.get('queue_overflows', 0))}</p><ul>{invalid_rows}</ul><ul>{error_rows}</ul></section>
<h2>证据与复现</h2><section><p><a href="summary.json">结构化汇总</a> · <a href="scenario.json">场景快照</a> · <a href="samples.jtl">原始 JTL</a> · <a href="collected.jsonl">采集记录</a> · <a href="test-plan.jmx">JMeter 脚本</a> · <a href="console.log">执行日志</a></p><p>故障配置：<code>{escape(json.dumps(result['faults'], ensure_ascii=False))}</code></p><p>本报告反映本次运行与配置，不构成整个平台的并发用户数、长期可用性、等保或信创适配验收结论。</p></section></main></html>"""
    (output / "report.html").write_text(document, encoding="utf-8")
    markdown = f"# JMeter 终端与链路测试报告\n\n场景：{result['scenario_name']}  \n运行：`{result['run_id']}`  \n结论：**{status}**\n\n"
    markdown += "| 指标 | 实测 |\n| --- | ---: |\n" + "".join(f"| {k} | {display(v)} |\n" for k, v in cards)
    markdown += "\n## 验收门禁\n\n| 项目 | 实际 | 阈值 | 结果 |\n| --- | ---: | --- | --- |\n"
    markdown += "".join(f"| {g['name']} | {display(g['actual'])} | {g['operator']} {g['expected']} | {'通过' if g['passed'] else '未通过'} |\n" for g in result["acceptance"]["gates"])
    markdown += "\n详见同目录 `report.html`、`summary.json` 与原始采样/采集记录。\n"
    (output / "report.md").write_text(markdown, encoding="utf-8")


def compare_results(baseline: Path, candidate: Path):
    def load(path):
        return json.loads((path / "summary.json" if path.is_dir() else path).read_text(encoding="utf-8"))
    a, b = load(baseline), load(candidate)
    metrics = {
        "request_p95_ms": lambda x: x["jmeter"]["labels"].get({"mqtt": "MQTT Publish", "tcp": "TCP Request", "udp": "UDP Request", "http": "HTTP Request"}[x.get("protocol", "mqtt")], {}).get("p95_ms"),
        "e2e_p95_ms": lambda x: x["collection"].get("e2e", {}).get("p95_ms"),
        "delivery_rate_pct": lambda x: x["collection"].get("delivery_rate_pct"),
        "error_rate_pct": lambda x: x["jmeter"].get("error_rate_pct"),
        "message_throughput_per_second": lambda x: x.get("message_throughput_per_second", x.get("publish_throughput_per_second")),
    }
    changes = {}
    for name, get in metrics.items():
        before, after = get(a), get(b)
        delta = after - before if before is not None and after is not None else None
        changes[name] = {"baseline": before, "candidate": after, "delta": delta,
                         "change_pct": delta / before * 100 if delta is not None and before else None}
    return {"baseline_run_id": a["run_id"], "candidate_run_id": b["run_id"],
            "comparable_load": a["load"] == b["load"],
            "same_protocol": a.get("protocol", "mqtt") == b.get("protocol", "mqtt"),
            "same_collection_stage": a.get("collection_stage", "up") == b.get("collection_stage", "up"), "metrics": changes}
