# 🚐 Campus Shuttle Bot (Vercel Edition)

A Telegram bot for managing student shuttle rides within Covenant University campus. Built with Python, deployed on Vercel in minutes.

## ✨ Features

- 🎓 **Student Booking**: Browse available shuttles, pick a route, and request a ride
- 🚐 **Driver Dashboard**: Go online/offline, accept/reject rides, mark trips complete
- ⏱️ **5-Minute Timeout**: Requests auto-expire if the driver doesn't respond
- 🛡️ **Admin Approval**: Drivers require admin approval before going active
- 📍 **14 Campus Locations**: All halls of residence + academic buildings

## 🗂️ Project Structure

```
campus-shuttle-bot/
├── api/
│   ├── webhook.py     ← All bot logic (receives Telegram messages)
│   ├── cron.py        ← Expires stale ride requests
│   └── setup.py       ← One-time webhook registration
├── lib/
│   ├── db.py          ← Database queries
│   └── keyboards.py   ← Telegram button builders
├── schema.sql         ← Database tables
├── vercel.json        ← Vercel config
├── requirements.txt
└── .env.example
```

## 🚀 Deployment (Step-by-Step)

### 1. Get a Bot Token
- Open Telegram, message [@BotFather](https://t.me/botfather)
- Send `/newbot`, follow the prompts, and copy the token

### 2. Create a Free Database
- Go to [neon.tech](https://neon.tech) and sign up (free)
- Create a new project → copy the **pooled connection string**
- Run the contents of `schema.sql` in the Neon SQL Editor

### 3. Deploy to Vercel
- Push this code to a GitHub repository
- Go to [vercel.com](https://vercel.com) → "Add New Project" → Import your repo
- Add these **Environment Variables** in Vercel dashboard:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your Telegram bot token |
| `DATABASE_URL` | Your Neon pooled connection string |
| `ADMIN_CHAT_IDS` | Your Telegram user ID (comma-separated for multiple) |

- Click **Deploy**

### 4. Register the Webhook
- After deployment, visit: `https://your-app.vercel.app/api/setup`
- You should see: ✅ Webhook registered

### 5. Set Up Expiry Pinger (Important!)
Vercel free-tier cron jobs only run once per day. To make the 5-minute timeout work properly, set up a free pinger:

- Go to [cron-job.org](https://cron-job.org) (free account)
- Create a new cron job:
  - **URL**: `https://your-app.vercel.app/api/cron`
  - **Schedule**: Every 1 minute
- This pings the expiry endpoint regularly so stale rides get cleaned up

> **Note**: Even without the pinger, stale accepts are blocked. If a driver clicks "Accept" after the 5 minutes, the bot will reject it automatically (lazy expiry).

### 6. Test It
- Open your bot in Telegram and send `/start`
- Register as a student, then try `/book`

## 🤖 Bot Commands

| Command | Role | Description |
|---|---|---|
| `/start` | All | Register and get started |
| `/book` | Student | Request a new ride |
| `/cancel` | Student | Cancel your current ride |
| `/mystatus` | Student | Check your ride status |
| `/driver` | Driver | Open your shuttle dashboard |
| `/help` | All | Show all commands |

## 🔧 How to Get Your Telegram User ID
Send `/start` to [@userinfobot](https://t.me/userinfobot) on Telegram. It will reply with your numeric user ID. Use this as `ADMIN_CHAT_IDS`.

## 📄 License
MIT
