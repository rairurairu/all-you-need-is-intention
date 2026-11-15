"""Regression tests for exact capture, pause/backfill, and cited reviews."""

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from archive import Repo
from sources import scan

EXACT = "  中文 🧪 cafe\u0301 \\literal\r\nsecond line  \n"


def iso():
    return datetime.now(timezone.utc).isoformat()


def append(path, *rows):
    with path.open("ab") as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))


def content(role, body=EXACT):
    return {"role": role, "content": [{"type": "text", "text": body}]}


def codex_turn(path, key, text, *, reply=None, cwd=None, event_mirror=False):
    rows = [
        {"type": "event_msg", "timestamp": iso(),
         "payload": {"type": "task_started", "turn_id": key}},
        {"type": "turn_context", "timestamp": iso(),
         "payload": {"turn_id": key, "cwd": str(cwd) if cwd else None}},
    ]
    if event_mirror:
        rows.append({"type": "event_msg", "timestamp": iso(),
                     "payload": {"type": "user_message", "message": text}})
    rows.append({"type": "response_item", "timestamp": iso(),
                 "payload": {"type": "message", "id": key, **content("user", text)}})
    if reply:
        rows.append({"type": "response_item", "timestamp": iso(),
                     "payload": {"type": "message", "id": f"{key}-reply",
                                 "phase": "final_answer", **content("assistant", reply)}})
    rows.append({"type": "event_msg", "timestamp": iso(),
                 "payload": {"type": "task_complete", "turn_id": key}})
    append(path, *rows)


class IntentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("INTENTION_TEST_TMP"))
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo with spaces"
        self.root.mkdir()
        self.git("init", "-q")
        (self.root / "README.md").write_text("baseline\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "Initial revision")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Tests",
                               "-c", "user.email=tests@example.invalid", *args], check=True,
                              capture_output=True, encoding="utf-8").stdout.strip()

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPTS / "intention.py"),
                                 "--repo", str(self.root), *map(str, args)],
                                capture_output=True, encoding="utf-8", timeout=30)
        if not ok:
            self.assertNotEqual(0, result.returncode)
            return result.stderr
        self.assertEqual(0, result.returncode, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def read(self, source, file, state=None):
        repo = Repo(self.root)
        errors = []
        rows = list(scan(source, [file], repo.scoped(source, state or repo.state()),
                         {"user", "assistant"}, errors=errors))
        self.assertEqual([], errors)
        return rows

    def codex(self):
        path = self.base / "codex.jsonl"
        append(path, {"type": "session_meta", "timestamp": iso(),
                      "payload": {"id": "session codex", "cwd": str(self.root)}})
        return path

    def test_codex_user_event_mirror_and_repo_scope(self):
        path = self.codex()
        append(path, {"type": "response_item", "timestamp": iso(), "payload": {
            "type": "message", **content("user", "<environment_context>\nmetadata")
        }})
        codex_turn(path, "first", EXACT, reply="private full reply", event_mirror=True)
        codex_turn(path, "second", EXACT, event_mirror=True)
        nested = self.root / "nested"
        nested.mkdir()
        (nested / ".git").mkdir()
        codex_turn(path, "wrong", "nested repo prompt", cwd=nested)
        messages = self.read("codex", path)
        self.assertEqual(["first", "first-reply", "second"], [m.native_id for m in messages])
        self.assertEqual((EXACT,), messages[0].parts)
        import_args = ["backfill", "--since", "2000-01-01T00:00:00Z", "--path", f"codex={path}"]
        self.cli("enable", "--no-start", "--source", "codex")
        self.assertEqual(2, self.cli(*import_args)[0]["added"])
        self.assertEqual(0, self.cli(*import_args)[0]["added"])
        self.assertEqual([[EXACT], [EXACT]], [r["parts"] for r in self.cli("prompts")])
        self.assertEqual([], self.cli("prompts", "--match", "private full reply"))

    def test_claude_turns_and_tool_messages(self):
        path = self.base / "claude.jsonl"
        base = {"type": "user", "sessionId": "s", "cwd": str(self.root), "timestamp": iso()}
        append(path, {**base, "uuid": "a", "message": content("user")},
               {**base, "uuid": "metadata", "isMeta": True, "message": content("user")},
               {**base, "uuid": "tool", "message": {"role": "user", "content": [
                   {"type": "tool_result", "content": "ignore"}
               ]}},
               {**base, "uuid": "wrong", "cwd": str(self.base), "message": content("user")})
        self.assertEqual([("a", (EXACT,))], [(m.native_id, m.parts)
                                             for m in self.read("claude", path)])

    def test_codex_preserves_literal_wrapper_with_user_provenance(self):
        path = self.codex()
        exact = "<environment_context>\nThese are the user's literal words.\n"
        append(path, {"type": "response_item", "timestamp": iso(), "payload": {
            "type": "message", "id": "p", "role": "user",
            "content": [
                {"type": "input_text", "text": "AGENTS.md injected text"},
                {"type": "input_text", "text": exact},
            ],
            "internal_chat_message_metadata_passthrough": {
                "content_item_metadata": [
                    {"provenance": {"type": "agents_md"}},
                    {"provenance": {"type": "user"}},
                ]
            },
        }})
        message, = self.read("codex", path)
        self.assertEqual((exact,), message.parts)

    def test_pi_multiple_parts(self):
        path = self.base / "pi.jsonl"
        append(path, {"type": "session", "id": "s", "cwd": str(self.root), "timestamp": iso()},
               {"type": "message", "id": "a", "message": {"role": "user",
                 "timestamp": int(time.time() * 1000), "content": [
                     {"type": "text", "text": EXACT},
                     {"type": "image", "data": "not stored"},
                     {"type": "text", "text": "\t final "},
                 ]}})
        message, = self.read("pi", path)
        self.assertEqual((EXACT, "\t final "), message.parts)
        self.assertEqual(1, message.attachments)

    def test_opencode_legacy_and_v2(self):
        path = self.base / "opencode.db"
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE session(id, directory);
                CREATE TABLE message(id, session_id, time_created, data);
                CREATE TABLE part(id, message_id, data);
                CREATE TABLE session_v2(id, directory);
                CREATE TABLE session_message(id, session_id, type, seq, time_created, data);
                CREATE TABLE session_part(message_id, type, ordinal, data);
            """)
            ms = int(time.time() * 1000)
            db.execute("INSERT INTO session VALUES(?, ?)", ("legacy", str(self.root)))
            db.execute("INSERT INTO message VALUES(?, ?, ?, ?)",
                       ("p", "legacy", ms, json.dumps({"role": "user"})))
            db.execute("INSERT INTO part VALUES(?, ?, ?)",
                       ("part", "p", json.dumps({"type": "text", "text": EXACT})))
            db.execute("INSERT INTO session_v2 VALUES(?, ?)", ("v2", str(self.root)))
            db.execute("INSERT INTO session_message VALUES(?, ?, ?, ?, ?, ?)",
                       ("p2", "v2", "user", 1, ms, json.dumps({"text": EXACT, "files": []})))
            db.execute("INSERT INTO session_message VALUES(?, ?, ?, ?, ?, ?)",
                       ("a2", "v2", "assistant", 2, ms + 1, "{}"))
            db.execute("INSERT INTO session_part VALUES(?, ?, ?, ?)",
                       ("a2", "text", 0, json.dumps({"type": "text", "text": "answer"})))
            db.commit()
        self.assertEqual([("p", (EXACT,)), ("p2", (EXACT,)), ("a2", ("answer",))],
                         [(m.native_id, m.parts) for m in self.read("opencode", path)])

    def test_hermes_binding_and_structured_text(self):
        path = self.base / "state.db"
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE sessions(id, cwd);
                CREATE TABLE messages(id, session_id, role, content, timestamp,
                                      message_uid, _compressed_summary);
            """)
            db.executemany("INSERT INTO sessions VALUES(?, ?)",
                           [("s", str(self.root)), ("unknown", None)])
            db.executemany("INSERT INTO messages VALUES(?, ?, ?, ?, ?, ?, ?)", [
                (1, "s", "user", EXACT, time.time(), "uid", 0),
                (2, "s", "user", "summary", time.time(), "synth", 1),
                (3, "unknown", "user", "\x00json:" + json.dumps(content("user")["content"]),
                 time.time(), "bound", 0),
            ])
            db.commit()
        self.assertEqual([("uid", (EXACT,))], [(m.native_id, m.parts)
                                               for m in self.read("hermes", path)])
        self.cli("enable", "--source", "hermes", "--no-start")
        self.cli("bind", "hermes", "unknown")
        self.assertEqual(2, self.cli("backfill", "--since", "2000-01-01T00:00:00Z",
                                     "--path", f"hermes={path}")[0]["added"])

    def wait_for(self, predicate):
        for _ in range(70):
            if predicate():
                return
            time.sleep(0.15)
        self.fail("recorder did not reach the expected state")

    def stop_monitor(self):
        self.cli("pause")
        self.wait_for(lambda: not Repo(self.root).running())

    def test_background_capture_and_paused_backfill(self):
        path = self.codex()
        self.addCleanup(self.stop_monitor)
        result = self.cli("enable", "--source", "codex", "--interval", "1",
                          "--path", f"codex={path}")[0]
        self.assertTrue(result["running"])
        codex_turn(path, "on", EXACT)
        self.wait_for(lambda: bool(self.cli("prompts", "--match", "literal")))
        self.cli("pause")
        codex_turn(path, "paused", "paused text")
        self.wait_for(lambda: not Repo(self.root).running())
        self.assertEqual([], self.cli("prompts", "--match", "paused text"))
        self.cli("resume")
        codex_turn(path, "resumed", "resumed text")
        self.wait_for(lambda: bool(self.cli("prompts", "--match", "resumed text")))
        self.assertEqual([], self.cli("prompts", "--match", "paused text"))
        preview = self.cli("backfill", "--paused", "--dry-run")[0]
        self.assertEqual((0, 1), (preview["added"], preview["matched"]))
        self.assertEqual(1, self.cli("backfill", "--paused")[0]["added"])
        self.assertEqual(0, self.cli("backfill", "--paused")[0]["added"])
        self.assertEqual(3, len(self.cli("prompts")))

    def test_review_snapshot_reply_quote_and_worktree(self):
        seed = self.base / "seed.jsonl"
        append(seed, {"type": "session", "session_id": "s"},
               {"type": "message", "role": "user", "id": "u1", "text": EXACT, "timestamp": iso()},
               {"type": "message", "role": "assistant", "id": "a1", "timestamp": iso(),
                "text": "First option\r\nSecond option\r\nUnrelated details"},
               {"type": "message", "role": "user", "id": "u2", "text": "Option two.",
                "timestamp": iso()})
        self.assertEqual(2, self.cli("import-seed", seed)[0]["added"])
        manifest = self.cli("prepare-review", "--model", "fixture", "--effort", "medium")[0]
        run_id = manifest["run_id"]
        first, = self.cli("review-prompts", run_id, "--limit", "1")
        last, = self.cli("review-prompts", run_id, "--offset", "1")
        self.assertEqual([EXACT], first["parts"])
        locator = self.cli("evidence", last["id"], "--seed", seed)[0]
        source = locator["replies"][0]["source_id"]
        quote = self.cli("evidence", last["id"], "--seed", seed, "--reply", source,
                         "--lines", "2:2")[0]
        self.assertEqual("Second option\r\n", quote["text"])
        report = self.base / "report.json"
        value = {
            "summary": "Use the second option.", "reviewed_prompt_count": 2,
            "requirements": [{"text": "Use the selected option", "basis": "explicit",
                              "prompt_ids": [last["id"]]}],
            "unresolved": [], "recommendation": {"kind": "repair", "rationale": "Local change"},
            "plan": ["Implement the selected option"], "findings": [], "verification": [],
            "reply_quotes": [{**quote, "text": "Altered"}],
        }
        report.write_text(json.dumps(value))
        refusal = self.cli("save-review", run_id, "--seed", seed, "--report", report, ok=False)
        self.assertIn("does not match", refusal)
        value["reply_quotes"] = [quote]
        report.write_text(json.dumps(value))
        result = self.cli("save-review", run_id, "--seed", seed, "--report", report)[0]
        self.assertTrue(result["coverage_complete"])
        self.assertNotIn("Unrelated details", Path(result["report"]).read_text())
        append(seed, {"type": "message", "role": "user", "id": "u3",
                      "text": "New requirement after review.", "timestamp": iso()})
        self.assertEqual(1, self.cli("import-seed", seed)[0]["added"])
        replay = self.cli("prepare-review", "--from-review", run_id)[0]
        self.assertEqual(2, replay["prompt_count"])
        self.assertEqual(manifest["prompt_sha256"], replay["prompt_sha256"])
        fresh = self.base / "fresh"
        checkout = self.cli("rebuild-worktree", run_id, fresh)[0]
        self.assertEqual(manifest["begin_revision"], checkout["base_revision"])
        self.assertEqual("baseline\n", (fresh / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
