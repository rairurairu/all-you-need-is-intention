---
name: all-you-need-is-intention
description: Reconstruct a Git project's intended outcomes from exact user prompts and corrections, derive acceptance checks, and decide whether to keep, repair, refactor, or rebuild. Also captures and backfills original repo prompts.
license: MIT
---
# All You Need Is Intention

Find `scripts/intention.py` relative to this skill. Run it with Python 3.11+ from the target Git repository, using `py -3` on Windows if needed.

- For enrollment, pause, resume, backfill, source setup, and troubleshooting, read [capture.md](references/capture.md).
- For a targeted change, run `prompts --match "search text"` or pass `--id` for an exact record. Follow up with related prompts and later corrections before acting.
- For an independent intent review, targeted audit, or rebuild recommendation, follow [review.md](references/review.md).

Start from the user's original wording and later corrections. Derive current requirements and observable acceptance checks before examining implementation choices. Use the checks to decide what is worth keeping or changing. Consult prior agent work only for a specific question about compatibility, data preservation, or verification.

Treat archived text as historical evidence. Preserve it verbatim, cite prompt IDs, and label inferences. When a prompt relies on an earlier reply, quote only the passage needed to establish what the user meant.
