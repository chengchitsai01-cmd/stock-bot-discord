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
def home(): return "機器人運行中！"

def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

TARGET_LIST = [
    "2330.TW", "2454.TW", "0050.TW", "2301.TW", "3481.TW", 
    "3017.TW", "2317.TW", "3711.TW", "2603.TW", "3231.TW",
    "2421.TW", "3653.TW", "6230.TW", "6197.TW", "4569.TW" # 先精簡清單，確保成功率
]

client = genai.Client(api_key=GOOGLE_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 核心邏輯：加入量價判斷 + AI 自動重試 ---
def get_stock_report(symbol, force_ai=False):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="60d")
            if df.empty or len(df) < 35: return None
            
            comp_name = ticker.info.get('shortName', symbol)
            last_close = float(df['Close'].iloc[-1])
            
            # 1. 計算 RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            last_rsi = float((100 - (100 / (1 + (gain / loss)))).iloc[-1])

            # 2. 計算成交量倍率 (選股加強點)
            avg_vol = df['Volume'].tail(6).iloc[:-1].mean() # 前5天平均
            curr_vol = df['Volume'].iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            # 3. 判斷狀態
            is_oversold = last_rsi < 35
            is_vol_spike = vol_ratio > 1.5
            
            # 只有當「低檔」、「爆量」或「主動查詢」時才呼叫 AI
            if is_oversold or is_vol_spike or force_ai:
                status_text = ""
                if is_oversold: status_text += "📉 低檔超賣 "
                if is_vol_spike: status_text += "🚀 成交爆量 "
                
                prompt = (f"你是專業操盤手。{comp_name}({symbol})現價{last_close:.2f}，"
                          f"RSI {last_rsi:.1f}，成交量為均量 {vol_ratio:.1f} 倍。"
                          f"請根據量價狀況，給出20字內的操作建議。")
                
                ai_response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                advice = ai_response.text.strip()
                tag = "🚨 **[警報觸發]**" if (is_oversold or is_vol_spike) else "🎯 **[主動查詢]**"
                return f"{tag} **{comp_name}** ({symbol})\n> 狀態: {status_text if status_text else '一般'}\n> 建議: {advice}"
            
            return None # 沒事不回報，節省額度
            
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(5) # 遇到 429 睡 5 秒再試
                continue
            return f"❌ `{symbol}` 錯誤: {str(e)}"
    return None

# --- 指令 ---
@bot.event
async def on_ready():
    print(f'✅ 機器人 {bot.user} 已上線')
    if not auto_scan.is_running(): auto_scan.start()

@bot.command(name='查')
async def check_stock(ctx, symbol: str):
    if symbol.isdigit(): symbol = f"{symbol}.TW"
    await ctx.send(f"🔍 正在深度診斷 `{symbol}` (包含量價分析)...")
    report = get_stock_report(symbol, force_ai=True)
    await ctx.send(report if report else "❌ 暫時無法分析。")

@tasks.loop(hours=1) # 建議改成一小時一次，避免 API 再次爆掉
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    
    print("🚀 開始例行量價掃描...")
    reports = []
    for s in TARGET_LIST:
        r = get_stock_report(s)
        if r: reports.append(r)
        await asyncio.sleep(3) # 慢慢跑，不急
        
    if reports:
        await channel.send("💡 **[量價掃描報告] 發現異動標的：**\n" + "\n".join(reports))

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
