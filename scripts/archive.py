"""Git-scoped archive and machine-local capture state."""

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tomllib

from sources import HARNESSES, default_paths, json_lines, moment, scan

VERSION = "1.0.0"
CONFIG = b'schema = 1\n'
UTC = timezone.utc


def now():
    return datetime.now(UTC).isoformat()


def json_bytes(value):
    # JSON escaping preserves embedded newlines, whitespace, and Unicode.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def object_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load(path):
    return json.loads(path.read_bytes())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def git(path, *args, check=True):
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if check and result.returncode:
        raise ValueError(result.stderr.strip() or "Git command failed")
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def _lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def lock(path, seconds=8):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        deadline = time.monotonic() + seconds
        while True:
            try:
                _lock(stream)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"lock busy: {path.name}") from exc
                time.sleep(0.04)
        yield


class Repo:
    def __init__(self, path):
        self.root = Path(git(path, "rev-parse", "--show-toplevel")).resolve()
        gitdir = Path(git(self.root, "rev-parse", "--absolute-git-dir")).resolve()
        self.local = gitdir / "intention"
        self.statefile = self.local / "state.json"
        self.config = self.file("config.toml")

    def file(self, *parts):
        path = self.root.joinpath(".intention", *parts)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("archive path points outside the repository")
        return path

    def enrolled(self):
        if not self.config.is_file():
            return False
        with self.config.open("rb") as stream:
            if tomllib.load(stream).get("schema") != 1:
                raise ValueError("unsupported .intention/config.toml schema")
        return True

    def init(self):
        if not self.enrolled():
            write(self.config, CONFIG)

    def state(self):
        if self.statefile.is_file():
            return load(self.statefile)
        return {"interval": 10, "sources": list(HARNESSES), "paths": {},
                "windows": [], "bindings": {}}

    def save_state(self, state):
        write(self.statefile, object_bytes(state))

    def lock(self):
        return lock(self.local / "archive.lock")

    def running(self):
        try:
            with lock(self.local / "monitor.lock", seconds=0):
                return False
        except TimeoutError:
            return True

    def scoped(self, source, state):
        @lru_cache(maxsize=1024)
        def matches(cwd, session):
            if not cwd:
                return session in state["bindings"].get(source, [])
            path = Path(cwd)
            if not path.is_absolute():
                return False
            path = path.resolve()
            if not path.is_relative_to(self.root):
                return False
            relative = path.relative_to(self.root)
            cursor = self.root
            for name in relative.parts:
                cursor = cursor / name
                if (cursor / ".git").exists():
                    return False
            return ".git" not in relative.parts
        return matches

    def append(self, messages):
        grouped = defaultdict(list)
        for message in messages:
            if message.role != "user":
                continue
            key = sha256(message.session.encode("utf-8")).hexdigest()[:32]
            grouped[f"{message.source}-{key}.jsonl"].append(message.record())
        added = 0
        for filename, records in sorted(grouped.items()):
            path = self.file("prompts", filename)
            previous = path.read_bytes() if path.exists() else b""
            existing = {}
            for row in previous.split(b"\n"):
                if row:
                    old = json.loads(row)
                    existing[old["id"]] = old
            changed = []
            for row in records:
                old = existing.get(row["id"])
                if old is not None:
                    if old["parts"] != row["parts"] or old["attachments"] != row["attachments"]:
                        raise ValueError(f"source text changed for {row['id']}; existing record retained")
                    continue
                existing[row["id"]] = row
                changed.append(json_bytes(row))
            if changed:
                separator = b"\n" if previous and not previous.endswith(b"\n") else b""
                write(path, previous + separator + b"".join(changed))
                added += len(changed)
        return added

    def prompts(self):
        records = {}
        for path in sorted(self.file("prompts").glob("*.jsonl")):
            for _, row in json_lines(self.file("prompts", path.name)):
                existing = records.setdefault(row["id"], row)
                if row["parts"] != existing["parts"] or row["attachments"] != existing["attachments"]:
                    raise ValueError(f"conflicting journal records for {row['id']}")
        return sorted(records.values(), key=lambda row: moment(row["timestamp"]))

    def collect(self, state, windows, names, paths=None, caches=None, session=None):
        floor = min((moment(left).timestamp() for left, _ in windows if left), default=0)
        if any(left is None for left, _ in windows):
            floor = 0
        ranges = [(moment(start) if start else None, moment(stop) if stop else None)
                  for start, stop in windows]
        messages = []
        errors = []
        availability = {}
        for source in names:
            options = paths or {}
            locations = options.get(source, state["paths"].get(source))
            locations = [Path(path) for path in locations] if locations else default_paths(source)
            availability[source] = any(path.exists() for path in locations)
            messages.extend(
                message for message in scan(
                    source, locations, self.scoped(source, state), {"user"}, floor, session,
                    caches.setdefault(source, {}) if caches is not None else None, errors,
                )
                if any((start is None or message.stamp >= start) and
                       (stop is None or message.stamp < stop) for start, stop in ranges)
            )
        return messages, availability, errors

    def source_locations(self, source, override=None):
        if override:
            return [Path(path) for path in override]
        configured = self.state()["paths"].get(source)
        return [Path(path) for path in configured] if configured else default_paths(source)


def active(state):
    return bool(state["windows"] and state["windows"][-1][1] is None)


def paused_windows(state):
    return [[left[1], right[0]] for left, right in zip(state["windows"], state["windows"][1:])
            if left[1] is not None and left[1] < right[0]]


def selected(records, match=None, ids=None, session=None, limit=None):
    requested = set(ids or [])
    if requested - {row["id"] for row in records}:
        raise ValueError("prompt ID is absent from this archive")
    needle = match.casefold() if match else ""
    subset = [row for row in records if (not requested or row["id"] in requested)
              and (session is None or row["session"] == session)
              and (not needle or any(needle in part.casefold() for part in row["parts"]))]
    return subset[-limit:] if limit is not None else subset
