# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
"""Generate Slack emoji candidates from a batch manifest in parallel.

This script intentionally owns the image-generation fan-out. Agents using the
skill should start this script instead of making one-off sequential image calls.

Two provider modes, each pinned to its provider's latest image model
(verified against OpenAI + Google DeepMind docs, 2026-06 — re-check before
trusting long-term; OpenAI is deprecating the gpt-image-1.x line by 2026-12):

  * ``openai`` -> ``gpt-image-2``            (legacy fallback: ``dall-e-3``)
  * ``google`` -> ``gemini-3.1-flash-image`` (Nano Banana 2; fast, top-ranked)
        alternatives: ``gemini-3-pro-image`` (Nano Banana Pro, best text),
                      ``gemini-2.5-flash-image`` (older Nano Banana)

Transparent backgrounds are handled here, automatically. Neither current top
model emits real transparency (gpt-image-2 dropped ``background:"transparent"``;
Gemini is opaque and stamps a SynthID watermark), so every option is prompted
onto a flat ``#00ff00`` chroma background, and this script keys that color out
and despills the green fringe before writing Slack-ready PNGs. No separate
cleanup step is needed.

The HTTP calls use only the standard library so the single dependency stays
Pillow. Credentials are read from the environment, then ``./.env`` /
``./.env.local``, then ``~/.config/credentials/.env`` (same convention as
check_image_credentials.py): ``OPENAI_API_KEY`` for openai, ``GEMINI_API_KEY``
or ``GOOGLE_API_KEY`` for google.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps


OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_BYTES = 128 * 1024
SIZES_TO_TRY = (128, 112, 96, 80, 64)
RETRYABLE_STATUSES = {408, 409, 429, 500, 502, 503, 504}
CHROMA = (0, 255, 0)  # #00ff00, the background color every option prompt requests

# Latest image model per provider. See module docstring for sourcing + caveats.
PROVIDER_DEFAULT_MODEL = {
    "openai": "gpt-image-2",
    "google": "gemini-3.1-flash-image",
}
PROVIDER_KEY_NAMES = {
    "openai": ("OPENAI_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


@dataclass(frozen=True)
class Job:
    index: int
    version: str
    filename: str
    prompt: str
    raw_path: Path
    final_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate all Slack emoji batch options in parallel.")
    parser.add_argument("--run", required=True, help="Run slug created by start_batch.py.")
    parser.add_argument("--output-root", type=Path, help="Output root. Default: ./slack-emojis.")
    parser.add_argument(
        "--provider",
        choices=("auto", "openai", "google"),
        default="auto",
        help="Image provider. auto picks the first with credentials (openai preferred).",
    )
    parser.add_argument("--model", help="Override the model id. Default: the provider's latest (see --provider).")
    parser.add_argument("--size", default="1024x1024", help="Requested image size (OpenAI). Default: 1024x1024.")
    parser.add_argument("--quality", default="medium", help="Image quality (OpenAI). Default: medium.")
    parser.add_argument("--background", default="opaque", choices=("opaque", "transparent", "auto"), help="GPT image background mode. Default: opaque.")
    parser.add_argument("--output-format", default="png", choices=("png", "webp", "jpeg"), help="GPT image output format. Default: png.")
    parser.add_argument("--transparent-mode", choices=("chroma", "preserve", "none"), default="chroma", help="Final PNG transparency handling. Default: chroma.")
    parser.add_argument("--max-workers", type=int, help="Parallel workers. Default: one worker per pending option.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Per-request timeout in seconds. Default: 300.")
    parser.add_argument("--retries", type=int, default=1, help="Retries for retryable API failures. Default: 1.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate options that already have final files.")
    parser.add_argument("--dry-run", action="store_true", help="Validate the manifest and print planned jobs without calling the API.")
    return parser.parse_args()


def default_output_root() -> Path:
    return Path.cwd() / "slack-emojis"


def default_env_files() -> list[Path]:
    cwd = Path.cwd()
    return [
        cwd / ".env",
        cwd / ".env.local",
        Path.home() / ".config" / "credentials" / ".env",
    ]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if name and value:
            values[name] = value
    return values


def secret_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    for path in default_env_files():
        values = parse_env_file(path.expanduser())
        if values.get(name):
            return values[name]
    return None


def provider_credential(provider: str) -> str | None:
    for name in PROVIDER_KEY_NAMES[provider]:
        value = secret_value(name)
        if value:
            return value
    return None


def resolve_provider(requested: str) -> str:
    if requested != "auto":
        return requested
    for provider in ("openai", "google"):
        if provider_credential(provider):
            return provider
    raise SystemExit("No image credentials found. Run check_image_credentials.py to inspect.")


def load_manifest(output_root: Path, run: str) -> dict[str, Any]:
    manifest_path = output_root / "work" / run / "options.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing batch manifest: {manifest_path}")
    return json.loads(manifest_path.read_text())


def build_jobs(manifest: dict[str, Any], overwrite: bool) -> tuple[list[Job], list[dict[str, Any]]]:
    generated_dir = Path(manifest["generated_dir"])
    work_dir = Path(manifest["work_dir"])
    raw_dir = work_dir / "model"
    raw_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[Job] = []
    skipped: list[dict[str, Any]] = []
    for option in manifest.get("options", []):
        filename = option["filename"]
        final_path = generated_dir / filename
        if final_path.exists() and not overwrite:
            skipped.append({"ok": True, "skipped": True, "filename": filename, "path": str(final_path)})
            continue
        jobs.append(
            Job(
                index=int(option["index"]),
                version=str(option["version"]),
                filename=filename,
                prompt=str(option["prompt"]),
                raw_path=raw_dir / filename,
                final_path=final_path,
            )
        )
    return jobs, skipped


# --------------------------------------------------------------------------- #
# OpenAI request
# --------------------------------------------------------------------------- #
def openai_payload(args: argparse.Namespace, model: str, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": args.size,
    }
    if model.startswith("gpt-image"):
        background = args.background
        if background == "transparent":
            # gpt-image-2 does not support transparent output; the chroma key
            # step makes it transparent anyway, so render opaque.
            background = "opaque"
        payload.update(
            {
                "background": background,
                "output_format": args.output_format,
                "quality": args.quality,
            }
        )
    elif model == "dall-e-3":
        payload["quality"] = "hd"
        payload["response_format"] = "b64_json"
    else:
        payload["quality"] = "standard"
        payload["response_format"] = "b64_json"
    return payload


def request_openai_image(args: argparse.Namespace, model: str, api_key: str, prompt: str) -> tuple[bytes, str | None]:
    body = json.dumps(openai_payload(args, model, prompt)).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    organization = secret_value("OPENAI_ORGANIZATION") or secret_value("OPENAI_ORG_ID")
    project = secret_value("OPENAI_PROJECT")
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project

    request = urllib.request.Request(OPENAI_IMAGES_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return image_bytes_from_openai(payload), response.headers.get("x-request-id")


def image_bytes_from_openai(response: dict[str, Any]) -> bytes:
    data = response.get("data") or []
    if not data:
        raise RuntimeError("Image API response did not include data.")
    first = data[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"])
    if first.get("url"):
        with urllib.request.urlopen(first["url"], timeout=120) as image_response:
            return image_response.read()
    raise RuntimeError("Image API response did not include b64_json or url.")


# --------------------------------------------------------------------------- #
# Google (Gemini / Nano Banana) request
# --------------------------------------------------------------------------- #
def request_gemini_image(args: argparse.Namespace, model: str, api_key: str, prompt: str) -> tuple[bytes, str | None]:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    body = json.dumps(payload).encode("utf-8")
    url = GEMINI_URL_TEMPLATE.format(model=model)
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
        return image_bytes_from_gemini(parsed), response.headers.get("x-request-id")


def image_bytes_from_gemini(response: dict[str, Any]) -> bytes:
    for candidate in response.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini response did not include inline image data.")


def request_image(args: argparse.Namespace, provider: str, model: str, api_key: str, prompt: str) -> tuple[bytes, str | None]:
    if provider == "openai":
        return request_openai_image(args, model, api_key, prompt)
    if provider == "google":
        return request_gemini_image(args, model, api_key, prompt)
    raise ValueError(f"Unknown provider: {provider}")


# --------------------------------------------------------------------------- #
# Transparent-background handling + Slack export
# --------------------------------------------------------------------------- #
def remove_green_background(image: Image.Image, chroma: tuple[int, int, int] = CHROMA) -> Image.Image:
    """Key a flat chroma background out to transparency and despill the fringe.

    Vectorized via ImageChops: alpha ramps from the per-pixel color distance to
    the chroma color, then green spill on soft edges is clamped so anti-aliased
    boundaries do not keep a green halo. Subjects never use #00ff00 (the prompt
    forbids it), so genuine green subject colors are preserved.
    """
    rgba = ImageOps.exif_transpose(image).convert("RGBA")
    rgb = rgba.convert("RGB")
    distance = ImageChops.difference(rgb, Image.new("RGB", rgb.size, chroma)).convert("L")
    tol, soft = 70, 50

    def ramp(d: int) -> int:
        if d <= tol:
            return 0
        if d >= tol + soft:
            return 255
        return int((d - tol) / soft * 255)

    rgba.putalpha(distance.point(ramp))
    r, g, b, a = rgba.split()
    g_clamped = ImageChops.darker(g, ImageChops.lighter(r, b))  # min(g, max(r, b))
    edge_mask = a.point(lambda v: 255 if v < 255 else 0)
    return Image.merge("RGBA", (r, Image.composite(g_clamped, g, edge_mask), b, a))


def fit_square(image: Image.Image, size: int) -> Image.Image:
    frame = ImageOps.exif_transpose(image).convert("RGBA")
    frame.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - frame.width) // 2
    y = (size - frame.height) // 2
    canvas.alpha_composite(frame, (x, y))
    return canvas


def export_slack_png(raw_path: Path, final_path: Path, transparent_mode: str) -> dict[str, Any]:
    with Image.open(raw_path) as source:
        if transparent_mode == "chroma":
            source_image = remove_green_background(source)
        elif transparent_mode == "preserve":
            source_image = ImageOps.exif_transpose(source).convert("RGBA")
        else:
            source_image = ImageOps.exif_transpose(source).convert("RGBA")
            source_image.putalpha(255)

        attempts: list[dict[str, int]] = []
        for size in SIZES_TO_TRY:
            prepared = fit_square(source_image, size)
            prepared.save(final_path, format="PNG", optimize=True)
            byte_count = final_path.stat().st_size
            attempts.append({"size": size, "bytes": byte_count})
            if byte_count <= MAX_BYTES:
                return {"path": str(final_path), "bytes": byte_count, "size": size, "attempts": attempts}

    return {"path": str(final_path), "bytes": final_path.stat().st_size, "size": SIZES_TO_TRY[-1], "attempts": attempts}


def generate_one(args: argparse.Namespace, provider: str, model: str, api_key: str, job: Job) -> dict[str, Any]:
    for attempt in range(args.retries + 1):
        try:
            image_data, request_id = request_image(args, provider, model, api_key, job.prompt)
            job.raw_path.write_bytes(image_data)
            export = export_slack_png(job.raw_path, job.final_path, args.transparent_mode)
            return {
                "ok": True,
                "index": job.index,
                "version": job.version,
                "filename": job.filename,
                "raw_path": str(job.raw_path),
                "path": export["path"],
                "bytes": export["bytes"],
                "size": export["size"],
                "request_id": request_id,
            }
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code in RETRYABLE_STATUSES and attempt < args.retries:
                time.sleep(2**attempt)
                continue
            return {
                "ok": False,
                "index": job.index,
                "version": job.version,
                "filename": job.filename,
                "status": error.code,
                "error": body,
            }
        except Exception as error:  # noqa: BLE001 - batch results should report per-option failures.
            if attempt < args.retries:
                time.sleep(2**attempt)
                continue
            return {
                "ok": False,
                "index": job.index,
                "version": job.version,
                "filename": job.filename,
                "error": str(error),
            }

    raise AssertionError("unreachable")


def main() -> int:
    args = parse_args()
    output_root = (args.output_root or default_output_root()).resolve()
    manifest = load_manifest(output_root, args.run)
    jobs, skipped = build_jobs(manifest, args.overwrite)

    provider = resolve_provider(args.provider)
    model = args.model or PROVIDER_DEFAULT_MODEL[provider]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "provider": provider,
                    "model": model,
                    "parallel_jobs": len(jobs),
                    "skipped": skipped,
                    "jobs": [{"index": job.index, "filename": job.filename} for job in jobs],
                },
                indent=2,
            )
        )
        return 0

    api_key = provider_credential(provider)
    if not api_key:
        names = " or ".join(PROVIDER_KEY_NAMES[provider])
        raise SystemExit(f"Missing {names}. Add it to the environment, repo .env/.env.local, or ~/.config/credentials/.env.")

    worker_count = args.max_workers or max(1, len(jobs))
    results: list[dict[str, Any]] = list(skipped)
    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(generate_one, args, provider, model, api_key, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda item: item.get("index", 0))
    work_dir = Path(manifest["work_dir"])
    results_path = work_dir / "generate-images-results.json"
    results_path.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"provider": provider, "model": model, "results_path": str(results_path), "results": results}, indent=2))
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
