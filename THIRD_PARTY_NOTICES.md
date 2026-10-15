# Third-party components and notices

JMeter Terminal & Link Tester is a wrapper and orchestration application. It is not an official Apache or EMQX product. The project's first-party source does not currently declare an outbound license; third-party software retains its own terms.

| Component | Source | License information |
| --- | --- | --- |
| Apache JMeter 5.6.3 | https://jmeter.apache.org/ | Apache License 2.0; bundled LICENSE, NOTICE and dependency licenses are retained |
| EMQX mqtt-jmeter 2.0.2 | https://github.com/emqx/mqtt-jmeter | Apache License 2.0; upstream dependency notices apply |
| Amazon Corretto 17 | https://aws.amazon.com/corretto/ | OpenJDK GPLv2 with Classpath Exception; bundled legal notices retained |
| Python | https://www.python.org/ | Python Software Foundation license |
| Eclipse Paho MQTT Python | https://github.com/eclipse-paho/paho.mqtt.python | EPL 2.0 / EDL 1.0 |
| PyYAML | https://pyyaml.org/ | MIT |
| psutil | https://github.com/giampaolo/psutil | BSD 3-Clause |
| PyInstaller bootloader | https://pyinstaller.org/ | GPL with bootloader exception; see upstream license |
| aMQTT, development only | https://github.com/Yakifo/amqtt | MIT |

The `source/` directory preserves the official Apache JMeter 5.6.3 source distribution for optional core development, including its LICENSE and NOTICE. It has not been represented as first-party work.

Runtime releases include the application and required vendor runtime files. Development fixtures, reference services, regression suites and experimental evidence remain in the source repository. Vendor runtime names containing the word “test” (for example JMeter's core `TestElement` classes) are functional runtime components, not bundled project regression cases.
