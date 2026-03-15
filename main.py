import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio
import json
from datetime import datetime
import matplotlib
matplotlib.use('Agg') # 讓 matplotlib 在背景產圖，避免伺服器報錯
import matplotlib.pyplot as plt

# ==========================================
# 1. 系統設定與環境變數
# ==========================================
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000  # 每月入金預算
RUN_MODE = os.environ.get("RUN_MODE", "listen")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. 核心 50 檔旗艦觀察名單
# ==========================================
STOCK_NAMES = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "2303.TW": "聯電", "3711.TW": "日月光投控",
    "2379.TW": "瑞昱", "3008.TW": "大立光", "3034.TW": "聯詠", "2308.TW": "台達電",
    "3037.TW": "欣興", "6415.TW": "矽力*-KY", "2317.TW": "鴻海", "2382.TW": "廣達", 
    "3231.TW": "緯創", "2357.TW": "華碩", "6669.TW": "緯穎", "2324.TW": "仁寶", 
    "3017.TW": "奇鋐", "4938.TW": "和碩", "2301.TW": "光寶科", "2345.TW": "智邦", 
    "2395.TW": "研華", "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", 
    "2886.TW": "兆豐金", "2884.TW": "玉山金", "2892.TW": "第一金", "2885.TW": "元大金", 
    "5880.TW": "合庫金", "2880.TW": "華南金", "2883.TW": "開發金", "2887.TW": "台新金", 
    "2890.TW": "永豐金", "5871.TW": "中租-KY", "2603.TW": "長榮", "2609.TW": "陽明", 
    "2615.TW": "萬海", "2002.TW": "中鋼", "1101.TW": "台泥", "1301.TW": "台塑", 
    "1303.TW": "南亞", "1326.TW": "台化", "1590.TW": "亞德客-KY", "2207.TW": "和泰車", 
    "9904.TW": "寶成", "2412.TW": "中華電", "3045.TW": "台灣大", "4904.TW": "遠傳",
    "1216.TW": "統一", "2912.TW": "統一超"
}
WATCHLIST = list(STOCK_NAMES.keys())
REVERSE_STOCK_NAMES = {v: k for k, v in STOCK_NAMES.items()}

# ==========================================
# 3. 虛擬帳本系統 (Portfolio)
# ==========================================
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f: return json.load(f)
        except: pass
    # 初始化空帳本
    return {"cash": 0.0, "holdings": {}, "last_month": ""}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f: json.dump(p, f, indent=4)

# ==========================================
# 4. K線圖繪製引擎
# ==========================================
def generate_chart(df, symbol):
    plt.figure(figsize=(10, 5))
    # 畫出收盤價與季線 (使用英文避免 Linux 伺服器中文亂碼問題)
    plt.plot(df.index, df['Close'], label='Close Price', color='blue', linewidth=1.5)
    plt.plot(df.index, df['Close'].rolling(60).mean(), label='60-Day MA', color='orange', linestyle='--')
    
    plt.title(f"{symbol} - Last 100 Days")
    plt.xlabel("Date")
    plt.ylabel("Price (TWD)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    chart_path = f"chart_{symbol}.png"
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    return chart_path

# ==========================================
# 5. 單股健檢與繪圖邏輯
# ==========================================
async def process_stock_query(channel, symbol):
    await channel.send(f"🔍 正在為您繪製 `{symbol}` 的量化圖表與健檢報告...")
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="100d")
        if df.empty or len(df) < 65:
            await channel.send(f"❌ 找不到 `{symbol}` 數據。")
            return
            
        last_p = df['Close'].iloc[-1]
        ma60 = df['Close'].tail(60).mean()
        mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
        
        name = STOCK_NAMES.get(symbol, symbol)
        status = "🟢 強勢" if last_p > ma60 else "🔴 弱勢"
        
        # 產生圖片
        chart_path = generate_chart(df, symbol)
        
        msg = (
            f"📊 **{name} ({symbol}) 量化健檢報告**\n"
            f"> 💰 目前股價：`{last_p:.2f}`\n"
            f"> 📏 60日季線：`{ma60:.2f}`\n"
            f"> 🚀 動能分數：`{mom20:.2f}`\n"
            f"> 🛡️ 趨勢判定：**{status}**\n"
        )
        # 加上圖片並傳送
        with open(chart_path, 'rb') as f:
            picture = discord.File(f)
            await channel.send(content=msg, file=picture)
            
        # 傳送後刪除本地圖片檔案，節省空間
        os.remove(chart_path)
    except Exception as e:
        await channel.send(f"❌ 查詢失敗: {e}")

