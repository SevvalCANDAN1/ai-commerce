import logging

from app.core.events import subscribe

logger = logging.getLogger(__name__)


async def handle_order_created(payload: dict) -> None:
    logger.info(
        "order.created order_number=%s user_id=%s total=%s",
        payload.get("order_number"),
        payload.get("user_id"),
        payload.get("grand_total"),
    )


async def handle_order_status_changed(payload: dict) -> None:
    logger.info(
        "order.status_changed order_number=%s status=%s by=%s",
        payload.get("order_number"),
        payload.get("status"),
        payload.get("changed_by"),
    )


def register_order_handlers() -> None:
    subscribe("order.created", handle_order_created)
    subscribe("order.status_changed", handle_order_status_changed)
