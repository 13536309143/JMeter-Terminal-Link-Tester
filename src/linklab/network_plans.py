"""Native JMeter TCP sampler and bounded Groovy UDP request/response sampler."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .plans import element, group, prop, script


def compile_network_plan(scenario, output: Path, run_id: str):
    v = scenario.values
    protocol = v["protocol"]
    output.mkdir(parents=True, exist_ok=True)
    devices = scenario.devices()
    csv_path = output / "devices.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["device_id", "device_type", "site"])
        writer.writeheader()
        writer.writerows(devices)
    root = ET.Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6.3")
    tree = ET.SubElement(root, "hashTree")
    plan, main = element(tree, "TestPlan", "TestPlanGui", f"JMeter Link Tester {protocol.upper()} · {v['name']}",
                         {"TestPlan.functional_mode": False, "TestPlan.serialize_threadgroups": False})
    args = ET.SubElement(plan, "elementProp", name="TestPlan.user_defined_variables", elementType="Arguments",
                         guiclass="ArgumentsPanel", testclass="Arguments", testname="Run variables")
    ET.SubElement(args, "collectionProp", name="Arguments.arguments")
    terminals = group(main, f"{protocol.upper()} 参数化终端", v["load"]["terminals"], v["load"]["ramp_up_seconds"])
    element(terminals, "CSVDataSet", "TestBeanGUI", "终端参数",
            {"filename": str(csv_path.resolve()), "fileEncoding": "UTF-8", "variableNames": "",
             "ignoreFirstLine": False, "delimiter": ",", "quotedData": False,
             "recycle": False, "stopThread": True, "shareMode": "shareMode.all"})
    base = json.dumps(str(output.resolve()))
    record = f"""
def receiptFile = new File({base}, 'network-replies-' + ctx.getThreadNum() + '.jsonl')
receiptFile.append(groovy.json.JsonOutput.toJson([received_at_ms: System.currentTimeMillis(),
    payload_b64: java.util.Base64.encoder.encodeToString(responseBytes)]) + '\\n', 'UTF-8')
"""
    if protocol == "udp":
        script(terminals, "UDP Open", f"""
def socket = new java.net.DatagramSocket()
socket.connect(java.net.InetAddress.getByName({json.dumps(v['network']['host'])}), {v['network']['port']})
vars.putObject('ll_socket', socket)
SampleResult.setIgnore()
""")
    _, loop = element(terminals, "LoopController", "LoopControlPanel", "定时请求",
                       {"LoopController.continue_forever": False, "LoopController.loops": v["load"]["messages_per_terminal"]})
    _, pacing = script(loop, "终端请求节拍", "SampleResult.setIgnore()")
    element(pacing, "ConstantTimer", "ConstantTimerGui", "终端请求间隔", {"ConstantTimer.delay": v["load"]["interval_ms"]})
    if protocol in ("tcp", "http"):
        if protocol == "http":
            settings = v["http"]
            node, request_tree = element(loop, "HTTPSamplerProxy", "HttpTestSampleGui", "HTTP Request",
                                          {"HTTPSampler.domain": settings["host"], "HTTPSampler.port": settings["port"],
                                           "HTTPSampler.protocol": "http", "HTTPSampler.path": settings["path"],
                                           "HTTPSampler.method": settings["method"], "HTTPSampler.follow_redirects": False,
                                           "HTTPSampler.auto_redirects": False, "HTTPSampler.use_keepalive": True,
                                           "HTTPSampler.connect_timeout": settings["connect_timeout_ms"],
                                           "HTTPSampler.response_timeout": settings["response_timeout_ms"],
                                           "HTTPSampler.postBodyRaw": settings["method"] != "GET"})
            args = ET.SubElement(node, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments",
                                 guiclass="HTTPArgumentsPanel", testclass="Arguments", testname="Payload")
            arguments = ET.SubElement(args, "collectionProp", name="Arguments.arguments")
            argument = ET.SubElement(arguments, "elementProp", name="payload" if settings["method"] == "GET" else "", elementType="HTTPArgument")
            for key, value in {"HTTPArgument.always_encode": settings["method"] == "GET",
                               "Argument.name": "payload" if settings["method"] == "GET" else "",
                               "Argument.value": "${ll_payload}", "Argument.metadata": "="}.items():
                prop(argument, key, value)
            headers, _ = element(request_tree, "HeaderManager", "HeaderPanel", "HTTP headers")
            entries = ET.SubElement(headers, "collectionProp", name="HeaderManager.headers")
            header_values = {"Content-Type": "application/json; charset=UTF-8"}
            if settings["bearer_token_env"]:
                header_values["Authorization"] = "Bearer ${__groovy(System.getenv('" + settings["bearer_token_env"] + "') ?: '')}"
            for name, value in header_values.items():
                header = ET.SubElement(entries, "elementProp", name="", elementType="Header")
                prop(header, "Header.name", name)
                prop(header, "Header.value", value)
            assertion, _ = element(request_tree, "ResponseAssertion", "AssertionGui", "Expected HTTP status",
                                    {"Assertion.test_field": "Assertion.response_code", "Assertion.assume_success": False})
            ET.SubElement(assertion, "intProp", name="Assertion.test_type").text = "8"
            values = ET.SubElement(assertion, "collectionProp", name="Asserion.test_strings")
            prop(values, "status", settings["expected_status"])
        else:
            node, request_tree = element(loop, "TCPSampler", "TCPSamplerGui", "TCP Request",
                                         {"TCPSampler.server": v["network"]["host"], "TCPSampler.port": v["network"]["port"],
                                          "TCPSampler.classname": "org.apache.jmeter.protocol.tcp.sampler.TCPClientImpl",
                                          "TCPSampler.nodelay": True, "TCPSampler.reUseConnection": True,
                                          "TCPSampler.closeConnection": False, "TCPSampler.EolByte": "10",
                                          "TCPSampler.ctimeout": v["network"]["connect_timeout_ms"],
                                          "TCPSampler.timeout": v["network"]["response_timeout_ms"],
                                          "TCPSampler.request": "${ll_payload}\n"})
        script(request_tree, "保存并关联响应", record.replace("responseBytes", "prev.getResponseData()") + """
