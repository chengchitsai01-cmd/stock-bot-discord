import os
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import time
from google import genai 

# ==========================================
# 1. 設定區
# ==========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

TARGET_LIST = [
    "2330.TW", "2454.TW", "0050.TW", "2301.TW", "3481.TW", 
    "3324.TWO", "3017.TW", "2344.TW", "2308.TW", "2317.TW",
    "3711.TW", "5289.TWO", "8299.TWO", "2327.TW", "2382.TW",
    "3289.TWO", "3260.TWO", "8039.TW", "1101.TW", "1301.TW",
    "2408.TW", "2449.TW", "3037.TW", "5469.TW", "6213.TW",
    "2603.TW", "3231.TW", "2421.TW", "3653.TW", "6805.TW",
    "8996.TW", "6125.TWO", "1587.TW", "6230.TW", "3533.TW",
    "4566.TW", "4551.TW", "2233.TW", "6197.TW", "2228.TW",
    "4569.TW", "3484.TWO", "3013.TW", "3162.TWO", "6982.TWO"
]

client = genai.Client(api_key=GOOGLE_API_KEY)

# ==========================================
# 2. 功能函數
# ==========================================
def send_discord_message(content):
    if not DISCORD_WEBHOOK_URL:
        print("❌ 錯誤：找不到 Discord Webhook 網址！請檢查 GitHub Secrets。")
        return
        
    data = {"content": content}
    try:
        print(f"👉 正在嘗試發送訊息至 Discord (字數: {len(content)})...")
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        
        # 強制印出 Discord 伺服器的回應
        if response.status_code in [200, 204]:
            print("✅ Discord 接收成功！")
        else:
            print(f"❌ Discord 拒絕接收！錯誤碼: {response.status_code}")
            print(f"❌ 錯誤詳情: {response.text}")
    except Exception as e:
        print(f"❌ 網路連線或發送異常: {e}")

def get_stock_report(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 35: 
            print(f"⚠️ {symbol}: 抓不到足夠的歷史資料，跳過。")
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        last_close = float(df['Close'].iloc[-1])
        support = float(df['Low'].tail(20).min())
        resistance = float(df['High'].tail(20).max())
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        last_rsi = float((100 - (100 / (1 + (gain / loss)))).iloc[-1])

        is_alert = last_rsi < 35
        alert_tag = "🚨 **[觸發低檔警報]** " if is_alert else "📊 **[例行診斷]** "

        prompt = (f"你是操盤手。{symbol}現價{last_close:.2f}，RSI {last_rsi:.1f}，"
                  f"支撐{support:.2f}/壓力{resistance:.2f}。請用20字內給出操作建議。")
        
        ai_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        print(f"🤖 {symbol}: AI 分析完成。")
        return f"{alert_tag}**{symbol}**: `{last_close:.2f}`\n> {ai_response.text.strip()}\n"
    except Exception as e:
        print(f"❌ {symbol} 執行錯誤: {str(e)}")
        return f"❌ {symbol} 錯誤: {str(e)}\n"

# ==========================================
# 3. 主程式
# ==========================================
def main():
    print(f"[{datetime.now()}] 🚀 啟動除錯版 Discord 市場掃描...")
    
    # 為了測試速度，我們暫時只掃描前 5 檔股票就好，找出問題比較快！
    test_list = TARGET_LIST[:5] 
    
    batch_reports = []
    for symbol in test_list:
        print(f"🔍 開始處理: {symbol}...")
        report = get_stock_report(symbol)
        if report:
            batch_reports.append(report)
        time.sleep(1) 
    
    if batch_reports:
        full_msg = "📈 **股市深度診斷報告 (測試)**\n" + "\n".join(batch_reports)
        send_discord_message(full_msg)
    else:
        print("⚠️ 警告：所有股票分析都失敗，無法生成報告！")
        
    print("✅ 程式執行結束。")

if __name__ == "__main__":
    main()
