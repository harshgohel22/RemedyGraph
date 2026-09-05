# Threat model

**Asset:** remaining incident entitlement (integer paise) and the right to call Razorpay refunds.

**Attacker / failure modes we design for (defense only):**

| Threat | Control |
|---|---|
| Model invents `ord_1001` | Grounding: identifiers must appear on the inbound message |
| Reckless SAME | Grounding downgrades without overlap or on ID conflict |
| Two agents, one remaining balance | Atomic `UPDATE` reservation; concurrency test |
| Duplicate / out-of-order webhooks | Signed body + `event_id` uniqueness |
| Timeout after reserve | `RECONCILIATION_REQUIRED`; do not settle; fetch before new key |
| Unknown cap | `REVIEW`, do not invent a price |
| Ambiguous which of two units failed | `REVIEW` (`UNIT_AMBIGUOUS`) |
| Prompt injection into refund | Model cannot call Razorpay or write the ledger |

**Out of scope:** stealing cards, attacking Razorpay, doxxing customers, generating refund-abuse playbooks.

Secrets stay in server env. The Next.js app talks to the API; it never sees `RAZORPAY_KEY_SECRET`.
