# /// script
# requires-python = ">=3.11"
# ///
"""Check for image-generation credentials without printing secret values."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


PROVIDERS = {
    "openai": ("OPENAI_API_KEY",),
    "replicate": ("REPLICATE_API_TOKEN",),
    "fal": ("FAL_KEY", "FAL_API_KEY"),
    "stability": ("STABILITY_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "together": ("TOGETHER_API_KEY",),
    "ideogram": ("IDEOGRAM_API_KEY",),
    "black-forest-labs": ("BFL_API_KEY", "BLACK_FOREST_LABS_API_KEY"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find image-generation credentials without exposing values.")
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(PROVIDERS),
        default=[],
        help="Limit the check to a provider. May be repeated. Default: all known providers.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        type=Path,
        default=[],
        help="Additional .env-style file to inspect. May be repeated.",
    )
    parser.add_argument(
        "--search-dir",
        action="append",
        type=Path,
        default=[],
        help="Additional directory to inspect for .env and .env.local. May be repeated.",
    )
    return parser.parse_args()


def default_env_files() -> list[Path]:
    cwd = Path.cwd()
    return [
        cwd / ".env",
        cwd / ".env.local",
        Path.home() / ".config" / "credentials" / ".env",
    ]


def env_files_from_dirs(dirs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in dirs:
        files.extend([directory / ".env", directory / ".env.local"])
    return files


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


def find_credentials(env_files: list[Path], providers: dict[str, tuple[str, ...]]) -> dict[str, object]:
    hits: list[dict[str, str]] = []
    checked_files: list[str] = []
    present_files: list[str] = []

    for provider, names in providers.items():
        for name in names:
            if os.environ.get(name):
                hits.append({"provider": provider, "variable": name, "source": "process environment"})
                break

    for path in env_files:
        resolved = path.expanduser().resolve()
        checked_files.append(str(resolved))
        values = parse_env_file(resolved)
        if values:
            present_files.append(str(resolved))
        for provider, names in providers.items():
            if any(values.get(name) for name in names):
                variable = next(name for name in names if values.get(name))
                hits.append({"provider": provider, "variable": variable, "source": str(resolved)})

    unique_hits: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for hit in hits:
        key = (hit["provider"], hit["variable"], hit["source"])
        if key not in seen:
            seen.add(key)
            unique_hits.append(hit)

    return {
        "found": bool(unique_hits),
        "credentials": unique_hits,
        "checked_files": checked_files,
        "present_env_files": present_files,
        "supported_variables": providers,
    }


def main() -> int:
    args = parse_args()
    env_files = default_env_files() + args.env_file + env_files_from_dirs(args.search_dir)
    providers = {name: PROVIDERS[name] for name in args.provider} if args.provider else PROVIDERS
    result = find_credentials(env_files, providers)
    print(json.dumps(result, indent=2))
    return 0 if result["found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
