# Free NSE F&O RGB/BGR Scanner

This reproduces the two Chartink conditions from the screenshots supplied by the user.

## RGB
- Daily EMA(5) > Daily EMA(10)
- Daily EMA(5) > Daily EMA(20)
- Daily EMA(10) > Daily EMA(20)
- EMA(5) crossed above EMA(10)
- EMA(5) crossed above EMA(20)

## BGR
- Daily EMA(5) < Daily EMA(10)
- Daily EMA(5) < Daily EMA(20)
- Daily EMA(10) < Daily EMA(20)
- EMA(5) crossed below EMA(10)
- EMA(5) crossed below EMA(20)

Universe: current NSE individual-stock F&O universe.

## Free setup
1. Create a GitHub repository and upload:
   - scanner.py
   - requirements.txt
   - .github/workflows/scanner.yml
   - last_alerts.txt containing nothing (or omit it; the script creates it)
2. Create a Telegram bot with BotFather.
3. Start a chat with your bot and send `/start`.
4. Get your chat ID.
5. In GitHub repository Settings → Secrets and variables → Actions, add:
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
6. Enable Actions and run the workflow manually once to test.

## Important limitations
- Yahoo Finance/NSE public data can be delayed or unavailable.
- GitHub scheduled workflows are not guaranteed to start at the exact minute.
- This is not a real-time trading alert system.
- The script checks the current partial daily candle using the latest hourly close when available, then evaluates the daily EMA crossover.
