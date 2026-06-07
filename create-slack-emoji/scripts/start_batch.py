# /// script
# requires-python = ">=3.11"
# ///
"""Prepare a Slack emoji option batch and start/reuse the proofing gallery."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path


WORK_SUBDIRS = ("sheets", "slices", "alpha", "prepared", "retired")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an emoji batch manifest and start the gallery.")
    parser.add_argument("--run", help="Run slug. Default: YYYY-MM-DD-slack-emoji.")
    parser.add_argument("--output-root", type=Path, help="Output root. Default: ./slack-emojis.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the gallery URL in the browser.")
    parser.add_argument("--watch", action="store_true", help="Wait for expected option files from an existing batch.")
    parser.add_argument("--timeout", type=float, default=600.0, help="Seconds to wait with --watch. Default: 600.")
    parser.add_argument("--poll", type=float, default=2.0, help="Polling interval with --watch. Default: 2.")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Launch generate_images.py as a durable background process after writing the manifest.",
    )
    parser.add_argument("--provider", help="Image provider for --generate (auto|openai|google). Forwarded to generate_images.py.")
    parser.add_argument("--model", help="Image model id for --generate. Forwarded to generate_images.py.")
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="VERSION|THEME|PROMPT",
        help="One option spec. Repeat for each option.",
    )
    return parser.parse_args()


def process_is_alive(pid_path: Path) -> bool:
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def parse_option(raw: str, index: int) -> dict[str, object]:
    parts = raw.split("|", 2)
    if len(parts) != 3:
        raise ValueError(f"--option #{index} must use VERSION|THEME|PROMPT")
    version, theme, prompt = (part.strip() for part in parts)
    if not version or not theme or not prompt:
        raise ValueError(f"--option #{index} has an empty VERSION, THEME, or PROMPT")
    return {
        "index": index,
        "version": version,
        "filename": f"{version}.png",
        "theme": theme,
        "prompt": prompt,
    }


def default_output_root(skill_dir: Path) -> Path:
    return Path.cwd() / "slack-emojis"


def watch_batch(output_root: Path, run: str, timeout: float, poll: float) -> int:
    generated_dir = output_root / "generated" / run
    work_dir = output_root / "work" / run
    manifest_path = work_dir / "options.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing batch manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    expected = [item["filename"] for item in manifest.get("options", [])]
    if not expected:
        raise SystemExit(f"Manifest has no options: {manifest_path}")

    deadline = time.monotonic() + timeout
    ready: list[Path] = []
    missing = expected
    while time.monotonic() <= deadline:
        ready = [generated_dir / name for name in expected if (generated_dir / name).is_file()]
        missing = [name for name in expected if not (generated_dir / name).is_file()]
        if not missing:
            print(json.dumps({"ready": [str(path) for path in ready], "missing": [], "timed_out": False}, indent=2))
            return 0
        time.sleep(poll)

    print(json.dumps({"ready": [str(path) for path in ready], "missing": missing, "timed_out": True}, indent=2))
    return 1


def start_gallery(skill_dir: Path, output_root: Path, run: str, host: str, port: int, open_gallery: bool) -> str:
    start_script = skill_dir / "scripts" / "start_gallery.py"
    cmd = [
        sys.executable,
        str(start_script),
        "--run",
        run,
        "--output-root",
        str(output_root),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if open_gallery:
        cmd.append("--open")
    result = subprocess.run(cmd, cwd=skill_dir, check=True, text=True, capture_output=True)
    print(result.stdout, end="")
    for line in result.stdout.splitlines():
        if line.startswith("url="):
            return line.removeprefix("url=").strip()
    raise RuntimeError("start_gallery.py did not print a url= line")


def launch_generation(
    skill_dir: Path,
    output_root: Path,
    run: str,
    provider: str | None,
    model: str | None,
    work_dir: Path,
) -> tuple[int, Path]:
    """Start generate_images.py as a durable detached process.

    Uses start_new_session=True (setsid) and redirects output to a log file so
    the generation survives after this command returns and the caller's shell
    exits. Do NOT launch generation with a trailing shell ``&``: that detaches it
    from the agent's tool wrapper and the process is killed when the shell exits.
    """
    generate_script = skill_dir / "scripts" / "generate_images.py"
    uv = shutil.which("uv") or "uv"
    cmd = [uv, "run", str(generate_script), "--run", run, "--output-root", str(output_root)]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    log_path = work_dir / "generate-images.log"
    log = log_path.open("ab")
    process = subprocess.Popen(
        cmd,
        cwd=skill_dir,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (work_dir / "generate.pid").write_text(f"{process.pid}\n")
    return process.pid, log_path


def main() -> int:
    args = parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    run = args.run or f"{date.today().isoformat()}-slack-emoji"
    output_root = (args.output_root or default_output_root(skill_dir)).resolve()

    if args.watch:
        return watch_batch(output_root, run, args.timeout, args.poll)

    if not args.option:
        raise SystemExit("At least one --option VERSION|THEME|PROMPT is required.")

    generated_dir = output_root / "generated" / run
    work_dir = output_root / "work" / run
    generated_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in WORK_SUBDIRS:
        (work_dir / name).mkdir(exist_ok=True)

    options = [parse_option(raw, index) for index, raw in enumerate(args.option, start=1)]
    manifest = {
        "run": run,
        "output_root": str(output_root),
        "generated_dir": str(generated_dir),
        "work_dir": str(work_dir),
        "options": options,
    }
    manifest_path = work_dir / "options.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # Gallery state is shared across runs at the work/ root so a single
    # persistent gallery is reused for every batch instead of one per run.
    gallery_state_dir = output_root / "work"
    url_path = gallery_state_dir / "gallery.url"
    pid_path = gallery_state_dir / "gallery.pid"
    if process_is_alive(pid_path) and url_path.exists():
        url = url_path.read_text().strip()
        print(f"generated_dir={generated_dir}")
        print(f"work_dir={work_dir}")
        print(f"url={url}")
        print(f"manifest={manifest_path}")
        print("gallery=reused")
    else:
        url = start_gallery(skill_dir, output_root, run, args.host, args.port, args.open)
        print(f"manifest={manifest_path}")
        print("gallery=started")

    if args.generate:
        pid, log_path = launch_generation(skill_dir, output_root, run, args.provider, args.model, work_dir)
        print(f"generation=launched pid={pid} log={log_path}")

    print("options:")
    for option in options:
        print(f"- {option['filename']} | {option['theme']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
