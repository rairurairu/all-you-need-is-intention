# Capture and backfill

Use `intention.py` from the checkout to be enrolled, or pass `--repo PATH` before the subcommand. Run it with Python 3.11+ and Git available.

```text
enable
status
pause
resume
resume --backfill
backfill --paused --dry-run
backfill --since 2026-01-01T00:00:00Z --until 2026-02-01T00:00:00Z
start
```

`enable` starts a local monitor, polling every 10 seconds by default. It automatically captures turns once the harness persists them. `start` restarts the monitor after a reboot or when a process manager stopped it. `enable --no-start` is useful for tests and for launching the foreground `monitor` explicitly. A new clone needs local enrollment. Each checkout's capture switch, source overrides, and pause windows live in its Git metadata directory.

`pause` closes the active window. `resume` opens a new one. `resume --backfill` also imports retained prompts from completed paused windows. Use `backfill --paused --dry-run` to inspect available counts and source IDs. Backfill accepts explicit UTC-bounded dates, `--source`, `--session`, and temporary `--path SOURCE=PATH` overrides. Missing sources and read errors appear in the command result. A missing or pruned native transcript can leave gaps.

The tracked `.intention/config.toml` marks the repo as enrolled. `.intention/prompts/` contains per-session JSONL files. A record has a stable source ID, a UTC timestamp, an ordered list of verbatim text parts, and an attachment count. Attachment contents and ordinary assistant replies remain in the original harness.

## Sharing prompt evidence

Anyone with access to the Git history can read committed prompts and reply excerpts. Keep sensitive sessions and reports local and inspect files before staging them from `.intention/prompts/` or `.intention/reviews/`. For files already tracked, inspect staged changes too, since [Git ignore rules apply to untracked files](https://git-scm.com/docs/gitignore). For a focused review, select shareable prompts by ID and record the limited scope.

Pause before entering sensitive material. Resume capture normally and backfill only the sessions or time ranges you have cleared to share. `resume --backfill` includes the paused intervals. Keep any published excerpt separate from the verbatim journal and cite its source. If a credential reaches shared history, [revoke or rotate it before cleaning the history](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Source readers

| Source | Where the recorder looks | Attribution |
| --- | --- | --- |
| Codex Desktop and CLI | `$CODEX_HOME/sessions` and `archived_sessions`, defaulting to `~/.codex` | Rollout or turn working directory |
| Claude Code | `$CLAUDE_CONFIG_DIR/projects`, defaulting to `~/.claude` | Turn working directory |
| Pi | `$PI_CODING_AGENT_SESSION_DIR` or the agent directory's `sessions`, defaulting to `~/.pi/agent/sessions` | Session working directory |
| OpenCode | `$OPENCODE_DB` or `$XDG_DATA_HOME/opencode/opencode.db`, defaulting to `~/.local/share/opencode/opencode.db` | Session directory in the legacy or v2 database |
| Hermes Agent | `$HERMES_HOME/state.db`, defaulting to `~/.hermes/state.db` | Session working directory, or local explicit binding for a missing directory |

Use `enable --source SOURCE --path SOURCE=PATH` for custom homes, named profiles, or explicitly selected session files. Repeat `--source` to select several harnesses, and `--path` to add multiple locations for the same harness. A source can be a JSONL file, a directory of JSONL files, or a SQLite file, according to the harness. Native databases are opened read-only. Source records must belong to the checkout or a subdirectory outside nested repos. Use `bind SOURCE SESSION_ID` only for a known repo session whose source lacks a working directory.

The recorder preserves the text persisted by each source. UI transformations, in-memory or hosted sessions, attachments, and harness schema changes can affect what is available. `status` reports matched and added records, source availability, and reader errors from the last scan. Measure capture coverage against an independent count of submitted turns when evaluating a harness.

Source layouts: [Codex](https://github.com/openai/codex) · [Claude Code](https://code.claude.com/docs/en/hooks) · [Pi](https://docs.pi.dev/latest/session-format) · [OpenCode legacy](https://github.com/anomalyco/opencode/blob/v1.4.0/packages/opencode/src/session/session.sql.ts) · [OpenCode v2](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/session/sql.ts) · [Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/sessions)
