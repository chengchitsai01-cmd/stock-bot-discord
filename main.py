import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio
from datetime import datetime

# ==========================================
# 1. 系統設定與環境變數
# ==========================================
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000  # 每月總預算

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心 15 勇士觀察名單 (嚴選台股各產業龍頭)
# ==========================================
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "3017.TW": "奇鋐", "2603.TW": "長榮",
    "2609.TW": "陽明", "2881.TW": "富邦金", "2882.TW": "國泰金", "2886.TW": "兆豐金",
    "2412.TW": "中華電", "2357.TW": "華碩", "3711.TW": "日月光投控"
}
WATCHLIST = list(STOCK_NAMES.keys())

# ==========================================
# 3. 記憶狀態管理 (避免盤中重複轟炸)
# ==========================================
def get_last_state():
    if os.path.exists("last_state.txt"):
        try:
            with open("last_state.txt", "r") as f:
                return f.read().strip()
        except: return ""
    return ""

def save_state(state_str):
    with open("last_state.txt", "w") as f:
        f.write(state_str)

# ==========================================
# 4. 核心量化引擎
# ==========================================
async def perform_scan():
    await bot.wait_until_ready()
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    # 【防線一：大盤狀態辨識 (Market Regime)】
    try:
        t_0050 = yf.Ticker("0050.TW")
        df_0050 = t_0050.history(period="100d")
        market_price = df_0050['Close'].iloc[-1]
        market_ma60 = df_0050['Close'].tail(60).mean()
        is_bull_market = market_price > market_ma60
    except:
        # 如果抓不到大盤，為了安全起見預設為危險狀態
        is_bull_market = False 

    current_state_signature = ""
    msg_lines = []

    if not is_bull_market:
        # ⛈️ 空頭雨天模式：大盤跌破季線，強制空手
        current_state_signature = "BEAR_CASH"
        msg_lines.append("🛑 **【大盤警報：空頭避險模式】**")
        msg_lines.append("台灣 50 (0050) 已跌破 60 日季線，系統判定整體市場風險過高。")
        msg_lines.append("✅ **操作指令：全面停止買進，請緊抱現金，等待市場落底！**")
    else:
        # 🌞 多頭晴天模式：掃描個股動能
        results = []
        for s in WATCHLIST:
            try:
                t = yf.Ticker(s)
                df = t.history(period="100d")
                if df.empty or len(df) < 65: continue
                
                last_p = df['Close'].iloc[-1]
                ma60 = df['Close'].tail(60).mean()
                mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
                
                # 【防線二：個股必須在季線之上】
                if last_p > ma60:
                    results.append({
                        'symbol': s, 'name': STOCK_NAMES.get(s, s), 
                        'price': last_p, 'score': mom20
                    })
            except: continue
            await asyncio.sleep(0.5)

        # 依照 20 日動能排序 (強者恆強)
        results.sort(key=lambda x: x['score'], reverse=True)

        if len(results) >= 2:
            # 【防線三：投資組合分散 (買前兩名)】
            top_2 = results[:2]
            budget_per_stock = INVEST_AMOUNT // 2
            current_state_signature = f"BULL_{top_2[0]['symbol']}_{top_2[1]['symbol']}"
            
            msg_lines.append("🌞 **【市場狀態：多頭晴天】大盤站上季線，允許攻擊！**")
            msg_lines.append(f"🎯 **本期動能最強雙箭頭 (總預算 {INVEST_AMOUNT} 元)：**")
            
            for i, stock in enumerate(top_2, 1):
                shares = budget_per_stock // stock['price']
                msg_lines.append(f"{i}. **{stock['name']}** ({stock['symbol']})")
                msg_lines.append(f"   └ 建議買進：`{int(shares)}` 股 | 動能分數: `{stock['score']:.1f}` | 現價: `{stock['price']:.2f}`")
        elif len(results) == 1:
            # 只有一檔符合條件
            top_1 = results[0]
            shares = INVEST_AMOUNT // top_1['price']
            current_state_signature = f"BULL_{top_1['symbol']}_ONLY"
            msg_lines.append("⚠️ **【市場警報：結構偏弱】** 僅剩一檔標的維持在季線之上。")
            msg_lines.append(f"🎯 建議將全額預算投入：**{top_1['name']}**，買進 `{int(shares)}` 股。")
        else:
            # 大盤在季線上，但 15 檔龍頭全破季線 (罕見背離現象)
            current_state_signature = "BULL_DIVERGENCE_CASH"
            msg_lines.append("⚠️ **【市場背離警報】** 大盤雖強，但核心觀察名單全數轉弱跌破季線。")
            msg_lines.append("✅ **操作指令：假突破機率高，本月暫停買進，保留現金！**")

    # ==========================================
    # 5. 智慧發送邏輯 (結合排程)
    # ==========================================
    last_state = get_last_state()
    now = datetime.now()
    # 判斷是否為每週一早上 10 點前 (例行公事)
    is_monday_morning = (now.weekday() == 0 and now.hour < 10)

    # 只有狀態改變，或者是週一早上，才發送 Discord 訊息
    if current_state_signature != last_state or is_monday_morning:
        header = "🔄 **【策略組合變更通知】**\n" if current_state_signature != last_state else "📅 **【每週量化巡邏報告】**\n"
        final_msg = header + "\n".join(msg_lines)
        await channel.send(final_msg)
        save_state(current_state_signature)

    await bot.close()

@bot.event
async def on_ready():
    print("🤖 系統啟動，準備執行量化掃描...")
    await perform_scan()

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
