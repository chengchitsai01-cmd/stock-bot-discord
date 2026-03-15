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
RUN_MODE = os.environ.get("RUN_MODE", "listen") # 執行模式：github_cron 或 listen

# 🌟 開啟機器人的意圖 (Intents)，允許它讀取對話內容
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心觀察名單 (全面擴充至台灣 50 大企業)
# ==========================================
STOCK_NAMES = {
    # 半導體 & 電子零組件
    "2330.TW": "台積電", "2454.TW": "聯發科", "2303.TW": "聯電", "3711.TW": "日月光投控",
    "2379.TW": "瑞昱", "3008.TW": "大立光", "3034.TW": "聯詠", "2308.TW": "台達電",
    "3037.TW": "欣興", "6415.TW": "矽力*-KY",
    # 電腦及週邊設備 (AI 伺服器群)
    "2317.TW": "鴻海", "2382.TW": "廣達", "3231.TW": "緯創", "2357.TW": "華碩",
    "6669.TW": "緯穎", "2324.TW": "仁寶", "3017.TW": "奇鋐", "4938.TW": "和碩",
    "2301.TW": "光寶科", "2345.TW": "智邦", "2395.TW": "研華",
    # 金融保險
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金",
    "2884.TW": "玉山金", "2892.TW": "第一金", "2885.TW": "元大金", "5880.TW": "合庫金",
    "2880.TW": "華南金", "2883.TW": "開發金", "2887.TW": "台新金", "2890.TW": "永豐金",
    "5871.TW": "中租-KY",
    # 航運 & 傳產 & 原物料
    "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "2002.TW": "中鋼",
    "1101.TW": "台泥", "1301.TW": "台塑", "1303.TW": "南亞", "1326.TW": "台化",
    "1590.TW": "亞德客-KY", "2207.TW": "和泰車", "9904.TW": "寶成",
    # 電信 & 民生消費
    "2412.TW": "中華電", "3045.TW": "台灣大", "4904.TW": "遠傳",
    "1216.TW": "統一", "2912.TW": "統一超"
}
WATCHLIST = list(STOCK_NAMES.keys())

# 建立反向字典，讓機器人可以聽懂中文名稱並轉成代碼
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
# 3. 獨立的查詢引擎邏輯 (包含專屬交易策略)
# ==========================================
async def process_stock_query(channel, symbol):
    await channel.send(f"🔍 收到！正在為您掃描 `{symbol}` 的量化狀態與交易策略...")
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
        
        # 💡 計算單次查詢的交易策略 (以設定的 INVEST_AMOUNT 預算為基準)
        shares_to_buy = INVEST_AMOUNT // last_p
        
        msg = (
            f"📊 **{name} ({symbol}) 量化健檢報告**\n"
            f"> 💰 目前股價：`{last_p:.2f}`\n"
            f"> 📏 60日季線：`{ma60:.2f}`\n"
            f"> 🚀 動能分數：`{mom20:.2f}` (近20日漲跌幅)\n"
            f"> 🛡️ 趨勢判定：**{status}**\n"
            f"---"
        )
        
        # 根據量化數據給出明確的操作策略
        if last_p > ma60 and mom20 > 5:
            msg += (
                f"\n✅ **診斷：趨勢向上且動能強勁，為標準多頭攻擊型態。**\n"
                f"🎯 **交易策略：若要單筆投入，建議買進 `{int(shares_to_buy)}` 股 (約 {INVEST_AMOUNT} 元)。**"
            )
        elif last_p > ma60 and mom20 <= 5:
            msg += (
                f"\n⚠️ **診斷：趨勢雖在季線之上，但近期動能溫吞，處於盤整。**\n"
                f"🎯 **交易策略：建議觀望，或僅縮小部位買進 `{int(shares_to_buy // 2)}` 股試單。**"
            )
        else:
            msg += (
                f"\n🛑 **診斷：已跌破季線，趨勢轉空！**\n"
                f"🎯 **交易策略：強烈建議避開或停損，請將資金保留為現金。**"
            )
            
        await channel.send(msg)
    except Exception as e:
        print(f"查詢發生錯誤: {e}")
        await channel.send("❌ 查詢失敗，可能是 Yahoo Finance 阻擋了請求。")

# ==========================================
# 4. 全頻道智慧監聽 (無指令觸發 + 老闆暗號)
# ==========================================
@bot.event
async def on_message(message):
    # 🎧 聽診器：只要頻道有人講話，就在終端機畫面印出來
    print(f"💬 [對話紀錄] {message.author}: {message.content}")

    # 避免機器人自己回自己，造成無限迴圈
    if message.author == bot.user:
        return

    # 取得使用者輸入的文字並去除前後空白
    content = message.content.strip()

    # 🌟 老闆專屬暗號：強制呼叫大盤與投資組合報告
    if content in ["全面掃描", "大盤", "投資組合"]:
        await message.channel.send("🚀 收到指令！正在喚醒量化經理人，執行 50 檔旗艦全市場掃描 (約需 25 秒)...")
        await perform_scan(force_send=True) # 強制發送報告
        return

    target_symbol = None

    # 智慧判斷邏輯：
    # 1. 輸入中文名稱 (例如: "長榮")
    if content in REVERSE_STOCK_NAMES:
        target_symbol = REVERSE_STOCK_NAMES[content]
    # 2. 輸入 4 位數字 (例如: "2603")
    elif content.isdigit() and len(content) == 4:
        target_symbol = content + ".TW"
    # 3. 輸入完整代碼 (例如: "2603.TW")
    elif content.endswith(".TW") and content[:-3].isdigit() and len(content[:-3]) == 4:
        target_symbol = content

    # 如果判斷出這是一檔股票，就啟動查詢引擎
    if target_symbol:
        await process_stock_query(message.channel, target_symbol)

    # 讓 bot 繼續處理其他可能的潛在預設指令
    await bot.process_commands(message)

