import os
import discord
from discord.ext import commands, tasks
import yfinance as yf
import pandas as pd
from google import genai
import asyncio
from flask import Flask
from threading import Thread
import time

# --- 假網頁維持連線 ---
app = Flask('')
@app.route('/')
def home(): return "股市機器人運行中！"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

# 中文名稱對照表 (手動維護最穩定)
STOCK_MAP = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "0050.TW": "元大台灣50", "2301.TW": "光寶科",
    "3481.TW": "群創", "3017.TW": "奇鋐", "2344.TW": "華邦電", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控", "5289.TWO": "宜鼎", "8299.TWO": "群聯",
    "2327.TW": "國巨", "2382.TW": "廣達", "3289.TWO": "宜特", "3260.TWO": "威剛",
    "8039.TW": "台虹", "1101.TW": "台泥", "1301.TW": "台塑", "2408.TW": "南亞科",
    "2449.TW": "京元電子", "3037.TW": "欣興", "5469.TW": "瀚宇博", "6213.TW": "聯茂",
    "2603.TW": "長榮", "3231.TW": "緯創", "2421.TW": "建準", "3653.TW": "健策",
    "6805.TW": "富世達", "8996.TW": "高力", "6125.TWO": "廣運", "1587.TW": "吉茂",
    "6230.TW": "超眾", "3533.TW": "嘉澤", "4566.TW": "時碩工業", "4551.TW": "智伸科",
    "2233.TW": "宇隆", "6197.TW": "佳必琪", "2228.TW": "劍麟", "4569.TW": "六角",
    "3484.TWO": "森田", "3013.TW": "晟銘電", "3162.TWO": "精確", "6982.TWO": "前進"
}

TARGET_LIST = list(STOCK_MAP.keys())

client = genai.Client(api_key=GOOGLE_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 核心邏輯 ---
def get_stock_report(symbol, force_ai=False):
    max_retries = 2
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="60d")
            if df.empty or len(df) < 35: return None
            
            # 使用我們定義的中文名稱，沒定義才用代碼
            comp_name = STOCK_MAP.get(symbol, symbol)
            last_close = float(df['Close'].iloc[-1])
            
            # 計算 RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            last_rsi = float((100 - (100 / (1 + (gain / loss)))).iloc[-1])

            # 計算成交量倍率
            avg_vol = df['Volume'].tail(6).iloc[:-1].mean()
            curr_vol = df['Volume'].iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            is_oversold = last_rsi < 35
            is_vol_spike = vol_ratio > 1.8 # 提高門檻至 1.8 倍才警報，減少 AI 壓力
            
            if is_oversold or is_vol_spike or force_ai:
                status_text = ""
                if is_oversold: status_text += "📉 低檔超賣 "
                if is_vol_spike: status_text += "🚀 成交爆量 "
                
                prompt = (f"你是專業操盤手。{comp_name}({symbol})現價{last_close:.2f}，"
                          f"RSI {last_rsi:.1f}，成交量為均量 {vol_ratio:.1f} 倍。"
                          f"請根據量價，給出20字內的操作建議。")
                
                ai_response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                advice = ai_response.text.strip()
                tag = "🚨 **[警報]**" if (is_oversold or is_vol_spike) else "🎯 **[診斷]**"
                return f"{tag} **{comp_name}** ({symbol})\n> 狀態: {status_text if status_text else '量價穩定'}\n> 建議: {advice}\n"
            return None
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(10) # 遇到 429 休息久一點
                continue
            return f"❌ `{symbol}` 錯誤: {str(e)}"
    return None

@bot.event
async def on_ready():
    print(f'✅ 機器人 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@bot.command(name='查')
async def check_stock(ctx, symbol: str):
    if symbol.isdigit(): symbol = f"{symbol}.TW"
    await ctx.send(f"🔍 正在診斷 **{STOCK_MAP.get(symbol, symbol)}**...")
    report = get_stock_report(symbol, force_ai=True)
    await ctx.send(report if report else "❌ 無法生成報告。")

@tasks.loop(hours=1.5) # 改成 1.5 小時掃描一次，避免爆額度
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    
    print("🚀 開始例行量價掃描...")
    reports = []
    for s in TARGET_LIST:
        r = get_stock_report(s)
        if r: reports.append(r)
        await asyncio.sleep(8) # 每一檔間隔 8 秒，對 Google 極度友善
        
    if reports:
        await channel.send("💡 **[自動巡邏報告] 發現異動標的：**\n" + "\n".join(reports))

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
