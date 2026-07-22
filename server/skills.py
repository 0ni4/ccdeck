"""Discover installed Claude Code skills from SKILL.md files.

Sources:
- personal: ~/.claude/skills/<name>/SKILL.md          -> invoked as /<name>
- plugin:   ~/.claude/plugins/**/<plugin>/skills/<name>/SKILL.md -> /<plugin>:<name>

Built-in skills bundled inside the claude CLI (e.g. dataviz) are not on disk, so
they are not listed here. Frontmatter is parsed without a YAML dependency.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
PLUGINS_DIR = CLAUDE_DIR / "plugins"

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line[:1].isspace() or line.lstrip().startswith("-"):
            # skip blank lines and nested/list entries (e.g. allowed-tools items)
            continue
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in fm:
            fm[key] = val
    return fm


def _read_skill(path: Path, source: str, command: str,
                plugin: Optional[str] = None) -> Optional[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm = _parse_frontmatter(text)
    name = fm.get("name") or path.parent.name
    invocable = fm.get("user-invocable", "").lower()
    return {
        "name": name,
        "command": command,
        "description": fm.get("description", ""),
        "source": source,           # "personal" or the plugin name
        "kind": "plugin" if plugin else "personal",
        "userInvocable": invocable != "false",  # default true when unspecified
        "path": str(path),
    }


def list_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()

    # personal: ~/.claude/skills/<name>/SKILL.md
    if SKILLS_DIR.is_dir():
        for sk in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            name = sk.parent.name
            item = _read_skill(sk, source="personal", command=f"/{name}")
            if item and item["command"] not in seen:
                seen.add(item["command"])
                skills.append(item)

    # plugin: ~/.claude/plugins/**/<plugin>/skills/<name>/SKILL.md
    if PLUGINS_DIR.is_dir():
        for sk in sorted(PLUGINS_DIR.rglob("skills/*/SKILL.md")):
            # .../<plugin>/skills/<skill_name>/SKILL.md
            skill_name = sk.parent.name
            plugin_dir = sk.parent.parent.parent  # the <plugin> dir
            plugin = plugin_dir.name
            item = _read_skill(sk, source=plugin,
                               command=f"/{plugin}:{skill_name}", plugin=plugin)
            if item and item["command"] not in seen:
                seen.add(item["command"])
                skills.append(item)

    skills.sort(key=lambda s: (s["kind"] != "personal", s["source"].lower(), s["name"].lower()))
    return skills
