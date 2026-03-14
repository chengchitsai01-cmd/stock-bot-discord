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
def home(): return "台股量化交易主機運行中！"
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

# --- 核心：台股雙引擎量化模型 ---
def run_quant_model(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="100d")
        if df.empty or len(df) < 65: return None
        
        info = ticker.info
        comp_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
        
        # 抓取數據
        last_close = df['Close'].iloc[-1]
        ma20 = df['Close'].tail(20).mean()
        ma60 = df['Close'].tail(60).mean()
        vol_ratio = df['Volume'].iloc[-1] / df['Volume'].tail(6).iloc[:-1].mean() if df['Volume'].tail(6).iloc[:-1].mean() > 0 else 1
        
        eps = info.get('trailingEps', 0) or 0
        pe = info.get('trailingPE', 999) or 999
        roe = info.get('returnOnEquity', 0) or 0
        
        # 📈 開始量化評分 (滿分 100)
        score = 0
        factors = []

        # [基本面引擎]
        if eps > 0: 
            score += 15
            factors.append("✅ 具獲利能力(EPS>0)")
        if roe > 0.10: 
            score += 15
            factors.append(f"✅ 高股東報酬(ROE>10%)")
        if pe < 25: 
            score += 10
            factors.append(f"✅ 估值合理(PE:{pe:.1f})")

        # [技術面引擎]
        if last_close > ma60:
            score += 20
            factors.append("📈 長線多頭(站上季線)")
        if last_close > ma20:
            score += 20
            factors.append("🔥 短線轉強(站上月線)")
        if vol_ratio > 1.5:
            score += 20
            factors.append(f"🚀 動能發動(量增{vol_ratio:.1f}倍)")

        # 🎯 決策輸出
        if score >= 85:
            action = "🌟 【極力推薦】雙引擎共振！基本面優良且技術面剛爆量發動，強烈建議進場。"
        elif score >= 65:
            action = "🟢 【偏多操作】體質不錯且趨勢向上，可沿著月線逢低佈局。"
        elif score >= 40:
            action = "🟡 【觀望盤整】動能不足或估值偏高，建議多看少做。"
        else:
            action = "🔴 【避開弱勢】空頭趨勢或基本面不佳，資金請撤離。"

        # 組合報告
        report = (
            f"📊 **量化交易主機 ➔ {comp_name} ({symbol})**\n"
            f"💰 **市價**: `{last_close:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏆 **綜合量化評分**: **{score} / 100** 分\n"
            f"💡 **觸發因子**:\n" + "\n".join([f"> {f}" for f in factors]) + "\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **演算法判定**: {action}"
        )
        return report, score
    except Exception as e:
        return f"❌ {symbol} 運算失敗: {str(e)}", 0

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
        msg = await message.channel.send(f"⚙️ 啟動多因子演算法，正在計算 **{STOCK_MAP.get(target_symbol, content)}** 的量化分數...")
        report, score = run_quant_model(target_symbol)
        await msg.edit(content=report if report else "❌ 暫時無法分析。")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ 量化交易主機 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@tasks.loop(hours=2)
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    
    await channel.send("🚀 **[量化主機自動掃描] 尋找分數 >= 85 的飆股...**")
    found_any = False
    for s in STOCK_MAP.keys():
        report, score = run_quant_model(s)
        # 嚴格濾網：只有綜合評分超過 85 分的完美股票才自動推播
        if score >= 85: 
            await channel.send(report)
            found_any = True
        await asyncio.sleep(2)
    
    if not found_any:
        await channel.send("💤 目前掃描池中無符合「雙引擎共振」的標的，嚴守紀律，持幣等待。")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
