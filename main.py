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
INVEST_AMOUNT = 5000  
RUN_MODE = os.environ.get("RUN_MODE", "listen") 

# 開啟機器人的意圖 (Intents)，允許它讀取訊息內容
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心 15 勇士觀察名單與字典
# ==========================================
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "3017.TW": "奇鋐", "2603.TW": "長榮",
    "2609.TW": "陽明", "2881.TW": "富邦金", "2882.TW": "國泰金", "2886.TW": "兆豐金",
    "2412.TW": "中華電", "2357.TW": "華碩", "3711.TW": "日月光投控"
}
WATCHLIST = list(STOCK_NAMES.keys())

# 建立反向字典，讓機器人可以聽懂「台積電」並轉成「2330.TW」
REVERSE_STOCK_NAMES = {v: k for k, v in STOCK_NAMES.items()}

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
# 3. 獨立的查詢引擎邏輯
# ==========================================
async def process_stock_query(channel, symbol):
    await channel.send(f"🔍 收到！正在為您掃描 `{symbol}` 的量化狀態...")
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="100d")
        
        if df.empty or len(df) < 65:
            await channel.send(f"❌ 找不到 `{symbol}` 的有效數據，請確認代碼是否正確。")
            return
            
        last_p = df['Close'].iloc[-1]
        ma60 = df['Close'].tail(60).mean()
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
            
        await channel.send(msg)
    except Exception as e:
        print(f"查詢發生錯誤: {e}")
        await channel.send("❌ 查詢失敗，可能是 Yahoo Finance 阻擋了請求。")

# ==========================================
# 4. 全頻道智慧監聽 (無指令觸發) + 聽診器除錯
# ==========================================
@bot.event
async def on_message(message):
    # 🎧 聽診器：只要頻道有人講話，就在你的黑色終端機畫面印出來
    print(f"💬 [測試] 聽到 {message.author} 說了：{message.content}")

    # 避免機器人自己回自己，造成無限迴圈
    if message.author == bot.user:
        return

    # 取得使用者輸入的文字並去除前後空白
    content = message.content.strip()
    target_symbol = None

    # 智慧判斷邏輯：
    if content in REVERSE_STOCK_NAMES:
        target_symbol = REVERSE_STOCK_NAMES[content]
    elif content.isdigit() and len(content) == 4:
        target_symbol = content + ".TW"
    elif content.endswith(".TW") and content[:-3].isdigit() and len(content[:-3]) == 4:
        target_symbol = content

    # 如果判斷出這是一檔股票，就啟動查詢引擎
    if target_symbol:
        await process_stock_query(message.channel, target_symbol)

    # 讓 bot 繼續處理其他可能的潛在預設指令
    await bot.process_commands(message)

# ==========================================
# 5. 核心量化引擎 (定時大盤與名單掃描)
# ==========================================
async def perform_scan():
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: 
        print("找不到頻道！請確認 CHANNEL_ID 是否正確。")
        return

    try:
        df_0050 = yf.Ticker("0050.TW").history(period="100d")
        is_bull_market = df_0050['Close'].iloc[-1] > df_0050['Close'].tail(60).mean()
    except: is_bull_market = False 

    current_state_signature = ""
    msg_lines = []

    if not is_bull_market:
        current_state_signature = "BEAR_CASH"
        msg_lines.append("🛑 **【大盤警報：空頭避險模式】**\n大盤跌破季線，風險過高，請緊抱現金！")
    else:
        results = []
        for s in WATCHLIST:
            try:
                df = yf.Ticker(s).history(period="100d")
                if df.empty or len(df) < 65: continue
                last_p = df['Close'].iloc[-1]
                
                if last_p > df['Close'].tail(60).mean():
                    mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
                    results.append({'symbol': s, 'name': STOCK_NAMES.get(s, s), 'price': last_p, 'score': mom20})
            except: continue
            await asyncio.sleep(0.5)

        results.sort(key=lambda x: x['score'], reverse=True)

        if len(results) >= 2:
            top_2 = results[:2]
            current_state_signature = f"BULL_{top_2[0]['symbol']}_{top_2[1]['symbol']}"
            msg_lines.append(f"🌞 **【多頭晴天】大盤站上季線，本期動能雙箭頭 (總預算 {INVEST_AMOUNT} 元)：**")
            for i, stock in enumerate(top_2, 1):
                shares = (INVEST_AMOUNT // 2) // stock['price']
                msg_lines.append(f"{i}. **{stock['name']}** | 買進 `{int(shares)}` 股 | 動能分數: `{stock['score']:.1f}`")
        else:
            current_state_signature = "BULL_WEAK"
            msg_lines.append("⚠️ **【市場警報：結構偏弱】** 符合強勢條件標的不足，建議保留現金。")

    last_state = get_last_state()
    is_monday_morning = (datetime.now().weekday() == 0 and datetime.now().hour < 11)

    if current_state_signature != last_state or is_monday_morning:
        header = "🔄 **【策略組合變更通知】**\n" if current_state_signature != last_state else "📅 **【每週量化巡邏報告】**\n"
        await channel.send(header + "\n".join(msg_lines))
        save_state(current_state_signature)

# ==========================================
# 6. 啟動與模式控制 (加入防重複執行保險絲)
# ==========================================
has_run_scan = False

@bot.event
async def on_ready():
    global has_run_scan
    if has_run_scan: return
        
    has_run_scan = True
    print(f"🤖 量化主機已連線！當前執行模式：{RUN_MODE}")
    
    if RUN_MODE == "github_cron":
        print("⏳ 開始執行 GitHub 排程掃描...")
        await perform_scan()
        print("✅ 掃描完成，準備關閉連線...")
        await bot.close()
    else:
        channel = bot.get_channel(int(CHANNEL_ID))
        if channel:
            print("🟢 進入常駐監聽模式，等待指令...")
            await channel.send("🟢 **量化主機已連線！您可以直接在對話框輸入「代碼 (如 2330)」或「名稱 (如 廣達)」來查詢。**")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
