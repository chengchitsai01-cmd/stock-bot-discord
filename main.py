import os
import discord
from discord.ext import commands, tasks
import yfinance as yf
import pandas as pd
import asyncio
from flask import Flask
from threading import Thread

# --- 假網頁維持連線 ---
app = Flask('')
@app.route('/')
def home(): return "邏輯選股機器人運行中！"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

STOCK_MAP = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "0050.TW": "元大台灣50", "2301.TW": "光寶科",
    "3481.TW": "群創", "3017.TW": "奇鋐", "2344.TW": "華邦電", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控", "2603.TW": "長榮", "3231.TW": "緯創",
    "2421.TW": "建準", "3653.TW": "健策", "6197.TW": "佳必琪", "4569.TW": "六角"
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 核心邏輯：股神篩選法 ---
def get_logic_report(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="60d")
        if df.empty or len(df) < 40: return None
        
        comp_name = STOCK_MAP.get(symbol, symbol)
        last_close = df['Close'].iloc[-1]
        ma20 = df['Close'].tail(20).mean() # 月線
        ma60 = df['Close'].tail(60).mean() # 季線
        
        # 1. RSI 計算
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]

        # 2. 成交量判斷
        avg_vol = df['Volume'].tail(6).iloc[:-1].mean()
        curr_vol = df['Volume'].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

        # --- 診斷邏輯 ---
        score = 0
        reasons = []

        # 趨勢分 (歐尼爾邏輯：強勢股必站上均線)
        if last_close > ma20: 
            score += 40
            reasons.append("✅ 站上月線 (趨勢翻正)")
        else:
            reasons.append("❌ 月線下方 (空頭格局)")

        # 動能分 (爆量通常是攻擊訊號)
        if vol_ratio > 1.8:
            score += 30
            reasons.append(f"🔥 成交量大增 {vol_ratio:.1f} 倍 (主力進場)")
        
        # 轉折分 (RSI 跌深反彈)
        if rsi < 35:
            score += 30
            reasons.append(f"📉 RSI 低檔超賣 ({rsi:.1f})")
        elif rsi > 70:
            reasons.append(f"⚠️ RSI 過熱 ({rsi:.1f})")

        # --- 綜合結論 ---
        if score >= 70:
            advice = "🌟 **【極力推薦】** 量價齊揚，趨勢極強！"
        elif score >= 40:
            advice = "🆗 **【維持觀望】** 趨勢尚可，等待爆量。"
        else:
            advice = "😴 **【不宜介入】** 暫無訊號，耐心等待。"

        report = (
            f"📊 **{comp_name} ({symbol})**\n"
            f"> 現價: `{last_close:.2f}` | RSI: `{rsi:.1f}`\n"
            f"> 分析: " + " / ".join(reasons) + "\n"
            f"> **總結: {advice}**"
        )
        return report

    except Exception as e:
        return f"❌ `{symbol}` 錯誤: {str(e)}"

@bot.event
async def on_ready():
    print(f'✅ 股神邏輯機器人 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@bot.command(name='查')
async def check_stock(ctx, symbol: str):
    if symbol.isdigit(): symbol = f"{symbol}.TW"
    await ctx.send(f"🔍 正在根據股神邏輯分析 **{STOCK_MAP.get(symbol, symbol)}**...")
    report = get_logic_report(symbol)
    await ctx.send(report if report else "❌ 暫時無法分析。")

@tasks.loop(hours=1)
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    
    reports = []
    for s in TARGET_LIST:
        # 自動巡邏只報「推薦」以上的標的
        ticker = yf.Ticker(s)
        # 簡化判斷...
        r = get_logic_report(s)
        if "【極力推薦】" in r or "爆量" in r:
            reports.append(r)
        await asyncio.sleep(1) # 無 AI，一秒一檔沒問題
        
    if reports:
        await channel.send("🚀 **[股神掃描儀] 發現高分標的！**\n" + "\n".join(reports))

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
