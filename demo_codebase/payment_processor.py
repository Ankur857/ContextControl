"""
Payment Processor Module
Handles charge authorizations and gateway transaction tokenization.
"""

import uuid
import time
from typing import Dict, Any


def create_idempotency_key(order_id: str, attempt_number: int = 1) -> str:
    """Generates a unique idempotency key for payment gateway requests."""
    timestamp = int(time.time())
    return f"idem_{order_id}_{attempt_number}_{timestamp}"


def authorize_charge(
    order_id: str,
    amount_usd: float,
    card_token: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    """
    Submits an authorization request to the payment gateway.
    Returns transaction payload with status and confirmation reference.
    """
    if amount_usd <= 0:
        return {
            "success": False,
            "error": "Authorization amount must be greater than zero.",
            "transaction_id": None,
        }

    if not card_token or not card_token.startswith("tok_"):
        return {
            "success": False,
            "error": "Invalid payment token provided.",
            "transaction_id": None,
        }

    # Simulate successful charge authorization
    transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
    return {
        "success": True,
        "transaction_id": transaction_id,
        "amount_usd": amount_usd,
        "order_id": order_id,
        "idempotency_key": idempotency_key,
        "status": "authorized",
    }

