import pandas as pd
import yfinance as yf
import requests
import os
import json
import time
import datetime

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

favorites = []
if os.path.exists('favorites.json'):
    try:
        with open('favorites.json', 'r') as f: favorites = json.load(f)
    except: pass

try:
    df = pd.read_csv('raw_stock_data.csv')
    screener_tickers = df['記号'].dropna().tolist()[:100]
except:
    screener_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

all_tickers = list(set(screener_tickers + favorites))
buy_messages = []
momentum_messages = []
sell_messages = []

print("究極精度（決算サイクル完全網羅＆大化け検知）スクリーニングを開始します...")

macro_warning = False
try:
    tnx = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
    irx = yf.Ticker("^IRX").history(period="1d")['Close'].iloc[-1]
    if tnx < irx: macro_warning = True
except: pass

for ticker in all_tickers:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        info = stock.info
        
        if hist.empty or len(hist) < 200: continue

        price = hist['Close'].iloc[-1]
        eps = info.get('trailingEps', 0) or 0
        roe = info.get('returnOnEquity', 0) or 0
        per = info.get('trailingPE', 0) or 0
        pbr = info.get('priceToBook', 0) or 0
        peg = info.get('pegRatio', 999) or 999
        
        vol = hist['Volume'].iloc[-1]
        avg_vol_50 = hist['Volume'].tail(50).mean()
        high_20 = hist['Close'].tail(20).max()
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        ma200 = hist['Close'].rolling(window=200).mean().iloc[-1]

        days_to_earn = 999
        earnings_str = "-"
        try:
            cal = stock.calendar
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                e_dates = cal['Earnings Date']
                if len(e_dates) > 0:
                    e_date = e_dates[0].date()
                    days_to_earn = (e_date - datetime.date.today()).days
                    if days_to_earn >= 0: earnings_str = e_date.strftime('%m/%d')
        except: pass

        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50

        exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
        exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        is_macd_gc = (macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0)
        is_macd_dc = (macd_hist.iloc[-1] < 0) and (macd_hist.iloc[-2] >= 0)

        financials, cashflow, balance_sheet = stock.financials, stock.cashflow, stock.balance_sheet
        accruals_negative, gross_margin_high, fcf_margin_high = False, False, False

        if not financials.empty and not cashflow.empty and not balance_sheet.empty:
            try:
                ni = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                ocf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
                ta = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
                gp = financials.loc['Gross Profit'].iloc[0] if 'Gross Profit' in financials.index else 0
                tr = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else 1
                fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0

                if ta > 0 and ((ni - ocf) / ta) < 0: accruals_negative = True
                if tr > 0 and (gp / tr) >= 0.40: gross_margin_high = True
                if tr > 0 and (fcf / tr) >= 0.15: fcf_margin_high = True
            except: pass

        # -----------------------------------
        # 【自動スクリーニング】 決算まで14日以内の銘柄は新規買いから完全除外
        # -----------------------------------
        if ticker in screener_tickers and not (0 <= days_to_earn <= 14):
            
            # 【A】究極の聖杯
            if not macro_warning and price <= 100:
                if eps > 0 and roe >= 0.15 and accruals_negative and gross_margin_high and fcf_margin_high:
                    if 0 < per <= 20 and peg <= 2.0 and rsi < 50 and is_macd_gc:
                        msg = f"\n■ {ticker} (${price:.2f})\n【質】ROE:{roe*100:.1f}% / 粗利40%超\n【反発】MACDゴールデンクロス\n📅次回決算: {earnings_str} (安全)"
                        buy_messages.append(msg)

            # 【C】大化け初動
            if (price > ma50 > ma200) and (avg_vol_50 > 0 and vol >= avg_vol_50 * 1.5) and (high_20 > 0 and price >= high_20 * 0.98) and (rsi < 85):
                msg = f"\n■ {ticker} (${price:.2f})\n🚀 出来高急増: 平均の{vol/avg_vol_50:.1f}倍\n🔥 高値ブレイクアウト近辺\n📅次回決算: {earnings_str} (安全)"
                momentum_messages.append(msg)

        # -----------------------------------
        # 【B】お気に入り銘柄の多段階警告
        # -----------------------------------
        if ticker in favorites:
            warnings = []
            if 0 <= days_to_earn <= 3: warnings.append(f"💀 【超危険】あと{days_to_earn}日で決算です。完全なギャンブル状態！")
            elif 4 <= days_to_earn <= 7: warnings.append(f"⚠️ 【危険水域】あと{days_to_earn}日で決算。乱高下に警戒。")
            elif 8 <= days_to_earn <= 14: warnings.append(f"⚡️ 【警戒】あと{days_to_earn}日で決算。利益確定も視野に。")
            
            if rsi >= 75: warnings.append(f"🔥 RSI {rsi:.1f} (買われすぎ水準)")
            if is_macd_dc: warnings.append("📉 MACDデッドクロス点灯")
            if len(hist) >= 50 and price < ma50 * 0.95: warnings.append("⚠️ トレンド崩壊")
            if eps <= 0: warnings.append("☠️ EPS赤字転落")
            
            if warnings:
                warn_str = "\n".join([f"  {w}" for w in warnings])
                sell_messages.append(f"\n■ {ticker} (${price:.2f})\n{warn_str}")

        time.sleep(0.5)
    except: continue

if buy_messages or momentum_messages or sell_messages:
    final_message = ""
    if macro_warning: final_message += "\n\n⚠️ 【マクロ警戒】逆イールド発生中"
    if buy_messages: final_message += "\n\n👑 【聖杯】超・厳選アラート\n底打ち反転の最強銘柄:" + "".join(buy_messages)
    if momentum_messages: final_message += "\n\n🚀 【大化け初動】モメンタム検知\n機関投資家買い集めの兆候:" + "".join(momentum_messages)
    if sell_messages: final_message += "\n\n⚠️ 【お気に入り】警告アラート\n保有銘柄に警戒シグナル:" + "".join(sell_messages)
        
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    data = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": final_message}]}
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    if res.status_code == 200: print("✅ LINE通知成功！")
else:
    print("本日は通知対象の銘柄はありませんでした。")
