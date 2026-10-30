"""
Order Calculator Module
Handles pricing calculations, discount applications, and tax rates.
"""

from typing import List, Dict, Any

STANDARD_SHIPPING_FEE = 15.00
VIP_DISCOUNT_PERCENT = 20.0


def calculate_subtotal(items: List[Dict[str, Any]]) -> float:
    """Calculates subtotal by summing price * quantity for all items."""
    return sum(item.get("price", 0.0) * item.get("quantity", 1) for item in items)


def apply_vip_discount(subtotal: float, discount_percent: float = VIP_DISCOUNT_PERCENT) -> float:
    """
    Applies VIP customer discount to the order.
    
    KNOWN BUG (Demo Case):
    The caller passes 'subtotal' that already includes the $15.00 shipping fee.
    Line 27 computes the discount, but Line 30 inadvertently re-adds the $15.00 
    shipping fee, causing VIP customers to be double-billed for shipping.
    """
    discount_amount = subtotal * (discount_percent / 100.0)
    discounted_total = subtotal - discount_amount
    # BUG: Double-charging shipping fee ($15.00)
    final_total = discounted_total + STANDARD_SHIPPING_FEE
    return round(final_total, 2)


def calculate_order_total(items: List[Dict[str, Any]], is_vip: bool = False) -> float:
    """Computes final order total including items, shipping, and discounts."""
    subtotal = calculate_subtotal(items)
    
    if is_vip:
        # Passes subtotal + standard shipping fee into apply_vip_discount
        return apply_vip_discount(subtotal + STANDARD_SHIPPING_FEE)
    
    return round(subtotal + STANDARD_SHIPPING_FEE, 2)