# ==========================================
# 6. 全頻道智慧監聽
# ==========================================
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    content = message.content.strip()

    # 指令 A：呼叫庫存帳本
    if content in ["我的庫存", "庫存", "帳本"]:
        await show_portfolio(message.channel)
        return

    # 指令 B：手動全面掃描與交易
    if content in ["全面掃描", "大盤", "投資組合"]:
        await message.channel.send("🚀 啟動全市場掃描與虛擬帳本結算...")
        await perform_scan(force_send=True)
        return

    # 指令 C：查單一股票
    target_symbol = None
    if content in REVERSE_STOCK_NAMES: target_symbol = REVERSE_STOCK_NAMES[content]
    elif content.isdigit() and len(content) == 4: target_symbol = content + ".TW"
    elif content.endswith(".TW"): target_symbol = content

    if target_symbol:
        await process_stock_query(message.channel, target_symbol)

    await bot.process_commands(message)

# ==========================================
# 7. 顯示虛擬帳本狀態
# ==========================================
async def show_portfolio(channel):
    p = load_portfolio()
    msg = f"💼 **【量化基金虛擬帳本】**\n💵 **可用現金：** `{p['cash']:.0f}` 元\n"
    
    if not p["holdings"]:
        msg += "📭 目前空手觀望中。"
    else:
        msg += "📦 **當前持股：**\n"
        total_value = p['cash']
        for sym, data in p["holdings"].items():
            name = STOCK_NAMES.get(sym, sym)
            # 抓取現價估算總值
            try:
                curr_p = yf.Ticker(sym).history(period="1d")['Close'].iloc[-1]
            except: curr_p = data["avg_cost"]
            
            profit_pct = (curr_p - data["avg_cost"]) / data["avg_cost"] * 100
            total_value += curr_p * data["shares"]
            
            msg += f"🔸 **{name}** ({sym}): `{data['shares']}` 股 | 均價 `{data['avg_cost']:.1f}` | 現價 `{curr_p:.1f}` | 報酬率 `{profit_pct:.1f}%`\n"
            msg += f"   *(歷史最高價: {data['high_price']:.1f}，跌破 {data['high_price']*0.85:.1f} 將觸發移動停利)*\n"
            
        msg += f"\n💰 **基金總淨值：** `{total_value:.0f}` 元"
    await channel.send(msg)

