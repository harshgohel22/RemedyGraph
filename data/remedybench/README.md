# RemedyBench

Public synthetic benchmark for compensation-integrity decisions.

Current freeze (submission):

| Split | Location | Size |
|---|---|---|
| Development / seed policy | `services/api/tests/fixtures/seed_scenarios.json` | 12 structured |
| Held-out e2e | `services/api/tests/fixtures/heldout_cases.json` | 16 timelines |
| Held-out policy arithmetic | `services/api/tests/fixtures/heldout_policy.json` | 8 structured |

Labels were written from the product rule, then the system was run. Do not retune tokens against held-out outcomes.

The handoff target of ~1,000 timelines remains the next expansion. Until then, quality of these frozen files is the evaluation claim.

Run:

```bash
cd services/api
python -m app.evaluation
```
