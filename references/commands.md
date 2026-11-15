# AYNII command

Apply these actions to the current Git checkout. The first argument names the action. With no action, `help`, or an unknown action, show the table below and stop.

| Action | What it does |
| --- | --- |
| `status` | Run `intention.py status`. Report whether capture is enrolled, enabled, and running. |
| `enable`, `pause`, `resume`, `start` | Run the matching `intention.py` subcommand. Pass options explicitly supplied for it. |
| `backfill --paused` or `backfill --since DATE` | Use the CLI to import the stated scope. Honor `--until`, `--session`, `--source`, and `--dry-run` when supplied. If the scope is missing, show the syntax. |
| `review` or `r` with an optional focus | Follow the [intent review workflow](review.md). Review the full prompt journal when the user supplies no focus. Use any supplied focus to scope the prompt selection. |
| `audit <claim>` | Follow the review workflow with `prepare-review --mode audit` and verify the given claim. If the claim is missing, show the syntax. |

Run the installed skill's script with Python 3.11+ (`py -3` on Windows). Pass values as CLI arguments, with shell quoting as needed. The host's normal tool permissions apply.