if (prev.isSuccessful()) { try {
    def body = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString())
    if (body.message_id != vars.get('ll_message_id')) { throw new IllegalStateException('Response message_id mismatch') }
} catch (Exception e) {
    prev.setSuccessful(false)
    prev.setResponseCode('502')
    prev.setResponseMessage('Invalid or uncorrelated response')
} }
""", "JSR223PostProcessor")
    else:
        _, request_tree = script(loop, "UDP Request", f"""
def socket = vars.getObject('ll_socket')
byte[] requestBytes = vars.get('ll_payload').getBytes('UTF-8')
try {{
    socket.send(new java.net.DatagramPacket(requestBytes, requestBytes.length))
    long deadline = System.nanoTime() + {v['network']['response_timeout_ms']}L * 1000000L
    boolean matched = false
    int packets = 0
    while (!matched && System.nanoTime() < deadline && packets < 1000) {{
        socket.setSoTimeout((int)Math.max(1L, java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime())))
        byte[] buffer = new byte[65507]
        def packet = new java.net.DatagramPacket(buffer, buffer.length)
        socket.receive(packet)
        packets++
        byte[] responseBytes = java.util.Arrays.copyOf(packet.getData(), packet.getLength())
        {record}
        def body = new groovy.json.JsonSlurper().parseText(new String(responseBytes, 'UTF-8'))
        if (body.message_id == vars.get('ll_message_id')) {{
            matched = true
            SampleResult.setResponseData(responseBytes)
            SampleResult.setDataType('text')
            SampleResult.setResponseCode('200')
            SampleResult.setResponseMessage('Correlated UDP reply')
            SampleResult.setSuccessful(true)
        }}
    }}
    if (!matched) {{ throw new java.net.SocketTimeoutException('No correlated UDP response') }}
}} catch (java.net.SocketTimeoutException e) {{
    SampleResult.setSuccessful(false)
    SampleResult.setResponseCode('504')
    SampleResult.setResponseMessage('UDP response timeout')
}} catch (Exception e) {{
    log.warn('UDP request failure', e)
    SampleResult.setSuccessful(false)
    SampleResult.setResponseCode('502')
    SampleResult.setResponseMessage('Invalid UDP response or socket failure: ' + e.getClass().getSimpleName())
}}
""")
    script(request_tree, "生成可追溯请求", f"""
int seq = (vars.get('ll_seq') ?: '0').toInteger() + 1
vars.put('ll_seq', seq.toString())
def rng = vars.getObject('ll_rng')
if (rng == null) {{ rng = new Random({v['data']['seed']}L + ctx.getThreadNum()); vars.putObject('ll_rng', rng) }}
def messageId = '{run_id}:' + vars.get('device_id') + ':' + seq
vars.put('ll_message_id', messageId)
def body = [schema_version: 1, run_id: '{run_id}', device_id: vars.get('device_id'),
    device_type: vars.get('device_type'), site: vars.get('site'), seq: seq, message_id: messageId,
    sent_at_ms: System.currentTimeMillis(), temperature_c: Math.round((20 + rng.nextDouble() * 15) * 100) / 100.0,
    padding: 'x' * {v['data']['padding_bytes']}]
if ({v['faults']['invalid_every']} > 0 && seq % Math.max(1, {v['faults']['invalid_every']}) == 0) {{ body.temperature_c = 'invalid' }}
vars.put('ll_payload', groovy.json.JsonOutput.toJson(body))
""", "JSR223PreProcessor")
    if protocol == "udp":
        script(terminals, "UDP Drain", f"""
def socket = vars.getObject('ll_socket')
try {{
    long deadline = System.nanoTime() + 500000000L
    socket.setSoTimeout(100)
    while (System.nanoTime() < deadline) {{
        byte[] buffer = new byte[65507]
        def packet = new java.net.DatagramPacket(buffer, buffer.length)
        socket.receive(packet)
        byte[] responseBytes = java.util.Arrays.copyOf(packet.getData(), packet.getLength())
        {record}
    }}
}} catch (java.net.SocketTimeoutException ignored) {{
}} finally {{
    if (socket != null) {{ socket.close() }}
}}
SampleResult.setIgnore()
""")
    ET.indent(root, space="  ")
    path = output / "test-plan.jmx"
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
    scenario.write(output / "scenario.json")
    return path, devices
