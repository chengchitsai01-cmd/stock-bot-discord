import os
import discord
from discord.ext import commands, tasks
import yfinance as yf
import pandas as pd
from google import genai
import asyncio

# ==========================================
# 1. 設定與金鑰讀取
# ==========================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# 機器人自動推播的頻道 ID (等等會教你怎麼拿)
CHANNEL_ID = os.environ.get("CHANNEL_ID") 

TARGET_LIST = ["2330.TW", "2454.TW", "0050.TW", "2317.TW", "3481.TW"] # 測試先放5檔

client = genai.Client(api_key=GOOGLE_API_KEY)

# 啟動機器人，設定指令前綴為 "!"
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心分析函數
# ==========================================
def get_stock_report(symbol, force_ai=False):
    try:
        ticker = yf.Ticker(symbol)
        comp_name = ticker.info.get('shortName', symbol)
        
        df = ticker.history(period="60d")
        if df.empty or len(df) < 35: return None
            
        last_close = float(df['Close'].iloc[-1])
        support = float(df['Low'].tail(20).min())
        resistance = float(df['High'].tail(20).max())
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        last_rsi = float((100 - (100 / (1 + (gain / loss)))).iloc[-1])

        is_alert = last_rsi < 35

        # force_ai=True 代表是你主動查詢的，不管 RSI 多少都叫 AI 講評！
        if is_alert or force_ai:
            alert_tag = "🚨 **[極度低估]**" if is_alert else "🎯 **[主動診斷]**"
            prompt = (f"你是操盤手。{comp_name}({symbol})現價{last_close:.2f}，RSI {last_rsi:.1f}，"
                      f"支撐{support:.2f}/壓力{resistance:.2f}。請用20字內給出操作建議。")
            ai_response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            advice = ai_response.text.strip()
        else:
            alert_tag = "📊 **[例行巡邏]**"
            advice = f"區間操作。跌近支撐 ({support:.2f}) 可撿，靠近壓力 ({resistance:.2f}) 考慮分批賣。"

        return f"{alert_tag} **{comp_name} ({symbol})**: `{last_close:.2f}`\n> {advice}\n"
    except Exception as e:
        return f"❌ `{symbol}` 查詢失敗: {str(e)}\n"

# ==========================================
# 3. 機器人事件與指令
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ 機器人 {bot.user} 已成功上線！')
    # 啟動背景定時巡邏任務
    if not auto_scan.is_running():
        auto_scan.start()

# 主動查詢指令：例如在頻道輸入 "!查 2330"
@bot.command(name='查')
async def check_stock(ctx, symbol: str):
    # 如果使用者只輸入數字，自動幫他加上 .TW
    if symbol.isdigit():
        symbol = f"{symbol}.TW"
        
    await ctx.send(f"🔍 收到！正在為您深度分析 `{symbol}`，請稍候...")
    
    # 這裡因為需要運算時間，我們讓它跑一下
    report = get_stock_report(symbol, force_ai=True)
    
    if report:
        await ctx.send(report)
    else:
        await ctx.send(f"❌ 找不到 `{symbol}` 的歷史資料。")

# ==========================================
# 4. 背景定時巡邏任務 (每 30 分鐘執行一次)
# ==========================================
@tasks.loop(minutes=30)
async def auto_scan():
    if not CHANNEL_ID:
        print("尚未設定推播的 CHANNEL_ID")
        return
        
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel:
        return

    batch_reports = []
    for symbol in TARGET_LIST:
        report = get_stock_report(symbol) # 這裡預設只有觸發 RSI < 35 才會叫 AI
        if report:
            batch_reports.append(report)
        await asyncio.sleep(2) # 避開 API 頻率限制
    
    if batch_reports:
        full_msg = f"📈 **股市每半小時自動巡邏報告**\n" + "\n".join(batch_reports)
        # 如果訊息太長，這裡可以做切片，但目前只有5檔一定沒問題
        await channel.send(full_msg)

# 執行機器人
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        bot.run(DISCORD_BOT_TOKEN)
    else:
        print("❌ 找不到 DISCORD_BOT_TOKEN")
