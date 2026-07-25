"""Launch the whole Lantern stack: 3 node sidecars + the broker. One command, health-checked.

    python -m app.run_all

Ctrl+C stops everything. This is the demo's ignition key -- five processes coming up
clean beats five terminals and a prayer.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SERVICES = [
    ("BCH sidecar", "app.node_service:app", 8011, {"LANTERN_NODE": "BCH"}),
    ("MGH sidecar", "app.node_service:app", 8012, {"LANTERN_NODE": "MGH"}),
    ("BWH sidecar", "app.node_service:app", 8013, {"LANTERN_NODE": "BWH"}),
    ("Broker", "app.broker:app", 8000, {}),
]


def _healthy(port: int, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def main() -> None:
    procs: list[subprocess.Popen] = []
    try:
        for name, target, port, extra_env in SERVICES:
            env = {**os.environ, **extra_env}
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", target, "--port", str(port), "--log-level", "warning"],
                cwd=str(REPO), env=env,
            )
            procs.append(proc)
            # sidecars must be up before the broker can serve a query cleanly
            if "sidecar" in name:
                for _ in range(40):
                    if _healthy(port):
                        break
                    time.sleep(0.25)
            print(f"  started {name:<14} :{port}")

        print("\nwaiting for all services to report healthy...")
        deadline = time.time() + 20
        while time.time() < deadline:
            states = {port: _healthy(port) for _, _, port, _ in SERVICES}
            if all(states.values()):
                break
            time.sleep(0.5)

        print("\n=== Lantern is up ===")
        for name, _, port, _ in SERVICES:
            print(f"  {'OK ' if _healthy(port) else 'DOWN'}  {name:<14} http://localhost:{port}")
        print("\nResearcher console: http://localhost:8000/   ·   Ctrl+C to stop.\n")

        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        print("\nstopping Lantern...")
    finally:
        for proc in procs:
            proc.terminate()


if __name__ == "__main__":
    main()
