import time
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RETRY_DELAYS = [0, 30, 300, 1800, 7200]   
MAX_ATTEMPTS = len(RETRY_DELAYS)


def _gen_id() -> str:
    import uuid
    return str(uuid.uuid4())[:12]


async def enqueue_webhook(
    db,
    webhook_url:  str,
    payload:      dict,
    project_id:   str,
    alert_id:     Optional[str] = None,
) -> str:
    from ..db.models import WebhookDelivery

    delivery = WebhookDelivery(
        id           = _gen_id(),
        alert_id     = alert_id,
        project_id   = project_id,
        webhook_url  = webhook_url,
        payload_json = payload,
        status       = "pending",
        attempts     = 0,
        next_retry_at= time.time(),   
        created_at   = time.time(),
    )
    db.add(delivery)
    await db.flush()
    logger.info(
        "Webhook delivery enqueued: %s → %s",
        delivery.id, webhook_url[:50],
    )
    return delivery.id


def process_pending_deliveries_sync(db_session) -> int:
    from ..db.models import WebhookDelivery

    now = time.time()
    due = (
        db_session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status.in_(["pending", "retrying"]),
            WebhookDelivery.next_retry_at <= now,
        )
        .limit(20)
        .all()
    )

    processed = 0
    for delivery in due:
        _attempt_delivery(db_session, delivery)
        processed += 1

    if processed:
        db_session.commit()

    return processed


def _attempt_delivery(db_session, delivery) -> None:
    from ..db.models import WebhookDelivery

    now = time.time()
    delivery.attempts       += 1
    delivery.last_attempt_at = now

    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(
                delivery.webhook_url,
                json    = delivery.payload_json,
                headers = {
                    "Content-Type":         "application/json",
                    "X-TraceMind-Delivery": delivery.id,
                    "X-TraceMind-Attempt":  str(delivery.attempts),
                },
            )
            r.raise_for_status()

        delivery.status       = "delivered"
        delivery.error_detail = None
        logger.info(
            "Webhook delivered: %s (attempt %d)",
            delivery.id, delivery.attempts,
        )

    except Exception as exc:
        error_msg = str(exc)[:500]
        delivery.error_detail = error_msg

        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
            logger.error(
                "Webhook permanently failed after %d attempts: %s — %s",
                delivery.attempts, delivery.id, error_msg,
            )
        else:
            delivery.status = "retrying"
            delay_idx           = min(delivery.attempts, len(RETRY_DELAYS) - 1)
            delay               = RETRY_DELAYS[delay_idx]
            delivery.next_retry_at = now + delay
            logger.warning(
                "Webhook failed (attempt %d/%d), retrying in %ds: %s",
                delivery.attempts, MAX_ATTEMPTS, delay, error_msg,
            )