# ccdeck

A desktop GUI to browse, search, and resume your Claude Code sessions.
The name is **cc** (Claude Code) + **deck** (a deck of saved sessions / a cockpit).

Built as an alternative to opcode that also works behind a corporate LLM gateway:
it wraps the `claude` CLI instead of calling the API directly, so whatever the CLI
is already configured with (`ANTHROPIC_BASE_URL` and other gateway settings) is
used as-is.

## Features

- **Session browser** — reads `~/.claude/projects/**.jsonl` directly and shows a
  project → session list (title, last prompt, git branch, PR link, tag).
- **Transcript viewer** — renders history as Markdown. Tool calls and thinking are
  collapsible. Large sessions load the last 200 items with load-earlier paging.
- **Full-text search** — searches session content across all projects, with a
  snippet and highlighted matches (fast via an `(mtime, size)` cache).
- **Session stats** — aggregates token counts (input/output/cache-read), reply
  count, models used, and web-tool calls (from the JSONL `usage`, in a single
  pass). List rows also show a total token count.
- **Auto-refresh** — lightweight polling detects changes under
  `~/.claude/projects`, so the sidebar updates even when you run a session from
  the CLI separately.
- **Session actions** — from each session's `⋯` menu:
  - **Rename** — set a custom title
  - **Fork** — branch a conversation into a new session (copied with fresh UUIDs)
  - **Tag** — set / clear a tag
  - **Delete** — remove the session JSONL (with confirmation)
- **Resume** — resume a selected session and keep chatting.
- **New session** — start a fresh session in any working directory.
- **Model selection** — pick a model when starting/resuming (blank = default),
  for environments where the gateway exposes multiple models.
- **Permission dialog** — in `default` mode, allow/deny each tool call in the GUI.
- **Streaming** — live response streaming, interrupt (stop) support, and per-turn
  cost display.

## Requirements

- Windows + WebView2 (bundled with Windows 11)
- Python 3.10+
- Claude Code CLI already set up (including auth and any gateway settings)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python app.py            # desktop window
.\.venv\Scripts\python app.py --browser  # open in the default browser
.\.venv\Scripts\python app.py --port 9000
```

Or double-click `start.bat`.

## Architecture

```
app.py                 launcher (runs uvicorn in a thread + a pywebview window)
server/
  main.py              FastAPI routing (REST + WebSocket)
  sessions.py          JSONL parser for ~/.claude/projects + full-text search (cached)
  manage.py            rename / tag / fork / delete (wraps claude-agent-sdk file ops)
  chat.py              WebSocket chat; runs the claude CLI via claude-agent-sdk
web/
  index.html / style.css / app.js   build-free vanilla JS SPA (no CDN dependencies)
```

### REST API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/projects` | list projects |
| GET | `/api/projects/{pid}/sessions` | list sessions |
| GET | `/api/projects/{pid}/sessions/{sid}` | get transcript (`?before=&limit=`) |
| GET | `/api/search?q=&limit=` | full-text search across all sessions |
| GET | `/api/state` | lightweight change signature (polled for auto-refresh) |
| POST | `/api/projects/{pid}/sessions/{sid}/rename` | `{title}` |
| POST | `/api/projects/{pid}/sessions/{sid}/tag` | `{tag}` (empty clears) |
| POST | `/api/projects/{pid}/sessions/{sid}/fork` | `{title?, upToMessageId?}` → `{newSessionId}` |
| DELETE | `/api/projects/{pid}/sessions/{sid}` | delete a session |
| WS | `/ws/chat` | live chat (new / resume) |

- Chat runs through [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/)'s
  `ClaudeSDKClient`, using `resume`, `can_use_tool` (the permission callback), and
  `include_partial_messages` (streaming).
- The SDK launches its bundled `claude` executable. To use an already-installed
  CLI instead, set the `CLAUDE_CLI_PATH` environment variable
  (e.g. `$env:CLAUDE_CLI_PATH = "$env:USERPROFILE\.local\bin\claude.exe"`).
- Like normal Claude Code, it reads the user/project/local setting files
  (`setting_sources`), so CLAUDE.md, MCP servers, and gateway settings all apply.

## Notes

- `bypassPermissions` mode runs every tool without asking — use with care.
- Resuming a session and chatting appends to the same session JSONL.

## License

MIT — see [LICENSE](LICENSE).
