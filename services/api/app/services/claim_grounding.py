from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.enums import Channel
from app.schemas.claims import ClaimDraft, CompiledClaim

_IDENTIFIER_FIELDS = ("order_reference", "product_reference", "unit_reference")


@dataclass(frozen=True)
class IdCatalog:
    """IDs this customer actually has. The extractor never receives this object."""

    order_ids: frozenset[str]
    product_ids: frozenset[str]
    unit_ids: frozenset[str]


def attestation_text(body: str, ingest_order_reference: str | None) -> str:
    if ingest_order_reference:
        return f"{body}\n{ingest_order_reference}"
    return body


def id_is_attested(value: str, attested: str) -> bool:
    """True when value appears as a whole token, not as a prefix of a longer id."""

    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])", attested) is not None


def amount_is_attested(amount_minor: int, body: str) -> bool:
    return str(amount_minor) in body


def ground_draft(
    *,
    claim_id: str,
    customer_id: str,
    channel: Channel,
    body: str,
    ingest_order_reference: str | None,
    draft: ClaimDraft,
    catalog: IdCatalog,
) -> CompiledClaim:
    """Keep language fields. Drop identifiers the message did not actually mention."""

    attested = attestation_text(body, ingest_order_reference)
    unknown: list[str] = list(draft.unknown_fields)

    order_reference = _ground_id(
        draft.order_reference,
        catalog.order_ids,
        attested,
        fallback=ingest_order_reference,
    )
    product_reference = _ground_id(draft.product_reference, catalog.product_ids, attested)
    unit_reference = _ground_id(draft.unit_reference, catalog.unit_ids, attested)

    requested_amount = draft.requested_amount_minor
    if requested_amount is not None and not amount_is_attested(requested_amount, body):
        requested_amount = None

    grounded = {
        "order_reference": order_reference,
        "product_reference": product_reference,
        "unit_reference": unit_reference,
    }
    for field in _IDENTIFIER_FIELDS:
        if grounded[field] is None:
            _add_unknown(unknown, field)
        else:
            _remove_unknown(unknown, field)

    if draft.incident_type is None:
        _add_unknown(unknown, "incident_type")
    if requested_amount is None:
        _add_unknown(unknown, "requested_amount_minor")
    else:
        _remove_unknown(unknown, "requested_amount_minor")

    description = draft.incident_description.strip() or body

    return CompiledClaim(
        claim_id=claim_id,
        customer_id=customer_id,
        channel=channel,
        order_reference=order_reference,
        product_reference=product_reference,
        unit_reference=unit_reference,
        incident_type=draft.incident_type,
        incident_description=description,
        incident_time=draft.incident_time,
        affected_quantity=draft.affected_quantity,
        requested_remedy=draft.requested_remedy,
        requested_amount_minor=requested_amount,
        extracted_facts=list(draft.extracted_facts),
        unknown_fields=unknown,
        model_confidence=draft.model_confidence,
    )


def _ground_id(
    value: str | None,
    allowed: frozenset[str],
    attested: str,
    fallback: str | None = None,
) -> str | None:
    if value and value in allowed and id_is_attested(value, attested):
        return value
    if fallback and fallback in allowed:
        return fallback
    return None


def _add_unknown(fields: list[str], name: str) -> None:
    if name not in fields:
        fields.append(name)


def _remove_unknown(fields: list[str], name: str) -> None:
    while name in fields:
        fields.remove(name)
