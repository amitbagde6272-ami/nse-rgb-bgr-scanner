import os
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

RGB_NAME = "RGB"
BGR_NAME = "BGR"

def in_market_hours(now=None):
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE

def get_fno_symbols():
    """Get the current NSE individual-stock F&O universe."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Android 11) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nseindia.com/",
    })
    session.get("https://www.nseindia.com/", timeout=15)
    url = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    symbols = [x["symbol"] for x in data if x.get("symbol")]
    if not symbols:
        raise RuntimeError("NSE returned no F&O symbols.")
    return symbols

def download_daily_history(symbols):
    tickers = [f"{s}.NS" for s in symbols]
    return yf.download(
        tickers=tickers,
        period="3mo",
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )

def download_today_hourly(symbols):
    tickers = [f"{s}.NS" for s in symbols]
    return yf.download(
        tickers=tickers,
        period="5d",
        interval="1h",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )

def get_close_series(daily, hourly, symbol):
    ticker = f"{symbol}.NS"
    try:
        if isinstance(daily.columns, pd.MultiIndex):
            s = daily[(ticker, "Close")].dropna()
        else:
            s = daily["Close"].dropna()
    except Exception:
        return None

    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)

    # Replace today's daily close with the latest available hourly close,
    # so the daily EMA reflects the current partial daily candle.
    try:
        if isinstance(hourly.columns, pd.MultiIndex):
            h = hourly[(ticker, "Close")].dropna()
        else:
            h = hourly["Close"].dropna()
        h.index = pd.to_datetime(h.index)
        if h.index.tz is not None:
            h.index = h.index.tz_convert(IST).tz_localize(None)
        today = datetime.now(IST).date()
        h_today = h[h.index.date == today]
        if not h_today.empty:
            latest = float(h_today.iloc[-1])
            if s.index[-1].date() == today:
                s.iloc[-1] = latest
            else:
                s.loc[pd.Timestamp(today)] = latest
    except Exception:
        pass

    return s.dropna()

def signal_for_close(close):
    if close is None or len(close) < 25:
        return None

    ema5 = close.ewm(span=5, adjust=False).mean()
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()

    if len(close) < 2:
        return None

    # "Crossed above/below" = yesterday on/opposite side, today on target side.
    rgb = (
        ema5.iloc[-1] > ema10.iloc[-1]
        and ema5.iloc[-1] > ema20.iloc[-1]
        and ema10.iloc[-1] > ema20.iloc[-1]
        and ema5.iloc[-2] <= ema10.iloc[-2]
        and ema5.iloc[-2] <= ema20.iloc[-2]
    )

    bgr = (
        ema5.iloc[-1] < ema10.iloc[-1]
        and ema5.iloc[-1] < ema20.iloc[-1]
        and ema10.iloc[-1] < ema20.iloc[-1]
        and ema5.iloc[-2] >= ema10.iloc[-2]
        and ema5.iloc[-2] >= ema20.iloc[-2]
    )

    if rgb:
        return RGB_NAME
    if bgr:
        return BGR_NAME
    return None

def scan():
    symbols = get_fno_symbols()
    daily = download_daily_history(symbols)
    hourly = download_today_hourly(symbols)

    rgb, bgr = [], []
    for symbol in symbols:
        close = get_close_series(daily, hourly, symbol)
        signal = signal_for_close(close)
        if signal == RGB_NAME:
            rgb.append(symbol)
        elif signal == BGR_NAME:
            bgr.append(symbol)

    return sorted(rgb), sorted(bgr)

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(message)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=15)
    r.raise_for_status()

def main():
    now = datetime.now(IST)
    if not in_market_hours(now):
        print(f"Outside market hours: {now:%Y-%m-%d %H:%M:%S %Z}")
        return

    rgb, bgr = scan()

    # State file prevents repeating the same symbol every hourly run.
    state_path = "last_alerts.txt"
    previous = set()
    if os.path.exists(state_path):
        previous = {x.strip() for x in open(state_path, encoding="utf-8") if x.strip()}

    current = {f"RGB:{s}" for s in rgb} | {f"BGR:{s}" for s in bgr}
    new_items = sorted(current - previous)

    with open(state_path, "w", encoding="utf-8") as f:
        for item in sorted(current):
            f.write(item + "\n")

    if not new_items:
        print(f"{now:%H:%M} IST - No new signals.")
        return

    lines = [f"📊 NSE F&O EMA Scanner\n🕐 {now:%d-%m-%Y %H:%M} IST", ""]
    for item in new_items:
        side, symbol = item.split(":", 1)
        icon = "🟢" if side == RGB_NAME else "🔴"
        lines.append(f"{icon} {side}: {symbol}")
    lines.append("")
    lines.append("Rules: daily EMA 5/10/20 crossover, matching the supplied Chartink scanners.")
    lines.append("Data may be delayed; this is not a real-time trading signal.")
    send_telegram("\n".join(lines))

if __name__ == "__main__":
    main()
