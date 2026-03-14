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
def home(): return "進出場決策機器人運行中！"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

STOCK_MAP = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "0050.TW": "元大台灣50", "2301.TW": "光寶科",
    "3481.TW": "群創", "3017.TW": "奇鋐", "2344.TW": "華邦電", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控", "2603.TW": "長榮", "3231.TW": "緯創",
    "2421.TW": "建準", "3653.TW": "健策", "2382.TW": "廣達", "2609.TW": "陽明"
}
NAME_TO_SYMBOL = {v: k for k, v in STOCK_MAP.items()}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def make_bar(value, max_val=100):
    nodes = 10
    filled = int((value / max_val) * nodes)
    filled = max(0, min(nodes, filled))
    return "█" * filled + "░" * (nodes - filled)

def get_full_report(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="60d")
        if df.empty or len(df) < 60: return None
        
        info = ticker.info
        comp_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
        pe_ratio = info.get('trailingPE', 0)
        eps = info.get('trailingEps', 0)
        
        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        change_pct = ((last_close - prev_close) / prev_close) * 100
        
        # 均線計算
        ma20 = df['Close'].tail(20).mean()
        ma60 = df['Close'].tail(60).mean() # 加入季線判斷長線趨勢
        bias_20 = ((last_close - ma20) / ma20) * 100
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
        
        avg_vol = df['Volume'].tail(6).iloc[:-1].mean()
        vol_ratio = df['Volume'].iloc[-1] / avg_vol if avg_vol > 0 else 1

        # ==========================================
        # 🎯 進出場決策邏輯 (紅綠燈系統)
        # ==========================================
        action_advice = ""
        
        # 1. 判斷危險/出場訊號 (風險優先)
        if rsi >= 75 or bias_20 >= 8:
            action_advice = "🔴 【逢高停利】短線已過熱，留意拉回風險，建議分批獲利了結。"
        elif last_close < ma20 and prev_close >= ma20:
            action_advice = "🔴 【破線警報】剛跌破月線支撐，趨勢轉弱，建議減碼或停損。"
        
        # 2. 判斷進場訊號
        elif last_close > ma20 and vol_ratio > 1.5 and rsi < 65:
            action_advice = "🟢 【強勢進場】帶量突破月線，動能強勁，可考慮順勢佈局。"
        elif last_close > ma60 and abs(bias_20) < 3 and rsi < 45:
            action_advice = "🟢 【拉回找買點】長線多頭但短線拉回月線附近，是不錯的低接機會。"
            
        # 3. 觀望
        else:
            action_advice = "🟡 【觀望為主】目前無明顯進出場訊號，建議多看少做。"

        # ==========================================

        report = (
            f"🏠 **{comp_name} ({symbol})**\n"
            f"💰 **市價**: `{last_close:.2f}` ({change_pct:+.2f}%)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 **基本面** | PE:`{pe_ratio:.1f}` EPS:`{eps:.2f}`\n"
            f"📏 **技術面** | 乖離:`{bias_20:.1f}%` \n"
            f"> RSI: `{rsi:.1f}` | {make_bar(rsi)}\n"
            f"> 量比: `{vol_ratio:.1f}x` | {make_bar(vol_ratio * 20)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **操作建議**:\n> **{action_advice}**"
        )
        return report
    except Exception as e:
        return f"❌ 分析失敗: {str(e)}"

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    content = message.content.strip()
    target_symbol = None

    if content.isdigit() and len(content) >= 4:
        target_symbol = f"{content}.TW"
    elif content in NAME_TO_SYMBOL:
        target_symbol = NAME_TO_SYMBOL[content]

    if target_symbol:
        msg = await message.channel.send(f"🔍 正在研判 **{STOCK_MAP.get(target_symbol, content)}** 的進出場時機...")
        report = get_full_report(target_symbol)
        await msg.edit(content=report if report else "❌ 暫時無法分析。")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ 決策機器人 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@tasks.loop(hours=2)
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    for s in STOCK_MAP.keys():
        r = get_full_report(s)
        # 巡邏時只報有進場或出場訊號的股票
        if r and ("🟢" in r or "🔴" in r): 
            await channel.send("📢 **[市場異動警報]**\n" + r)
        await asyncio.sleep(2)

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
