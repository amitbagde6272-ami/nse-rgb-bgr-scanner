import os
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

# NSE F&O individual-security universe.
# This is intentionally kept in the repository instead of relying
# on the discontinued/unstable NSE index API endpoint.
FNO_SYMBOLS = [
        "ATHERENERG",
    "MAHABANK",
    "SAGILITY",
    "FORCEMOT",
    "GODFRYPHLP",
    "AARTIIND", "ABB", "ABBOTINDIA", "ACC", "ADANIENT", "ADANIPORTS",
    "ABCAPITAL", "ABFRL", "ALKEM", "AMBUJACEM", "APOLLOHOSP",
    "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "AUBANK",
    "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV",
    "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA", "BATAINDIA",
    "BERGEPAINT", "BEL", "BHARATFORG", "BHEL", "BPCL", "BHARTIARTL",
    "BIOCON", "BSOFT", "BOSCHLTD", "BRITANNIA", "CANFINHOME", "CANBK",
    "CHAMBLFERT", "CHOLAFIN", "CIPLA", "CUB", "COALINDIA", "COFORGE",
    "COLPAL", "CONCOR", "COROMANDEL", "CROMPTON", "CUMMINSIND",
    "DABUR", "DALBHARAT", "DEEPAKNTR", "DELTACORP", "DIVISLAB", "DIXON",
    "DLF", "LALPATHLAB", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND",
    "GAIL", "GLENMARK", "GMRINFRA", "GODREJCP", "GODREJPROP", "GRANULES",
    "GRASIM", "GUJGASLTD", "GNFC", "HAVELLS", "HCLTECH", "HDFCAMC",
    "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HAL", "HINDCOPPER",
    "HINDPETRO", "HINDUNILVR", "HDFC", "ICICIBANK", "ICICIGI",
    "ICICIPRULI", "IDFCFIRSTB", "IDFC", "IBULHSGFIN", "INDIAMART", "IEX",
    "IOC", "IRCTC", "IGL", "INDUSTOWER", "INDUSINDBK", "NAUKRI", "INFY",
    "INTELLECT", "INDIGO", "IPCALAB", "ITC", "JINDALSTEL", "JKCEMENT",
    "JSWSTEEL", "JUBLFOOD", "KOTAKBANK", "LTTS", "LTIM", "LT",
    "LAURUSLABS", "LICHSGFIN", "LUPIN", "MGL", "M&MFIN", "M&M",
    "MANAPPURAM", "MARICO", "MARUTI", "MFSL", "METROPOLIS", "MOTHERSON",
    "MPHASIS", "MRF", "MCX", "MUTHOOTFIN", "NATIONALUM", "NAVINFLUOR",
    "NESTLEIND", "NMDC", "NTPC", "OBEROIRLTY", "ONGC", "OFSS", "PAGEIND",
    "PERSISTENT", "PETRONET", "PIIND", "PIDILITIND", "PEL", "POLYCAB",
    "PFC", "POWERGRID", "PNB", "PVRINOX", "RAIN", "RBLBANK", "RECLTD",
    "RELIANCE", "SBICARD", "SBILIFE", "SHREECEM", "SHRIRAMFIN",
    "SIEMENS", "SRF", "SBIN", "SAIL", "SUNPHARMA", "SUNTV", "SYNGENE",
    "TATACHEM", "TATACOMM", "TCS", "TATACONSUM", "TATAMOTORS",
    "TATAPOWER", "TATASTEEL", "TECHM", "FEDERALBNK", "INDIACEM",
    "INDHOTEL", "RAMCOCEM", "TITAN", "TORNTPHARM", "TRENT", "TVSMOTOR",
    "ULTRACEMCO", "UBL", "MCDOWELL-N", "UPL", "VEDL", "IDEA", "VOLTAS",
    "WHIRLPOOL", "WIPRO", "ZEEL", "ZYDUSLIFE"
]


def in_market_hours(now=None):
    now = now or datetime.now(IST)

    if now.weekday() >= 5:
        return False

    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def get_fno_symbols():
    """Return NSE F&O individual-security symbols."""

    symbols = sorted(set(FNO_SYMBOLS))

    if not symbols:
        raise RuntimeError("F&O symbol list is empty.")

    print(f"Using {len(symbols)} F&O symbols.")

    return symbols


def download_daily_history(symbols):
    """
    Download approximately 3 months of daily data.

    This is enough to calculate EMA 5/10/20 reliably.
    """

    tickers = [f"{s}.NS" for s in symbols]

    print(f"Downloading daily data for {len(tickers)} symbols...")

    data = yf.download(
        tickers=tickers,
        period="3mo",
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )

    if data is None or data.empty:
        raise RuntimeError("Yahoo Finance returned no daily data.")

    print("Daily data downloaded successfully.")

    return data


