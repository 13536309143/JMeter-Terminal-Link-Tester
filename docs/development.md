# Development and verification

The public application name is **JMeter Terminal & Link Tester**. The Python namespace remains `linklab` so existing generated plans and development commands remain compatible. `jmeter-link-tester` is the production command surface; `linklab` includes development fixtures and experiments.

## Source environment

Run `python3 scripts/bootstrap.py` on macOS or `py -3 scripts/bootstrap.py` on Windows. It creates an isolated virtual environment and installs pinned components. Open the repository in an IDE with `.venv` selected as the interpreter.

The `source/` tree is the unmodified official JMeter 5.6.3 source distribution. Its LICENSE and NOTICE are retained. Ordinary wrapper development happens in `src/linklab/`; building JMeter itself is optional, using `scripts/gradlew createDist` with the project JDK.

## Extension points

| Change | Modules |
| --- | --- |
| Add terminal fields | `config.py`, payload generation in `plans.py`/`network_plans.py`, `CollectionState` validation |
| Add a protocol | Scenario validation, plan compiler, business sample label, receipt import, external reference fixture and integration scenarios |
| Add an acceptance gate | `metrics.evaluate`, structured summary and report presentation |
| Connect a real collector | Emit correlated messages after the collector's commit, configure `collection.topic_stage` |
| Change report layout | `reporting.py`; keep external data escaped and avoid remote dependencies |
| Change distribution contents | `scripts/release_bundle.py` allowlist and production dependency graph |

Never infer delivery from a successful publish alone. Preserve message identities, validate expected sample counts, and treat missing or unmeasurable data as a failed gate. Generate timestamps after pacing. Keep protocol fixtures out of the production import graph.

## Automated checks

```bash
.venv/bin/python -m unittest discover -s tests -v
LINKLAB_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
./linklab experiments --protocol all
```

On Windows use `.venv\Scripts\python.exe` and `$env:LINKLAB_INTEGRATION="1"`. The normal suite skips the two expensive real-JMeter methods unless the flag is set. The full suite covers MQTT QoS 0/2, TCP, UDP and HTTP in addition to unit and local socket checks.

The experimental matrix validates expected detector signals, not merely a nonzero exit status. Negative cases must fail business acceptance for the intended reason. Evidence is retained in the repository under `docs/evidence/` and in GitHub Actions artifacts.

## Release construction

Install PyInstaller 6.16.0 in the source environment and run `scripts/release_bundle.py` on each target operating system. PyInstaller cannot produce a Windows application from macOS, so the release workflow builds Windows x64, macOS ARM64 and macOS x64 separately.

The bundle entry is `scripts/frozen_entry.py` → `production_cli.py`. It excludes development CLI, Broker, reference services, SQLite lab bridge, regression modules, fault scenarios and evidence. The package embeds Java/JMeter, application dependencies, four editable operational profiles and runtime guides.

`scripts/verify_release.py <extracted-bundle>` starts fixtures from the source checkout, executes the frozen application with invalid system Java paths, verifies all four protocols and a negative HTTP path, and writes evidence outside the bundle. This verification code is never copied into the runtime archive.

GitHub Actions `release.yml` builds and verifies all three platforms before publishing the tagged release. Attached runtime archives exclude project testing material. GitHub also automatically exposes source archives for a release tag; those source archives retain repository tests by design.
