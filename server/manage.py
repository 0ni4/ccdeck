"""Thin wrappers for session operations (rename / tag / fork / delete).

Calls claude-agent-sdk's file-based session functions. Each one takes a
`directory` (the project's real cwd) to locate the target; when the cwd is
unavailable we pass None and let the SDK search across all projects.
"""

from __future__ import annotations

from claude_agent_sdk import (
    rename_session,
    delete_session,
    fork_session,
    tag_session,
)

from . import sessions


def _dir_for(project_id: str, session_id: str) -> str | None:
    return sessions.session_cwd(project_id, session_id) or None


def rename(project_id: str, session_id: str, title: str) -> None:
    rename_session(session_id, title, directory=_dir_for(project_id, session_id))


def set_tag(project_id: str, session_id: str, tag: str | None) -> None:
    # empty string clears the tag (SDK treats "" as clear)
    tag_session(session_id, tag or None, directory=_dir_for(project_id, session_id))


def fork(project_id: str, session_id: str, title: str | None = None,
         up_to_message_id: str | None = None) -> str:
    res = fork_session(
        session_id,
        directory=_dir_for(project_id, session_id),
        up_to_message_id=up_to_message_id,
        title=title,
    )
    return res.session_id


def delete(project_id: str, session_id: str) -> None:
    delete_session(session_id, directory=_dir_for(project_id, session_id))
