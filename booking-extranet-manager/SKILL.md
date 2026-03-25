---
name: Booking.com Extranet Manager
description: Manage Booking.com properties — download reservations, list/reply to guest messages, update rates. Wraps a Python CLI that automates the Booking.com extranet via real Chrome.
version: 1.0.0
tags:
  - booking
  - hospitality
  - reservations
  - property-management
  - automation
author: matsei-ruka
source: https://github.com/matsei-ruka/booking-extranet-bot
---

# Booking.com Extranet Manager

Automate Booking.com property management through a CLI tool. This skill provides commands to download reservations, manage guest messages, and update room rates.

## Prerequisites

The CLI tool must be installed and configured on the host machine:

```bash
git clone https://github.com/matsei-ruka/booking-extranet-bot.git
cd booking-extranet-bot
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env       # Then fill in BOOKING_USERNAME and BOOKING_PASSWORD
```

Google Chrome must be installed. The bot launches Chrome with remote debugging automatically.

## Environment

- `BOT_DIR`: Path to the booking-extranet-bot directory
- Python venv at `$BOT_DIR/venv/bin/python3`
- CLI entry point: `$BOT_DIR/cli.py`

All commands output JSON to stdout. Logs go to stderr.

## Available Commands

### List Properties

Get all properties with hotel IDs and unread message counts.

```bash
cd $BOT_DIR && source venv/bin/activate && python3 cli.py list-properties
```

Returns:
```json
{
  "status": "success",
  "action": "list-properties",
  "count": 3,
  "properties": [
    {"hotel_id": "10353912", "name": "Property Name", "unread_messages": 4}
  ]
}
```

### Download Reservations

Download reservations for a date range. Use `--json` to get data directly, or omit it to save an Excel file.

```bash
# As JSON (for processing)
cd $BOT_DIR && source venv/bin/activate && python3 cli.py download-reservations --start 2026-03-01 --end 2026-09-30 --json

# As Excel file
cd $BOT_DIR && source venv/bin/activate && python3 cli.py download-reservations --start 2026-03-01 --end 2026-09-30
```

Options:
- `--start YYYY-MM-DD` (required): Start date
- `--end YYYY-MM-DD` (required): End date
- `--date-type`: `arrival` (default), `departure`, or `booking`
- `--json`: Return data as JSON instead of Excel
- `--output-dir`: Directory for Excel file (default: `./downloads`)

### List Messages

List guest messages for a property. Defaults to unanswered.

```bash
cd $BOT_DIR && source venv/bin/activate && python3 cli.py list-messages --hotel-id 10353912
```

Options:
- `--hotel-id` (required): Property hotel ID from list-properties
- `--filter`: `unanswered` (default), `sent`, or `all`

### Read Message

Open and read a specific conversation with reservation details.

```bash
cd $BOT_DIR && source venv/bin/activate && python3 cli.py read-message --hotel-id 10353912 --index 0
```

Options:
- `--hotel-id` (required): Property hotel ID
- `--index` (required): Message index from list-messages (0-based)

### Send Message

Reply to a guest conversation. Always use list-messages first to get the correct index.

```bash
cd $BOT_DIR && source venv/bin/activate && python3 cli.py send-message --hotel-id 10353912 --index 0 --message "Thank you for your message"
```

Options:
- `--hotel-id` (required): Property hotel ID
- `--index` (required): Message index from list-messages (0-based)
- `--message` (required): Reply text

### Update Rates

Update room rates from the CSV pricing file.

```bash
cd $BOT_DIR && source venv/bin/activate && python3 cli.py update-rates
cd $BOT_DIR && source venv/bin/activate && python3 cli.py update-rates --hotel-id 13616005
```

## Typical Workflow

1. **List properties** to get hotel IDs and see which have unread messages
2. **List messages** for properties with unread messages
3. **Read** each conversation to understand the guest's request
4. **Send replies** as appropriate
5. **Download reservations** periodically to track bookings

## First Run

On first run, Chrome opens and you must complete the login (including SMS 2FA). Subsequent runs reuse the session — no login needed until the session expires.
