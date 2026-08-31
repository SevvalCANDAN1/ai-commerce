"""Late-delivery risk for B2B (Modül 3-style).

The training pipeline lives in ml/src/train_late_delivery.py (sklearn joblib).
The API image does not include scikit-learn, so we score with a transparent
logistic heuristic that uses the same purchase-time features. Swap this
function for the joblib pipeline later without changing the router contract.
"""

import math

from bson import ObjectId
from bson.errors import InvalidId

from app.models.order import Order
from app.models.product import Product
from app.schemas.late_delivery import LateDeliveryRequest, LateDeliveryResponse
from app.services.forecast_service import forecast_ready, resolve_category

THRESHOLD = 0.18
MODEL_NAME = "heuristic_olist_v1"


def _sigmoid(z: float) -> float:
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _risk(probability: float) -> str:
    if probability >= 0.35:
        return "high"
    if probability >= THRESHOLD:
        return "medium"
    return "low"


def score_features(request: LateDeliveryRequest) -> LateDeliveryResponse:
    same_state = request.customer_state.strip().upper() == request.seller_state.strip().upper()
    freight_ratio = request.total_freight / max(request.total_price, 1.0)
    mapped_category = None
    if request.category and forecast_ready():
        mapped_category = resolve_category(request.category)

    # Intercept ≈ Olist late rate (~6–8%). Weights follow the training features:
    # different state, tight SLA, freight-heavy baskets, weak seller history.
    z = -2.55
    drivers: list[str] = []

    if not same_state:
        z += 0.85
        drivers.append("Müşteri ve satıcı farklı bölgede; kargo gecikme riski artar.")
    if request.estimated_days <= 1:
        z += 1.2
        drivers.append("Vaadedilen teslimat 1 gün; gecikme riski yüksek.")
    elif request.estimated_days <= 3:
        z += 0.7
        drivers.append("Vaadedilen teslimat süresi kısa (2–3 gün).")
    elif request.estimated_days <= 5:
        z += 0.25
        drivers.append("Teslimat penceresi dar.")
    if request.seller_prior_late_rate >= 0.12:
        z += 1.1
        drivers.append("Satıcının geçmiş gecikme oranı yüksek.")
    elif request.seller_prior_late_rate >= 0.08:
        z += 0.45
        drivers.append("Satıcının geçmiş gecikme oranı ortalamanın üzerinde.")
    if freight_ratio >= 0.25:
        z += 0.4
        drivers.append("Kargo tutarı ürüne göre yüksek (uzak/ağır sevkiyat).")
    if request.n_sellers > 1:
        z += 0.35 * min(request.n_sellers - 1, 3)
        drivers.append("Sipariş birden fazla satıcıdan toplanıyor.")
    if request.n_items >= 5:
        z += 0.2
        drivers.append("Kalem sayısı fazla; paketleme/sevkiyat karmaşık.")
    if request.payment_installments >= 8:
        z += 0.15
        drivers.append("Uzun taksit; operasyonel olarak daha kırılgan sipariş profili.")
    if mapped_category in {"furniture_decor", "bed_bath_table", "garden_tools"}:
        z += 0.2
        drivers.append("Hacimli kategori; teslimat süresi uzayabilir.")

    if not drivers:
        drivers.append("Profil ortalama Olist siparişine yakın; gecikme olasılığı düşük.")

    probability = round(_sigmoid(z), 4)
    return LateDeliveryResponse(
        late=probability >= THRESHOLD,
        late_probability=probability,
        threshold=THRESHOLD,
        risk=_risk(probability),
        drivers=drivers,
        model=MODEL_NAME,
    )


async def features_from_order(order: Order, *, estimated_days: int = 7) -> LateDeliveryRequest:
    pricing = order.pricing_snapshot
    n_items = sum(item.quantity for item in order.items_snapshot) or 1
    category = None
    if order.items_snapshot:
        try:
            product = await Product.get(ObjectId(order.items_snapshot[0].product_id))
        except InvalidId:
            product = None
        if product and product.categories:
            category = product.categories[0]
    customer_region = (order.address_snapshot.city or order.address_snapshot.country or "SP").strip()
    return LateDeliveryRequest(
        estimated_days=estimated_days,
        customer_state=customer_region[:32],
        seller_state="Istanbul",
        n_items=n_items,
        n_sellers=1,
        total_price=max(pricing.subtotal, 0.01),
        total_freight=max(pricing.shipping_amount, 0.0),
        category=category,
        seller_prior_late_rate=0.07,
        payment_installments=1,
    )


async def get_order_or_404(order_id: str) -> Order:
    try:
        order = await Order.get(ObjectId(order_id))
    except InvalidId:
        order = None
    if order is None:
        raise ValueError(order_id)
    return order


async def score_order(order_id: str, *, estimated_days: int = 7) -> LateDeliveryResponse:
    order = await get_order_or_404(order_id)
    result = score_features(await features_from_order(order, estimated_days=estimated_days))
    result.order_id = str(order.id)
    result.order_number = order.order_number
    return result
