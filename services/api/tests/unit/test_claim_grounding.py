from app.domain.enums import Channel, IncidentType
from app.schemas.claims import ClaimDraft
from app.services.claim_grounding import IdCatalog, ground_draft, id_is_attested


CATALOG = IdCatalog(
    order_ids=frozenset({"ord_1001"}),
    product_ids=frozenset({"wireless_earbuds"}),
    unit_ids=frozenset({"unit_right", "unit_left", "unit_right_r2"}),
)


def _draft(**overrides: object) -> ClaimDraft:
    payload: dict = {
        "incident_description": "The right side produces no audio. Please refund me.",
        "incident_type": IncidentType.FUNCTIONAL_FAILURE,
        "requested_remedy": "CASH_REFUND",
    }
    payload.update(overrides)
    return ClaimDraft.model_validate(payload)


def _ground(draft: ClaimDraft, *, body: str, ingest_order: str | None = None):
    return ground_draft(
        claim_id="clm_test",
        customer_id="cus_asha",
        channel=Channel.EMAIL,
        body=body,
        ingest_order_reference=ingest_order,
        draft=draft,
        catalog=CATALOG,
    )


def naive_keep_if_in_catalog(order_reference: str | None, catalog: IdCatalog) -> str | None:
    """Broken: any real order id is kept, even if the message never mentioned it."""

    if order_reference in catalog.order_ids:
        return order_reference
    return None


def test_naive_accepts_unmentioned_but_real_order_id() -> None:
    body = "The right side produces no audio. Please refund me."
    hallucinated = "ord_1001"
    assert naive_keep_if_in_catalog(hallucinated, CATALOG) == "ord_1001"

    grounded = _ground(_draft(order_reference=hallucinated), body=body)
    assert grounded.order_reference is None
    assert "order_reference" in grounded.unknown_fields


def test_invented_order_id_not_in_catalog_is_dropped() -> None:
    body = "Refund order ord_9999 please."
    grounded = _ground(_draft(order_reference="ord_9999"), body=body)
    assert grounded.order_reference is None
    assert "order_reference" in grounded.unknown_fields


def test_attested_catalog_order_is_kept() -> None:
    body = "About order ord_1001: the right side produces no audio."
    grounded = _ground(_draft(order_reference="ord_1001"), body=body)
    assert grounded.order_reference == "ord_1001"
    assert "order_reference" not in grounded.unknown_fields


def test_ingest_order_reference_is_not_treated_as_model_invention() -> None:
    body = "The right earbud has stopped working. Please send a replacement."
    grounded = _ground(
        _draft(order_reference=None, requested_remedy="REPLACEMENT"),
        body=body,
        ingest_order="ord_1001",
    )
    assert grounded.order_reference == "ord_1001"


def test_prefix_id_is_not_attested_inside_a_longer_id() -> None:
    assert not id_is_attested("ord_1", "please look at ord_1001")
    assert id_is_attested("ord_1001", "please look at ord_1001")


def test_unit_id_guessed_from_language_is_dropped() -> None:
    body = "The right side produces no audio."
    grounded = _ground(_draft(unit_reference="unit_right"), body=body)
    assert grounded.unit_reference is None
    assert "unit_reference" in grounded.unknown_fields


def test_unmentioned_catalog_price_is_not_copied_into_requested_amount() -> None:
    body = "The right side produces no audio. Please refund me."
    grounded = _ground(_draft(requested_amount_minor=499900), body=body)
    assert grounded.requested_amount_minor is None
    assert "requested_amount_minor" in grounded.unknown_fields


def test_customer_and_channel_come_from_the_record_not_the_draft() -> None:
    grounded = _ground(_draft(), body="no audio, refund me")
    assert grounded.claim_id == "clm_test"
    assert grounded.customer_id == "cus_asha"
    assert grounded.channel is Channel.EMAIL
    assert grounded.incident_type is IncidentType.FUNCTIONAL_FAILURE
