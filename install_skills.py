#!/usr/bin/env python3
"""Install exported skills globally as symlinks.

Reads the JSON written by export_skills.py and runs, for each skill:

    npx skills add <source> --skill <name> --global --yes --agent <agents...>

Agents come from the export. PromptScript and Eve are omitted because they
have no global skills directory; leaving agent selection to the CLI adds every
universal agent and those two then fail the install.

The skills CLI uses symlink mode unless `--copy` is passed, so each skill is
linked from the agent directories to the global canonical copy.

Examples:
    python install_skills.py skills-export.json
    python export_skills.py -o - | python install_skills.py -
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def is_local_skill(skill: dict[str, Any]) -> bool:
    """Return True when a skill was installed from a local path."""
    source_type = str(skill.get("sourceType") or "").strip().lower()
    if source_type == "local":
        return True

    source = str(skill.get("source") or "").strip()
    if source.startswith(("~", "/", "./", "../")):
        return True
    if len(source) >= 3 and source[1] == ":" and source[2] in "\\/":
        return True
    return False


# Display names whose CLI id is not the hyphenated lowercase form.
_AGENT_IDS = {
    "AiderDesk": "aider-desk",
    "Autohand Code CLI": "autohand-code",
    "IBM Bob": "bob",
    "Code Studio": "codestudio",
    "Cortex Code": "cortex",
    "Deep Agents": "deepagents",
    "Devin for Terminal": "devin",
    "Grok Build": "grok",
    "inference.sh": "inference-sh",
    "Kilo Code": "kilo",
    "Rovo Dev": "rovodev",
    "Roo Code": "roo",
}

# These agents reject `skills add --global`.
_NO_GLOBAL_AGENTS = {"promptscript", "eve"}


def agent_id(label: str) -> str:
    """Map a skills-list display name to a CLI agent id."""
    label = label.strip()
    if label in _AGENT_IDS:
        return _AGENT_IDS[label]
    return label.lower().replace(" ", "-")


def target_agents(skill: dict[str, Any]) -> list[str]:
    """Return global-capable agent ids recorded on an exported skill."""
    agents: list[str] = []
    raw = skill.get("agents") or []
    if not isinstance(raw, list):
        return agents
    for label in raw:
        agent = agent_id(str(label))
        if not agent or agent in _NO_GLOBAL_AGENTS or agent in agents:
            continue
        agents.append(agent)
    return agents


def package_spec(skill: dict[str, Any]) -> str | None:
    """Return the package argument for `skills add`, or None if it cannot be installed."""
    if is_local_skill(skill):
        return None
    source = str(skill.get("source") or "").strip()
    if source:
        return source
    source_url = str(skill.get("sourceUrl") or "").strip()
    return source_url or None


def build_add_command(
    npx: str,
    package: str,
    skill_name: str,
    agents: list[str],
) -> list[str]:
    """Build a global symlink install command for one skill."""
    command = [
        npx,
        "--yes",
        "skills",
        "add",
        package,
        "--skill",
        skill_name,
        "--global",
        "--yes",
    ]
    if agents:
        command.append("--agent")
        command.extend(agents)
    return command


def load_export(path: str) -> list[dict[str, Any]]:
    """Load an export JSON array from a file path or stdin."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("export JSON must be an array of skills")
    return parsed


def install_skill(npx: str, skill: dict[str, Any]) -> bool:
    """Install one skill. Return True when npx succeeds."""
    name = str(skill.get("name") or "").strip()
    package = package_spec(skill)
    if not name or not package:
        label = name or "<unnamed>"
        print(f"Skipped {label}: no remote source", file=sys.stderr)
        return False

    agents = target_agents(skill)
    if not agents:
        print(f"Skipped {name}: no agents that support global install", file=sys.stderr)
        return False

    command = build_add_command(npx, package, name, agents)
    print(
        f"Installing {name} from {package} for {', '.join(agents)}",
        file=sys.stderr,
    )
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(f"Failed to install {name} (exit {result.returncode})", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Install each exported skill globally as a symlink.",
    )
    parser.add_argument(
        "export",
        nargs="?",
        default="-",
        help="Export JSON from export_skills.py, or '-' for stdin (default: stdin)",
    )
    parser.add_argument(
        "--npx",
        default="npx",
        help="npx executable to run (default: npx)",
    )
    args = parser.parse_args(argv)

    if args.export == "-" and sys.stdin.isatty():
        parser.error("pass an export file, or pipe JSON on stdin")

    try:
        skills = load_export(args.export)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"Could not read export: {exc}\n")
        raise SystemExit(1) from exc

    if not skills:
        print("Export contains no skills", file=sys.stderr)
        return

    failed = 0
    for skill in skills:
        if not isinstance(skill, dict):
            print("Skipped a non-object entry in the export", file=sys.stderr)
            failed += 1
            continue
        if not install_skill(args.npx, skill):
            failed += 1

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
