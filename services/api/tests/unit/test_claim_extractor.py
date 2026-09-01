from datetime import datetime, timezone

from app.domain.enums import Channel, IncidentType
from app.services.claim_extractor import ExtractRequest, HeuristicClaimExtractor


def test_heuristic_does_not_fill_unit_from_the_word_right() -> None:
    extractor = HeuristicClaimExtractor()
    draft = extractor.extract(
        ExtractRequest(
            customer_id="cus_asha",
            channel=Channel.EMAIL,
            body="The right side produces no audio. Please refund me.",
            occurred_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
            ingest_order_reference=None,
        )
    )
    assert draft.unit_reference is None
    assert draft.order_reference is None
    assert draft.requested_amount_minor is None
    assert draft.incident_type is IncidentType.FUNCTIONAL_FAILURE
    assert draft.requested_remedy == "CASH_REFUND"


def test_heuristic_copies_ingest_order_reference_only() -> None:
    extractor = HeuristicClaimExtractor()
    draft = extractor.extract(
        ExtractRequest(
            customer_id="cus_asha",
            channel=Channel.WHATSAPP,
            body="The right earbud has stopped working. Please send a replacement.",
            occurred_at=datetime(2026, 8, 10, 11, 15, tzinfo=timezone.utc),
            ingest_order_reference="ord_1001",
        )
    )
    assert draft.order_reference == "ord_1001"
    assert draft.requested_remedy == "REPLACEMENT"
    assert draft.incident_type is IncidentType.FUNCTIONAL_FAILURE
