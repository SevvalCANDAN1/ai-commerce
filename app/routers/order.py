from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_store_admin, get_current_user
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.order import OrderListResponse, OrderResponse, OrderStatusUpdateRequest
from app.services.order_service import transition_order_status

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


def _to_order_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=str(order.id),
        order_number=order.order_number,
        user_id=str(order.user_id),
        items_snapshot=order.items_snapshot,
        address_snapshot=order.address_snapshot,
        pricing_snapshot=order.pricing_snapshot,
        status=order.status,
        status_history=order.status_history,
        payment_id=order.payment_id,
        coupon_code=order.coupon_code,
    )


@router.get("/", response_model=OrderListResponse)
async def list_my_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List orders for the authenticated customer."""
    skip = (page - 1) * page_size
    query = Order.find(Order.user_id == current_user.id).sort("-_id")
    total = await query.count()
    orders = await query.skip(skip).limit(page_size).to_list()

    return OrderListResponse(
        items=[_to_order_response(order) for order in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin", response_model=OrderListResponse)
async def list_all_orders_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    _: User = Depends(get_current_store_admin),
):
    """Admin list of all orders with optional status filter."""
    skip = (page - 1) * page_size
    if status_filter is not None:
        query = Order.find(Order.status == status_filter)
    else:
        query = Order.find_all()

    query = query.sort("-_id")
    total = await query.count()
    orders = await query.skip(skip).limit(page_size).to_list()

    return OrderListResponse(
        items=[_to_order_response(order) for order in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single order (owner or store admin)."""
    try:
        object_id = ObjectId(order_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found") from exc

    order = await Order.get(object_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.user_id != current_user.id and current_user.role != UserRole.STORE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return _to_order_response(order)


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    request: OrderStatusUpdateRequest,
    admin: User = Depends(get_current_store_admin),
):
    """Admin-only order status transition with timeline history."""
    try:
        object_id = ObjectId(order_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found") from exc

    order = await Order.get(object_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await transition_order_status(
        order,
        new_status=request.status,
        changed_by=admin.email,
        note=request.note,
    )
    return _to_order_response(order)