def get_close_series(daily, symbol):
    ticker = f"{symbol}.NS"

    try:
        if isinstance(daily.columns, pd.MultiIndex):

            # Standard yfinance structure:
            # ticker -> field
            if (ticker, "Close") in daily.columns:
                series = daily[(ticker, "Close")]

            # Some yfinance versions may reverse the levels.
            elif ("Close", ticker) in daily.columns:
                series = daily[("Close", ticker)]

            else:
                return None

        else:
            series = daily["Close"]

    except Exception:
        return None

    if series is None:
        return None

    series = series.dropna().copy()

    if series.empty:
        return None

    series.index = pd.to_datetime(series.index)

    if series.index.tz is not None:
        series.index = series.index.tz_convert(IST).tz_localize(None)

    return series.dropna()


def signal_for_close(close):
    """
    Reproduce the supplied Chartink conditions:

    RGB:
        EMA5 > EMA10
        EMA5 > EMA20
        EMA10 > EMA20
        EMA5 crossed above EMA10
        EMA5 crossed above EMA20

    BGR:
        EMA5 < EMA10
        EMA5 < EMA20
        EMA10 < EMA20
        EMA5 crossed below EMA10
        EMA5 crossed below EMA20
    """

    if close is None or len(close) < 25:
        return None

    ema5 = close.ewm(
        span=5,
        adjust=False
    ).mean()

    ema10 = close.ewm(
        span=10,
        adjust=False
    ).mean()

    ema20 = close.ewm(
        span=20,
        adjust=False
    ).mean()

    current_5 = ema5.iloc[-1]
    current_10 = ema10.iloc[-1]
    current_20 = ema20.iloc[-1]

    previous_5 = ema5.iloc[-2]
    previous_10 = ema10.iloc[-2]
    previous_20 = ema20.iloc[-2]

    # RGB
    rgb = (
        current_5 > current_10
        and current_5 > current_20
        and current_10 > current_20
        and previous_5 <= previous_10
        and previous_5 <= previous_20
    )

    # BGR
    bgr = (
        current_5 < current_10
        and current_5 < current_20
        and current_10 < current_20
        and previous_5 >= previous_10
        and previous_5 >= previous_20
    )

    if rgb:
        return RGB_NAME

    if bgr:
        return BGR_NAME

    return None


def scan():

    symbols = get_fno_symbols()

    daily = download_daily_history(symbols)

    rgb = []
    bgr = []

    processed = 0

    failed_symbols = []

for symbol in symbols:

    close = get_close_series(
        daily,
        symbol
    )

    if close is None or len(close) < 25:
        failed_symbols.append(symbol)
        continue

    signal = signal_for_close(close)

    if signal == RGB_NAME:
        rgb.append(symbol)

    elif signal == BGR_NAME:
        bgr.append(symbol)

        if close is not None:
            processed += 1

    print(
        f"Processed {processed}/{len(symbols)} symbols."
    )
        if failed_symbols:
        print(
            f"Symbols without usable data "
            f"({len(failed_symbols)}): "
            f"{failed_symbols}"
        )

    return sorted(rgb), sorted(bgr)


def send_telegram(message):

    token = os.environ.get(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.environ.get(
        "TELEGRAM_CHAT_ID"
    )

    if not token or not chat_id:
        print(
            "Telegram secrets are not configured."
        )
        print(message)
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message
        },
        timeout=15
    )

    response.raise_for_status()

    print("Telegram notification sent.")


def main():

    now = datetime.now(IST)

    print(
        f"Scanner started: "
        f"{now:%Y-%m-%d %H:%M:%S %Z}"
    )

    if not in_market_hours(now):

        print(
            f"Outside market hours: "
            f"{now:%Y-%m-%d %H:%M:%S %Z}"
        )

        return

    rgb, bgr = scan()

    print(
        f"RGB matches: {rgb}"
    )

    print(
        f"BGR matches: {bgr}"
    )

    # Prevent repeatedly sending the same signal
    # on every hourly run.
    state_path = "last_alerts.txt"

    previous = set()

    if os.path.exists(state_path):

        with open(
            state_path,
            "r",
            encoding="utf-8"
        ) as file:

            previous = {
                line.strip()
                for line in file
                if line.strip()
            }

    current = (
        {f"RGB:{symbol}" for symbol in rgb}
        |
        {f"BGR:{symbol}" for symbol in bgr}
    )

    new_items = sorted(
        current - previous
    )

    with open(
        state_path,
        "w",
        encoding="utf-8"
    ) as file:

        for item in sorted(current):
            file.write(
                item + "\n"
            )

    if not new_items:

        print(
            f"{now:%H:%M} IST - "
            f"No new signals."
        )

        return

    lines = [
        "📊 NSE F&O EMA Scanner",
        f"🕐 {now:%d-%m-%Y %H:%M} IST",
        ""
    ]

    for item in new_items:

        side, symbol = item.split(
            ":",
            1
        )

        icon = (
            "🟢"
            if side == RGB_NAME
            else "🔴"
        )

        lines.append(
            f"{icon} {side}: {symbol}"
        )

    lines.extend([
        "",
        "Rules:",
        "Daily EMA 5/10/20 crossover",
        "",
        "Data source: Yahoo Finance delayed data.",
        "Not a real-time trading signal."
    ])

    send_telegram(
        "\n".join(lines)
    )


if __name__ == "__main__":
    main()
