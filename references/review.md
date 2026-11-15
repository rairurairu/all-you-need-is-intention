# Reconstruct intent and choose a change

1. Run `prepare-review` to freeze the prompts and Git revision. Record the provider, model, reasoning effort, harness, and version when known. The default mode is `intent`. Omit scope filters for a full review, or use `--id` or `--match` for a focused review. Read the originals in order using `review-prompts RUN_ID --offset 0 --limit 20` and advance the offset through the requested scope.
2. Derive current requirements from the original requests and later corrections. Cite the prompt IDs, label inferred requirements, and record unresolved choices. For each material outcome, write an acceptance check with an action and an observable expected result before inspecting the implementation. If a prompt like “go with option two” depends on a reply, retrieve the shortest exact passage that establishes the user's choice.
3. Check current behavior when it affects the decision. Start with the interfaces, data, or tests that can answer the acceptance checks. Use `--mode audit` when verifying a specific delivery or historical claim. Consult previous agent work only to resolve a concrete compatibility, data-preservation, or verification question. Cite what establishes the finding and mark gaps in evidence as unverified.
4. Recommend `keep` when the outcomes are met, `repair` for a bounded gap, `refactor` when restructuring helps deliver the outcome, or `rebuild` when the expected gains justify migration and validation costs. Make the recommendation conditional if the necessary checks are still open. Save the report with `save-review RUN_ID --report FILE`, which validates citations and records the finish time.

Use `evidence PROMPT_ID` to locate reply IDs, then `evidence PROMPT_ID --reply REPLY_ID` to inspect one reply. Pass `--part 1 --lines 8:10` for an inclusive verbatim excerpt. Record an unresolved question if the source is unavailable. For a supplied seed, pass `--seed PATH` to evidence and save. For a custom native source, pass `--path SOURCE=PATH` when saving. Use `prepare-review --from-review RUN_ID` to reproduce a previous prompt set and verify its digest.

## Report fields

```json
{
  "summary": "The outcome the user wants and the decision this review supports.",
  "reviewed_prompt_count": 1,
  "requirements": [
    {"text": "A specific requirement", "basis": "explicit", "prompt_ids": ["SOURCE:SESSION:ID"]}
  ],
  "unresolved": ["A decision that needs the user's input"],
  "recommendation": {"kind": "repair", "rationale": "Evidence and tradeoffs"},
  "plan": ["A concrete action toward the requested outcome"],
  "findings": [
    {"claim": "A statement about the implementation", "status": "unverified", "evidence": []}
  ],
  "verification": ["From a signed-in session, choose Export CSV. A valid CSV downloads without a second login prompt."],
  "reply_quotes": []
}
```

Requirements use `explicit` or `inferred`. Put acceptance checks in the existing `verification` field and actual outcomes in `findings` with sources and a status of `verified`, `diverged`, `pending`, or `unverified`. Put citation objects from `evidence --lines` in `reply_quotes`. Review files can contain sensitive quotes. Check the [sharing guidance](capture.md#sharing-prompt-evidence) before staging them.

When the user requests a rebuild, save the review first, then run `rebuild-worktree RUN_ID NEW_PATH` to create a detached worktree at the reviewed commit. Apply the same acceptance checks to the rebuild and the current checkout. Account for uncommitted changes if the review flags a dirty base.

## Test a seed

In an isolated Git repo, run `import-seed PATH` with the supplied session export. The prompt journal receives only the user's messages. Use the seed as a source for exact reply citations.
