# /// script
# requires-python = ">=3.11"
# ///
"""Create a Slack emoji run folder and start the proofing gallery."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the create-slack-emoji proofing gallery.")
    parser.add_argument("--run", help="Run slug. Default: YYYY-MM-DD-slack-emoji.")
    parser.add_argument("--output-root", type=Path, help="Output root. Default: ./slack-emojis.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the gallery URL in the browser.")
    parser.add_argument("--foreground", action="store_true", help="Run the gallery in the foreground.")
    return parser.parse_args()


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        if port_is_free(host, port):
            return port
    raise RuntimeError(f"No free port found from {preferred} to {preferred + 49}")


def log_tail(log_path: Path, limit: int = 4000) -> str:
    if not log_path.exists():
        return "(gallery log does not exist yet)"
    text = log_path.read_text(errors="replace")
    return text[-limit:] or "(gallery log is empty)"


def wait_until_ready(url: str, process: subprocess.Popen[bytes], log_path: Path, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Gallery server exited before it was reachable with status {process.returncode}.\n"
                f"Log tail:\n{log_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=0.3) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.15)

    process.terminate()
    raise RuntimeError(f"Gallery server was not reachable after {timeout:.1f}s.\nLog tail:\n{log_tail(log_path)}")


def default_output_root(skill_dir: Path) -> Path:
    return Path.cwd() / "slack-emojis"


def main() -> int:
    args = parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    run = args.run or f"{date.today().isoformat()}-slack-emoji"
    output_root = (args.output_root or default_output_root(skill_dir)).resolve()
    generated_dir = output_root / "generated" / run
    work_dir = output_root / "work" / run
    generated_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in ("sheets", "slices", "alpha", "prepared", "retired"):
        (work_dir / name).mkdir(exist_ok=True)

    port = available_port(args.host, args.port)
    serve_script = skill_dir / "scripts" / "serve_gallery.py"
    url = f"http://{args.host}:{port}/"
    cmd = [
        sys.executable,
        str(serve_script),
        str(generated_dir),
        "--host",
        args.host,
        "--port",
        str(port),
    ]

    print(f"generated_dir={generated_dir}", flush=True)
    print(f"work_dir={work_dir}", flush=True)
    print(f"url={url}", flush=True)
    (work_dir / "gallery.url").write_text(f"{url}\n")

    if args.foreground:
        if args.open:
            webbrowser.open(url)
        return subprocess.call(cmd)

    log_path = work_dir / "gallery.log"
    log = log_path.open("ab")
    process = subprocess.Popen(
        cmd,
        cwd=skill_dir,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (work_dir / "gallery.pid").write_text(f"{process.pid}\n")
    wait_until_ready(url, process, log_path)
    print(f"pid={process.pid}", flush=True)
    print(f"log={log_path}", flush=True)
    print("ready=true", flush=True)
    if args.open:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
