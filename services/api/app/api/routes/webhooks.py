from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_webhook_processor
from app.services.exceptions import IngestError
from app.services.webhook_processor import WebhookProcessor

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    processor: WebhookProcessor = Depends(get_webhook_processor),
) -> dict:
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id") or request.headers.get("x-razorpay-event-id") or ""
    try:
        return processor.handle(raw, signature, event_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
