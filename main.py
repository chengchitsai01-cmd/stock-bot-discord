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
# 執行模式：github_cron (定時執行後關機) 或 listen (常駐監聽指令)
RUN_MODE = os.environ.get("RUN_MODE", "listen") 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心 15 勇士觀察名單
# ==========================================
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "3017.TW": "奇鋐", "2603.TW": "長榮",
    "2609.TW": "陽明", "2881.TW": "富邦金", "2882.TW": "國泰金", "2886.TW": "兆豐金",
    "2412.TW": "中華電", "2357.TW": "華碩", "3711.TW": "日月光投控"
}
WATCHLIST = list(STOCK_NAMES.keys())

# --- 狀態記憶功能 ---
def get_last_state():
    if os.path.exists("last_state.txt"):
        try:
            with open("last_state.txt", "r") as f: return f.read().strip()
        except: return ""
    return ""

def save_state(state_str):
    with open("last_state.txt", "w") as f: f.write(state_str)

# ==========================================
# 3. 手動查詢機制 (指令：!查詢 代碼)
# ==========================================
@bot.command(name="查詢")
async def query_stock(ctx, symbol: str):
    await ctx.send(f"🔍 啟動量化雷達，正在計算 `{symbol}` 的動能與趨勢...")
    try:
        # 自動防呆：如果使用者只輸入 2330，自動補上 .TW
        if not symbol.endswith(".TW") and symbol.isdigit():
            symbol += ".TW"
            
        t = yf.Ticker(symbol)
        df = t.history(period="100d")
        
        if df.empty or len(df) < 65:
            await ctx.send(f"❌ 找不到 `{symbol}` 的有效數據，請確認代碼是否正確。")
            return
            
        last_p = df['Close'].iloc[-1]
        ma60 = df['Close'].tail(60).mean()
        # 動能分數：近 20 日漲幅百分比
        mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
        
        name = STOCK_NAMES.get(symbol, t.info.get('shortName', symbol))
        status = "🟢 強勢 (季線之上)" if last_p > ma60 else "🔴 弱勢 (跌破季線)"
        
        msg = (
            f"📊 **{name} ({symbol}) 量化健檢報告**\n"
            f"> 💰 目前股價：`{last_p:.2f}`\n"
            f"> 📏 60日季線：`{ma60:.2f}`\n"
            f"> 🚀 動能分數：`{mom20:.2f}` (近20日漲跌幅)\n"
            f"> 🛡️ 趨勢判定：**{status}**\n"
            f"---"
        )
        
        if last_p > ma60 and mom20 > 5:
            msg += "\n✅ **診斷：趨勢向上且動能強勁，為標準多頭攻擊型態。**"
        elif last_p > ma60 and mom20 <= 5:
            msg += "\n⚠️ **診斷：趨勢雖在季線之上，但近期動能溫吞，處於盤整。**"
        else:
            msg += "\n🛑 **診斷：已跌破季線，趨勢轉空，強烈建議避開或停損！**"
            
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ 查詢失敗，可能是 Yahoo Finance 阻擋了請求或代碼錯誤。")

# ==========================================
# 4. 核心量化引擎 (定時大盤與名單掃描)
# ==========================================
async def perform_scan():
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    # 【大盤濾網】
    try:
        df_0050 = yf.Ticker("0050.TW").history(period="100d")
        is_bull_market = df_0050['Close'].iloc[-1] > df_0050['Close'].tail(60).mean()
    except: is_bull_market = False 

    current_state_signature = ""
    msg_lines = []

    if not is_bull_market:
        current_state_signature = "BEAR_CASH"
        msg_lines.append("🛑 **【大盤警報：空頭避險模式】**\n台灣 50 (0050) 跌破季線，系統判定風險過高。\n✅ **操作指令：全面停止買進，請緊抱現金！**")
    else:
        results = []
        for s in WATCHLIST:
            try:
                df = yf.Ticker(s).history(period="100d")
                if df.empty or len(df) < 65: continue
                last_p = df['Close'].iloc[-1]
                
                # 【個股季線濾網】
                if last_p > df['Close'].tail(60).mean():
                    mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
                    results.append({'symbol': s, 'name': STOCK_NAMES.get(s, s), 'price': last_p, 'score': mom20})
            except: continue
            await asyncio.sleep(0.5) # 避免 API 抓太快被鎖

        # 依照動能分數排序
        results.sort(key=lambda x: x['score'], reverse=True)

        if len(results) >= 2:
            top_2 = results[:2]
            current_state_signature = f"BULL_{top_2[0]['symbol']}_{top_2[1]['symbol']}"
            msg_lines.append(f"🌞 **【多頭晴天】大盤站上季線，本期動能雙箭頭 (總預算 {INVEST_AMOUNT} 元)：**")
            
            for i, stock in enumerate(top_2, 1):
                shares = (INVEST_AMOUNT // 2) // stock['price']
                msg_lines.append(f"{i}. **{stock['name']}** ({stock['symbol']})")
                msg_lines.append(f"   └ 買進 `{int(shares)}` 股 | 動能分數: `{stock['score']:.1f}` | 現價: `{stock['price']:.2f}`")
        else:
            current_state_signature = "BULL_WEAK"
            msg_lines.append("⚠️ **【市場警報：結構偏弱】**\n符合強勢條件的標的不足，假突破機率高，建議本期保留現金觀望。")

    # 狀態比對與發送
    last_state = get_last_state()
    is_monday_morning = (datetime.now().weekday() == 0 and datetime.now().hour < 11)

    if current_state_signature != last_state or is_monday_morning:
        header = "🔄 **【策略組合變更通知】**\n" if current_state_signature != last_state else "📅 **【每週量化巡邏報告】**\n"
        await channel.send(header + "\n".join(msg_lines))
        save_state(current_state_signature)

# ==========================================
# 5. 啟動與模式控制
# ==========================================
@bot.event
async def on_ready():
    print(f"🤖 量化主機已連線！當前執行模式：{RUN_MODE}")
    
    if RUN_MODE == "github_cron":
        # GitHub 排程模式：執行完掃描後立刻關機，保護免費額度
        await perform_scan()
        await bot.close()
    else:
        # 常駐監聽模式 (本機執行)：發送上線通知，並持續等待 !查詢 指令
        channel = bot.get_channel(int(CHANNEL_ID))
        if channel:
            await channel.send("🟢 **量化主機已在本機端連線！您可以隨時輸入 `!查詢 股票代號` (例如 `!查詢 2382`) 進行即時健檢。**")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