# ==========================================
# 5. 核心量化引擎 (定時大盤與名單掃描，含投資組合配置)
# ==========================================
async def perform_scan(force_send=False):
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: 
        print("找不到頻道！請確認環境變數 CHANNEL_ID 是否正確。")
        return

    try:
        # 【大盤狀態辨識】
        df_0050 = yf.Ticker("0050.TW").history(period="100d")
        is_bull_market = df_0050['Close'].iloc[-1] > df_0050['Close'].tail(60).mean()
    except: 
        is_bull_market = False 

    current_state_signature = ""
    msg_lines = []

    if not is_bull_market:
        current_state_signature = "BEAR_CASH"
        msg_lines.append("🛑 **【大盤警報：空頭避險模式】**\n台灣 50 (0050) 已跌破季線，整體市場風險過高。\n✅ **操作指令：全面停止買進，請緊抱現金，等待落底！**")
    else:
        results = []
        for s in WATCHLIST:
            try:
                df = yf.Ticker(s).history(period="100d")
                if df.empty or len(df) < 65: continue
                last_p = df['Close'].iloc[-1]
                
                # 【個股必須在季線之上】
                if last_p > df['Close'].tail(60).mean():
                    mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
                    results.append({'symbol': s, 'name': STOCK_NAMES.get(s, s), 'price': last_p, 'score': mom20})
            except: continue
            await asyncio.sleep(0.5) # 💡 保護機制：50檔掃描約需等待 25 秒，避免被鎖 IP

        # 依照動能分數排序 (強者恆強)
        results.sort(key=lambda x: x['score'], reverse=True)

        if len(results) >= 2:
            # 【投資組合最佳化：選前兩名，預算各半】
            top_2 = results[:2]
            budget_per_stock = INVEST_AMOUNT // 2
            current_state_signature = f"BULL_{top_2[0]['symbol']}_{top_2[1]['symbol']}"
            
            msg_lines.append(f"🌞 **【多頭晴天】大盤站上季線，允許攻擊！**")
            msg_lines.append(f"🎯 **本期 50 檔成分股中最強雙箭頭 (總預算 {INVEST_AMOUNT} 元)：**")
            
            for i, stock in enumerate(top_2, 1):
                shares = budget_per_stock // stock['price']
                msg_lines.append(f"{i}. **{stock['name']}** ({stock['symbol']})")
                msg_lines.append(f"   └ 建議買進：`{int(shares)}` 股 (約 {int(shares * stock['price'])} 元) | 動能: `{stock['score']:.1f}`")
        else:
            current_state_signature = "BULL_WEAK"
            msg_lines.append("⚠️ **【市場背離警報】**\n大盤雖強，但核心名單內符合強勢條件的標的不足（假突破機率高）。\n✅ **操作指令：本期建議暫停買進，保留現金觀望。**")

    # 發送邏輯
    last_state = get_last_state()
    now = datetime.now()
    is_monday_morning = (now.weekday() == 0 and now.hour < 11)

    # 🌟 邏輯修改：加上 force_send，只要是你手動查的，就算狀態沒變也會印出來給你！
    if force_send or current_state_signature != last_state or is_monday_morning:
        if force_send:
            header = "🚀 **【手動全面掃描報告】**\n"
        elif current_state_signature != last_state:
            header = "🔄 **【量化策略組合變更通知】**\n"
        else:
            header = "📅 **【每週量化巡邏報告】**\n"
            
        await channel.send(header + "\n".join(msg_lines))
        save_state(current_state_signature)

# ==========================================
# 6. 啟動與模式控制 (加入防重複執行保險絲)
# ==========================================
has_run_scan = False

@bot.event
async def on_ready():
    global has_run_scan
    
    # 防止網路不穩導致的重複執行
    if has_run_scan: 
        return
        
    has_run_scan = True
    print(f"🤖 量化主機已連線！當前執行模式：{RUN_MODE}")
    
    if RUN_MODE == "github_cron":
        # GitHub 排程模式
        print("⏳ 開始執行 GitHub 排程掃描...")
        await perform_scan()
        print("✅ 掃描完成，準備關閉連線...")
        await bot.close()
    else:
        # 本機監聽模式
        channel = bot.get_channel(int(CHANNEL_ID))
        if channel:
            print("🟢 進入常駐監聽模式，等待 Discord 頻道指令...")
            await channel.send("🟢 **量化大腦已連線！(目前守備範圍：台灣 50 旗艦成分股)**\n您可以直接輸入「股票代碼」查個股，或輸入「全面掃描」查看大盤與投資組合策略。")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
