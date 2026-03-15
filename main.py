import os
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import asyncio
import json
from datetime import datetime
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask
from threading import Thread

# --- Render 存活檢查 (Fake Web Server) ---
app = Flask('')
@app.route('/')
def home(): return "Quant Bot 4.0: MACD + EMA Strategy Online!"
def run(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): Thread(target=run).start()

# ==========================================
# 1. 系統設定與環境變數
# ==========================================
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
INVEST_AMOUNT = 5000  
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
# 3. 虛擬帳本系統
# ==========================================
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f: return json.load(f)
        except: pass
    return {"cash": 0.0, "holdings": {}, "last_month": ""}

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f: json.dump(p, f, indent=4)

# ==========================================
# 4. MACD + 200 EMA 策略邏輯與繪圖
# ==========================================
def generate_advanced_chart(df, symbol):
    plt.figure(figsize=(12, 8))
    plt.rcParams['font.family'] = 'DejaVu Sans'
    
    # 主圖：Price & 200 EMA
    ax1 = plt.subplot(2, 1, 1)
    ema200 = df['Close'].ewm(span=200, adjust=False).mean()
    plt.plot(df.index, df['Close'], label='Price', color='blue', alpha=0.6)
    plt.plot(df.index, ema200, label='200 EMA', color='red', linewidth=2)
    plt.title(f"Technical Analysis: {symbol}")
    plt.legend()
    plt.grid(True, alpha=0.3)

    # 副圖：MACD
    ax2 = plt.subplot(2, 1, 2, sharex=ax1)
    exp1 = df['Close'].ewm(span=12).mean()
    exp2 = df['Close'].ewm(span=26).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=9).mean()
    hist = macd - sig
    
    plt.plot(df.index, macd, label='MACD', color='blue')
    plt.plot(df.index, sig, label='Signal', color='orange')
    plt.bar(df.index, hist, label='Histogram', color='gray', alpha=0.3)
    plt.axhline(0, color='black', linewidth=1)
    plt.legend()
    plt.grid(True, alpha=0.3)

    chart_path = f"analysis_{symbol}.png"
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    return chart_path

# ==========================================
# 5. 智慧指令監聽
# ==========================================
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    content = message.content.strip()

    if content in ["我的庫存", "庫存", "帳本"]:
        await show_portfolio(message.channel)
        return

    if content in ["全面掃描", "大盤", "投資組合"]:
        await message.channel.send("🚀 啟動 200 EMA + MACD 全市場策略掃描...")
        await perform_scan(force_send=True)
        return

    target_symbol = None
    if content in REVERSE_STOCK_NAMES: target_symbol = REVERSE_STOCK_NAMES[content]
    elif content.isdigit() and len(content) == 4: target_symbol = content + ".TW"
    elif content.endswith(".TW"): target_symbol = content

    if target_symbol:
        await process_stock_query(message.channel, target_symbol)

    await bot.process_commands(message)

# ==========================================
# 6. 核心分析與交易引擎
# ==========================================
async def process_stock_query(channel, symbol):
    await channel.send(f"🔍 正在對 `{symbol}` 進行深度高勝率策略分析...")
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y") # 獲取一年數據以計算 200 EMA
        if df.empty or len(df) < 200:
            await channel.send(f"❌ `{symbol}` 數據不足（需至少 200 天）。")
            return
            
        # 計算指標
        close = df['Close']
        ema200 = close.ewm(span=200, adjust=False).mean()
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        sig = macd.ewm(span=9, adjust=False).mean()
        
        curr_p = close.iloc[-1]
        curr_ema200 = ema200.iloc[-1]
        curr_macd = macd.iloc[-1]
        curr_sig = sig.iloc[-1]
        prev_macd = macd.iloc[-2]
        prev_sig = sig.iloc[-2]

        # 策略判斷
        trend = "上升趨勢" if curr_p > curr_ema200 else "下降趨勢"
        is_long = (curr_p > curr_ema200) and (prev_macd < prev_sig) and (curr_macd > curr_sig) and (curr_macd < 0)
        
        chart_path = generate_advanced_chart(df, symbol)
        
        msg = (
            f"📊 **{STOCK_NAMES.get(symbol, symbol)} 策略報告**\n"
            f"> 1. 【趨勢】：目前處於 **{trend}** (Price vs 200 EMA)\n"
            f"> 2. 【MACD】：快線 `{curr_macd:.2f}` / 慢線 `{curr_sig:.2f}` (零軸下交叉：{'✅ 是' if curr_macd < 0 else '❌ 否'})\n"
            f"> 3. 【行動】：🚀 **{'可以做多' if is_long else '繼續觀望'}**\n"
        )
        
        if is_long:
            sl = curr_ema200 * 0.98
            tp = curr_p + (curr_p - sl) * 1.5
            msg += f"> 4. 【風險】：停損 `{sl:.1f}`，停利 `{tp:.1f}` (R/R 1:1.5)"

        with open(chart_path, 'rb') as f:
            await channel.send(content=msg, file=discord.File(f))
        os.remove(chart_path)
    except Exception as e:
        await channel.send(f"❌ 查詢失敗: {e}")

# ==========================================
# 7. 全自動巡邏引擎 (包含 15% 移動停利)
# ==========================================
import concurrent.futures

# ... (其他程式碼保持不變) ...

async def fetch_single_stock_data(symbol):
    """
    在獨立的線程中抓取單檔股票數據，避免阻塞主線程。
    """
    loop = asyncio.get_running_loop()
    try:
        # 使用 run_in_executor 在背景執行同步的 yfinance 查詢
        df = await loop.run_in_executor(None, lambda: yf.Ticker(symbol).history(period="1y"))
        return symbol, df
    except Exception as e:
        print(f"抓取 {symbol} 失敗: {e}")
        return symbol, pd.DataFrame() # 失敗回傳空 DataFrame

