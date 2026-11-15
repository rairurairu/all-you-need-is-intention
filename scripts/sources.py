"""Read user messages from local harness stores and retrieve individual replies."""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
from urllib.parse import quote

UTC = timezone.utc
HARNESSES = ("codex", "claude", "pi", "opencode", "hermes")
TEXT_TYPES = {"text", "input_text", "output_text"}


def moment(value, scale=1):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / scale, UTC)
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("source timestamp has no time zone")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class Message:
    source: str
    session: str
    native_id: str
    role: str
    stamp: datetime
    parts: tuple[str, ...]
    attachments: int = 0
    phase: str | None = None

    @property
    def id(self):
        return ":".join(quote(value, safe="") for value in (
            self.source, self.session, self.native_id
        ))

    def record(self):
        return {
            "id": self.id,
            "source": self.source,
            "session": self.session,
            "native_id": self.native_id,
            "timestamp": self.stamp.isoformat(),
            "parts": list(self.parts),
            "attachments": self.attachments,
        }


def text_parts(content):
    if isinstance(content, str):
        return (content,), 0
    if not isinstance(content, list):
        return (), 0
    parts = []
    attachments = 0
    for block in content:
        if not isinstance(block, dict) or block.get("synthetic") or block.get("ignored"):
            continue
        kind = block.get("type")
        if kind in TEXT_TYPES and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif kind in {"image", "input_image", "file", "input_file", "document", "audio"}:
            attachments += 1
    return tuple(parts), attachments


def from_blocks(source, session, key, role, stamp, content, phase=None):
    parts, attachments = text_parts(content)
    if parts or (role == "user" and attachments):
        return Message(source, session, str(key), role, moment(stamp), parts, attachments, phase)
    return None


def json_lines(path, growing=False):
    with path.open("rb") as stream:
        for lineno, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                if growing and not raw.endswith(b"\n"):
                    break
                raise ValueError(f"{path.name}:{lineno}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{lineno}: expected a JSON object")
            yield lineno, row


def codex_user_content(payload):
    content = payload.get("content")
    metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
    items = metadata.get("content_item_metadata") or []
    if isinstance(content, list) and len(items) == len(content):
        origins = [(item.get("provenance") or {}).get("type") if isinstance(item, dict) else None
                   for item in items]
        if all(origins):
            return [part for part, origin in zip(content, origins) if origin == "user"]
    kinds = metadata.get("content_item_kinds") or []
    if (isinstance(content, list) and len(kinds) == len(content)
            and any(isinstance(kind, str) and kind.startswith("user.") for kind in kinds)):
        return [part for part, kind in zip(content, kinds)
                if isinstance(kind, str) and kind.startswith("user.")]
    # Legacy rollouts omit provenance. Exclude the known injected wrappers.
    parts, _ = text_parts(content)
    if (any(text.startswith(("<environment_context>", "<permissions instructions>",
                             "<user_instructions>", "<collaboration_mode>"))
            for text in parts)
            or len(parts) > 1 and parts[0].startswith("# AGENTS.md instructions")):
        return []
    return content


def read_codex(path, scoped, roles, session_id=None):
    rows = json_lines(path, growing=True)
    session = None
    cwd = None
    turn = None
    response = []
    events = []

    def flush(closed=False):
        # A rollout can store the same user submission as a response item and
        # an event. Response items preserve the original text parts and IDs.
        if any(message.role == "user" for message in response) or not closed:
            return response
        return [*events, *response]

    for lineno, row in rows:
        kind = row.get("type")
        p = row.get("payload", {})
        if kind == "session_meta":
            session = p.get("id")
            cwd = p.get("cwd")
            source = p.get("source")
            origin = p.get("thread_source")
            if (not session or (session_id and session != session_id)
                    or isinstance(source, dict) and "subagent" in source
                    or origin == "subagent"):
                return
            # Check individual turn cwd below. A resumed conversation can move.
            continue
        if session is None:
            continue

        subtype = p.get("type")
        if kind == "event_msg" and subtype in {
            "task_started", "turn_started", "task_complete", "turn_complete"
        }:
            yield from (m for m in flush(closed=True) if m.role in roles)
            response, events = [], []
            turn = p.get("turn_id") if subtype in {"task_started", "turn_started"} else None
        elif kind == "turn_context":
            next_turn = p.get("turn_id")
            if turn and next_turn and turn != next_turn:
                yield from (m for m in flush(closed=True) if m.role in roles)
                response, events = [], []
            turn = next_turn or turn
            cwd = p.get("cwd") or cwd
        elif kind == "response_item" and subtype == "message" and scoped(cwd, session):
            role = p.get("role")
            content = codex_user_content(p) if role == "user" else p.get("content")
            if role == "user" or (role == "assistant" and role in roles):
                message = from_blocks("codex", session, p.get("id") or f"line:{lineno}",
                                      role, row["timestamp"], content, p.get("phase"))
                if message:
                    response.append(message)
        elif kind == "event_msg" and subtype == "user_message" and scoped(cwd, session):
            message = from_blocks("codex", session, p.get("id") or f"event:{lineno}",
                                  "user", row["timestamp"], p.get("message"))
            if message:
                events.append(message)
    yield from (m for m in flush() if m.role in roles)


