"""Reads the Claude Code session store (~/.claude/projects/**.jsonl).

To avoid fully parsing huge JSONL files (10MB+) on every listing, session
metadata is gathered with a single raw-text pass plus an (mtime, size) cache.
Only fetching a transcript itself parses every line as JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PROJECTS_ROOT = Path.home() / ".claude" / "projects"

_RE_CWD = re.compile(r'"cwd":"((?:[^"\\]|\\.)*)"')
_RE_TS = re.compile(r'"timestamp":"([^"]+)"')
_RE_BRANCH = re.compile(r'"gitBranch":"((?:[^"\\]|\\.)*)"')


def _json_unescape(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


@dataclass
class SessionMeta:
    session_id: str
    project_id: str
    title: str = ""
    last_prompt: str = ""
    cwd: str = ""
    git_branch: str = ""
    first_ts: str = ""
    last_ts: str = ""
    user_turns: int = 0
    size_bytes: int = 0
    pr_url: str = ""
    version: str = ""
    tag: str = ""
    has_custom_title: bool = False
    # stats (aggregated from assistant-message usage during the single pass)
    in_tokens: int = 0
    out_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    web_searches: int = 0
    web_fetches: int = 0
    assistant_turns: int = 0
    models: set = field(default_factory=set)

    def _duration_ms(self) -> Optional[int]:
        if not self.first_ts or not self.last_ts:
            return None
        try:
            from datetime import datetime
            a = datetime.fromisoformat(self.first_ts.replace("Z", "+00:00"))
            b = datetime.fromisoformat(self.last_ts.replace("Z", "+00:00"))
            return int((b - a).total_seconds() * 1000)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "projectId": self.project_id,
            "title": self.title,
            "lastPrompt": self.last_prompt,
            "cwd": self.cwd,
            "gitBranch": self.git_branch,
            "firstTs": self.first_ts,
            "lastTs": self.last_ts,
            "userTurns": self.user_turns,
            "sizeBytes": self.size_bytes,
            "prUrl": self.pr_url,
            "tag": self.tag,
            "hasCustomTitle": self.has_custom_title,
            "inTokens": self.in_tokens,
            "outTokens": self.out_tokens,
            "cacheReadTokens": self.cache_read_tokens,
            "cacheCreationTokens": self.cache_creation_tokens,
            "webSearches": self.web_searches,
            "webFetches": self.web_fetches,
            "assistantTurns": self.assistant_turns,
            "models": sorted(self.models),
            "durationMs": self._duration_ms(),
        }


# path -> (mtime_ns, size, SessionMeta)
_meta_cache: dict[str, tuple[int, int, SessionMeta]] = {}


def _scan_meta(path: Path, project_id: str) -> SessionMeta:
    st = path.stat()
    key = str(path)
    cached = _meta_cache.get(key)
    if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2]

    meta = SessionMeta(session_id=path.stem, project_id=project_id, size_bytes=st.st_size)
    ai_title = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not meta.cwd:
                    m = _RE_CWD.search(line)
                    if m:
                        meta.cwd = _json_unescape(m.group(1))
                if not meta.first_ts:
                    m = _RE_TS.search(line)
                    if m:
                        meta.first_ts = m.group(1)
                if not meta.git_branch:
                    m = _RE_BRANCH.search(line)
                    if m and m.group(1):
                        meta.git_branch = _json_unescape(m.group(1))
                m = _RE_TS.search(line)
                if m:
                    meta.last_ts = m.group(1)

                # type detection uses raw-text substrings (quotes inside JSON
                # string values are escaped as \", so this won't misfire)
                if '"type":"user"' in line:
                    if ('"isMeta":true' not in line
                            and '"isSidechain":true' not in line
                            and '"tool_use_id"' not in line):
                        meta.user_turns += 1
                elif '"type":"assistant"' in line and '"usage"' in line:
                    try:
                        msg = (json.loads(line).get("message") or {})
                        u = msg.get("usage") or {}
                        meta.in_tokens += u.get("input_tokens", 0) or 0
                        meta.out_tokens += u.get("output_tokens", 0) or 0
                        meta.cache_read_tokens += u.get("cache_read_input_tokens", 0) or 0
                        meta.cache_creation_tokens += u.get("cache_creation_input_tokens", 0) or 0
                        stu = u.get("server_tool_use") or {}
                        meta.web_searches += stu.get("web_search_requests", 0) or 0
                        meta.web_fetches += stu.get("web_fetch_requests", 0) or 0
                        meta.assistant_turns += 1
                        model = msg.get("model")
                        if model and not model.startswith("<"):
                            meta.models.add(model)
                    except json.JSONDecodeError:
                        pass
                elif '"type":"ai-title"' in line:
                    try:
                        ai_title = json.loads(line).get("aiTitle", "") or ai_title
                    except json.JSONDecodeError:
                        pass
                elif '"type":"custom-title"' in line:
                    try:
                        ct = json.loads(line).get("customTitle", "")
                        if ct:
                            meta.title = ct
                            meta.has_custom_title = True
                    except json.JSONDecodeError:
                        pass
                elif '"type":"tag"' in line:
                    try:
                        # tag_session(None) writes "", which means cleared; last value wins.
                        meta.tag = json.loads(line).get("tag", "") or ""
                    except json.JSONDecodeError:
                        pass
                elif '"type":"last-prompt"' in line:
                    try:
                        meta.last_prompt = json.loads(line).get("lastPrompt", "") or meta.last_prompt
                    except json.JSONDecodeError:
                        pass
                elif '"type":"pr-link"' in line:
                    try:
                        meta.pr_url = json.loads(line).get("prUrl", "") or meta.pr_url
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass

    if not meta.title:
        meta.title = ai_title
    if not meta.title:
        meta.title = (meta.last_prompt[:60] or meta.session_id)

    _meta_cache[key] = (st.st_mtime_ns, st.st_size, meta)
    return meta


def _safe_project_dir(project_id: str) -> Optional[Path]:
    if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
        return None
    d = PROJECTS_ROOT / project_id
    return d if d.is_dir() else None


def list_projects() -> list[dict[str, Any]]:
    projects = []
    if not PROJECTS_ROOT.is_dir():
        return projects
    for d in sorted(PROJECTS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        files = list(d.glob("*.jsonl"))
        if not files:
            continue
        newest = max(files, key=lambda f: f.stat().st_mtime)
        # the real path can't be recovered from the slug, so use the newest session's cwd
        meta = _scan_meta(newest, d.name)
        projects.append({
            "projectId": d.name,
            "path": meta.cwd or d.name,
            "sessionCount": len(files),
            "lastActive": meta.last_ts,
        })
    projects.sort(key=lambda p: p["lastActive"] or "", reverse=True)
    return projects


def list_sessions(project_id: str) -> list[dict[str, Any]]:
    d = _safe_project_dir(project_id)
    if d is None:
        return []
    metas = [_scan_meta(f, project_id) for f in d.glob("*.jsonl")]
    metas.sort(key=lambda m: m.last_ts or "", reverse=True)
    return [m.to_dict() for m in metas]


def state_version() -> str:
    """A lightweight change signature from (count, newest mtime, total size) of all JSONL.

    Uses stat only (no reads), so it is cheap. The frontend polls it and reloads
    the sidebar whenever the value changes.
    """
    if not PROJECTS_ROOT.is_dir():
        return "0"
    count = 0
    max_mtime = 0
    total = 0
    for proj in PROJECTS_ROOT.iterdir():
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            try:
                st = f.stat()
            except OSError:
                continue
            count += 1
            total += st.st_size
            if st.st_mtime_ns > max_mtime:
                max_mtime = st.st_mtime_ns
    return f"{count}:{max_mtime}:{total}"


# ---------------------------------------------------------------------------
# transcript


def _blocks_from_content(content: Any) -> list[dict[str, Any]]:
    """Convert message.content (a str or a block list) into a UI block list."""
    blocks: list[dict[str, Any]] = []
    if isinstance(content, str):
        if content.strip():
            blocks.append({"t": "text", "text": content})
        return blocks
    if not isinstance(content, list):
        return blocks
    for b in content:
        if not isinstance(b, dict):
            continue
        bt = b.get("type")
        if bt == "text":
            if (b.get("text") or "").strip():
                blocks.append({"t": "text", "text": b["text"]})
        elif bt == "thinking":
            if (b.get("thinking") or "").strip():
                blocks.append({"t": "thinking", "text": b["thinking"]})
        elif bt == "tool_use":
            try:
                inp = json.dumps(b.get("input", {}), ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                inp = str(b.get("input"))
            blocks.append({
                "t": "tool_use",
                "id": b.get("id", ""),
                "name": b.get("name", "?"),
                "input": inp[:4000],
                "result": None,
                "isError": False,
            })
        elif bt == "image":
            blocks.append({"t": "text", "text": "[image]"})
    return blocks


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif isinstance(c, dict) and c.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return str(content)


def load_transcript(project_id: str, session_id: str,
                    before: Optional[int] = None, limit: int = 200) -> dict[str, Any]:
    """Parse the whole session and return a slice (the tail) of UI items.

    tool_result blocks are embedded into their matching tool_use block.
    """
    d = _safe_project_dir(project_id)
    if d is None:
        return {"items": [], "total": 0, "meta": None}
    path = d / f"{session_id}.jsonl"
    if not path.is_file() or path.resolve().parent != d.resolve():
        return {"items": [], "total": 0, "meta": None}

    items: list[dict[str, Any]] = []
    tool_use_index: dict[str, dict[str, Any]] = {}

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("type")
            if t not in ("user", "assistant", "system"):
                continue
            if obj.get("isSidechain"):
                continue

            if t == "system":
                if obj.get("subtype") == "compact_boundary":
                    items.append({
                        "kind": "divider",
                        "ts": obj.get("timestamp", ""),
                        "text": "Conversation compacted",
                    })
                elif obj.get("level") == "error" and obj.get("content"):
                    items.append({
                        "kind": "system",
                        "ts": obj.get("timestamp", ""),
                        "blocks": [{"t": "text", "text": str(obj.get("content"))[:2000]}],
                    })
                continue

            msg = obj.get("message") or {}
            content = msg.get("content")

            if t == "user":
                # a user line carrying tool_result -> embed into the preceding tool_use
                consumed_all = True
                rest_blocks: list[dict[str, Any]] = []
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            tu = tool_use_index.get(b.get("tool_use_id", ""))
                            if tu is not None:
                                tu["result"] = _tool_result_text(b.get("content"))[:4000]
                                tu["isError"] = bool(b.get("is_error"))
                        else:
                            consumed_all = False
                            if isinstance(b, dict):
                                rest_blocks.extend(_blocks_from_content([b]))
                    if consumed_all and not rest_blocks:
                        continue
                    blocks = rest_blocks
                else:
                    blocks = _blocks_from_content(content)
                if obj.get("isMeta"):
                    continue
                if blocks:
                    items.append({
                        "kind": "user",
                        "ts": obj.get("timestamp", ""),
                        "uuid": obj.get("uuid", ""),
                        "blocks": blocks,
                    })
            else:  # assistant
                blocks = _blocks_from_content(content)
                for b in blocks:
                    if b["t"] == "tool_use" and b.get("id"):
                        tool_use_index[b["id"]] = b
                if blocks:
                    items.append({
                        "kind": "assistant",
                        "ts": obj.get("timestamp", ""),
                        "uuid": obj.get("uuid", ""),
                        "model": (msg.get("model") or ""),
                        "isError": bool(obj.get("isApiErrorMessage")),
                        "blocks": blocks,
                    })

    total = len(items)
    end = total if before is None else max(0, min(before, total))
    start = max(0, end - limit)
    meta = _scan_meta(path, project_id)
    return {
        "items": items[start:end],
        "start": start,
        "total": total,
        "meta": meta.to_dict(),
    }


# ---------------------------------------------------------------------------
# helpers for session operations / full-text search


def session_cwd(project_id: str, session_id: str) -> str:
    """Return the session's working directory (passed as the SDK's `directory` arg)."""
    d = _safe_project_dir(project_id)
    if d is None:
        return ""
    path = d / f"{session_id}.jsonl"
    if not path.is_file():
        return ""
    return _scan_meta(path, project_id).cwd


# path -> (mtime_ns, size, lowered_text, orig_text)
_text_cache: dict[str, tuple[int, int, str, str]] = {}


def _extract_text(path: Path) -> tuple[str, str]:
    """Extract and cache human-readable text (user/assistant text and thinking).

    Tool-call JSON and results are excluded since they are search noise.
    """
    st = path.stat()
    key = str(path)
    c = _text_cache.get(key)
    if c and c[0] == st.st_mtime_ns and c[1] == st.st_size:
        return c[2], c[3]

    parts: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"type":"user"' not in line and '"type":"assistant"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("isSidechain") or obj.get("isMeta"):
                    continue
                content = (obj.get("message") or {}).get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        bt = b.get("type")
                        if bt == "text" and b.get("text"):
                            parts.append(b["text"])
                        elif bt == "thinking" and b.get("thinking"):
                            parts.append(b["thinking"])
    except OSError:
        pass

    orig = "\n".join(parts)
    low = orig.lower()
    _text_cache[key] = (st.st_mtime_ns, st.st_size, low, orig)
    return low, orig


def _snippet(orig: str, idx: int, qlen: int, pad: int = 70) -> str:
    start = max(0, idx - pad)
    end = min(len(orig), idx + qlen + pad)
    s = orig[start:end].replace("\n", " ").replace("\r", " ").strip()
    if start > 0:
        s = "…" + s
    if end < len(orig):
        s = s + "…"
    return s


def search_all(query: str, limit: int = 60) -> list[dict[str, Any]]:
    """Substring-search session content across all projects."""
    q = query.strip().lower()
    if not q or not PROJECTS_ROOT.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for proj in PROJECTS_ROOT.iterdir():
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            low, orig = _extract_text(f)
            idx = low.find(q)
            if idx == -1:
                continue
            meta = _scan_meta(f, proj.name)
            d = meta.to_dict()
            d["matchCount"] = low.count(q)
            d["snippet"] = _snippet(orig, idx, len(q))
            results.append(d)
    results.sort(key=lambda r: r.get("lastTs") or "", reverse=True)
    return results[:limit]
