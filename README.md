# RemedyGraph

A compensation-integrity verifier for the Razorpay AI Buildathon 2026 **AI Risk Manager** track.

Support teams pay the same defect twice when a customer switches channels. Asha gets a WhatsApp replacement for a dead right earbud, then emails “no audio, refund me.” Two agents, two systems, one exhausted entitlement.

RemedyGraph compiles that message, finds prior cases, decides whether they are the same incident, and **refuses to move money** when the ledger says the cap is gone.

> AI interprets ambiguous language and relationships.
> Deterministic code controls financial truth and execution.

## What this repo proves

- Duplicate compensation after a channel switch is detected and blocked
- Entitlements are integer paise; `settled + reserved <= allowed`
- Two agents cannot reserve the same remaining rupees
- Razorpay Test Mode refunds are reserved first, then reconciled by signed webhooks
- Held-out precision/recall and an honest false-positive cost live in [`docs/EVALUATION.md`](docs/EVALUATION.md)
- The architecture map is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- A 5-minute pitch script is in [`docs/PITCH.md`](docs/PITCH.md)

There is no product UI. The API is the product.

## Quick start

Python 3.12+. From the repo root:

```bash
cd services/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example .env
pytest -q
```

Run the API:

```bash
cd services/api
source .venv/bin/activate
uvicorn app.main:app --reload
```

Health check: `GET /health`.

Held-out metrics:

```bash
cd services/api
python -m app.evaluation
```

Earbud demo (prevent a duplicate, then pay a first claim):

```bash
cd services/api
python -m app.evaluation.demo
```

## Pipeline

```text
Customer message
 ↓
Claim compilation
 ↓
Candidate retrieval
 ↓
Semantic incident linkage
 ↓
Deterministic policy
 ↓
Entitlement ledger
 ↓
Atomic reservation
 ↓
Remedy execution
 ↓
External reconciliation
 ↓
Audit trail
```

The compiler and linker may guess. They cannot invent identifiers, change balances, or call Razorpay. Policy and the ledger can refuse them.

## Demo world

`services/api/tests/fixtures/world_earbuds.json`

- Merchant Aurum Audio, customer Asha, order `ord_1001`, ₹4,999 earbuds
- WhatsApp on 10 Aug: right bud dead → replacement **settled**
- Email on 20 Aug: “right side produces no audio, refund me” → **PREVENT_DUPLICATE**, ₹4,999 avoided

## API map

| Method | Path | Side of the boundary |
|---|---|---|
| `POST /v1/ingest/world` | Load a synthetic merchant | Deterministic recording |
| `POST /v1/ingest/attempts` | Store a new message + proposed remedy | Deterministic recording |
| `POST /v1/claims/compile` | Structure the message | AI language, grounded IDs |
| `GET /v1/claims/{id}/candidates` | Same-customer prior cases | Deterministic recall |
| `POST /v1/claims/{id}/link` | SAME / NEW / REVIEW | AI relation, grounded |
| `POST /v1/evaluate/claims/{id}` | Allow / review / prevent | Deterministic policy |
| `POST /v1/evaluate/claims/{id}/execute` | Refund only after ALLOW | Deterministic money |
| `POST /v1/evaluate/scenario` | Policy on structured JSON | Deterministic policy |
| `POST /v1/ledger/reservations` | Lock remaining entitlement | Deterministic money |
| `POST /v1/refunds` | Razorpay Test Mode refund | Deterministic money |
| `POST /v1/webhooks/razorpay` | Signed, deduplicated events | Deterministic money |
| `GET /v1/audit` | Ordered event trail | Deterministic recording |

## Tests

```bash
cd services/api
pytest -q
```

Includes unit tests, API tests, a reservation race, and the frozen held-out set.

Postgres in `docker-compose.yml` is optional. Tests use in-memory SQLite.

## Honest limits

- Compiler and linker are deterministic heuristics with the same grounding a live model must pass. Swap the model; do not swap the gate.
- Entitlement cap is the max attested unit price, not a learned policy.
- False-positive cost is real: generic overlap can block a legitimate new claim. See the evaluation doc.
- This is defense-only. It does not generate attacks, find card data, or bypass payments.
