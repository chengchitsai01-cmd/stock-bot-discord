import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio
from datetime import datetime

# 1. 讀取環境變數
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 📌 絕對固定觀察名單 (不再更動) ---
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "3017.TW": "奇鋐", "2603.TW": "長榮",
    "2609.TW": "陽明", "2881.TW": "富邦金", "2882.TW": "國泰金", "2886.TW": "兆豐金",
    "2412.TW": "中華電", "2357.TW": "華碩", "3711.TW": "日月光投控"
}
WATCHLIST = list(STOCK_NAMES.keys())

# --- 記憶功能：避免重複發送 ---
def get_last_recommendation():
    if os.path.exists("last_result.txt"):
        with open("last_result.txt", "r") as f:
            return f.read().strip()
    return ""

def save_recommendation(symbol):
    with open("last_result.txt", "w") as f:
        f.write(symbol)

async def perform_scan():
    await bot.wait_until_ready()
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    results = []
    for s in WATCHLIST:
        try:
            t = yf.Ticker(s)
            df = t.history(period="100d")
            if df.empty or len(df) < 65: continue
            
            last_p = df['Close'].iloc[-1]
            ma60 = df['Close'].tail(60).mean()
            # 計算 20 日動能
            mom20 = df['Close'].pct_change(periods=20).iloc[-1]
            
            if last_p > ma60: # 只有在季線之上的才列入考慮
                results.append({
                    'symbol': s, 
                    'name': STOCK_NAMES.get(s, s), 
                    'score': mom20 * 100, 
                    'price': last_p
                })
        except: continue

    results.sort(key=lambda x: x['score'], reverse=True)
    
    current_top = results[0]['symbol'] if results else "NONE"
    last_top = get_last_recommendation()
    is_monday = datetime.now().weekday() == 0 # 週一

    # --- 邏輯：只有「換人當老大」或「週一」才傳訊息 ---
    if current_top != last_top or is_monday:
        if results:
            top_1 = results[0]
            shares = INVEST_AMOUNT // top_1['price']
            
            header = "🔄 **【標的輪動】**" if current_top != last_top else "📅 **【每週報到】**"
            msg = (
                f"{header}\n"
                f"🏆 本月推薦：**{top_1['name']}** ({top_1['symbol']})\n"
                f"✅ 操作建議：買進 `{int(shares)}` 股\n"
                f"💰 目前股價：`{top_1['price']:.2f}`\n"
                f"💡 動能評分：`{top_1['score']:.2f}`"
            )
            await channel.send(msg)
            save_recommendation(current_top)
        else:
            if last_top != "NONE":
                await channel.send("🛑 **【避險提醒】市場轉弱，所有標的皆跌破季線，請保留現金。**")
                save_recommendation("NONE")
    
    await bot.close()

@bot.event
async def on_ready():
    await perform_scan()

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
