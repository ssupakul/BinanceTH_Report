import os
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf

# -------------------------------------------------------------------------
# SETUP & CONFIGURATION
# -------------------------------------------------------------------------
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# รายชื่อเหรียญคู่ THB บน Yahoo Finance (เสถียร ไม่โดนบล็อก IP)
# ตัวอย่าง: BTC-THB, ETH-THB, BNB-THB, SOL-THB, XRP-THB, ADA-THB, DOGE-THB, FLOKI-THB
WATCHLIST = ["BTC-THB", "ETH-THB", "BNB-THB", "SOL-THB", "XRP-THB", "ADA-THB", "DOGE-THB", "FLOKI-THB"]

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

def get_historical_data_yf(symbol, interval="1h"):
    """ 
    ดึงข้อมูลกราฟย้อนหลังจาก Yahoo Finance 
    หมายเหตุ: yfinance ข้อจำกัดข้อมูลระหว่างวัน (Intraday) เช่น 1h หรือ 90m จะดึงย้อนหลังได้ไม่เกิน 60 วัน 
    ซึ่งเพียงพอต่อการคำนวณ RSI 14 และ EMA 50/200 ครับ
    """
    try:
        # ใช้ interval 1h เพื่อนำมาประมวลผลคำนวณทรงกราฟที่ละเอียดครอบคลุมช่วง 4h ได้
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="60d", interval=interval)
        
        if df.empty:
            print(f"No data found for {symbol} on Yahoo Finance")
            return None
            
        # ปรับชื่อคอลัมน์ให้เป็นตัวพิมพ์เล็กตามมาตรฐานโครงสร้างเดิม
        df = df.reset_index()
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        return df
    except Exception as e:
        print(f"Exception fetching {symbol} from Yahoo Finance: {e}")
        return None

def check_bullish_divergence(df, rsi):
    if len(df) < 20:
        return False
    current_close = df["close"].iloc[-1]
    older_close = df["close"].iloc[-10:-3].min()
    current_rsi = rsi.iloc[-1]
    older_rsi = rsi.iloc[-10:-3].min()
    
    if current_close < older_close and current_rsi > older_rsi and current_rsi < 45:
        return True
    return False

def screen_crypto():
    print("🚀 Starting Binance Thailand Crypto Screener [Engine: Yahoo Finance Data Gateway]...")
    signals = []
    
    for symbol in WATCHLIST:
        display_name = symbol.replace("-", "_") # แปลงชื่อให้ดูเหมือนคู่เทรดปกติ เช่น BTC_THB
        print(f"Scanning {display_name}...")
        
        # ดึงข้อมูลกราฟรายชั่วโมง
        df = get_historical_data_yf(symbol, interval="1h")
        if df is None or df.empty:
            continue
            
        # คำนวณอินดิเคเตอร์เทคนิคัล (EMA50, EMA200, RSI)
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
            take_profit = f"{(last_close * 1.05):,.2f} (หรือแนวต้าน EMA50: {last_ema50:,.2f})"
            stop_loss = f"{(last_close * 0.95):,.2f}"
            
            status_context = "📉 RSI Oversold"
            if last_close > last_ema200:
                status_context += "\n+ ยืนเหนือเส้น EMA200 (แนวโน้มหลักภาพใหญ่ยังเป็นขาขึ้น)"
            else:
                status_context += "\n- อยู่ใต้เส้น EMA200 (ภาพใหญ่ขาลง ระวังเน้นเข้าเร็วออกเร็ว)"
                
            if is_bull_div:
                status_context += "\n🔥 พบบูลลิชไดเวอร์เจนท์ (Bullish Divergence) มีโอกาสกลับตัวสูง!"
                
            msg = (
                f"\n🟢 [SIGNAL BUY] {display_name}\n"
                f"ราคาปัจจุบัน: {last_close:,.2f} THB\n"
                f"RSI (1h): {last_rsi:.2f}\n"
                f"สถานะกราฟ: {status_context}\n"
                f"📍 ช่วงราคาเข้าซื้อ: {buy_zone} THB\n"
                f"🎯 เป้าขายทำกำไร: {take_profit} THB\n"
                f"❌ จุดตัดขาดทุน: {stop_loss} THB\n"
                f"--------------------------------"
            )
            signals.append(msg)
            
        # 🔴 เงื่อนไขเตือนขาย: RSI Overbought (>= 70)
        elif last_rsi >= 70:
            msg = (
                f"\n🔴 [SIGNAL SELL] {display_name}\n"
                f"ราคาปัจจุบัน: {last_close:,.2f} THB\n"
                f"RSI (1h): {last_rsi:.2f} (Overbought ⚠️)\n"
                f"คำแนะนำ: ราคาเงินบาทเข้าโซนซื้อมากเกินไปแล้ว พิจารณาแบ่งขายทำกำไร\n"
                f"--------------------------------"
            )
            signals.append(msg)

    if signals:
        alert_header = "📊 [Binance TH Crypto Screener Report]"
        full_message = alert_header + "".join(signals)
        send_line_messaging_api(full_message)
        print("Success! Notification sent to LINE.")
    else:
        print("Process complete: No assets matched the criteria at this hour.")

if __name__ == "__main__":
    screen_crypto()
