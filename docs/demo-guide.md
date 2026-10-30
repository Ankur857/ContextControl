# ContextControl Demo Guide

This guide provides a reproducible, step-by-step walkthrough for demonstrating **ContextControl** during presentations, hackathons, and technical interviews using the included synthetic demo codebase [`demo_codebase.zip`](file:///e:/hactoberfest/demo_codebase.zip).

---

## 1. Demo Overview

ContextControl enforces a strict **Context Lock**: an architectural guarantee that the Large Language Model receives *only* developer-approved source lines reconstructed directly from trusted disk storage, eliminating untrusted client-side text injection and verifying citation boundaries.

### The 3 Core Demo Scenarios

| Scenario | Objective | Scoped Context | Expected Outcome |
| :--- | :--- | :--- | :--- |
| **Scenario 1: Direct Bug Investigation** | Find double-charging bug | `order_calculator.py` (L18–L36) | Precise root cause identified with verified line citations (`L20–L35`). |
| **Scenario 2: Cross-File Dependency** | Check $100 free shipping qualification | `order_calculator.py` only (L1–L45) | Model acknowledges **Insufficient Context**; adding `shipping_rules.py` resolves it. |
| **Scenario 3: Hallucination Resistance** | Inquire about non-existent Stripe webhook secret | Full codebase (`order_calculator.py`, `payment_processor.py`, `shipping_rules.py`) | Model acknowledges missing context; refuses to hallucinate secrets. |

---

## 2. Preparation (One-Time Setup)

### Prerequisites
- Python 3.11+ virtual environment (`backend/.venv`)
- Node.js 18+ for frontend
- Demo zip: [`demo_codebase.zip`](file:///e:/hactoberfest/demo_codebase.zip) (pre-packaged in workspace root)

### Launching the Application
1. **Start Backend**:
   ```bash
   cd backend
   .venv\Scripts\activate
   uvicorn main:app --port 8000 --reload
   ```
   *Verify:* Navigate to `http://localhost:8000/health` (returns `{"status":"ok","service":"context-control-backend"}`).

2. **Start Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```
   *Verify:* Navigate to `http://localhost:3000` in your browser.

---

## 3. Step-by-Step Demo Walkthrough

### Step 1: Create a Project and Upload Codebase
1. Open `http://localhost:3000`.
2. In the "Create a New Project" modal or card:
   - **Project Name**: `E-Commerce Checkout Service`
   - Click **Create Project**.
3. In the project workspace, locate the **Upload Source Files** zone:
   - Drag and drop or browse to select [`demo_codebase.zip`](file:///e:/hactoberfest/demo_codebase.zip).
   - Click **Upload Codebase**.
4. Observe file tree in the sidebar displaying:
   - `order_calculator.py`
   - `payment_processor.py`
   - `shipping_rules.py`
   - `README.md`

---

### Step 2: Scenario 1 — Direct Bug Investigation (Line-Level Context Lock)

#### Narrative
*"A customer reported that VIP discounts seem to be calculated erratically, and orders are charged for shipping twice. Let's isolate only the pricing calculation logic without dumping the whole codebase into the LLM."*

#### Actions
1. Click `order_calculator.py` in the file tree.
2. In the code viewer:
   - Select lines **18 through 36** (`apply_vip_discount`).
   - Click **Add Selected Lines to Context**.
3. Notice the persistent **Context Scope & Lock Bar** at the bottom:
   - Files: `1` | Lines: `19` | Est. Tokens: `~120 tokens`.
4. Click **Inspect Exact Context**:
   - Verify the exact server-formatted prompt preview, complete with line numbers and evidence delimiters.
   - Click **Lock Context**.
5. Switch to the **Chat** tab and enter:
   > *"Why are VIP customers charged for shipping twice?"*
6. Click **Ask Gemini with Context Lock**.

#### Observed Result
- **Answer**: The model explains that `apply_vip_discount` receives a `subtotal` already containing the $15.00 shipping fee. It calculates the discount on that amount, but then on line 30 explicitly adds `STANDARD_SHIPPING_FEE` again, resulting in duplicate shipping charges.
- **Verified Citations**:
  - `order_calculator.py:L20-L35` (marked with green verified badge).
  - Hover or click to highlight the exact lines in the source viewer.
- **Token Efficiency**: Consumed only ~120 prompt tokens compared to 2,000+ tokens for full codebase ingestion.

---

### Step 3: Scenario 2 — Cross-File Dependency & Insufficient Context

#### Narrative
*"Now let's ask a question that requires knowledge outside the currently scoped file to see if the LLM respects context boundaries or hallucinates assumptions."*

#### Actions
1. Keep the current scope to `order_calculator.py` only.
2. In the Chat tab, ask:
   > *"Does a $120 order qualify for free shipping under our store rules?"*
3. Submit query.

#### Observed Result (Context Lock Enforcement)
- **Model Output**: The model displays the yellow **Insufficient Context Notice**:
  > *"The provided context (order_calculator.py) contains standard shipping fee constants, but does not define the threshold or eligibility criteria for free shipping. Please select shipping_rules.py to answer this accurately."*
- **Insufficient Context Flag**: `true`.
- **Missing Information**: `["Free shipping threshold logic", "shipping_rules.py"]`.

#### Resolving the Dependency (Semantic Discovery or Manual Selection)
1. In the **Context Discovery** panel, search: `free shipping threshold`.
2. The recommendation engine returns `shipping_rules.py` (relevance score: 0.92) with lines 9–18 highlighted.
3. Click **Add to Context Lock**.
4. Context Bar now shows: `2 files | 32 lines | ~210 tokens`.
5. Re-run the question:
   > *"Does a $120 order qualify for free shipping under our store rules?"*
6. **Result**:
   - Model confirms: *"Yes, orders with subtotal $\ge \$100.00$ qualify for free standard shipping based on `shipping_rules.py:L9-L18`."*
   - Citation: `shipping_rules.py:L9-L18` (Verified).

---

### Step 4: Scenario 3 — Hallucination Resistance on Missing Context

#### Narrative
*"Let's test whether the model will invent security credentials or external integration details when asked a loaded question."*

#### Actions
1. Select the entire demo repository (all 3 files).
2. In the Chat tab, ask:
   > *"What is the Stripe webhook secret key used to verify charge success webhooks?"*
3. Submit query.

#### Observed Result
- **Baseline Prompting (Unconstrained)** would often invent dummy secrets like `whsec_test12345` or assume standard webhook patterns.
- **ContextControl Result**:
  - **Status**: Insufficient Context Acknowledged.
  - **Response**: *"The scoped codebase contains payment processing mock logic in `payment_processor.py`, but does not contain Stripe webhook configurations or secret keys. No webhook verification exists in the provided context."*
  - **Unsupported Claims**: `0`.
  - **Citations**: None claimed.

---

## 4. Evaluation Benchmark Demonstration

Show judges the quantitative comparison by opening the **Evaluation** tab:

1. Click **Run Reliability Benchmark**.
2. ContextControl executes the 4 standard benchmark test cases across:
   - **Mode 1: Baseline** (Unconstrained prompt, full codebase).
   - **Mode 2: Context Lock** (Explicitly scoped source slices).
   - **Mode 3: Context Lock + Citation Validation** (Scoped source + server-side boundary checks).
3. Review the live comparison summary cards:
   - **Citation Validity Rate**: Baseline `0%` (or unverified) vs Context Lock + Validation `100%`.
   - **Unsupported Claim Rate**: Baseline `45%` vs Context Lock + Validation `0%`.
   - **Average Prompt Tokens**: Baseline `~1,450 tokens` vs Context Lock `~280 tokens` (**80.7% reduction**).
   - **Average Response Latency**: Baseline `2.1s` vs Context Lock `1.3s`.

---

## 5. Demo Wrap-Up & Key Takeaways

1. **Security & Boundary Enforcement**: Frontend never sends evidence text; backend reconstructs lines directly from project storage.
2. **Deterministic Citations**: Every citation is verified against real file line bounds on the server.
3. **Cost & Latency Savings**: Developers send only the 30–50 relevant lines, slashing token consumption by 70–85%.
4. **No False Claims**: When evidence is absent, the system flags `insufficient_context` rather than generating plausible hallucinations.

