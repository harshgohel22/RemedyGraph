# Evaluation

Track bar: measured precision and recall on a **held-out** set, plus an honest false-positive cost.

Development scenarios live in `services/api/tests/fixtures/seed_scenarios.json` (12 structured policy cases). They are **not** the held-out set.

Held-out files were frozen on **5 September 2026**:

- `services/api/tests/fixtures/heldout_cases.json` — 16 end-to-end cases (ingest → compile → retrieve → link → policy)
- `services/api/tests/fixtures/heldout_policy.json` — 8 structured policy cases with amounts that do not appear in the seed file

Labels were written from the product rule, not from model output. Re-run:

```bash
cd services/api
python -m app.evaluation
```

## What “positive” means

The loss we are paid to stop is **duplicate compensation**. The positive class is `PREVENT_DUPLICATE`.

| Error | Meaning | Cost we report |
|---|---|---|
| False prevent | We blocked a claim that should have been `ALLOW` | proposed paise (customer denied) |
| Unsafe miss | Gold `PREVENT`, we `ALLOW` | proposed paise (merchant pays twice) |
| Safe miss | Gold `PREVENT`, we `REVIEW` | ₹0 paid; hurts recall only |

Linkage is scored separately: positive class is `SAME_INCIDENT`.

## Held-out results (frozen)

End-to-end (16 cases, heuristic compiler + heuristic linker + grounding + policy):

| Metric | Value |
|---|---|
| PREVENT precision | **62.5%** (5 / 8) |
| PREVENT recall | **83.3%** (5 / 6) |
| SAME precision | **66.7%** (6 / 9) |
| SAME recall | **85.7%** (6 / 7) |
| Decision accuracy | **75.0%** (12 / 16) |
| Relation accuracy | **68.8%** (11 / 16) |
| False-positive cost | **₹14,997** (3 × ₹4,999) |
| Missed-loss cost (unsafe `ALLOW`) | **₹0** |
| REVIEW predictions | 3 |

Structured policy held-out: **8 / 8 exact**. That is expected. `decide()` has no weights. The number exists to prove unseen ledger arithmetic, not to inflate an ML score.

## Documented miss

`holdout_paraphrase_miss`

- Prior WhatsApp: “The right earbud has stopped working. Please send a replacement.” Replacement settled.
- New email: “Audio is gone on one side, send my money back.”
- Gold: `SAME_INCIDENT` → `PREVENT_DUPLICATE`
- Predicted: `NEW_INCIDENT` → `REVIEW`

No shared content tokens, no order id. The linker does not prove SAME. Policy does not invent a cap without an attested order, so it reviews instead of paying. **Recall miss, fail-closed.** We did not auto-refund.

If we had treated “customer has only one order” as evidence, this case would look solved and the metric would be a lie.

## False prevents (the expensive mistakes)

All three are the same failure mode: **prior remedy + weak overlap (or same order) ⇒ SAME**.

| Case | What the customer said | What we did |
|---|---|---|
| `holdout_generic_tokens_false_same` | Charger “not working” after earbuds replacement | Blocked ₹4,999 |
| `holdout_damaged_after_functional` | Box arrived cracked, same order | Blocked ₹4,999 |
| `holdout_wrong_item_after_replacement` | Different product received, same order | Blocked ₹4,999 |

That is the honest false-positive cost. A live embedding model might shrink it. It must still pass grounding, and it must still be measured on this frozen file.

## What we do not claim

- These numbers are not from a production traffic sample.
- The compiler/linker are heuristics. A hosted LLM can replace them; the ledger cannot.
- We did not peek at this file and then retune token lists to raise precision.
- Defense only. No offensive fraud tooling.

## Naive versions that fail

| Naive design | What happens on this set |
|---|---|
| Every prior case is SAME | Invoice questions and second orders get blocked or, worse, share one entitlement |
| Invent `ord_1001` because it is the only order | Paraphrase miss looks “solved”; identifiers are laundered |
| Reuse the candidate incident id when the relation is NEW | A second attested order inherits the first incident’s exhaustion |
| Let the model write `allowed` | Cap becomes a prompt |
| Count only the earbud demo | One cherry-picked prevent proves nothing |
