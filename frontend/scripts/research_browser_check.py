"""Run Chrome against a temporary synthetic database and isolated API/Vite ports.

No collector or analytics watch process is launched. Existing services are untouched.
Only the node process created here and the in-process test API are stopped on exit.
"""

import asyncio
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from export_research_fixtures import capture, fixture_settings

from marketpulse.api.app import create_app


def main():
    frontend = Path(__file__).resolve().parents[1]
    # Refuse occupied test ports; never terminate or replace an existing server.
    for port in (8001, 5174):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    with TemporaryDirectory(prefix="marketpulse-research-browser-") as directory:
        path = Path(directory) / "synthetic.sqlite3"
        asyncio.run(capture(path))
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(fixture_settings(path)), host="127.0.0.1", port=8001, log_level="warning"
            )
        )
        thread = threading.Thread(target=server.run)
        thread.start()
        environment = dict(
            os.environ,
            MARKETPULSE_API_TARGET="http://127.0.0.1:8001",
            DASHBOARD_URL="http://127.0.0.1:5174",
        )
        log = (frontend / "test-results").resolve()
        log.mkdir(exist_ok=True)
        node = None
        try:
            with (log / "research-vite.log").open("w") as output:
                node = subprocess.Popen(
                    [
                        "node",
                        str(frontend / "node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "5174",
                        "--strictPort",
                    ],
                    cwd=frontend,
                    env=environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:5174/api/research/v1/status", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Isolated browser services failed startup")
                result = subprocess.run(
                    ["node", str(frontend / "node_modules/@playwright/test/cli.js"), "test"],
                    cwd=frontend,
                    env=environment,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError(f"Browser suite failed: {result.returncode}")
        finally:
            if node is not None and node.poll() is None:
                node.terminate()
                node.wait(timeout=15)
            server.should_exit = True
            thread.join(timeout=20)
            if thread.is_alive():
                raise RuntimeError("Isolated test API did not shut down")


if __name__ == "__main__":
    main()
