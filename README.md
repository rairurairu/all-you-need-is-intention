# All You Need Is Intention

Keep the original user prompts for a repo and use them to reconstruct intent, audit what shipped, or plan a repair, refactor, or rebuild. The recorder uses Python 3.11+, Git, and local harness history. The review runs in the agent you choose.

## Get started

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

Copyright 2026 All You Need Is Intention contributors. Licensed under the [Apache License, Version 2.0](LICENSE).
