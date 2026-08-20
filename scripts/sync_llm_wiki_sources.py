"""Export Bub's useful code and docs into an LLM Wiki source folder."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_DESTINATION = Path.home() / "Documents" / "Bub Wiki" / "raw" / "sources" / "bub"
INCLUDED_SUFFIXES = {".json", ".md", ".py", ".service", ".sh", ".txt"}
TEXT_WRAPPED_SUFFIXES = {".py", ".service", ".sh"}
EXCLUDED_DIRS = {
    ".git",
    ".llm-wiki",
    ".opencode",
    ".venv",
    "__pycache__",
    "agent-workspace",
    "sf6frames",
}
EXCLUDED_NAMES = {
    ".env",
    "bub_response_log.jsonl",
    "buenavista_pin_tiers.json",
    "memory.md",
    "quiz_leaderboard.json",
    "sf6-sync.lock",
    "sf6_sync.log",
    "streetfighterdle_scores.json",
}


def should_export(relative_path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in relative_path.parts):
        return False
    if relative_path.name in EXCLUDED_NAMES:
        return False
    if relative_path.name.endswith("_move_images.py"):
        return False
    return relative_path.suffix.lower() in INCLUDED_SUFFIXES


def destination_path(root: Path, destination: Path, source: Path) -> Path:
    relative_path = source.relative_to(root)
    if source.suffix.lower() in TEXT_WRAPPED_SUFFIXES:
        relative_path = relative_path.with_name(f"{relative_path.name}.txt")
    return destination / relative_path


def sync_sources(root: Path, destination: Path) -> tuple[int, int]:
    expected: set[Path] = set()
    copied = 0

    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative_path = source.relative_to(root)
        if not should_export(relative_path):
            continue
        target = destination_path(root, destination, source)
        expected.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or source.read_bytes() != target.read_bytes():
            shutil.copy2(source, target)
            copied += 1

    removed = 0
    if destination.exists():
        for target in sorted(
            (path for path in destination.rglob("*") if path.is_file()),
            reverse=True,
        ):
            if target not in expected:
                target.unlink()
                removed += 1
        for directory in sorted(
            (path for path in destination.rglob("*") if path.is_dir()),
            reverse=True,
        ):
            if not any(directory.iterdir()):
                directory.rmdir()

    return copied, removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    destination = args.destination.expanduser().resolve()
    copied, removed = sync_sources(root, destination)
    print(f"LLM Wiki sources synced: copied={copied} removed={removed} destination={destination}")


if __name__ == "__main__":
    main()
