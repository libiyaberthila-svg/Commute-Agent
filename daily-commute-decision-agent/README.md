# Daily Commute Decision Agent & Autonomous Seat Booking System

A stateful, production-grade **Agentic AI system** for multi-modal daily commute optimization, RAG-grounded transit policy lookups, simulated demo wallet payments, and autonomous seat reservations.

---

## What's New in Version 2.1

1. **Demo Account & Simulated Wallet**:
   - Initialized with **₹5,000** demo funds (`demo_commuter` / `demo123`).
   - Atomic wallet balance deductions with zero double-charge guarantee.
   - Quick top-up (+₹500, +₹1,000, +₹2,000) and persistent transaction ledger in SQLite.
   - Prominently labeled simulated demo funds (never connects to real financial institutions).
2. **Online / Offline Payment Modes**:
   - **ONLINE (Demo Wallet)**: Validates fare, verifies wallet balance, deducts money atomically upon verified booking success, and generates an official receipt. If balance is insufficient, rejects booking with zero deduction.
   - **OFFLINE (Pay Later)**: Does not deduct wallet. Records `OFFLINE_PAY_LATER` and preserves booking reservation in `PENDING_PAYMENT` status.
3. **12 New Executable Agent Tools**:
   - `demo_account_tool`, `wallet_balance_tool`, `wallet_topup_tool`
   - `seat_availability_tool`, `seat_selection_tool`, `fare_validation_tool`
   - `payment_method_tool`, `demo_wallet_payment_tool`, `offline_payment_tool`
   - `transaction_verification_tool`, `booking_verification_tool`, `payment_reconciliation_tool`
   *(Total: 36 registered tools in `ToolRegistry`)*
4. **Live Commute Tracking**:
   - Real-time simulated GPS coordinates, speed (km/h), remaining ETA (minutes), stop-by-stop progress bar, and simulation step advancement.
5. **Dark / Light Theme Switcher**:
   - Toggle seamlessly between dark obsidian glow and clean light themes with persistent user preference.

---

## 34 Registered Agent Tools

### Core Travel & Constraint Tools
- `route_search`, `weather`, `traffic_status`, `transport_search`
- `travel_time`, `fare_comparison`, `budget_check`, `deadline_check`
- `departure_time`, `alternative_route`
- `seat_availability`, `seat_selection`, `booking_eligibility`
- `booking_execution`, `booking_verification`, `booking_status`, `booking_recovery`
- `rag_retrieval`, `user_preferences`, `commute_history`
- `delay_monitor`, `replanning`, `notification`, `decision_explanation`

### Demo Account, Wallet & Payment Tools
- `demo_account_tool` - Retrieve user profile and linked wallet summary
- `wallet_balance_tool` - Fetch real-time simulated wallet balance
- `wallet_topup_tool` - Add demo funds to wallet
- `seat_availability_tool` - Query live coach layout & open seats
- `seat_selection_tool` - Lock best matching seat preference
- `fare_validation_tool` - Validate fares & wallet solvency
- `payment_method_tool` - Configure ONLINE_WALLET vs. OFFLINE_PAY_LATER
- `demo_wallet_payment_tool` - Atomic debit from demo wallet
- `offline_payment_tool` - Record pay-later outstanding dues
- `transaction_verification_tool` - Verify wallet transaction ledger
- `booking_verification_tool` - Verify provider confirmation code & receipt
- `payment_reconciliation_tool` - Reconcile uncertain transaction states

---

## Autonomous Seat Booking & Payment Flow

$$\text{SEARCH} \rightarrow \text{CHECK AVAILABILITY} \rightarrow \text{SELECT SEAT} \rightarrow \text{VALIDATE FARE} \rightarrow \text{CHOOSE PAYMENT MODE} \rightarrow \text{PROCESS} \rightarrow \text{VERIFY} \rightarrow \text{CONFIRM} \rightarrow \text{SAVE}$$

---

## Running the Application

### 1. Launch FastAPI Server & Frontend
```powershell
cd C:\Users\NPRICC\.gemini\antigravity\scratch\daily-commute-decision-agent
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Open Web Dashboard
Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000)

### 3. Run Test Suite
```powershell
pytest -v
```
