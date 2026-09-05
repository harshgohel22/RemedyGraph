# Product spec

RemedyGraph is a cross-channel compensation-integrity verifier. One incident has one entitlement. Multiple partial remedies may be legitimate. Paying the same defect twice is not.

**Loss class:** merchant overcompensation when settled + reserved remedies exceed the allowed entitlement for the same underlying incident.

**Users:** a support agent about to issue a refund/replacement/credit; a reviewer on `REVIEW` cases.

**Non-goals:** customer-fraud scores, chargeback packs, CRM, real PII, offensive refund advice, graph databases.

**Flow:** ingest → compile (language) → retrieve → link (relation) → policy (ALLOW/REVIEW/PREVENT) → atomic reserve → Razorpay cash refund or simulated replacement/credit → webhook reconcile → audit.

**AI may** structure a message and propose SAME/NEW/UNCERTAIN. **Code must** own identifiers, paise, locks, Razorpay, and execution.

**MVP channels:** synthetic email, chat, WhatsApp, internal notes. No live Gmail/WhatsApp.

Full architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Evaluation: [EVALUATION.md](EVALUATION.md). Threat model: [THREAT_MODEL.md](THREAT_MODEL.md).
