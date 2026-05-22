import os
import requests
import pandas as pd
import pandas_ta as ta

# -------------------------------------------------------------------------
# SETUP & CONFIGURATION
# -------------------------------------------------------------------------
BINANCE_TH_URL = "https://api.binance.th/api/v3"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# รายชื่อเหรียญที่เราอยากได้ (ใส่เป็นตัวใหญ่ปกติ ระบบจะไปแมตช์ชื่อจริงให้เอง)
TARGET_COINS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "FLOKI", "EIGEN"]

def send_line_messaging_api(text_msg):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("Error: Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID.")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text_msg}]
    }
    
    try:
        response = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            print("Successfully sent message via LINE Messaging API.")
        else:
            print(f"Failed to send LINE message: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception while sending LINE message: {e}")

def get_valid_thb_symbols():
    """
    ดึงรายชื่อคู่เหรียญทั้งหมดที่เปิดซื้อขายจริงบน Binance TH เพื่อหาชื่อสัญลักษณ์ที่แท้จริง
    """
    url = f"{BINANCE_TH_URL}/exchangeInfo"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Cannot fetch exchangeInfo: {response.status_code}")
            return {}
            
        data = response.json()
        valid_symbols = {}
        
        # วนลูปหาคู่เหรียญที่จับคู่กับ THB
        for s in data.get("symbols", []):
            base_asset = s.get("baseAsset", "").upper()
            quote_asset = s.get("quoteAsset", "").upper()
            symbol_name = s.get("symbol") # ชื่อที่ระบบใช้เรียกใน API เช่น btcthb หรือ btc_thb
            
            if quote_asset == "THB" and base_asset in TARGET_COINS:
                valid_symbols[base_asset] = symbol_name
                
        return valid_symbols
    except Exception as e:
        print(f"Error fetching exchange info: {e}")
        return {}

def get_historical_data(symbol, interval="4h", limit=100):
    url = f"{BINANCE_TH_URL}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Error fetching {symbol} from Binance TH: {response.status_code}")
            return None
        data = response.json()
        
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "count", "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["close"] = pd.to_numeric(df["close"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def check_bullish_divergence(df, rsi):
    if len(df) < 10:
        return False
    current_close = df["close"].iloc[-1]
    older_close = df["close"].iloc[-5:-2].min()
    current_rsi = rsi.iloc[-1]
    older_rsi = rsi.iloc[-5:-2].min()
    
    if current_close < older_close and current_rsi > older_rsi and current_rsi < 45:
        return True
    return False

def screen_crypto():
    print("Fetching active THB pairs from Binance Thailand...")
    # ค้นหาคู่เหรียญจริงจากหน้าเว็บ
    available_pairs = get_valid_thb_symbols()
    
    if not available_pairs:
        print("Error: Could not find any valid THB trading pairs from API.")
        return
        
    print(f"Found active pairs for screening: {list(available_pairs.values())}")
    signals = []
    
    for base_coin, exact_symbol in available_pairs.items():
        print(f"Scanning {base_coin}/THB (Using API key name: '{exact_symbol}')...")
        
        df = get_historical_data(exact_symbol)
        if df is None or df.empty:
            continue
            
        df["EMA_50"] = ta.ema(df["close"], length=50)
        df["EMA_200"] = ta.ema(df["close"], length=200)
        df["RSI"] = ta.rsi(df["close"], length=14)
        
        last_close = df["close"].iloc[-1]
        last_rsi = df["RSI"].iloc[-1]
        last_ema50 = df["EMA_50"].iloc[-1]
        last_ema200 = df["EMA_200"].iloc[-1]
        
        is_bull_div = check_bullish_divergence(df, df["RSI"])
        
        # 🟢 เงื่อนไขเข้าซื้อ: RSI Oversold (<= 32)
        if last_rsi <= 32:
            buy_zone = f"{last_close:,.2f} - {(last_close * 0.98):,.2f}"
            take_profit = f"{(last_close * 1.05):,.2f} (หรือแถว EMA50: {last_ema50:,.2f})"
            stop_loss = f"{(last_close * 0.95):,.2f}"
            
            status_context = "📉 RSI Oversold"
            if last_close > last_ema200:
                status_context += "\n+ ยืนเหนือเส้น EMA200 (เทรนด์ใหญ่เงินบาทยังเป็นขาขึ้น)"
            else:
                status_context += "\n- ต่ำกว่าเส้น EMA200 (เทรนด์ใหญ่เป็นขาลง ระวังการเด้งสั้น)"
                
            if is_bull_div:
                status_context += "\n🔥 พบสัญญาณ Bullish Divergence บนคู่ THB!"
                
            msg = (
                f"\n🟢 [SIGNAL BUY] {base_coin}_THB\n"
                f"ราคาปัจจุบัน: {last_close:,.2f} THB\n"
                f"RSI (4h): {last_rsi:.2f}\n"
                f"สถานะหลัก: {status_context}\n"
                f"📍 ช่วงราคาเข้าซื้อ: {buy_zone} THB\n"
                f"🎯 เป้าขายทำกำไร: {take_profit} THB\n"
                f"❌ จุดตัดขาดทุน: {stop_loss} THB\n"
                f"--------------------------------"
            )
            signals.append(msg)
            
        # 🔴 เงื่อนไขเตือนขาย: RSI Overbought (>= 70)
        elif last_rsi >= 70:
            msg = (
                f"\n🔴 [SIGNAL SELL] {base_coin}_THB\n"
                f"ราคาปัจจุบัน: {last_close:,.2f} THB\n"
                f"RSI (4h): {last_rsi:.2f} (Overbought ⚠️)\n"
                f"คำแนะนำ: ราคาเงินบาทตึงมากแล้ว พิจารณาแบ่งขายทำกำไร\n"
                f"--------------------------------"
            )
            signals.append(msg)

    if signals:
        alert_header = "📊 [Binance TH Crypto Screener Report]"
        full_message = alert_header + "".join(signals)
        send_line_messaging_api(full_message)
        print("Signal notification sent to LINE.")
    else:
        print("No assets matched the technical criteria on Binance TH at this time.")

if __name__ == "__main__":
    screen_crypto()
