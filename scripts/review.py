"""Review packets, exact reply citations, and independent worktrees."""

from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from archive import VERSION, git, json_bytes, load, now, object_bytes, selected, write
from sources import json_lines, moment, read_seed, scan


def run_dir(repo, run):
    if not re.fullmatch(r"[0-9a-f]{32}", run):
        raise ValueError("invalid review run ID")
    return repo.local / "runs" / run


def prepare(repo, args):
    current = repo.prompts()
    if args.from_review:
        if args.match or args.id or args.session:
            raise ValueError("--from-review already specifies the exact prompt scope")
        run_dir(repo, args.from_review)
        prior = load(repo.file("reviews", f"{args.from_review}.json"))
        by_id = {row["id"]: row for row in current}
        if set(prior["prompt_ids"]) - by_id.keys():
            raise ValueError("some prompts from the prior snapshot are unavailable")
        archive = [by_id[item] for item in prior["prompt_ids"]]
    else:
        archive = selected(current, args.match, args.id, args.session)
    if not archive:
        raise ValueError("no prompts match the review scope")
    run = uuid4().hex
    path = run_dir(repo, run)
    data = b"".join(json_bytes(row) for row in archive)
    digest = sha256(data).hexdigest()
    if args.from_review and digest != prior["prompt_sha256"]:
        raise ValueError("the recorded prompts no longer match the prior snapshot")
    revision = git(repo.root, "rev-parse", "--verify", "HEAD", check=False)
    metadata = {
        "schema": 1,
        "run_id": run,
        "skill_version": VERSION,
        "started_at": now(),
        "mode": args.mode,
        "provider": args.provider,
        "model": args.model,
        "effort": args.effort,
        "harness": args.harness,
        "harness_version": args.harness_version,
        "begin_revision": revision,
        "begin_worktree_dirty": bool(git(repo.root, "status", "--porcelain")),
        "scope": {"match": args.match, "ids": args.id, "session": args.session,
                  "from_review": args.from_review},
        "prompt_count": len(archive),
        "prompt_sha256": digest,
        "prompt_ids": [row["id"] for row in archive],
    }
    write(path / "prompts.jsonl", data)
    write(path / "input.json", object_bytes(metadata))
    return {key: value for key, value in metadata.items() if key != "prompt_ids"}


def packet(repo, run):
    path = run_dir(repo, run)
    manifest = load(path / "input.json")
    data = (path / "prompts.jsonl").read_bytes()
    if manifest["prompt_sha256"] != sha256(data).hexdigest():
        raise ValueError("review prompt snapshot changed since preparation")
    return path, manifest


def prompt(repo, prompt_id):
    return selected(repo.prompts(), ids=[prompt_id])[0]


def replies_before(repo, original, seed=None, paths=None):
    errors = []
    if seed:
        stream = read_seed(seed)
    else:
        source = original["source"]
        stream = scan(source, repo.source_locations(source, paths),
                      repo.scoped(source, repo.state()), {"user", "assistant"},
                      session_id=original["session"], errors=errors)
    records = [entry for entry in stream if entry.session == original["session"]]
    records.sort(key=lambda entry: entry.stamp)
    index = next((i for i, entry in enumerate(records) if entry.id == original["id"]), None)
    preceding = records[:index] if index is not None else [
        entry for entry in records if entry.stamp < moment(original["timestamp"])
    ]
    return {entry.id: entry for entry in preceding if entry.role == "assistant"}, errors


def quote_reply(original, entry, part, start, end):
    if not 1 <= part <= len(entry.parts):
        raise ValueError("reply part is outside the available text")
    lines = entry.parts[part - 1].splitlines(keepends=True)
    if start is None:
        return {"parts": list(entry.parts), "source_id": entry.id, "prompt_id": original["id"]}
    if not 1 <= start <= end <= len(lines):
        raise ValueError("quote lines are outside the reply part")
    return {
        "prompt_id": original["id"],
        "source_id": entry.id,
        "source_timestamp": entry.stamp.isoformat(),
        "source_phase": entry.phase,
        "part": part,
        "start_line": start,
        "end_line": end,
        "text": "".join(lines[start - 1:end]),
    }


