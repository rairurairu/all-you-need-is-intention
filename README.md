# All You Need Is Intention

All You Need Is Intention helps you judge a repo by the outcomes you asked for. It preserves your exact prompts and corrections in Git so a future agent can reconstruct the requirements, write acceptance checks, and decide whether to keep, repair, refactor, or rebuild.

## Why keep the original prompts?

1. **Models are changing quickly.** The same request can get a much better result from a model released a few months later.
2. **The harness matters too.** Different models, harnesses, skills, and tools can produce different results from the same prompt.
3. **Rebuilding is getting easier and cheaper.** If earlier work left the repo cluttered or took it in the wrong direction, a later agent can read the original requests and decide whether to fix, refactor, or rebuild.

An improved model may understand a rough or ambiguous prompt better than the agent that first acted on it. The original wording gives a second agent an independent starting point. Designs and code can change freely within the requested outcomes and necessary compatibility and data-preservation constraints.

For a focused task, a handful of relevant prompts and corrections may be enough to get started. The reviewer can pull in a specific reply or check the code when a decision needs more context.

## Get started

The recorder uses Python 3.11+, Git, and local harness history. The review runs in the agent you choose.

1. Put this entire folder in a skill location supported by your harness, or give your agent the path to [SKILL.md](SKILL.md).
2. From the Git checkout you want to enroll, run `python3 /path/to/all-you-need-is-intention/scripts/intention.py enable`. On Windows use `py -3` with the script's path.
3. Commit `.intention/config.toml` and review prompt journals for sensitive material before sharing them in Git. In a new clone, run `enable` once to start local capture.
4. Ask your agent to reconstruct intent from the original prompts. It derives acceptance checks, uses current behavior to evaluate the options, and saves a cited review.

Use [capture.md](references/capture.md) for pause, resume, source paths, and backfill. Use [review.md](references/review.md) for the report format and worktree workflow.

## Chat command

Install the main AYNII skill, then use the shortcut for your agent.

| Agent | Shortcut setup | Run it in chat |
| --- | --- | --- |
| Codex | Install the whole AYNII folder, including `commands/`, in a Codex skill directory such as `.agents/skills/`. Codex discovers the bundled alias. | `$aynii status` |
| Claude Code | Copy [`aynii.md`](commands/aynii.md) to `.claude/commands/aynii.md` in the target checkout. | `/aynii status` |
| OpenCode | Copy [`aynii.md`](commands/aynii.md) to `.opencode/commands/aynii.md` in the target checkout. | `/aynii status` |
| Pi | Copy [`aynii.md`](commands/aynii.md) to `~/.pi/agent/prompts/aynii.md`. | `/aynii status` |
| Hermes Agent | Install the whole AYNII folder in `~/.hermes/skills/`. If the alias is absent from `/help skills`, copy the [`aynii` skill folder](commands/aynii) beside the main skill. | `/aynii status` |

Try `review CSV export` after the shortcut name to start a focused review. See the [command list](references/commands.md) for other actions.

Chat shortcuts start an agent turn. Run the [capture CLI](references/capture.md) directly for local operations that use zero model tokens. Template-based shortcuts can expand before capture. AYNII preserves the text the host persists to its session store.

Each host documents its shortcut format. [OpenAI Docs](https://learn.chatgpt.com/docs/build-skills) · [Claude Code](https://code.claude.com/docs/en/skills) · [OpenCode](https://opencode.ai/docs/commands) · [Pi](https://docs.pi.dev/latest/prompt-templates) · [Hermes Agent](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)

## A review from original prompts

Suppose you told an agent, “Keep CSV export available without requiring another login.” A later reviewer can turn that into a check. From a signed-in session, Export CSV downloads a readable CSV without a second login prompt. If the current export passes, keep it. If it fails, use the result to scope the change.

## Share the project

> All You Need Is Intention turns your original coding-agent prompts into acceptance checks so another agent can decide what to keep, fix, or rebuild.

If the skill is useful to you, star it on GitHub. If you write about it, feel free to quote the description and link readers to the [original repository](https://github.com/rairurairu/all-you-need-is-intention).

## License

Copyright 2026 All You Need Is Intention contributors. Released under the [MIT License](LICENSE).
