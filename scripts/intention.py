#!/usr/bin/env python3
"""Capture a Git repo's submitted prompts and prepare cited intent reviews."""

import argparse
from pathlib import Path
import subprocess
import sys
import time

from archive import (VERSION, Repo, active, json_bytes, load, lock, now, object_bytes,
                     paused_windows, selected, write)
import review
from sources import HARNESSES, json_lines, moment, read_seed


def print_json(value):
    sys.stdout.buffer.write(json_bytes(value))


def bounded(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def offset(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative offset")
    return number


def timestamp(value):
    try:
        return moment(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use an ISO date and time with a zone") from exc


def line_range(value):
    try:
        start, end = (bounded(part) for part in value.split(":"))
        if start <= end:
            return start, end
    except (ValueError, argparse.ArgumentTypeError):
        pass
    raise argparse.ArgumentTypeError("use START:END with one-based inclusive line numbers")


def locations(values):
    paths = {}
    for value in values or []:
        source, separator, path = value.partition("=")
        if not separator or source not in HARNESSES or not path:
            raise ValueError("--path expects SOURCE=PATH with a supported source")
        paths.setdefault(source, []).append(str(Path(path).expanduser().resolve()))
    return paths


def start(repo):
    if not repo.enrolled() or not active(repo.state()):
        raise ValueError("run enable or resume before starting capture")
    if repo.running():
        return
    command = [sys.executable, str(Path(__file__).resolve()), "--repo", str(repo.root), "monitor"]
    options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if sys.platform == "win32" else {"start_new_session": True})
    log = repo.local / "monitor.log"
    with log.open("wb") as stream:
        process = subprocess.Popen(command, cwd=repo.root, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=stream, **options)
    for _ in range(50):
        if repo.running():
            return
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise ValueError(f"capture monitor did not start; see {log}")


def enable(repo, args):
    with repo.lock():
        repo.init()
        state = repo.state()
        if args.source:
            state["sources"] = list(dict.fromkeys(args.source))
        if args.interval:
            state["interval"] = args.interval
        state["paths"].update(locations(args.path))
        if not active(state):
            state["windows"].append([now(), None])
        repo.save_state(state)
    if not args.no_start:
        start(repo)
    return status(repo)


def pause(repo):
    with repo.lock():
        state = repo.state()
        if active(state):
            state["windows"][-1][1] = now()
            repo.save_state(state)
    return status(repo)


def resume(repo, args):
    if not repo.enrolled():
        raise ValueError("repo is not enrolled; run enable")
    enable(repo, argparse.Namespace(source=None, interval=None, path=None, no_start=args.no_start))
    if args.backfill:
        result = backfill(repo, argparse.Namespace(paused=True, since=None, until=None,
                                                   source=None, path=None, session=None,
                                                   dry_run=False))
        return {"capture": status(repo), "backfill": result}
    return status(repo)


def status(repo):
    state = repo.state()
    last = repo.local / "last-scan.json"
    return {"enrolled": repo.enrolled(), "enabled_here": active(state),
            "running": repo.running(), "interval_seconds": state["interval"],
            "sources": state["sources"], "paused_windows": paused_windows(state),
            "last_scan": load(last) if last.exists() else None}


def summary(added, messages, availability, errors):
    return {"added": added, "matched": len({m.id for m in messages}),
            "sources_available": availability, "errors": errors}


def monitor(repo):
    caches = {}
    previous_state = None
    with lock(repo.local / "monitor.lock", seconds=0):
        while repo.enrolled():
            state = repo.state()
            if not active(state):
                return
            if state != previous_state:
                caches.clear()
                previous_state = state
            messages, available, errors = repo.collect(state, state["windows"], state["sources"],
                                                       caches=caches)
            with repo.lock():
                if repo.state() != state or not repo.enrolled():
                    # Discard offsets and buffered writes after a policy change.
                    caches.clear()
                    continue
                try:
                    added = repo.append(messages)
                except (ValueError, OSError) as exc:
                    # Retry after recoverable custom-store conflicts or I/O errors.
                    added = None
                    caches.clear()
                    errors.append({"error": str(exc)})
                details = summary(added, messages, available, errors)
                write(repo.local / "last-scan.json",
                      object_bytes({"at": now(), **details}))
            time.sleep(state["interval"])


def backfill(repo, args):
    if not repo.enrolled():
        raise ValueError("repo is not enrolled; run enable")
    state = repo.state()
    if args.paused and (args.since or args.until):
        raise ValueError("--paused and explicit dates select different intervals")
    if not args.paused and not args.since:
        raise ValueError("provide --since or --paused")
    if args.since and args.until and args.until <= args.since:
        raise ValueError("--until must follow --since")
    windows = paused_windows(state) if args.paused else [[args.since, args.until]]
    names = args.source or state["sources"]
    if not windows:
        return {"added": 0, "matched": 0, "windows": [], "sources_available": {}, "errors": []}
    messages, availability, errors = repo.collect(state, windows, names, locations(args.path),
                                                  session=args.session)
    with repo.lock():
        added = 0 if args.dry_run else repo.append(messages)
    detail = summary(added, messages, availability, errors)
    detail["windows"] = windows
    if not messages:
        detail["note"] = "No retained matching prompts were found in these intervals."
    if args.dry_run:
        detail["dry_run"] = True
        detail["prompt_ids"] = list(dict.fromkeys(m.id for m in messages))
    return detail


def bind(repo, args):
    if not repo.enrolled():
        raise ValueError("repo is not enrolled; run enable")
    with repo.lock():
        state = repo.state()
        sessions = state["bindings"].setdefault(args.source, [])
        if args.session not in sessions:
            sessions.append(args.session)
            repo.save_state(state)
    return {"source": args.source, "session": args.session, "repo": str(repo.root)}


def import_seed(repo, args):
    messages = [message for message in read_seed(args.seed) if message.role == "user"]
    with repo.lock():
        repo.init()
        added = repo.append(messages)
    return {"added": added, "user_messages": len(messages)}


def command_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    subs = parser.add_subparsers(dest="command", required=True)

    enrollment = subs.add_parser("enable", help="enroll this checkout and start automatic capture")
    enrollment.add_argument("--source", action="append", choices=HARNESSES)
    enrollment.add_argument("--path", action="append", metavar="SOURCE=PATH")
    enrollment.add_argument("--interval", type=bounded)
    enrollment.add_argument("--no-start", action="store_true")
    subs.add_parser("start", help="start an enabled recorder after a reboot or login")
    subs.add_parser("pause", help="pause automatic capture in this checkout")
    resume_parser = subs.add_parser("resume", help="resume capture in this checkout")
    resume_parser.add_argument("--backfill", action="store_true")
    resume_parser.add_argument("--no-start", action="store_true")
    subs.add_parser("status", help="show local recorder state and the last scan")
    subs.add_parser("monitor", help="run the recorder in the foreground")

    fill = subs.add_parser("backfill", help="import user prompts from retained native history")
    fill.add_argument("--paused", action="store_true")
    fill.add_argument("--since", type=timestamp)
    fill.add_argument("--until", type=timestamp)
    fill.add_argument("--source", action="append", choices=HARNESSES)
    fill.add_argument("--path", action="append", metavar="SOURCE=PATH")
    fill.add_argument("--session")
    fill.add_argument("--dry-run", action="store_true")
    binding = subs.add_parser("bind", help="associate a cwd-less session with this repo locally")
    binding.add_argument("source", choices=HARNESSES)
    binding.add_argument("session")
    seed = subs.add_parser("import-seed", help="import the user messages of an explicit seed file")
    seed.add_argument("seed", type=Path)

    def scope(command):
        command.add_argument("--match")
        command.add_argument("--id", action="append")
        command.add_argument("--session")

    prompts = subs.add_parser("prompts", help="emit matching original prompts as JSONL")
    scope(prompts)
    prompts.add_argument("--limit", type=bounded)

    evidence = subs.add_parser("evidence", help="locate or quote a prior assistant reply")
    evidence.add_argument("prompt_id")
    evidence.add_argument("--seed", type=Path)
    evidence.add_argument("--path", type=Path, action="append")
    evidence.add_argument("--reply")
    evidence.add_argument("--part", type=bounded, default=1)
    evidence.add_argument("--lines", type=line_range)
    evidence.add_argument("--limit", type=bounded, default=5)

    prep = subs.add_parser("prepare-review", help="freeze the prompt inputs and run metadata")
    scope(prep)
    prep.add_argument("--mode", choices=["intent", "audit"], default="audit")
    prep.add_argument("--from-review", help="use a previous review's exact recorded prompt set")
    for name in ("provider", "model", "effort", "harness", "harness-version"):
        prep.add_argument(f"--{name}", default="unknown")

    batch = subs.add_parser("review-prompts", help="read a batch from a frozen prompt snapshot")
    batch.add_argument("run_id")
    batch.add_argument("--offset", type=offset, default=0)
    batch.add_argument("--limit", type=bounded, default=20)

    finish = subs.add_parser("save-review", help="validate citations and write the review JSON")
    finish.add_argument("run_id")
    finish.add_argument("--report", type=Path, required=True)
    finish.add_argument("--seed", type=Path)
    finish.add_argument("--path", action="append", metavar="SOURCE=PATH")

    rebuild = subs.add_parser("rebuild-worktree", help="create an isolated worktree for a rebuild")
    rebuild.add_argument("run_id")
    rebuild.add_argument("destination", type=Path)
    return parser


def main():
    args = command_parser().parse_args()
    try:
        repo = Repo(args.repo)
        if args.command == "monitor":
            monitor(repo)
            return 0
        if args.command == "prompts":
            for row in selected(repo.prompts(), args.match, args.id, args.session, args.limit):
                print_json(row)
            return 0
        if args.command == "review-prompts":
            path, _ = review.packet(repo, args.run_id)
            for index, (_, row) in enumerate(json_lines(path / "prompts.jsonl")):
                if index >= args.offset + args.limit:
                    break
                if index >= args.offset:
                    print_json(row)
            return 0
        if args.command == "start":
            start(repo)
            result = status(repo)
        elif args.command == "pause":
            result = pause(repo)
        elif args.command == "status":
            result = status(repo)
        elif args.command == "rebuild-worktree":
            result = review.rebuild_worktree(repo, args.run_id, args.destination)
        elif args.command == "save-review":
            result = review.save(repo, args, locations(args.path))
        else:
            result = {
                "enable": enable, "resume": resume, "backfill": backfill, "bind": bind,
                "import-seed": import_seed, "evidence": review.evidence,
                "prepare-review": review.prepare,
            }[args.command](repo, args)
        print_json(result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"intention: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