def read_claude(path, scoped, roles, session_id=None):
    for _, row in json_lines(path, growing=True):
        role = row.get("type")
        if (role not in roles or row.get("isMeta") or row.get("isSidechain")
                or row.get("isCompactSummary") or row.get("isVisibleInTranscriptOnly")):
            continue
        session = row.get("sessionId")
        info = row.get("message", {})
        if (not session or (session_id and session != session_id)
                or info.get("role") != role or not scoped(row.get("cwd"), session)):
            continue
        content = info.get("content")
        parts, attachments = text_parts(content)
        if role == "user" and isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") == "tool_result" for part in content
        ):
            continue
        if role == "user" and parts and parts[0].startswith(
            ("<local-command-", "<command-name>", "<user-prompt-submit-hook>")
        ):
            continue
        if (parts or role == "user" and attachments) and row.get("uuid"):
            yield Message("claude", session, str(row["uuid"]), role, moment(row["timestamp"]),
                          parts, attachments)


def read_pi(path, scoped, roles, session_id=None):
    rows = json_lines(path, growing=True)
    first = next(rows, None)
    if not first:
        return
    header = first[1]
    session = header.get("id")
    if (header.get("type") != "session" or not session
            or (session_id and session != session_id) or not scoped(header.get("cwd"), session)):
        return
    for lineno, row in rows:
        if row.get("type") != "message":
            continue
        info = row.get("message", {})
        role = info.get("role")
        if role in roles:
            stamp = (moment(row["timestamp"]) if row.get("timestamp") else
                     moment(info["timestamp"], 1000))
            parts, attachments = text_parts(info.get("content"))
            if parts or (role == "user" and attachments):
                yield Message("pi", session, row.get("id") or f"line:{lineno}", role,
                              stamp, parts, attachments)