async def fetch_single_stock_data(symbol):
    """
    使用自訂 Session 抓取資料，並解開超時限制，讓 Render 慢慢算
    """
    loop = asyncio.get_running_loop()
    try:
        df = await loop.run_in_executor(
            None, 
            lambda: yf.Ticker(symbol, session=session).history(period="1y")
        )
        return symbol, df
    except Exception as e:
        print(f"抓取 {symbol} 失敗: {e}")
        return symbol, pd.DataFrame()

async def perform_scan(force_send=False):
    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel: return

    p = load_portfolio()
    msg_lines = []
    
    # 1. 處理入金
    curr_month = datetime.now().strftime("%Y-%m")
    if p.get("last_month", "") != curr_month:
        p["cash"] = p.get("cash", 0.0) + INVEST_AMOUNT
        p["last_month"] = curr_month
        msg_lines.append(f"🏦 **入金成功**：帳戶已存入 {INVEST_AMOUNT} 元，可用現金：`{p['cash']:.0f}`")

    # 2. 判斷大盤 (0050)
    _, df_0050 = await fetch_single_stock_data("0050.TW")
    if df_0050.empty:
        msg_lines.append("⚠️ 警告：無法取得 0050 數據，保護機制啟動，暫停買進。")
        is_bull_market = False
    else:
        ma60_0050 = df_0050['Close'].tail(60).mean()
        is_bull_market = df_0050['Close'].iloc[-1] > ma60_0050
        if not is_bull_market:
            msg_lines.append("🛑 **【大盤警報】** 台灣 50 (0050) 目前位於季線之下。策略規定：空頭市場嚴禁做多，機器人進入觀望模式！")

    # 3. 如果大盤是多頭，開始掃描 50 檔
    results = []
    if is_bull_market:
        scan_msg = await channel.send("⏳ 大盤確認偏多！正在逐檔掃描 50 檔成分股的 MACD 狀態，這大約需要 30 秒...")
        
        for s in WATCHLIST:
            _, df = await fetch_single_stock_data(s)
            if df.empty or len(df) < 200: continue
            
            close = df['Close']
            ema200 = close.ewm(span=200, adjust=False).mean()
            macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
            sig = macd.ewm(span=9, adjust=False).mean()
            
            # 策略：站上 200EMA + 零軸下金叉
            if (close.iloc[-1] > ema200.iloc[-1]) and (macd.iloc[-2] < sig.iloc[-2]) and (macd.iloc[-1] > sig.iloc[-1]) and (macd.iloc[-1] < 0):
                results.append({'symbol': s, 'price': close.iloc[-1], 'score': macd.iloc[-1] - sig.iloc[-1]})
        
        # 刪除「掃描中」的提示訊息
        try:
            await scan_msg.delete()
        except: pass

        if not results:
            msg_lines.append("🔎 **【掃描結果】** 巡邏了 50 檔旗艦股，目前 **沒有任何一檔** 發生「零軸下 MACD 黃金交叉」。策略嚴格執行，不胡亂追高，維持觀望！")

    # 4. 檢查現有持股 (移動停利)
    for sym, data_p in list(p.get("holdings", {}).items()):
        _, df = await fetch_single_stock_data(sym)
        if df.empty: continue
        
        curr_p = df['Close'].iloc[-1]
        ema200 = df['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        if curr_p > data_p["high_price"]: data_p["high_price"] = curr_p
            
        if curr_p < ema200 or curr_p < data_p["high_price"] * 0.85:
            sell_val = data_p["shares"] * curr_p
            profit_pct = ((curr_p - data_p["avg_cost"]) / data_p["avg_cost"]) * 100
            p["cash"] += sell_val
            name = STOCK_NAMES.get(sym, sym)
            msg_lines.append(f"🚨 **自動平倉**：{name} 觸發保護機制。賣出價 `{curr_p:.1f}` (報酬率 `{profit_pct:.1f}%`)")
            del p["holdings"][sym]

    # 5. 執行買進
    results.sort(key=lambda x: x['score'], reverse=True)
    if results and p.get("cash", 0) > 1000:
        targets = results[:2]
        budget = p["cash"] / len(targets)
        for target in targets:
            sym = target['symbol']
            if sym not in p.get("holdings", {}):
                shares = int(budget // target['price'])
                if shares > 0:
                    p["cash"] -= shares * target['price']
                    if "holdings" not in p: p["holdings"] = {}
                    p["holdings"][sym] = {"shares": shares, "avg_cost": target['price'], "high_price": target['price']}
                    msg_lines.append(f"🛒 **策略進場**：完美捕捉起漲點！買入 {STOCK_NAMES.get(sym, sym)} `{shares}` 股。")

    save_portfolio(p)
    if force_send or msg_lines:
        final_msg = "🛰️ **【量化艦隊執行報告】**\n" + "\n".join(msg_lines)
        await channel.send(final_msg[:2000])

async def show_portfolio(channel):
    p = load_portfolio()
    msg = f"💼 **帳本狀態**\n現金：`{p['cash']:.0f}` 元\n"
    for s, d in p["holdings"].items():
        msg += f"🔸 {STOCK_NAMES.get(s, s)}: `{d['shares']}`股 (均價:{d['avg_cost']:.1f})\n"
    await channel.send(msg)

has_run_scan = False
@bot.event
async def on_ready():
    global has_run_scan
    if has_run_scan: return
    has_run_scan = True
    print(f"🤖 Bot Online: {bot.user}")
    keep_alive()
    if RUN_MODE == "github_cron":
        await perform_scan(force_send=True)
        await bot.close()

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
