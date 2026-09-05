# RemedyGraph

Compensation-integrity verifier for the Razorpay AI Buildathon 2026 **AI Risk Manager** track.

**One class of loss:** duplicate compensation after a channel switch.

Asha gets a WhatsApp replacement for a dead right earbud, then emails “no audio, refund me.” Two agents, two systems, one exhausted entitlement. RemedyGraph compiles that message, finds prior cases, decides whether they are the same incident, and **refuses to move money** when the ledger says the cap is gone.

> AI interprets ambiguous language and relationships.
> Deterministic code controls financial truth and execution.

The model never writes `allowed` / `settled` / `reserved`, never mints order or incident ids, and never calls Razorpay. Defense only.

## What this repo proves

- Duplicate compensation after a channel switch is detected and blocked
- Entitlements are integer paise; `settled + reserved <= allowed`
- Two agents cannot reserve the same remaining rupees
- Razorpay-shaped refunds: reserve first, settle on success, signed webhooks, idempotent retries
- Held-out **PREVENT** precision **62.5%**, recall **83.3%**, false-positive cost **₹14,997**, unsafe miss **₹0** — full write-up in [`docs/EVALUATION.md`](docs/EVALUATION.md)

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Product: [`docs/PRODUCT.md`](docs/PRODUCT.md) · Threat model: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)

The Next.js console in `apps/web` is a demo surface. The FastAPI app in `services/api` is the source of truth.

## Quick start

Python 3.12+ and Node 22+. No OpenAI key. No Razorpay key. Defaults are `CLAIM_COMPILER_MODE=heuristic` and `RAZORPAY_MODE=fake`.

```bash
cd services/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example .env
pytest -q
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Second terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open http://127.0.0.1:3000

1. **Run prevent** — WhatsApp replacement already settled; email wants cash; `PREVENT_DUPLICATE`
2. **Run allow** — first named failure; fake refund settles
3. **Run review** — “one of the earbuds”; no unit guess; no money moved
4. **Evaluation** — frozen held-out report from the API

Health: `GET http://127.0.0.1:8000/health`

Held-out metrics from the CLI:

```bash
cd services/api
python -m app.evaluation
```

Optional: set `CLAIM_COMPILER_MODE=llm` and `INCIDENT_LINKER_MODE=llm` plus `OPENAI_API_KEY` to swap the **draft** generator. `ground_draft` and `ground_link` still run. The ledger does not change.

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
| `POST /v1/refunds` | Razorpay-shaped refund | Deterministic money |
| `POST /v1/webhooks/razorpay` | Signed, deduplicated events | Deterministic money |
| `GET /v1/audit` | Ordered event trail | Deterministic recording |
| `GET /v1/demo/scenarios` | Allow / review / prevent | Deterministic demo |
| `POST /v1/demo/run` | Full pipeline for one demo case | Orchestration, not AI |
| `GET /v1/evaluate/heldout` | Frozen held-out metrics | Deterministic scoring |

## Tests

```bash
cd services/api
pytest -q
```

Unit tests, API tests, a reservation race, demo back-to-back runs, and the frozen held-out set. Tests use in-memory SQLite. Postgres is optional via `docker-compose.yml`.

## Honest limits

- Compiler and linker default to heuristics so held-out numbers stay frozen. A hosted LLM is an optional draft generator behind the same grounding.
- Retrieval is token and identifier overlap, not embeddings. Paraphrases with no shared tokens are a known miss (`holdout_paraphrase_miss`).
- Held-out set is 16 labeled timelines, not 1,000. Label quality was preferred over a round number.
- Razorpay is a fake Test Mode stand-in unless `RAZORPAY_MODE=live` and test keys are set. No real money in the default path.
- Entitlement cap is the max attested unit price, not a full merchant policy engine.
- Replacement and store credit are simulated. Only cash refunds call the payment gateway.
- This is defense-only. It does not generate attacks, find card data, or bypass payments.
