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
def home(): return "全能選股機器人運行中！"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- 設定 ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

STOCK_MAP = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "0050.TW": "元大台灣50", "2301.TW": "光寶科",
    "3481.TW": "群創", "3017.TW": "奇鋐", "2344.TW": "華邦電", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控", "2603.TW": "長榮", "3231.TW": "緯創",
    "2421.TW": "建準", "3653.TW": "健策", "6197.TW": "佳必琪", "4569.TW": "六角",
    "2382.TW": "廣達", "3037.TW": "欣興", "2609.TW": "陽明", "2615.TW": "萬海"
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 輔助工具：製作強度條 ---
def make_bar(value, max_val=100):
    nodes = 10
    filled = int((value / max_val) * nodes)
    filled = max(0, min(nodes, filled))
    return "█" * filled + "░" * (nodes - filled)

# --- 核心邏輯：全能診斷 ---
def get_full_report(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="60d")
        if df.empty or len(df) < 40: return None
        
        comp_name = STOCK_MAP.get(symbol, symbol)
        
        # 1. 基礎數據
        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        day_open = df['Open'].iloc[-1]
        day_high = df['High'].iloc[-1]
        day_low = df['Low'].iloc[-1]
        change_pct = ((last_close - prev_close) / prev_close) * 100
        
        # 2. 技術指標
        ma20 = df['Close'].tail(20).mean()
        bias_20 = ((last_close - ma20) / ma20) * 100
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]

        # 成交量
        avg_vol = df['Volume'].tail(6).iloc[:-1].mean()
        curr_vol = df['Volume'].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

        # 3. 診斷邏輯評分
        score = 0
        details = []
        
        # K線顏色
        k_icon = "🔴" if last_close > day_open else "🟢"
        
        # 趨勢
        if last_close > ma20:
            score += 40
            details.append("✅ 站上月線")
        else:
            details.append("❌ 月線下方")
            
        # 動能
        if vol_ratio > 1.8:
            score += 30
            details.append("🚀 爆量發動")
            
        # 超賣
        if rsi < 35:
            score += 30
            details.append("📉 跌深反彈機會")

        # 乖離警示
        bias_msg = ""
        if bias_20 > 8: bias_msg = "⚠️ 乖離過高，勿追"
        elif bias_20 < -8: bias_msg = "📉 負乖離大，具支撐"

        # 結論
        if score >= 70: status = "🔥 強烈建議關注"
        elif score >= 40: status = "⚖️ 維持區間觀察"
        else: status = "❄️ 目前趨勢疲弱"

        # --- 組合報告 ---
        report = (
            f"🏠 **{comp_name} ({symbol})**\n"
            f"💰 **市價**: `{last_close:.2f}` ({change_pct:+.2f}%) | {k_icon}\n"
            f"📏 **乖離**: 月線 `{ma20:.2f}` (偏離 `{bias_20:.1f}%`) {bias_msg}\n"
            f"📊 **RSI**: `{rsi:.1f}` | {make_bar(rsi)}\n"
            f"📈 **量比**: `{vol_ratio:.1f}x` | {make_bar(vol_ratio * 20)}\n"
            f"----------------------------------\n"
            f"📝 **診斷**: {' / '.join(details)}\n"
            f"💡 **結論**: **{status}**"
        )
        return report

    except Exception as e:
        return f"❌ `{symbol}` 分析失敗: {str(e)}"

@bot.event
async def on_ready():
    print(f'✅ 全能選股機器人 {bot.user} 上線')
    if not auto_scan.is_running(): auto_scan.start()

@bot.command(name='查')
async def check_stock(ctx, symbol: str):
    if symbol.isdigit(): symbol = f"{symbol}.TW"
    await ctx.send(f"🔍 正在進行全能數據診斷 **{STOCK_MAP.get(symbol, symbol)}**...")
    report = get_full_report(symbol)
    await ctx.send(report if report else "❌ 暫時無法分析。")

@tasks.loop(hours=1.5)
async def auto_scan():
    if not CHANNEL_ID: return
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return
    
    target_keys = list(STOCK_MAP.keys())
    for s in target_keys:
        # 巡邏時只發送高分或爆量的
        r = get_full_report(s)
        if "🔥" in r or "🚀" in r:
            await channel.send("📢 **[自動巡邏：發現強勢標的]**\n" + r)
        await asyncio.sleep(1)

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
