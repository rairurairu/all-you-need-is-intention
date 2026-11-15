# All You Need Is Intention

All You Need Is Intention saves your original coding-agent prompts in Git so a future agent can recover what you wanted and check what shipped.

## Why keep the original prompts?

1. **Models are changing quickly.** The same request can get a much better result from a model released a few months later.
2. **The harness matters too.** Different models, harnesses, skills, and tools can produce different results from the same prompt.
3. **Rebuilding is getting easier and cheaper.** If earlier work left the repo cluttered or took it in the wrong direction, a later agent can read the original requests and decide whether to fix, refactor, or rebuild.

An improved model may understand a rough or ambiguous prompt better than the agent that first acted on it. The original wording also lets a second agent form an independent reading before comparing it with the first agent's plan or implementation.

For a focused task, a handful of relevant prompts and corrections may be enough to get started. The reviewer can pull in a specific reply or check the code when a decision needs more context.

## Get started

The recorder uses Python 3.11+, Git, and local harness history. The review runs in the agent you choose.

1. Put this entire folder in a skill location supported by your harness, or give your agent the path to [SKILL.md](SKILL.md).
2. From the Git checkout you want to enroll, run `python3 /path/to/all-you-need-is-intention/scripts/intention.py enable`. On Windows use `py -3` with the script's path.
3. Include `.intention/config.toml` and prompt journals in ordinary Git commits. In a new clone, run `enable` once to start local capture.
4. Ask your agent to review the repo against the archive. It snapshots the prompts, cites the evidence, and saves a dated review.

Use [capture.md](references/capture.md) for pause, resume, source paths, and backfill. Use [review.md](references/review.md) for the report format and worktree workflow.

## A review from original prompts

Suppose you told an agent, “Keep CSV export available without requiring another login.” Months later, a reviewer can cite that exact prompt, check whether the current export honors the constraint, and record the result alongside the Git revision and the model that ran the review.

## Share the project

> All You Need Is Intention saves your exact coding-agent prompts in Git so future agents can recover what you asked for, check what shipped, and plan a fix or rebuild.

If the skill is useful to you, star it on GitHub. If you write about it, feel free to quote the description and link readers to the [original repository](https://github.com/rairurairu/all-you-need-is-intention).

## License

Copyright 2026 All You Need Is Intention contributors. Released under the [MIT License](LICENSE).
