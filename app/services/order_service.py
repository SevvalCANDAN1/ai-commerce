from datetime import datetime, timedelta, timezone
import random
import secrets
import string

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import AsyncMongoClient

from app.config import settings
from app.core.events import publish
from app.database import get_mongo_client
from app.models.cart import Cart
from app.models.checkout_session import CheckoutSession
from app.models.idempotency import IdempotencyRecord, StockReservation
from app.models.order import (
    ALLOWED_ORDER_TRANSITIONS,
    AddressSnapshot,
    Order,
    OrderItemSnapshot,
    OrderStatus,
    PricingSnapshot,
    StatusHistoryEntry,
)
from app.models.product import Product
from app.models.user import Address, User
from app.services.cart_service import build_cart_response, get_user_cart, validate_cart_product
from app.services.cart_service import get_variant_or_404
from app.services.pricing_service import calculate_cart_pricing, get_unit_price


def generate_order_number() -> str:
    date_part = datetime.now(timezone.utc).strftime("%m%d")
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"ORD-{date_part}-{suffix}"


def snapshot_address(address: Address) -> AddressSnapshot:
    return AddressSnapshot(
        title=address.title,
        city=address.city,
        country=address.country,
        full_address=address.full_address,
        zip_code=address.zip_code,
    )


async def _reserved_quantity(
    product_id: ObjectId,
    variant_sku: str,
    exclude_session_id: ObjectId | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    reservations = await StockReservation.find(
        StockReservation.product_id == product_id,
        StockReservation.variant_sku == variant_sku,
        StockReservation.released == False,
        StockReservation.expires_at > now,
    ).to_list()

    total = 0
    for reservation in reservations:
        if exclude_session_id and reservation.checkout_session_id == exclude_session_id:
            continue
        total += reservation.quantity
    return total


async def _available_stock(product: Product, variant_sku: str, exclude_session_id: ObjectId | None = None) -> int:
    variant = get_variant_or_404(product, variant_sku)
    reserved = await _reserved_quantity(product.id, variant_sku, exclude_session_id)
    return max(variant.stock - reserved, 0)


async def create_checkout_preview(user: User, address_index: int, coupon_code: str | None) -> CheckoutSession:
    if address_index < 0 or address_index >= len(user.addresses):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid address index")

    cart = await get_user_cart(user)
    if not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    cart_response = await build_cart_response(cart, coupon_code=coupon_code)
    if not cart_response.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid cart items")

    items_snapshot: list[OrderItemSnapshot] = []
    for line in cart_response.items:
        product = await validate_cart_product(line.product_id)
        available = await _available_stock(product, line.variant_sku)
        if line.quantity > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for {line.variant_sku}. Only {available} available.",
            )
        items_snapshot.append(
            OrderItemSnapshot(
                product_id=line.product_id,
                variant_sku=line.variant_sku,
                product_name=line.product_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        )

    pricing_snapshot = PricingSnapshot(
        subtotal=cart_response.subtotal,
        tax_amount=cart_response.tax_amount,
        shipping_amount=cart_response.shipping_amount,
        discount_amount=cart_response.discount_amount,
        grand_total=cart_response.grand_total,
    )

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.checkout_session_minutes)
    session = CheckoutSession(
        user_id=user.id,
        address_snapshot=snapshot_address(user.addresses[address_index]),
        items_snapshot=items_snapshot,
        pricing_snapshot=pricing_snapshot,
        coupon_code=coupon_code,
        expires_at=expires_at,
        consumed=False,
    )
    await session.insert()

    reservation_expires = datetime.now(timezone.utc) + timedelta(minutes=settings.stock_reservation_minutes)
    for item in items_snapshot:
        await StockReservation(
            user_id=user.id,
            checkout_session_id=session.id,
            product_id=ObjectId(item.product_id),
            variant_sku=item.variant_sku,
            quantity=item.quantity,
            expires_at=reservation_expires,
        ).insert()

    return session


