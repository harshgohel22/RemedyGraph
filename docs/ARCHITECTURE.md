# Architecture

RemedyGraph is a verifier, not a chatbot. One proposed remedy is checked against one incident entitlement. If the remaining rupees are gone, money does not move.

## Who uses it

A support agent (or a ticket system) submits a customer message and a proposed refund, replacement, or store credit. The Next.js console in `apps/web` is that agent surface: intake, investigation, decision/ledger, evaluation.

## The boundary

| AI may | Deterministic code must |
|---|---|
| Read messy language | Store integer paise |
| Suggest incident type and remedy | Refuse invented order / unit / payment IDs |
| Propose SAME / NEW / UNCERTAIN | Downgrade an unsafe SAME |
| Explain why two messages look related | Decide ALLOW / REVIEW / PREVENT |
| | Reserve, settle, release, fail |
| | Call Razorpay and apply webhooks |

A model output never writes `allowed`, `settled`, or `reserved`. It never is the refund idempotency key. It never creates an incident id.

## Parts

```text
ingest  →  compile  →  retrieve  →  link  →  policy  →  ledger  →  Razorpay  →  audit
                 (language)     (recall)  (relation)  (money gate)  (lock)
```

**Ingest** stores the merchant world and the new attempt exactly as they arrived, including null order ids.

**Compile** turns a paragraph into a grounded claim. The extractor may guess `FUNCTIONAL_FAILURE`. Grounding drops any identifier that was not on the inbound message.

**Retrieve** lists earlier messages for the same customer. It scores overlap. It does not output `SAME_INCIDENT`.

**Link** asks whether the top candidate is the same incident. Grounding downgrades SAME when order ids conflict, unit ids conflict, or there is no shared evidence.

**Policy** is a pure function of ledger position + relation + proposed paise. Uncertain links become `REVIEW`. Same incident over remaining becomes `PREVENT_DUPLICATE`.

**Ledger** is one lockable row per `(merchant, incident)`. `settled + reserved <= allowed` is a table check and an atomic `UPDATE`.

**Execute** calls Razorpay only after `ALLOW`. Reserve first. Timeout leaves `RECONCILIATION_REQUIRED`. Duplicate webhooks are ignored.

**Audit** appends every world load, compile, link, decision, refund, and webhook.

## Failure

| Failure | What we do |
|---|---|
| Missing order id | Leave it null. Do not pick the customer's only order. |
| Reckless SAME | Grounding downgrades to UNCERTAIN or NEW. |
| Two agents, one remaining balance | One `UPDATE` wins; the other gets `409`. |
| Razorpay timeout after reserve | Hold the reservation; wait for the webhook or a fetch. |
| Duplicate webhook | Same `event_id` is stored once. |
| Model asks for more than the cap on a new incident | `REVIEW`, not a silent raise of the cap. |

## What is not in this architecture

No graph database. No multi-agent planner. Default compiler/linker are heuristics so held-out scores stay frozen. Set `CLAIM_COMPILER_MODE=llm` / `INCIDENT_LINKER_MODE=llm` to swap in a hosted model as the draft generator; grounding and the ledger stay the same. The Next.js console is a demo surface over the same API; it cannot write the ledger except by calling ALLOW execute.

## Storage

SQLite for local tests and the default API. Postgres is optional via `docker-compose.yml`. Amounts are integers. Currency is INR.
