# Booking.com Extranet Bot

A CLI tool for automating Booking.com partner extranet operations — downloading reservations, managing rates, and handling guest messages.

Forked from [acekavi/booking-extranet-bot](https://github.com/acekavi/booking-extranet-bot) with the goal of building a reliable, agent-friendly tool that can be used by AI orchestrators like [OpenClaw](https://github.com/openclaw), [Nanobot](https://github.com/nanobot-ai), and similar agent frameworks. Every command outputs structured JSON to stdout, making it easy for any agent or script to parse and act on the results.

## What changed from the original

- **Real Chrome instead of Playwright's Chromium** — the original used Playwright's bundled browser, which triggers Booking.com's CAPTCHA/bot detection. We connect to your actual Chrome via CDP.
- **Updated login flow** — Booking.com changed their 2FA to a verification method selection page (SMS, Pulse app, Phone call). The original bot's selectors were broken.
- **CLI with JSON output** — replaced the script-based approach with a proper CLI that agents can call via subprocess.
- **Reservation scraping** — Booking.com's download button is unreliable via CDP, so we scrape the table directly and build the Excel file ourselves. Output matches Booking.com's native export format.
- **Multi-property support** — works with group accounts managing multiple properties.

## Prerequisites

- Python 3.8+
- Google Chrome installed (not Chromium, not Brave — the real Chrome)
- Booking.com partner account with admin access

## Installation

```bash
git clone https://github.com/matsei-ruka/booking-extranet-bot.git
cd booking-extranet-bot

python3 -m venv venv
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

No need to run `playwright install` — we use your real Chrome, not Playwright's browser.

## Configuration

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

```env
BOOKING_USERNAME=your_login_name
BOOKING_PASSWORD=your_password
BOOKING_HOTEL_ID=your_default_hotel_id   # optional
```

## CLI Usage

All commands output JSON to stdout. Logs go to stderr and `booking_bot.log`.

### List properties

```bash
python cli.py list-properties
```

```json
{
  "status": "success",
  "action": "list-properties",
  "count": 3,
  "properties": [
    {"hotel_id": "10353912", "name": "Property A", "unread_messages": 4},
    {"hotel_id": "10353978", "name": "Property B", "unread_messages": 2},
    {"hotel_id": "13616005", "name": "Property C", "unread_messages": 0}
  ]
}
```

### Download reservations

```bash
# As Excel file (Booking.com-compatible format)
python cli.py download-reservations --start 2026-03-01 --end 2026-09-30

# As JSON to stdout
python cli.py download-reservations --start 2026-03-01 --end 2026-09-30 --json

# Filter by booking date instead of arrival
python cli.py download-reservations --start 2026-01-01 --end 2026-03-31 --date-type booking

# Custom output directory
python cli.py download-reservations --start 2026-03-01 --end 2026-09-30 --output-dir /path/to/folder
```

### List messages

```bash
# Unanswered messages (default)
python cli.py list-messages --hotel-id 13616005

# All messages
python cli.py list-messages --hotel-id 13616005 --filter all
```

### Read a conversation

```bash
python cli.py read-message --hotel-id 13616005 --index 0
```

### Send a reply

```bash
python cli.py send-message --hotel-id 13616005 --index 0 --message "Thank you for your message!"
```

### Update rates

```bash
python cli.py update-rates
python cli.py update-rates --hotel-id 13616005
```

## How it works

1. **First run**: Chrome launches with a persistent profile (`.chrome-data/`). You log in once, including 2FA via SMS.
2. **Subsequent runs**: the session is reused from `.chrome-data/`, no login or 2FA needed.
3. **Commands**: each CLI call connects to Chrome via CDP (port 9222), performs the action, outputs JSON, and disconnects.

If the session expires, the bot detects it and goes through the login flow again, prompting for the SMS code in the terminal.

## For AI agents

The CLI is designed to be called by AI agents as a subprocess:

```python
import subprocess, json

result = subprocess.run(
    ["python", "cli.py", "list-messages", "--hotel-id", "13616005"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
```

Every command returns a JSON object with at least `status` ("success" or "error") and `action` (the command name). Errors include an `error` field with details.

## Project structure

```
cli.py                     # CLI entry point
booking_extranet_bot.py    # Bot core: Chrome launch, login, session
reservations.py            # Reservation scraping and Excel export
messaging.py               # Inbox, conversations, replies
rate_manager.py            # Rate/pricing calendar updates
.env                       # Credentials (not committed)
.chrome-data/              # Persistent Chrome profile (not committed)
downloads/                 # Downloaded reservation files
```

## Troubleshooting

**CAPTCHA on login**: This happens when logging in too many times in quick succession. Wait a few minutes and try again. Using real Chrome (not Playwright's Chromium) prevents this in normal use.

**Chrome won't connect**: Make sure no other Chrome instance is using port 9222. The bot will launch Chrome automatically if it's not running.

**Session expired**: Just run any command — the bot will detect the expired session and prompt for login + SMS code.

**Linux: Playwright doesn't support my Ubuntu version**: That's fine. We don't use Playwright's browser. Just install Chrome (`google-chrome-stable`) and run the bot directly.

## License

MIT