async def get_checkout_session_for_user(session_id: str, user: User) -> CheckoutSession:
    try:
        object_id = ObjectId(session_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found") from exc

    session = await CheckoutSession.get(object_id)
    if (
        session is None
        or session.user_id != user.id
        or session.consumed
        or session.expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout session not found")
    return session


def validate_status_transition(current: OrderStatus, new_status: OrderStatus) -> None:
    allowed = ALLOWED_ORDER_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {current.value} to {new_status.value}",
        )


async def _decrement_inventory(items: list[OrderItemSnapshot], session) -> None:
    for item in items:
        product = await Product.get(ObjectId(item.product_id), session=session)
        if product is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product missing during fulfillment")

        updated = False
        for variant in product.variants:
            if variant.sku == item.variant_sku:
                if variant.stock < item.quantity:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock")
                variant.stock -= item.quantity
                updated = True
                break

        if not updated:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variant missing during fulfillment")

        product.total_stock = sum(v.stock for v in product.variants)
        await product.save(session=session)


async def finalize_paid_order(
    checkout_session: CheckoutSession,
    payment_id: str,
    mongo_client: AsyncMongoClient | None = None,
) -> Order:
    client = mongo_client or get_mongo_client()
    order: Order | None = None
    async with await client.start_session() as session:
        async with session.start_transaction():
            checkout_session.consumed = True
            await checkout_session.save(session=session)

            cart = await Cart.find_one(Cart.user_id == checkout_session.user_id, session=session)
            if cart is not None:
                cart.items = []
                await cart.save(session=session)

            await _decrement_inventory(checkout_session.items_snapshot, session=session)

            reservations = await StockReservation.find(
                StockReservation.checkout_session_id == checkout_session.id,
                StockReservation.released == False,
                session=session,
            ).to_list()
            for reservation in reservations:
                reservation.released = True
                await reservation.save(session=session)

            now = datetime.now(timezone.utc)
            order = Order(
                order_number=generate_order_number(),
                user_id=checkout_session.user_id,
                items_snapshot=checkout_session.items_snapshot,
                address_snapshot=checkout_session.address_snapshot,
                pricing_snapshot=checkout_session.pricing_snapshot,
                status=OrderStatus.CONFIRMED,
                status_history=[
                    StatusHistoryEntry(
                        status=OrderStatus.CONFIRMED,
                        changed_at=now,
                        changed_by="system",
                        note="Payment captured",
                    )
                ],
                payment_id=payment_id,
                coupon_code=checkout_session.coupon_code,
            )
            await order.insert(session=session)

    if order is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order creation failed")

    await publish(
        "order.created",
        {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "user_id": str(order.user_id),
            "grand_total": order.pricing_snapshot.grand_total,
        },
    )
    return order


async def transition_order_status(
    order: Order,
    new_status: OrderStatus,
    changed_by: str,
    note: str | None = None,
) -> Order:
    validate_status_transition(order.status, new_status)
    order.status = new_status
    order.status_history.append(
        StatusHistoryEntry(
            status=new_status,
            changed_at=datetime.now(timezone.utc),
            changed_by=changed_by,
            note=note,
        )
    )
    await order.save()
    await publish(
        "order.status_changed",
        {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "status": new_status.value,
            "changed_by": changed_by,
        },
    )
    return order


async def get_idempotent_response(key: str) -> IdempotencyRecord | None:
    return await IdempotencyRecord.find_one(IdempotencyRecord.key == key)


async def store_idempotent_response(key: str, endpoint: str, response_body: dict, status_code: int) -> None:
    await IdempotencyRecord(
        key=key,
        endpoint=endpoint,
        response_body=response_body,
        status_code=status_code,
        created_at=datetime.now(timezone.utc),
    ).insert()


def simulate_mock_payment_failure() -> str | None:
    if random.random() < settings.mock_payment_failure_rate:
        return random.choice(["INSUFFICIENT_FUNDS", "CONNECTION_ERROR"])
    return None