# ==========================================
# 8. 核心引擎 (包含移動停利與虛擬交易)
# ==========================================
async def perform_scan(force_send=False):
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    p = load_portfolio()
    msg_lines = []
    
    # 【每月定時入金】
    curr_month = datetime.now().strftime("%Y-%m")
    if p["last_month"] != curr_month:
        p["cash"] += INVEST_AMOUNT
        p["last_month"] = curr_month
        msg_lines.append(f"🏦 **【每月入金】** 系統已自動撥款 {INVEST_AMOUNT} 元，可用現金：`{p['cash']:.0f}` 元")

    # 【防線一：大盤狀態辨識】
    try:
        df_0050 = yf.Ticker("0050.TW").history(period="100d")
        is_bull_market = df_0050['Close'].iloc[-1] > df_0050['Close'].tail(60).mean()
    except: is_bull_market = False 

    # ==========================================
    # 【移動停利 / 停損機制】檢查目前庫存
    # ==========================================
    for sym, data in list(p["holdings"].items()):
        try:
            df_stock = yf.Ticker(sym).history(period="100d")
            curr_p = df_stock['Close'].iloc[-1]
            ma60 = df_stock['Close'].tail(60).mean()
            
            # 更新歷史最高價
            if curr_p > data["high_price"]:
                data["high_price"] = curr_p
                
            # 觸發條件：跌破季線，或從最高點回落 15% (移動停利)
            trailing_stop_price = data["high_price"] * 0.85
            if curr_p < ma60 or curr_p < trailing_stop_price:
                sell_val = data["shares"] * curr_p
                profit = sell_val - (data["shares"] * data["avg_cost"])
                p["cash"] += sell_val
                name = STOCK_NAMES.get(sym, sym)
                reason = "跌破季線" if curr_p < ma60 else "觸發 15% 移動停利"
                msg_lines.append(f"🚨 **【自動賣出】** {name}({sym}) {reason}！以 `{curr_p:.1f}` 賣出，獲利/虧損 `{profit:.0f}` 元。")
                del p["holdings"][sym]
        except: continue
        await asyncio.sleep(0.5)

    # ==========================================
    # 【動能尋找與買進機制】
    # ==========================================
    if not is_bull_market:
        msg_lines.append("🛑 **【大盤警報】** 台灣 50 跌破季線，暫停一切買進動作，緊抱現金！")
    else:
        results = []
        for s in WATCHLIST:
            try:
                df = yf.Ticker(s).history(period="100d")
                if df.empty or len(df) < 65: continue
                last_p = df['Close'].iloc[-1]
                if last_p > df['Close'].tail(60).mean():
                    mom20 = df['Close'].pct_change(periods=20).iloc[-1] * 100
                    results.append({'symbol': s, 'price': last_p, 'score': mom20})
            except: continue
            await asyncio.sleep(0.5)

        results.sort(key=lambda x: x['score'], reverse=True)
        top_2 = results[:2]
        
        # 虛擬買進邏輯：如果有現金，且最強的股票我們還沒滿手
        if len(top_2) > 0 and p["cash"] > 1000: # 現金大於1000才動作
            budget_per_stock = p["cash"] / len(top_2)
            msg_lines.append(f"🌞 **【大盤偏多】** 偵測到可用資金，準備買進本期最強勢股...")
            
            for stock in top_2:
                sym = stock['symbol']
                name = STOCK_NAMES.get(sym, sym)
                # 只有在手上沒有這檔股票時才買進 (避免重複建倉)
                if sym not in p["holdings"]:
                    shares_to_buy = int(budget_per_stock // stock['price'])
                    if shares_to_buy > 0:
                        cost = shares_to_buy * stock['price']
                        p["cash"] -= cost
                        p["holdings"][sym] = {
                            "shares": shares_to_buy,
                            "avg_cost": stock['price'],
                            "high_price": stock['price']
                        }
                        msg_lines.append(f"🛒 **【自動買進】** 買入 {name}({sym}) `{shares_to_buy}` 股，動能 `{stock['score']:.1f}`。")
        else:
            msg_lines.append("⏸️ 大盤偏多，但資金已滿載或無合適標的，維持現有部位。")

    # 儲存帳本
    save_portfolio(p)
    
    if force_send or msg_lines:
        header = "🚀 **【量化基金執行報告】**\n"
        await channel.send(header + "\n".join(msg_lines))

has_run_scan = False

@bot.event
async def on_ready():
    global has_run_scan
    if has_run_scan: return
    has_run_scan = True
    print(f"🤖 量化主機已連線！模式：{RUN_MODE}")
    
    if RUN_MODE == "github_cron":
        await perform_scan(force_send=True)
        await bot.close()
    else:
        channel = bot.get_channel(int(CHANNEL_ID))
        if channel:
            await channel.send("🟢 **旗艦版 3.0 已連線！**\n🔹 輸入 `庫存` 看帳戶績效\n🔹 輸入 `全面掃描` 執行買賣\n🔹 輸入 `2330` 看 K 線圖")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
