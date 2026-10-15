"""Import correlated network responses without development server dependencies."""
import base64
import json
from copy import deepcopy

from .collector import CollectionState
from .config import Scenario


def read_receipts(scenario, run_id, devices, directory):
    values = deepcopy(scenario.values)
    values["faults"]["processing_delay_ms"] = 0
    state = CollectionState(Scenario.from_mapping(values, scenario.origin), run_id, devices)
    with (directory / "collected.jsonl").open("w", encoding="utf-8") as output:
        for path in sorted(directory.glob("network-replies-*.jsonl")):
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        payload = base64.b64decode(item["payload_b64"], validate=True)
                        received = item["received_at_ms"]
                        if type(received) is not int:
                            raise ValueError("Invalid receipt timestamp")
                        record = state.process(payload, None, received, processed_ms=received)
                        record["protocol"] = scenario.values["protocol"]
                        output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    except (ValueError, TypeError, KeyError) as exc:
                        state.worker_error = f"Malformed network receipt file: {type(exc).__name__}"
    return state.summary()

