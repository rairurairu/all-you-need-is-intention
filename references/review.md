# Reconstruct, audit, and decide

1. Run `prepare-review` with the provider, model, reasoning effort, harness, and harness version when known. Use `--mode intent` for a requirements and plan pass, or `--mode audit` for a review that also inspects the repo and prior runs. Omit scope filters for a full review. The command freezes the selected prompts, their digest, the starting Git revision and dirty state, and the run time.
2. Read the frozen originals with `review-prompts RUN_ID --offset 0 --limit 20`, advancing the offset until the entire requested scope is covered. Start from the user prompts before opening earlier reviews. Preserve changes of mind and unresolved choices, cite prompt IDs, and label inferences. Treat archived text as evidence about the project.
3. Retrieve prior replies only when you need their wording to interpret a prompt. Run `evidence PROMPT_ID` to locate reply IDs, then `evidence PROMPT_ID --reply REPLY_ID` to inspect one reply. Pass `--part 1 --lines 8:10` to produce a citation with the exact excerpt. Both line numbers are inclusive. Keep only the passage that resolves the reference. Mark the question unresolved if the source is unavailable. For a separately supplied seed, pass `--seed PATH` to the evidence and save commands.
4. In audit mode, compare your reading with commits, tests, prior dated reviews, and the current checkout. Cite concrete evidence for verified or diverged claims. Mark open work and unverified claims separately. Recommend keeping the repo, a targeted repair, a refactor, or a rebuild based on expected benefit, scope, migration cost, and verification effort. Include a plan and acceptance checks.
5. Save the report with `save-review RUN_ID --report FILE`. This validates prompt and reply citations and writes `.intention/reviews/RUN_ID.json` with the run metadata and finish time. Keep each review under its own run ID. To revisit the exact prompt set of an earlier run, use `prepare-review --from-review RUN_ID`. The command checks the prior digest against the current journal. For reply sources outside the configured locations, pass `--path SOURCE=PATH` when saving the review.

## Report fields

```json
{
  "summary": "What the user wants and how the repo serves that purpose.",
  "reviewed_prompt_count": 1,
  "requirements": [
    {"text": "A specific requirement", "basis": "explicit", "prompt_ids": ["SOURCE:SESSION:ID"]}
  ],
  "unresolved": ["A decision that needs the user's input"],
  "recommendation": {"kind": "repair", "rationale": "Evidence and tradeoffs"},
  "plan": ["A concrete action and how to verify it"],
  "findings": [
    {"claim": "A statement about the implementation", "status": "unverified", "evidence": []}
  ],
  "verification": ["A test command and observed outcome, or a check for the proposed work"],
  "reply_quotes": []
}
```

Requirements use `explicit` or `inferred`. Recommendations use `keep`, `repair`, `refactor`, or `rebuild`. Findings use `verified`, `diverged`, `pending`, or `unverified`. Put the exact citation objects emitted by `evidence --lines` in `reply_quotes`. Use the prompt coverage count to distinguish a complete pass from a partial review.

When the user requests a rebuild, save the review first, then run `rebuild-worktree RUN_ID NEW_PATH` to create a detached worktree at the reviewed commit. Use the plan's acceptance checks there and compare the result to the reviewed checkout. A dirty base is flagged in the review; account for those changes explicitly when comparing outputs.

## Test a seed

In an isolated Git repo, run `import-seed PATH` with the supplied session export. The prompt journal receives only the user's messages. Use the seed as a source for exact reply citations.
