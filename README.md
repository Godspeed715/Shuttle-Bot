# 🚐 Campus Shuttle Bot (v2.0)

A Telegram bot for managing student shuttle rides within Covenant University campus, with dynamic passenger pricing, Paystack online transfers, driver wallets with bank withdrawals, bidirectional route pricing, and cash remittance tracking.

---

## ✨ Features in v2.0

- 🎓 **Student Booking**: 
  - Select pickup & destination
  - **Passenger count selection** (1 to 4/7+ seats, dynamically calculates total fare)
  - **Payment Options**: Cash on arrival or Online Transfer (via Paystack)
  - Real-time fare breakdown & Paystack instant checkout link
- 🚐 **Driver Dashboard & Wallet**:
  - Vehicle type onboarding: **Car (4 seats)** or **Siena (7 seats)**
  - Go online/offline, update current location, complete trips
  - **/wallet Dashboard**: Check balance, lifetime earnings, cash commission debt, and net withdrawable funds
  - **Bank Linking**: Link NUBAN bank account with Paystack name verification
  - **Bank Withdrawals**: Automated payouts directly to Nigerian bank accounts via Paystack Transfers API
- 💰 **Bidirectional Route Pricing Matrix**:
  - Configurable default fare (default: ₦500 per passenger)
  - Configurable platform commission (default: 15%)
  - Custom route price overrides stored once and applied automatically in both directions
- 📊 **Cash Remittances & Admin Panel**:
  - Automatic debt tracking for drivers completing cash rides
  - Admin panel (`/admin`) to view drivers with outstanding cash commissions
  - One-tap button to mark cash remittances as collected
  - In-bot Route Price Manager to add, edit, or delete custom route fares without touching code
- ⏱️ **5-Minute Timeout**: Pending ride requests auto-expire if the driver does not respond
- 🛡️ **Admin Approval**: Drivers require admin approval before going online

---

## 🗂️ Project Structure

```
Shuttle-Bot/
├── api/
│   ├── cron.py               ← Auto-expires stale ride requests
│   ├── paystack_webhook.py   ← Paystack charge.success & transfer webhooks
│   └── setup.py              ← Telegram webhook registration
├── bot/
│   ├── handlers/
│   │   ├── admin.py          ← /admin panel, remittances, route pricing
│   │   ├── driver.py         ← /driver dashboard, trip lifecycle, approvals
│   │   ├── start.py          ← /start & registration FSM (student/driver + vehicle type)
│   │   ├── student.py        ← /book (5-step booking flow), /cancel, /mystatus
│   │   └── wallet.py         ← /wallet, bank linking, withdrawal FSM
│   └── keyboards/
│       ├── admin.py          ← Admin panel & route pricing keyboards
│       ├── common.py         ← Role & vehicle type keyboards
│       ├── driver.py         ← Dashboard, location, wallet & bank keyboards
│       └── student.py        ← Locations, passenger count, payment method
├── functions/
│   ├── db.py                 ← All PostgreSQL queries (wallets, routes, rides)
│   ├── paystack.py           ← Paystack REST API wrapper (charges, transfers, banks)
│   └── pricing.py            ← Unit fare calculation & platform cut logic
├── migrations/
│   └── v2_schema.sql         ← Database migration script for v2.0
├── config.py                 ← Centralized configuration & environment variables
├── main.py                   ← Flask application & Telegram update dispatcher
├── vercel.json               ← Vercel serverless routing configuration
├── schema.sql                ← Base database schema
├── requirements.txt
└── .env
```

---

## 🚀 Setup & Migration

### 1. Database Migration (Neon PostgreSQL)
Before running v2, run the migration script in your **Neon SQL Editor**:
- Open [neon.tech](https://neon.tech) → SQL Editor
- Copy and run the contents of [`migrations/v2_schema.sql`](file:///C:/Users/chimz/Github%20Repsoitories/Shuttle-Bot/migrations/v2_schema.sql)
- This adds the `route_prices`, `driver_wallets`, `wallet_transactions` tables and payment columns to `ride_requests`.

### 2. Environment Variables
Add or update these variables in `.env` (and Vercel dashboard):

| Variable | Description | Example / Default |
|---|---|---|
| `BOT_TOKEN` | Telegram Bot Token from @BotFather | `8055334578:...` |
| `DATABASE_URL` | Neon pooled PostgreSQL connection string | `postgresql://...` |
| `ADMIN_CHAT_IDS` | Telegram numeric user ID(s) (comma-separated) | `7831722967` |
| `PAYSTACK_SECRET_KEY` | Paystack Secret Key | `sk_test_...` or `sk_live_...` |
| `PAYSTACK_PUBLIC_KEY` | Paystack Public Key | `pk_test_...` or `pk_live_...` |
| `DEFAULT_FARE_NAIRA` | Base per-passenger fare in Naira | `500` |
| `PLATFORM_CUT_PCT` | Platform commission percentage | `0.15` (15%) |
| `REQUEST_TIMEOUT_SECONDS` | Timeout before ride request expires | `300` (5 minutes) |

### 3. Paystack Webhook Configuration
In your [Paystack Dashboard](https://dashboard.paystack.com/#/settings/developer):
- Set **Webhook URL** to: `https://your-app.vercel.app/api/paystack/webhook`

---

## 🤖 Bot Commands

| Command | Role | Description |
|---|---|---|
| `/start` | All | Register as student or driver (with vehicle type) |
| `/book` | Student | 5-step booking flow (pickups, passengers, cash/transfer) |
| `/cancel` | Student | Cancel active pending or accepted ride |
| `/mystatus` | Student | View current ride details, payment status & driver info |
| `/driver` | Driver | Control panel (online/offline, location, complete trip) |
| `/wallet` | Driver | View earnings, cash debt, link bank & withdraw funds |
| `/admin` | Admin | Cash remittance ledger & bidirectional route prices manager |
| `/help` | All | Show command guide |

---

## 📄 License
MIT
