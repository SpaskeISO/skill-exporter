#!/usr/bin/env python3
"""Export globally installed skills that did not come from a local path.

Runs `npx skills list --global --json`, drops skills whose source is a local
filesystem path, and writes the remaining entries as JSON.

Examples:
    python export_skills.py
    python export_skills.py -o skills-export.json
    python export_skills.py -o - > skills-export.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def is_local_skill(skill: dict[str, Any]) -> bool:
    """Return True when a listed skill was installed from a local path."""
    source_type = str(skill.get("sourceType") or "").strip().lower()
    if source_type == "local":
        return True

    source = str(skill.get("source") or "").strip()
    if source.startswith(("~", "/", "./", "../")):
        return True
    if len(source) >= 3 and source[1] == ":" and source[2] in "\\/":
        return True
    return False


def installable_skills(skills: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """Split a skills list into exportable entries, local skips, and unsourced skips."""
    exported: list[dict[str, Any]] = []
    local_count = 0
    unsourced_count = 0
    for skill in skills:
        if is_local_skill(skill):
            local_count += 1
            continue
        source = str(skill.get("source") or "").strip()
        source_url = str(skill.get("sourceUrl") or "").strip()
        if not source and not source_url:
            unsourced_count += 1
            continue
        exported.append(skill)
    return exported, local_count, unsourced_count


def parse_skills_json(stdout: str) -> list[dict[str, Any]]:
    """Parse `skills list --json` stdout, ignoring any leading non-JSON noise."""
    text = stdout.strip()
    start = text.find("[")
    if start == -1:
        raise ValueError("skills list did not return a JSON array")
    parsed = json.loads(text[start:])
    if not isinstance(parsed, list):
        raise ValueError("skills list JSON was not an array")
    return parsed


def list_global_skills(npx: str) -> list[dict[str, Any]]:
    """Run npx and return the global skill list."""
    result = subprocess.run(
        [npx, "--yes", "skills", "list", "--global", "--json"],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    try:
        return parse_skills_json(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"Could not parse skills list JSON: {exc}\n")
        raise SystemExit(1) from exc


def write_export(skills: list[dict[str, Any]], output: str) -> None:
    payload = json.dumps(skills, indent=2) + "\n"
    if output == "-":
        sys.stdout.write(payload)
        return
    path = Path(output)
    path.write_text(payload, encoding="utf-8")
    print(f"Wrote {len(skills)} skills to {path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export global skills that were not installed from a local path.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="skills-export.json",
        help="Output JSON file, or '-' for stdout (default: skills-export.json)",
    )
    parser.add_argument(
        "--npx",
        default="npx",
        help="npx executable to run (default: npx)",
    )
    args = parser.parse_args(argv)

    skills = list_global_skills(args.npx)
    exported, local_count, unsourced_count = installable_skills(skills)
    if local_count:
        print(f"Skipped {local_count} local skills", file=sys.stderr)
    if unsourced_count:
        print(
            f"Skipped {unsourced_count} skills with no remote source",
            file=sys.stderr,
        )
    write_export(exported, args.output)


if __name__ == "__main__":
    main()