def evidence(repo, args):
    if args.lines and not args.reply:
        raise ValueError("--lines requires --reply")
    original = prompt(repo, args.prompt_id)
    replies, errors = replies_before(repo, original, args.seed, args.path)
    if args.reply:
        if args.reply not in replies:
            raise ValueError("reply is unavailable or does not precede this prompt")
        return quote_reply(original, replies[args.reply], args.part,
                           *(args.lines if args.lines else (None, None)))
    return {"prompt_id": original["id"], "replies": [
        {"source_id": entry.id, "source_timestamp": entry.stamp.isoformat(),
         "source_phase": entry.phase, "part_line_counts": [
             len(text.splitlines()) for text in entry.parts
         ]}
        for entry in list(replies.values())[-args.limit:]
    ], "errors": errors}


def report_list(report, field):
    value = report.get(field)
    if not isinstance(value, list):
        raise ValueError(f"review report requires a {field} list")
    return value


def validate_report(repo, report, manifest, prompts, seed, paths):
    if not isinstance(report, dict):
        raise ValueError("review report must be an object")
    if not isinstance(report.get("summary"), str) or not report["summary"].strip():
        raise ValueError("review report needs a summary")
    recommendation = report.get("recommendation")
    if (not isinstance(recommendation, dict)
            or recommendation.get("kind") not in {"keep", "repair", "refactor", "rebuild"}
            or not recommendation.get("rationale")):
        raise ValueError("recommendation needs a kind and rationale")
    coverage = report.get("reviewed_prompt_count")
    if type(coverage) is not int or not 0 <= coverage <= manifest["prompt_count"]:
        raise ValueError("reviewed_prompt_count is outside the prompt snapshot")
    for requirement in report_list(report, "requirements"):
        ids = requirement.get("prompt_ids", [])
        if (not requirement.get("text") or requirement.get("basis") not in {"explicit", "inferred"}
                or not isinstance(ids, list) or not ids or set(ids) - prompts.keys()):
            raise ValueError("each requirement needs a basis and prompt IDs from the snapshot")
    for key in ("unresolved", "plan", "verification"):
        if any(not isinstance(item, str) for item in report_list(report, key)):
            raise ValueError(f"{key} must contain text")
    for finding in report_list(report, "findings"):
        if not finding.get("claim") or finding.get("status") not in {
            "verified", "diverged", "pending", "unverified"
        }:
            raise ValueError("each finding needs a claim and a valid status")
        if finding["status"] in {"verified", "diverged"} and not finding.get("evidence"):
            raise ValueError("a verified or diverged finding needs evidence")
    for cited in report_list(report, "reply_quotes"):
        original = prompts.get(cited["prompt_id"])
        if original is None:
            raise ValueError("reply quote refers to a prompt outside the snapshot")
        replies, _ = replies_before(repo, original, seed, paths.get(original["source"]))
        reply = replies.get(cited["source_id"])
        if reply is None:
            raise ValueError("cited reply is unavailable or does not precede the prompt")
        exact = quote_reply(original, reply, cited["part"], cited["start_line"], cited["end_line"])
        if any(cited.get(key) != value for key, value in exact.items()):
            raise ValueError("reply citation does not match the original quoted lines")


def save(repo, args, paths):
    path, manifest = packet(repo, args.run_id)
    prompts = {row["id"]: row for _, row in json_lines(path / "prompts.jsonl")}
    report = load(args.report)
    validate_report(repo, report, manifest, prompts, args.seed, paths)
    destination = repo.file("reviews", f"{args.run_id}.json")
    with repo.lock():
        if destination.exists():
            raise ValueError("review already saved; prepare a new run to keep both versions")
        result = {
            **manifest,
            "finished_at": now(),
            "end_revision": git(repo.root, "rev-parse", "--verify", "HEAD", check=False),
            "coverage_complete": report["reviewed_prompt_count"] == manifest["prompt_count"],
            "report": report,
        }
        write(destination, object_bytes(result))
    return {"report": str(destination), "run_id": args.run_id,
            "coverage_complete": result["coverage_complete"]}


def rebuild_worktree(repo, run_id, destination):
    run_dir(repo, run_id)
    review = load(repo.file("reviews", f"{run_id}.json"))
    revision = review["begin_revision"]
    if not revision or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("the reviewed project has no committed base revision")
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(repo.root):
        raise ValueError("choose a new worktree path outside the existing checkout")
    git(repo.root, "worktree", "add", "--detach", "--", str(destination), revision)
    return {"path": str(destination), "base_revision": revision, "run_id": run_id}
