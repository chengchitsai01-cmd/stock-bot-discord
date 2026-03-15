import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio

# 1. 讀取環境變數
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000  # 設定你每個月要投入的金額

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 台灣 50 強觀察池 (可根據需求增減)
WATCHLIST = [
    "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2881.TW", "2882.TW", "2357.TW", 
    "3711.TW", "2603.TW", "2382.TW", "3231.TW", "3008.TW", "2886.TW", "2412.TW"
]

async def perform_scan():
    await bot.wait_until_ready()
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    await channel.send(f"🔍 **[自動量化掃描啟動]** 本月預算：`{INVEST_AMOUNT}` 元")
    
    results = []
    for s in WATCHLIST:
        try:
            t = yf.Ticker(s)
            # 抓取最近 100 天數據計算季線
            df = t.history(period="100d")
            if df.empty or len(df) < 65: continue
            
            last_p = df['Close'].iloc[-1]
            ma60 = df['Close'].tail(60).mean()
            mom20 = df['Close'].pct_change(periods=20).iloc[-1] # 20日動能
            
            # 濾網：股價必須在季線之上 (確保安全)
            if last_p > ma60:
                results.append({
                    'symbol': s,
                    'name': t.info.get('shortName', s),
                    'score': mom20 * 100,
                    'price': last_p
                })
        except: continue
        await asyncio.sleep(0.5)

    # 依照動能分數排名
    results.sort(key=lambda x: x['score'], reverse=True)
    
    if results:
        top_1 = results[0]
        # 計算建議買進股數 (無條件捨去取整數)
        suggested_shares = INVEST_AMOUNT // top_1['price']
        
        msg = (
            f"🏆 **本月最強推薦：{top_1['name']} ({top_1['symbol']})**\n"
            f"📈 動能評分：`{top_1['score']:.2f}`\n"
            f"💰 目前股價：`{top_1['price']:.2f}`\n"
            f"✅ **操作建議：請買進 `{int(suggested_shares)}` 股零股**\n"
            f"---"
        )
        
        # 顯示另外兩檔備選
        if len(results) > 1:
            msg += "\n預備標的（若不想買第一名可考慮）：\n"
            for res in results[1:3]:
                msg += f"• {res['name']} ({res['symbol']}) - 現價 `{res['price']:.2f}`\n"
        
        await channel.send(msg)
    else:
        await channel.send("🛑 **警報：目前觀察池中沒有股票在安全水位（全破季線），建議本月不要買，保留現金！**")
    
    await bot.close()

@bot.event
async def on_ready():
    await perform_scan()

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
