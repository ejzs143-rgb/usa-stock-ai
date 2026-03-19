import pandas as pd
import yfinance as yf
import requests
import os
import json
import time

# GitHubの金庫からLINEの鍵を取り出す
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

# ==========================================
# 1. データの読み込み
# ==========================================
favorites = []
if os.path.exists('favorites.json'):
    try:
        with open('favorites.json', 'r') as f:
            favorites = json.load(f)
    except Exception:
        pass

try:
    df = pd.read_csv('raw_stock_data.csv')
    screener_tickers = df['記号'].dropna().tolist()[:100]
except Exception:
    screener_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

all_tickers = list(set(screener_tickers + favorites))
buy_messages = []
sell_messages = []

print("極限精度（MACD実装版）スクリーニングを開始します...")

# ==========================================
# 2. マクロ環境の判定（第1関門）
# ==========================================
macro_warning = False
try:
    tnx = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
    irx = yf.Ticker("^IRX").history(period="1d")['Close'].iloc[-1]
    if tnx < irx:
        macro_warning = True
        print(f"⚠️ マクロ警戒シグナル点灯: 逆イールド発生中")
except Exception:
    pass

# ==========================================
# 3. 最新データの取得とミクロ判定ループ
# ==========================================
for ticker in all_tickers:
    try:
        stock = yf.Ticker(ticker)
        # MACDとMA50を完璧に計算するため、過去6ヶ月分のデータを取得
        hist = stock.history(period="6mo")
        info = stock.info
        
        if hist.empty or len(hist) < 50:
            continue

        # 基本指標の取得
        price = hist['Close'].iloc[-1]
        eps = info.get('trailingEps', 0) or 0
        roe = info.get('returnOnEquity', 0) or 0
        per = info.get('trailingPE', 0) or 0
        pbr = info.get('priceToBook', 0) or 0
        peg = info.get('pegRatio', 999) or 999
        
        # RSI(14日)の計算
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50
        
        # 50日移動平均線の計算
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]

        # MACDの計算 (12日EMA, 26日EMA, 9日シグナル)
        exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
        exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        # ゴールデンクロス判定（今日ヒストグラムがプラスに転換）
        is_macd_gc = (macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0)
        # デッドクロス判定（今日ヒストグラムがマイナスに転換）
        is_macd_dc = (macd_hist.iloc[-1] < 0) and (macd_hist.iloc[-2] >= 0)

        # 財務諸表からの高度な計算（アクルーアル・粗利率・FCFマージン）
        financials = stock.financials
        cashflow = stock.cashflow
        balance_sheet = stock.balance_sheet

        accruals_negative = False
        gross_margin_high = False
        fcf_margin_high = False

        if not financials.empty and not cashflow.empty and not balance_sheet.empty:
            try:
                net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                op_cf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
                total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
                gross_profit = financials.loc['Gross Profit'].iloc[0] if 'Gross Profit' in financials.index else 0
                total_revenue = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else 1
                fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0

                if total_assets > 0 and ((net_income - op_cf) / total_assets) < 0: accruals_negative = True
                if total_revenue > 0 and (gross_profit / total_revenue) >= 0.40: gross_margin_high = True
                if total_revenue > 0 and (fcf / total_revenue) >= 0.15: fcf_margin_high = True
            except Exception:
                pass

        # -----------------------------------
        # 【A】新規買い時スクリーニング（MACD底打ち検知）
        # -----------------------------------
        if ticker in screener_tickers:
            if not macro_warning and price <= 100:
                if eps > 0 and roe >= 0.15 and accruals_negative and gross_margin_high and fcf_margin_high:
                    # 割安圏(RSI50未満) かつ 反発初日(MACDゴールデンクロス)
                    if 0 < per <= 20 and 0 < pbr <= 3 and peg <= 2.0 and rsi < 50 and is_macd_gc:
                        msg = f"\n■ {ticker} (${price:.2f})\n【質】ROE:{roe*100:.1f}% / 粗利40%超 / FCF豊富\n【割安】PER:{per:.1f} / PBR:{pbr:.2f}\n【反発】RSI:{rsi:.1f} ＆ MACDゴールデンクロス点灯！(🚀底打ち反転の初動)"
                        buy_messages.append(msg)

        # -----------------------------------
        # 【B】お気に入り銘柄の売り時・警告監視
        # -----------------------------------
        if ticker in favorites:
            warnings = []
            if rsi >= 75: warnings.append(f"🔥 RSI {rsi:.1f} (買われすぎ水準)")
            if is_macd_dc: warnings.append("📉 MACDデッドクロス点灯 (下落トレンド入りの予兆)")
            if len(hist) >= 50 and price < ma50 * 0.95: warnings.append("⚠️ トレンド崩壊 (50日線から5%以上下落)")
            if eps <= 0: warnings.append("☠️ EPS赤字転落 (ファンダメンタルズ悪化)")
            if macro_warning: warnings.append("🚨 マクロ警戒 (逆イールド発生中につき保有リスク増)")
            
            if warnings:
                warn_str = "\n".join([f"  {w}" for w in warnings])
                sell_messages.append(f"\n■ {ticker} (${price:.2f})\n{warn_str}")

        time.sleep(0.5)

    except Exception:
        continue

# ==========================================
# 4. LINEへの通知処理
# ==========================================
if buy_messages or sell_messages:
    final_message = ""
    
    if macro_warning:
        final_message += "\n\n⚠️ 【マクロ環境 警戒警報】\n長短金利の逆転(逆イールド)が発生中です。相場全体の暴落リスクが高まっています。"

    if buy_messages:
        final_message += "\n\n🚨 【米国株 100ドル以下 究極精度アラート】\n全指標をクリアし、底打ち反転（ゴールデンクロス）した銘柄を発見！" + "".join(buy_messages)
        
    if sell_messages:
        final_message += "\n\n⚠️ 【お気に入り 売り時・警告アラート】\n保有銘柄に警戒シグナルが点灯しています！" + "".join(sell_messages)
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": final_message}]
    }
    
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    if res.status_code == 200:
        print("✅ LINE通知成功！")
    else:
        print(f"❌ LINE通知失敗: {res.text}")
else:
    print("本日は通知対象の銘柄（買い・売りともに）はありませんでした。")
