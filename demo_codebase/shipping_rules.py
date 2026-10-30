"""
Shipping Rules Module
Determines shipping tiers, delivery thresholds, and free-shipping eligibility.
"""

FREE_SHIPPING_THRESHOLD_USD = 100.00
EXPRESS_SURCHARGE_USD = 25.00


def is_eligible_for_free_shipping(items_total_usd: float) -> bool:
    """Checks if order total meets or exceeds the $100 free-shipping threshold."""
    return items_total_usd >= FREE_SHIPPING_THRESHOLD_USD


def get_applicable_shipping_rate(
    items_total_usd: float,
    is_express: bool = False,
) -> float:
    """
    Returns shipping charge:
    - Standard shipping ($15.00) is waived if items total >= $100.00.
    - Express surcharge ($25.00) always applies if requested.
    """
    base_shipping = 0.0 if is_eligible_for_free_shipping(items_total_usd) else 15.00
    
    if is_express:
        return base_shipping + EXPRESS_SURCHARGE_USD
    
    return base_shipping

