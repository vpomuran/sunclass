# Sunclass Reservation Monitor

Automatically compares reservations from **Booking.com / Airbnb** against the reservations listed in the **Sunclass Durbuy management portal** and alerts you when something does not match.

Alerts are sent via **Telegram** and always printed to the screen so you can also read them directly.

---

## What it detects

| Situation | What it means |
|---|---|
| 🔴 Only in iCal | A date is blocked on Booking.com or Airbnb but there is no matching reservation in Sunclass |
| 🟠 Only in Sunclass | A reservation exists in the Sunclass portal but is not blocked in any iCal feed |
| 🟡 Date mismatch | The same booking appears in both systems but the check-in or check-out date differs |
| ⚠️ Suspicious match | Dates are close but not identical — needs a manual look |

---

## Requirements

Before you start, make sure you have:

- **Python 3.11 or newer** — download from [python.org](https://www.python.org/downloads/)
  - During installation on Windows, tick **"Add Python to PATH"**
- A **Telegram bot token and chat ID** — see [setup guide below](#setting-up-telegram)
- Your **iCal feed URLs** from Booking.com and/or Airbnb — see [how to find them below](#finding-your-ical-urls)
- Your **Sunclass portal login** (email + password for mijn.sunclassdurbuy.com)

---

## Installation

Open a terminal (on Windows: press `Win + R`, type `cmd`, press Enter).

### Step 1 — Download the project

If you have Git installed:
```
git clone https://github.com/your-repo/sunclass.git
cd sunclass
```

Or download the ZIP from GitHub and unzip it, then navigate into the folder.

### Step 2 — Create a virtual environment

A virtual environment keeps the dependencies isolated from the rest of your system.

**Windows:**
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

**Linux / Mac:**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3 — Install the browser for scraping

The tool uses a headless browser to log in to the Sunclass portal. Install it once:

**Windows:**
```
.venv\Scripts\playwright install chromium
```

**Linux / Mac:**
```
.venv/bin/playwright install chromium
```

> This downloads a ~150 MB browser. It only needs to be done once.

### Step 4 — Create your configuration file

Copy the example file:

**Windows:**
```
copy .env.example .env
```

**Linux / Mac:**
```
cp .env.example .env
```

Now open the `.env` file in any text editor (Notepad is fine) and fill in your details. See the next section for what each line means.

---

## Configuration

Open `.env` in a text editor. It looks like this:

```
ICAL_URLS=https://feeds.booking.com/xxxx.ics,https://www.airbnb.com/calendar/ical/xxxx.ics
ICAL_SOURCES=ical_bookingcom,ical_airbnb
ICAL_LABELS=Booking.com,Airbnb

SUNCLASS_EMAIL=you@example.com
SUNCLASS_PASSWORD=secret
SUNCLASS_LOGIN_URL=https://mijn.sunclassdurbuy.com/login
SUNCLASS_URL=https://mijn.sunclassdurbuy.com/reservations

NOTIFIER_CHANNELS=telegram,stdout

TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789
```

### Required settings

| Setting | What to put here |
|---|---|
| `ICAL_URLS` | Your iCal feed URLs, separated by commas. [How to find them ↓](#finding-your-ical-urls) |
| `ICAL_SOURCES` | Internal labels for each URL — use `ical_bookingcom` and/or `ical_airbnb` |
| `ICAL_LABELS` | Human-readable names shown in alerts, e.g. `Booking.com,Airbnb` |
| `SUNCLASS_EMAIL` | Your login email for mijn.sunclassdurbuy.com |
| `SUNCLASS_PASSWORD` | Your login password for mijn.sunclassdurbuy.com |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token. [How to get one ↓](#setting-up-telegram) |
| `TELEGRAM_CHAT_ID` | The chat or group where alerts are sent. [How to find it ↓](#setting-up-telegram) |

### Optional settings (defaults shown)

| Setting | Default | What it does |
|---|---|---|
| `SUNCLASS_LOGIN_URL` | `https://mijn.sunclassdurbuy.com/login` | Login page URL — change only if the portal moves |
| `SUNCLASS_URL` | `https://mijn.sunclassdurbuy.com/reservations` | Reservations page URL |
| `SCRAPER_TIMEOUT_MS` | `30000` | Browser wait timeout in milliseconds |
| `PROPERTY_LABEL` | _(empty)_ | Label added to alerts to identify the property (useful if you manage multiple) |
| `NOTIFIER_CHANNELS` | `telegram,stdout` | Comma-separated list of alert channels: `telegram` and/or `stdout` |
| `CRITICAL_WINDOW_DAYS` | `30` | Discrepancies with check-in within this many days are treated as critical and re-alerted on every run |
| `DATE_TOLERANCE_DAYS` | `0` | Allow ±N days when fuzzy-matching dates across sources (`0` = exact match only) |
| `ICAL_FETCH_TIMEOUT_SECONDS` | `30` | HTTP timeout when downloading iCal feeds |
| `CANONICAL_TZ` | `Europe/Brussels` | Timezone used to normalise datetime values from iCal feeds |
| `STATE_DB_PATH` | `data/state.db` | Path to the SQLite database that tracks which alerts have been sent |
| `LOG_FILE_PATH` | `data/sunclass.log` | Path to the rotating log file |
| `LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `PLAYWRIGHT_HEADLESS` | `true` | Set to `false` to open a visible browser window (useful for debugging login issues) |
| `PLAYWRIGHT_SLOWMO` | `0` | Slow down each browser action by this many milliseconds |

---

## Running the tool

All commands below assume you are in the project folder.

### First run — establish a baseline

The first time you run the tool, it will mark all existing reservations as already known so you do not get flooded with alerts about bookings that are already in order.

**Windows:**
```
.venv\Scripts\python main.py --bootstrap
```

**Linux / Mac:**
```
.venv/bin/python main.py --bootstrap
```

### Test run — see what it would report without sending any alerts

```
.venv\Scripts\python main.py --dry-run
```

This is safe to run any time. It connects to both systems, compares the reservations, and prints any discrepancies to the screen — but does **not** send a Telegram message.

### Normal run

```
.venv\Scripts\python main.py
```

The tool will:
1. Fetch blocked dates from your iCal feeds
2. Log in to the Sunclass portal and read the reservation table
3. Compare the two lists
4. Print results to the screen
5. Send a Telegram message for any new discrepancies

### Running on a schedule (automated)

**Windows — Task Scheduler:**
1. Open Task Scheduler → Create Basic Task
2. Set trigger: Daily, repeat every 6 hours
3. Action: Start a program
   - Program: `C:\path\to\sunclass\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\path\to\sunclass`

**Linux — cron:**
```
crontab -e
```
Add this line (runs every 6 hours):
```
0 */6 * * * cd /home/user/sunclass && .venv/bin/python main.py >> data/cron.log 2>&1
```

---

## Command reference

| Command | What it does |
|---|---|
| `python main.py` | Normal run — compare and alert |
| `python main.py --dry-run` | Compare and print results, do not send alerts |
| `python main.py --bootstrap` | Mark all current bookings as baseline (run once on setup) |
| `python main.py --log-level DEBUG` | Verbose output, useful for troubleshooting |
| `python main.py --env-file /path/to/.env` | Use a different configuration file |
| `python main.py --debug-browser` | Open a visible browser window and save screenshots to `data/` — useful for diagnosing login failures |

---

## Finding your iCal URLs

### Booking.com

1. Log in to the Booking.com extranet
2. Go to **Calendar** → **Sync your calendar**
3. Copy the **Export** URL — it ends in `.ics`

### Airbnb

1. Log in to Airbnb and go to your listing
2. Go to **Calendar** → **Availability settings** → **Sync calendars**
3. Copy the **Export calendar** link — it ends in `.ics`

---

## Setting up Telegram

### Create a bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you — it looks like `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`
4. Paste it as `TELEGRAM_BOT_TOKEN` in your `.env` file

### Get your chat ID

**Option A — personal chat:**
1. Search for **@userinfobot** on Telegram
2. Send it any message
3. It replies with your ID — paste it as `TELEGRAM_CHAT_ID`

**Option B — a group chat:**
1. Add your bot to the group
2. Send a message in the group
3. Open this URL in your browser (replace `TOKEN` with your token):
   `https://api.telegram.org/botTOKEN/getUpdates`
4. Find `"chat":{"id":` in the response — that negative number is your `TELEGRAM_CHAT_ID`

---

## Troubleshooting

**"No module named sunclass"**
You are running Python from outside the virtual environment. Make sure to use `.venv\Scripts\python main.py` (Windows) or `.venv/bin/python main.py` (Linux).

**"SUNCLASS_EMAIL is not set" or similar config error**
Your `.env` file is missing or has a typo. Make sure the file is named exactly `.env` (not `.env.txt`) and is in the same folder as `main.py`.

**"Sunclass scrape failed" / login failure**
The tool could not log in to the Sunclass portal. Check `SUNCLASS_EMAIL`, `SUNCLASS_PASSWORD`, and `SUNCLASS_LOGIN_URL` in `.env`. Run with `--debug-browser` to open a visible browser window and see screenshots saved to `data/` that show exactly where it fails.

**"Failed to fetch iCal"**
One of your iCal URLs may have changed or expired. Log in to Booking.com or Airbnb and copy a fresh URL.

**The tool runs but reports no discrepancies when there should be some**
Run `--dry-run --log-level DEBUG` to see exactly how many reservations were found from each source. If one source returns 0 reservations, that is where to investigate.

---

## File structure (for reference)

```
sunclass/
├── main.py              ← entry point, run this
├── .env                 ← your private configuration (never share this)
├── .env.example         ← configuration template
├── requirements.txt     ← Python dependencies
├── src/sunclass/        ← application source code
├── tests/               ← automated tests
└── data/                ← runtime data: logs, state database, debug screenshots
```
