import os
import discord
from discord.ext import commands
import pandas as pd
import asyncio
import json
import requests
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from flask import Flask
from threading import Thread

# --- Render 存活檢查 (維持不變) ---
app = Flask('')
@app.route('/')
def home(): return "Quant Bot 4.0: FinMind Data Engine Online!"
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
# ==========================================
# 2. 台股前瞻科技戰略包 (AI伺服器 + Rubin架構 + 低軌衛星)
# ==========================================
STOCK_NAMES = {
    # 🌟【NVIDIA Rubin 架構概念股】(先進封裝、HBM測試、矽光子CPO、次世代散熱)
    "2330.TW": "台積電", "3711.TW": "日月光投控", "3450.TW": "聯鈞", "6442.TW": "光聖",
    "3363.TW": "上詮", "3163.TW": "波若威", "4979.TW": "華星光", "6223.TW": "旺矽",
    "6515.TW": "穎崴", "3653.TW": "健策", "3324.TW": "雙鴻", "3017.TW": "奇鋐",
    "8996.TW": "高力", "3189.TW": "景碩", "3037.TW": "欣興", "2368.TW": "金像電",

    # 🚀【AI 伺服器 & 零組件大軍】(代工廠、機殼、滑軌、BMC、電源)
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2376.TW": "技嘉",
    "2356.TW": "英業達", "2357.TW": "華碩", "2377.TW": "微星", "3706.TW": "神達",
    "2059.TW": "川湖", "5274.TW": "信驊", "2308.TW": "台達電", "2301.TW": "光寶科",
    "6117.TW": "迎廣", "8210.TW": "勤誠", "3693.TW": "營邦", "3032.TW": "偉訓",

    # 🛰️【低軌衛星 LEO 概念股】(網通設備、微波元件、地面接收站、衛星PCB)
    "3491.TW": "昇達科", "6285.TW": "啟碁", "2383.TW": "華通", "3138.TW": "耀登",
    "2314.TW": "台揚", "3062.TW": "建漢", "2312.TW": "金寶", "3305.TW": "昇貿",
    "6282.TW": "康舒", "2412.TW": "中華電", 

    # 🛡️【護國群山 & 大型權值股】(維持大盤敏感度與防禦力)
    "2454.TW": "聯發科", "2317.TW": "鴻海", "3008.TW": "大立光", "2303.TW": "聯電",
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "2603.TW": "長榮",
    "2609.TW": "陽明", "1519.TW": "華城", "1514.TW": "亞力", "1503.TW": "士電",
    
    # 📈【大盤與高股息 ETF】(用來判斷大盤水位與資金避風港)
    "0050.TW": "元大台灣50", "0056.TW": "元大高股息", "00878.TW": "國泰永續高股息",
    "00929.TW": "復華台灣科技優息"
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
import traceback # 記得在最上面加上這行 (跟 import os 放一起)

async def process_stock_query(channel, symbol):
    # 發送初步確認訊息
    initial_msg = await channel.send(f"🔍 正在對 `{symbol}` 進行深度高勝率策略分析與倉位精算...")
    
    try:
        # 1. 獲取資料
        print(f"DEBUG: 準備呼叫 fetch_single_stock_data 抓取 {symbol}")
        _, df = await fetch_single_stock_data(symbol)
        
        print(f"DEBUG: fetch_single_stock_data 回傳結果，df 長度: {len(df)}")
        if df.empty or len(df) < 200:
            await initial_msg.edit(content=f"❌ `{symbol}` 歷史數據不足（需至少 200 天，目前取得 {len(df)} 天）或 API 暫時無回應。")
            return
            
        # 2. 讀取虛擬帳本
        p = load_portfolio()
        cash = p.get("cash", 0.0)
        holdings = p.get("holdings", {})
            
        # 3. 計算技術指標
        print("DEBUG: 開始計算技術指標")
        close = df['Close']
        ema200 = close.ewm(span=200, adjust=False).mean()
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        sig = macd.ewm(span=9, adjust=False).mean()
        
        curr_p = close.iloc[-1]
        curr_ema200 = ema200.iloc[-1]
        curr_macd = macd.iloc[-1]
        curr_sig = sig.iloc[-1]

        # 4. 策略判斷
        trend = "上升趨勢" if curr_p > curr_ema200 else "下降趨勢"
        is_long = (curr_p > curr_ema200) and (macd.iloc[-2] < sig.iloc[-2]) and (curr_macd > curr_sig) and (curr_macd < 0)
        
        # 5. 畫圖 
        print("DEBUG: 開始畫圖")
        chart_path = generate_advanced_chart(df, symbol)
        
        # 6. 組合報告
        msg = (
            f"📊 **{STOCK_NAMES.get(symbol, symbol)} ({symbol}) 策略與倉位報告**\n"
            f"> 1. 【趨勢】：目前處於 **{trend}** (現價 `{curr_p:.1f}` vs 200 EMA `{curr_ema200:.1f}`)\n"
            f"> 2. 【MACD】：快線 `{curr_macd:.2f}` / 慢線 `{curr_sig:.2f}` (零軸下交叉：{'✅ 是' if curr_macd < 0 else '❌ 否'})\n"
            f"> 3. 【行動】：🚀 **{'強烈建議做多' if is_long else '未達嚴格進場標準，建議觀望'}**\n"
        )
        
        if is_long:
            sl = curr_ema200 * 0.98
            tp = curr_p + (curr_p - sl) * 1.5
            msg += f"> 4. 【風險設置】：停損防線 `{sl:.1f}`，停利目標 `{tp:.1f}` (R/R 1:1.5)\n"

        # 7. 智慧倉位分析 
        msg += "\n💼 **【專屬帳戶健檢】**\n"
        if symbol in holdings:
            data_p = holdings[symbol]
            shares = data_p["shares"]
            avg_cost = data_p["avg_cost"]
            profit_pct = ((curr_p - avg_cost) / avg_cost) * 100
            
            msg += f"> 📦 庫存狀態：目前持有 `{shares}` 股 | 平均成本 `{avg_cost:.1f}` | 帳面報酬 **`{profit_pct:.1f}%`**\n"
            
            high_p = data_p.get("high_price", curr_p)
            if curr_p < curr_ema200 or curr_p < high_p * 0.85:
                msg += "> 🚨 **賣出警告**：已跌破 200 EMA 或從高點回落 15%，建議**立刻平倉賣出**！\n"
            else:
                msg += "> 🛡️ **持股建議**：目前趨勢健康，尚未觸發停利損，建議**繼續抱牢**。\n"
        else:
            if is_long:
                max_shares = int(cash // curr_p)
                if max_shares > 0:
                    msg += f"> 💰 資金評估：目前可用現金 `{cash:.0f}` 元，以現價計算，您最多可買入 **`{max_shares}` 股**。\n"
                else:
                    msg += f"> ⚠️ 資金評估：目前可用現金 `{cash:.0f}` 元，餘額不足以買入 1 股。\n"
            else:
                 msg += "> 📭 庫存狀態：目前未持有此檔股票。\n"

        # 傳送圖片與報告 (先刪除一開始的等待訊息)
        await initial_msg.delete()
        with open(chart_path, 'rb') as f:
            await channel.send(content=msg, file=discord.File(f))
        os.remove(chart_path)
        
    except Exception as e:
        # 如果發生任何錯誤，把錯誤的詳細原因 (Traceback) 傳到頻道裡
        error_msg = traceback.format_exc()
        await initial_msg.edit(content=f"❌ 系統發生嚴重錯誤！\n```python\n{error_msg}\n```")
        print(f"ERROR in process_stock_query:\n{error_msg}")
# ==========================================
# 7. 全自動巡邏引擎 (包含 15% 移動停利)
# ==========================================
import concurrent.futures

# ... (其他程式碼保持不變) ...

def get_finmind_data(symbol):
    """
    透過 FinMind API 獲取台股過去一年的歷史資料，並轉換成相容的格式
    """
    # 1. 處理代號轉換 (把 2330.TW 變成 2330，把 ^TWII 變成 TAIEX)
    stock_id = symbol.replace('.TW', '')
    if stock_id == '^TWII': 
        stock_id = 'TAIEX'

    # 2. 設定抓取時間 (過去 365 天)
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        
        # 3. 如果成功抓到資料，轉換成原本程式看得懂的格式 (DataFrame)
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.rename(columns={'close': 'Close'}, inplace=True) # 把小寫 close 換成大寫 Close
            return df
    except Exception as e:
        print(f"FinMind API 錯誤 ({stock_id}): {e}")
        
    return pd.DataFrame() # 失敗回傳空資料

async def fetch_single_stock_data(symbol, retries=2):
    """
    非同步包裝，避免卡住 Discord 機器人
    """
    loop = asyncio.get_running_loop()
    for attempt in range(retries):
        df = await loop.run_in_executor(None, get_finmind_data, symbol)
        
        if not df.empty and len(df) > 0:
            return symbol, df
            
        await asyncio.sleep(1) # 抓不到就休息一秒再試
        
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

    # 2. 判斷大盤 (雙重保險：先看大盤指數，抓不到再看 0050)
    _, df_market = await fetch_single_stock_data("^TWII")
    market_name = "加權指數 (^TWII)"
    
    if df_market.empty:
        _, df_market = await fetch_single_stock_data("0050.TW")
        market_name = "台灣 50 (0050)"

    if df_market.empty:
        msg_lines.append("⚠️ 警告：Yahoo API 異常，大盤與 0050 皆無法取得數據！保護機制啟動，暫停買進。")
        is_bull_market = False
    else:
        ma60_market = df_market['Close'].tail(60).mean()
        is_bull_market = df_market['Close'].iloc[-1] > ma60_market
        if not is_bull_market:
            msg_lines.append(f"🛑 **【大盤警報】** {market_name} 目前位於季線之下。空頭市場嚴禁做多，維持觀望！")

    # 3. 如果大盤是多頭，開始掃描 50 檔
    results = []
    if is_bull_market:
        scan_msg = await channel.send(f"✅ 大盤 ({market_name}) 確認偏多！正在逐檔掃描 50 檔成分股的 MACD 狀態，約需 30~60 秒...")
        
        for s in WATCHLIST:
            _, df = await fetch_single_stock_data(s)
            if df.empty or len(df) < 200: 
                await asyncio.sleep(0.5)
                continue
            
            close = df['Close']
            ema200 = close.ewm(span=200, adjust=False).mean()
            macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
            sig = macd.ewm(span=9, adjust=False).mean()
            
            # 策略：站上 200EMA + 零軸下金叉
            if (close.iloc[-1] > ema200.iloc[-1]) and (macd.iloc[-2] < sig.iloc[-2]) and (macd.iloc[-1] > sig.iloc[-1]) and (macd.iloc[-1] < 0):
                results.append({'symbol': s, 'price': close.iloc[-1], 'score': macd.iloc[-1] - sig.iloc[-1]})
            
            await asyncio.sleep(0.5) # 乖乖排隊不塞車
        
        try:
            await scan_msg.delete()
        except: pass

        if not results:
            msg_lines.append("🔎 **【掃描結果】** 巡邏了 50 檔旗艦股，目前 **無任何一檔** 發生「零軸下 MACD 黃金交叉」。策略嚴格執行，不胡亂追高！")

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
