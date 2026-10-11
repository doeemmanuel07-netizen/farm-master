"""
Shared Product Catalogue / InputOrder response-building -- single call site
for both routers/vendor.py (own catalogue, incoming orders) and
routers/farmer.py (browsing the catalogue, own placed orders), same
"integrate, don't duplicate" pattern as formula.py/dispatch.py/
reconciliation.py.
"""

from sqlalchemy.orm import Session

from .models import User, Product, InputOrder, InputOrderLine, DispatchJob
from .marketplace import line_label
from .schemas import ProductResponse, InputOrderResponse, InputOrderLineResponse


def product_view(product: Product, vendor_name: str) -> ProductResponse:
    return ProductResponse(
        id=product.id, vendor_id=product.vendor_id, vendor_name=vendor_name,
        name=product.name, category=product.category, formula_input_type=product.formula_input_type,
        unit=product.unit, unit_price=product.unit_price, stock_qty=product.stock_qty,
    )


def order_view(order: InputOrder, db: Session) -> InputOrderResponse:
    farmer = db.query(User).filter(User.id == order.farmer_id).first()
    vendor = db.query(User).filter(User.id == order.vendor_id).first()
    lines = db.query(InputOrderLine).filter(InputOrderLine.input_order_id == order.id).all()
    line_views = []
    for line in lines:
        name, unit, kind = line_label(db, line)
        line_views.append(InputOrderLineResponse(
            product_id=line.product_id,
            product_name=name,
            quantity=line.quantity,
            unit=unit,
            unit_price=line.unit_price,
            line_total=round(line.quantity * line.unit_price, 2),
            listing_id=line.listing_id, kind=kind, requested_date=line.requested_date,
        ))
    job = db.query(DispatchJob).filter(DispatchJob.input_order_id == order.id).first()
    return InputOrderResponse(
        id=order.id,
        farmer_name=farmer.full_name,
        vendor_id=order.vendor_id,
        vendor_name=vendor.organisation_name or vendor.full_name,
        status=order.status,
        total_cost=order.total_cost,
        lines=line_views,
        dispatch_status=job.status if job else None,
        created_at=order.created_at,
        checkout_ref=order.checkout_ref,
    )
