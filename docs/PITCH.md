# 5-minute pitch

Track: **AI Risk Manager**. Product: **RemedyGraph**. Loss class: **duplicate compensation after a channel switch**.

## 0:00–0:40 — The failure

Asha’s right earbud dies. WhatsApp agent sends a replacement. Ten days later she emails “right side has no audio, refund me.” A second agent does not see WhatsApp. The merchant pays twice.

That is not fraud in the cinema sense. It is two honest tickets against one entitlement.

## 0:40–1:40 — The split

AI reads the email and the WhatsApp history. Code owns the rupees.

If we let the model decide the refund, it will invent `ord_1001` because she only has one order, or it will say SAME with no evidence. RemedyGraph forbids that. Identifiers must appear on the message. SAME without overlap is downgraded. The ledger is a locked row: settled plus reserved cannot exceed allowed.

## 1:40–3:10 — Live path (demo)

1. Load `world_earbuds.json`. Replacement already `SETTLED` for ₹4,999.
2. Ingest the email. Compile. Retrieve. Link → `SAME_INCIDENT` on `inc_msg_wa_001`.
3. Evaluate → `PREVENT_DUPLICATE`. Avoidable overcompensation ₹4,999. Ledger remaining ₹0. Execute is a no-op.
4. Repeat on a world with no history. Evaluate → `ALLOW`. Execute → fake Razorpay refund, reservation settles.
5. Show `GET /v1/audit`.

Commands:

```bash
cd services/api
python -m app.evaluation.demo
pytest tests/concurrency/test_reservation_race.py -q
python -m app.evaluation
```

## 3:10–4:20 — Held-out honesty

Sixteen frozen cases, labeled before looking at output. Positive class is `PREVENT_DUPLICATE`.

Say the numbers from `docs/EVALUATION.md` out loud: precision, recall, false-positive cost, missed-loss cost.

Name the documented miss: *“Audio is gone on one side, send my money back.”* No shared tokens, no order id. The heuristic calls it new and would pay again. We kept that miss in the set.

Policy on structured inputs is exact. That is not an ML win. It is the money gate having no weights.

## 4:20–5:00 — Why this is hireable

- Defense only. No offense-capable tooling.
- Razorpay Test Mode shaped like production: reserve, refund, signed webhook, idempotency.
- One concurrency proof: two reservations, one remaining balance, one winner.
- Safe failure: timeout does not settle; duplicate webhook does not settle twice.
- I can open any money file and say what invariant it protects.

If asked “why not just embed and threshold?”: embeddings still cannot write the ledger. The interesting bug is leakage (NEW when it was SAME) and false SAME (blocking a new charger claim because both messages said “not working”). Those are evaluation problems, not prompt problems.
