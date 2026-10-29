"""Start either the competition runner or both local web services."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    mode = os.environ.get("NEURON_MODE", "arena").strip().lower()
    if mode == "arena":
        os.execv(sys.executable, [sys.executable, str(ROOT / "runner.py"),
                 "--universe", os.environ.get("ARENA_INPUT", "/universe/universe.csv"),
                 "--lexicon", os.environ.get("ARENA_LEXICON", "/universe/lexicon.json"),
                 "--output", os.environ.get("ARENA_OUTPUT", "/output/output.csv")])
    if mode != "web":
        raise SystemExit("NEURON_MODE must be 'arena' or 'web'.")

    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    children: list[subprocess.Popen] = []
    try:
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=ROOT / "backend",
        ))
        if not stopping:
            children.append(subprocess.Popen(
                ["node", "server.js"],
                cwd=ROOT / "frontend",
                env={**os.environ, "HOSTNAME": "0.0.0.0", "PORT": "3000"},
            ))
        print("NEURON5 web: frontend on port 3000, API on port 8000.", flush=True)
        while not stopping:
            for child in children:
                code = child.poll()
                if code is not None:
                    print(f"Web service exited with code {code}; stopping container.", flush=True)
                    return code if code > 0 else 1
            time.sleep(0.1)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
