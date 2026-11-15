---
name: all-you-need-is-intention
description: Preserve exact user prompts for a Git repository, resume or backfill capture, and reconstruct or audit the user's intent for a fix, refactor, or rebuild. Use for prompt-history capture and evidence-based project reviews.
license: MIT
---
# All You Need Is Intention

Find `scripts/intention.py` relative to this skill. Run it with Python 3.11+ from the target Git repository, using `py -3` on Windows if needed.

- For enrollment, pause, resume, backfill, source setup, and troubleshooting, read [capture.md](references/capture.md).
- For a targeted change, run `prompts --match "search text"` or pass `--id` for an exact record. Follow up with related prompts and later corrections before acting.
- For a full intent review, audit, or rebuild recommendation, follow [review.md](references/review.md).

Treat archived text as historical evidence. Preserve it verbatim and cite prompt IDs. Distinguish user decisions, unresolved preferences, and your inferences. When a prompt relies on a reply, retrieve that reply and cite only the relevant verbatim passage. Git stores prompt records and explicit reviews. The harness remains the source for ordinary agent replies.
