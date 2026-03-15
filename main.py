import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio
from datetime import datetime

# 1. 讀取環境變數 (請確保 GitHub Secrets 已設定)
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 📌 絕對固定觀察名單 (維持 237% 報酬率的核心) ---
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "3017.TW": "奇鋐", "2603.TW": "長榮",
    "2609.TW": "陽明", "2881.TW": "富邦金", "2882.TW": "國泰金", "2886.TW": "兆豐金",
    "2412.TW": "中華電", "2357.TW": "華碩", "3711.TW": "日月光投控"
}
WATCHLIST = list(STOCK_NAMES.keys())

# --- 記憶功能：避免盤中重複轟炸 ---
def get_last_recommendation():
    if os.path.exists("last_result.txt"):
        try:
            with open("last_result.txt", "r") as f:
                return f.read().strip()
        except:
            return ""
    return ""

def save_recommendation(symbol):
    with open("last_result.txt", "w") as f:
        f.write(symbol)

async def perform_scan():
    await bot.wait_until_ready()
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    results = []
    # 進行全名單掃描
    for s in WATCHLIST:
        try:
            t = yf.Ticker(s)
            df = t.history(period="100d")
            if df.empty or len(df) < 65: continue
            
            last_p = df['Close'].iloc[-1]
            ma60 = df['Close'].tail(60).mean()
            mom20 = df['Close'].pct_change(periods=20).iloc[-1]
            
            # 濾網：只考慮季線之上的股票
            if last_p > ma60:
                results.append({
                    'symbol': s, 
                    'name': STOCK_NAMES.get(s, s), 
                    'score': mom20 * 100, 
                    'price': last_p
                })
        except:
            continue
        await asyncio.sleep(0.5)

    # 排序找出當前第一名
    results.sort(key=lambda x: x['score'], reverse=True)
    
    current_top = results[0]['symbol'] if results else "NONE"
    last_top = get_last_recommendation()
    
    # 判斷是否為週一開盤 (10:00 前) 作為每週例行報告
    now = datetime.now()
    is_monday_morning = (now.weekday() == 0 and now.hour < 11)

    # --- 盤中智慧發送邏輯 ---
    should_send = False
    msg_header = ""

    if current_top != last_top:
        # 情況 A：第一名換人了 (趨勢轉動)
        should_send = True
        msg_header = "⚡ **【盤中趨勢轉向提醒】**\n市場資金流向變動，新的領頭羊出現！"
        save_recommendation(current_top)
    elif is_monday_morning:
        # 情況 B：每週一早上的定期點名
        should_send = True
        msg_header = "📅 **【每週開盤總結】**\n目前觀察池狀況如下："
    
    if should_send:
        if results:
            top_1 = results[0]
            shares = INVEST_AMOUNT // top_1['price']
            msg = (
                f"{msg_header}\n"
                f"🏆 當前最強：**{top_1['name']}** ({top_1['symbol']})\n"
                f"✅ 操作建議：買進 `{int(shares)}` 股\n"
                f"💰 目前股價：`{top_1['price']:.2f}`\n"
                f"💡 動能分數：`{top_1['score']:.2f}`"
            )
            await channel.send(msg)
        elif last_top != "NONE":
            # 情況 C：原本有標的，盤中突然全部跌破季線 (發生大跌)
            await channel.send("⚠️ **【盤中避險警告】** 所有標的均跌破季線，趨勢轉空，請暫停買進並保留現金！")
            save_recommendation("NONE")
    
    # 執行完畢關閉機器人，省電省時數
    await bot.close()

@bot.event
async def on_ready():
    await perform_scan()

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
