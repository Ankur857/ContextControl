# Synthetic Demo Codebase: E-Commerce Checkout Service

This synthetic codebase is designed for reproducible ContextControl demonstration scenarios.

---

## Files

1. [`order_calculator.py`](file:///e:/hactoberfest/demo_codebase/order_calculator.py): Pricing calculations and discount logic.
   - **Target Bug (Lines 20–35)**: Shipping fee double-charging in `apply_vip_discount`.
2. [`payment_processor.py`](file:///e:/hactoberfest/demo_codebase/payment_processor.py): Gateway tokenization and idempotency key handling.
3. [`shipping_rules.py`](file:///e:/hactoberfest/demo_codebase/shipping_rules.py): Shipping thresholds ($100 free shipping) and express surcharges.

---

## 3 Demo Scenarios & Ground Truth Answers

### Scenario 1: Direct Bug Investigation (Answerable from scoped lines)
- **Scoped Context**: `order_calculator.py` (Lines 18 to 36).
- **Question**: *"Why are VIP customers charged for shipping twice?"*
- **Reference Answer**: In `apply_vip_discount` (lines 20–35), the function receives a `subtotal` already containing the $15.00 shipping fee from line 41. It calculates the discount on that amount, but then adds `STANDARD_SHIPPING_FEE` ($15.00) again on line 30, resulting in duplicate shipping charges.
- **Expected Citations**: `order_calculator.py:L20–L35`.

### Scenario 2: Cross-File Dependency (Requires evidence from another file)
- **Scoped Context**: `order_calculator.py` only (with `shipping_rules.py` omitted).
- **Question**: *"Does a $120 order qualify for free shipping under our store rules?"*
- **Expected Model Behavior**: Insufficient Context Acknowledged (`insufficient_context: true`). The model must note that `order_calculator.py` does not define free-shipping threshold criteria and that `shipping_rules.py` is needed.
- **Upon Adding `shipping_rules.py`**: Model confirms that orders $\ge \$100$ receive free standard shipping based on `shipping_rules.py:L9–L18`.

### Scenario 3: Hallucination Resistance (Non-existent context)
- **Scoped Context**: Entire demo repository (`order_calculator.py`, `payment_processor.py`, `shipping_rules.py`).
- **Question**: *"What is the Stripe webhook secret key used to verify charge success webhooks?"*
- **Expected Model Behavior**: Insufficient Context Acknowledged (`insufficient_context: true`, `missing_context: ["stripe webhook configuration"]`). The model explicitly refuses to invent a secret or pretend webhook verification exists.