def connection(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    return db


def match_sessions(db, sql, scoped, session_id):
    for row in db.execute(sql):
        if (not session_id or row["id"] == session_id) and scoped(row["cwd"], row["id"]):
            yield row["id"]


def read_hermes(db, scoped, roles, session_id, floor):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}
    if "id" not in columns:
        raise ValueError("Hermes database has no sessions table")
    sessions = "SELECT id, cwd FROM sessions" if "cwd" in columns else (
        "SELECT id, NULL AS cwd FROM sessions"
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(messages)")}
    uid = "message_uid" if "message_uid" in columns else "NULL"
    summary = " AND COALESCE(_compressed_summary, 0) = 0" if "_compressed_summary" in columns else ""
    active = " AND (COALESCE(active, 1) = 1 OR COALESCE(compacted, 0) = 1)" if {
        "active", "compacted"
    } <= columns else ""
    query = (f"SELECT id, {uid} AS uid, role, content, timestamp FROM messages"
             f" WHERE session_id = ? AND timestamp >= ?{summary}{active} ORDER BY timestamp, id")
    for session in match_sessions(db, sessions, scoped, session_id):
        for row in db.execute(query, (session, floor)):
            if row["role"] not in roles:
                continue
            content = row["content"]
            prefix = "\x00json:"
            if isinstance(content, str) and content.startswith(prefix):
                content = json.loads(content[len(prefix):])
            message = from_blocks("hermes", session, row["uid"] or row["id"],
                                  row["role"], row["timestamp"], content)
            if message:
                yield message


def read_opencode(db, scoped, roles, session_id, floor):
    tables = {row["name"] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    if {"session", "message", "part"} <= tables:
        for session in match_sessions(db, "SELECT id, directory AS cwd FROM session", scoped,
                                      session_id):
            query = """SELECT id, time_created, data FROM message
                       WHERE session_id = ? AND time_created >= ? ORDER BY time_created, id"""
            for row in db.execute(query, (session, floor * 1000)):
                info = json.loads(row["data"])
                role = info.get("role")
                if role not in roles:
                    continue
                parts = [json.loads(p["data"]) for p in db.execute(
                    "SELECT data FROM part WHERE message_id = ? ORDER BY id", (row["id"],)
                )]
                texts, attachments = text_parts(parts)
                if texts or (role == "user" and attachments):
                    yield Message("opencode", session, row["id"], role,
                                  moment(row["time_created"], 1000), texts, attachments)

    if {"session_v2", "session_message", "session_part"} <= tables:
        for session in match_sessions(db, "SELECT id, directory AS cwd FROM session_v2", scoped,
                                      session_id):
            query = """SELECT id, type, time_created, data FROM session_message
                       WHERE session_id = ? AND time_created >= ? ORDER BY seq"""
            for row in db.execute(query, (session, floor * 1000)):
                role = row["type"]
                if role not in roles:
                    continue
                info = json.loads(row["data"])
                if role == "user":
                    parts, extras = text_parts(info.get("text"))
                    attachments = len(info.get("files", [])) + extras
                else:
                    content = [json.loads(p["data"]) for p in db.execute(
                        "SELECT data FROM session_part WHERE message_id = ? AND type = 'text'"
                        " ORDER BY ordinal", (row["id"],)
                    )]
                    parts, attachments = text_parts(content or info.get("content", []))
                if parts or (role == "user" and attachments):
                    yield Message("opencode", session, row["id"], role,
                                  moment(row["time_created"], 1000), parts, attachments)
    elif not {"session", "message", "part"} <= tables:
        raise ValueError("OpenCode database does not match a supported schema")


def default_paths(source):
    home = Path.home()
    if source == "codex":
        base = Path(os.environ.get("CODEX_HOME", home / ".codex"))
        return [base / "sessions", base / "archived_sessions"]
    if source == "claude":
        return [Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "projects"]
    if source == "pi":
        base = Path(os.environ.get("PI_CODING_AGENT_DIR", home / ".pi" / "agent"))
        return [Path(os.environ.get("PI_CODING_AGENT_SESSION_DIR", base / "sessions"))]
    if source == "hermes":
        base = Path(os.environ.get("HERMES_HOME", home / ".hermes"))
        return [base / "state.db"]
    base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "opencode"
    db = os.environ.get("OPENCODE_DB")
    if db == ":memory:":
        return []
    return [base / db] if db else [base / "opencode.db"]


def files_for(source, paths):
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir() and source in {"codex", "claude", "pi"}:
            yield from path.rglob("*.jsonl")
        elif path.is_dir():
            yield from path.glob("*.db")


def scan(source, paths, scoped, roles, floor=0, session_id=None, cache=None, errors=None):
    errors = errors if errors is not None else []
    visited = set()
    for path in files_for(source, paths):
        try:
            path = path.resolve()
            if path in visited:
                continue
            visited.add(path)
            if source in {"codex", "claude", "pi"}:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if stat.st_mtime < floor - 120 or (cache is not None and cache.get(path) == signature):
                    continue
                read = {"codex": read_codex, "claude": read_claude, "pi": read_pi}[source]
                yield from (m for m in read(path, scoped, roles, session_id)
                            if m.stamp.timestamp() >= floor)
                if cache is not None:
                    cache[path] = signature
            else:
                wal = path.with_name(path.name + "-wal")
                stat = path.stat()
                try:
                    wal_stat = wal.stat()
                except FileNotFoundError:
                    wal_stat = None
                signature = (stat.st_mtime_ns, stat.st_size,
                             (wal_stat.st_mtime_ns, wal_stat.st_size) if wal_stat else None)
                if cache is not None and cache.get(path) == signature:
                    continue
                with closing(connection(path)) as db:
                    read = read_hermes if source == "hermes" else read_opencode
                    yield from read(db, scoped, roles, session_id, floor)
                if cache is not None:
                    cache[path] = signature
        except (OSError, ValueError, KeyError, TypeError, OverflowError, sqlite3.Error) as exc:
            errors.append({"source": source, "file": path.name, "error": str(exc)})


def read_seed(path):
    """Convert the explicitly provided, role-tagged Codex seed into evidence."""
    session = None
    for _, row in json_lines(path):
        if row.get("type") == "session":
            session = row.get("session_id")
        if row.get("type") != "message" or row.get("role") not in {"user", "assistant"}:
            continue
        if not session or not isinstance(row.get("text"), str) or not row.get("id"):
            raise ValueError("seed messages require a session ID, message ID, and text")
        stamp = row.get("timestamp") or row.get("prepared_at")
        if not stamp:
            raise ValueError("seed message has no timestamp")
        yield Message("codex", session, row["id"], row["role"], moment(stamp), (row["text"],),
                      phase=row.get("phase"))
