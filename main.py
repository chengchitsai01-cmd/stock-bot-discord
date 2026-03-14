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
def home(): return "智慧感應投資機器人運行中！"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

# 建立代碼與中文的「雙向」對照表
STOCK_MAP = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "0050.TW": "元大台灣50", "2301.TW": "光寶科",
    "3481.TW": "群創", "3017.TW": "奇鋐", "2344.TW": "華邦電", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控", "2603.TW": "長榮", "3231.TW": "緯創",
    "2421.TW": "建準", "3653.TW": "健策", "2382.TW": "廣達", "2609.TW": "陽明"
}
# 建立一個反向查找表 (中文 -> 代碼)
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
        if df.empty or len(df) < 40: return None
        
        info = ticker.info
        comp_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
        pe_ratio = info.get('trailingPE', 0)
        eps = info.get('trailingEps', 0)
        dividend = info.get('dividendRate', 0)
        yield_pct = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        
        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        change_pct = ((last_close - prev_close) / prev_close) * 100
        ma20 = df['Close'].tail(20).mean()
        bias_20 = ((last_close - ma20) / ma20) * 100
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
        vol_ratio = df['Volume'].iloc[-1] / df['Volume'].tail(6).iloc[:-1].mean()

        details = ["📈 趨勢偏多" if last_close > ma20 else "📉 趨勢偏空"]
        if vol_ratio > 1.8: details.append("🚀 爆量攻擊")
        
        report = (
            f"🏠 **{comp_name} ({symbol})**\n"
            f"💰 **市價**: `{last_close:.2f}` ({change_pct:+.2f}%)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 **基本面** | PE:`{pe_ratio:.1f}` EPS:`{eps:.2f}`\n"
            f"> 配息: `{dividend:.1f}` 元 (殖利率 `{yield_pct:.1f}%`)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📏 **技術面** | 乖離: `{bias_20:.1f}%` \n"
            f"> RSI: `{rsi:.1f}` | {make_bar(rsi)}\n"
            f"> 量比: `{vol_ratio:.1f}x` | {make_bar(vol_ratio * 20)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 **診斷**: {' / '.join(details)}\n"
        )
        return report
    except Exception as e:
        return f"❌ 分析失敗: {str(e)}"

# --- 智慧感應監聽器 ---
@bot.event
async def on_message(message):
    # 排除機器人自己的訊息
    if message.author == bot.user:
        return

    content = message.content.strip()
    target_symbol = None

    # 1. 判斷是否為純數字代碼 (如 2330)
    if content.isdigit() and len(content) >= 4:
        target_symbol = f"{content}.TW"
    
    # 2. 判斷是否為中文名稱 (如 台積電)
    elif content in NAME_TO_SYMBOL:
        target_symbol = NAME_TO_SYMBOL[content]

    # 如果有對應到股票，就直接查詢
    if target_symbol:
        msg = await message.channel.send(f"🔍 偵測到關鍵字，正在調閱 **{STOCK_MAP.get(target_symbol, content)}** 投資檔案...")
        report = get_full_report(target_symbol)
        await msg.edit(content=report if report else "❌ 暫時無法分析。")

    # 依然保留原本的指令功能 (!查 等等)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ 智慧感應機器人 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@tasks.loop(hours=2)
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    for s in STOCK_MAP.keys():
        r = get_full_report(s)
        if r and ("🚀" in r or "📉" in r): # 篩選有訊號的
            await channel.send("📢 **[巡邏發現異動標的]**\n" + r)
        await asyncio.sleep(2)

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
