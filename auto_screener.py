import pandas as pd
import yfinance as yf
import requests
import os
import json

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

# 重複を排除した全監視リスト
all_tickers = list(set(screener_tickers + favorites))

buy_messages = []
sell_messages = []

print("究極版スクリーニングおよび監視を開始します...")

# ==========================================
# 2. 最新データの取得と判定ループ
# ==========================================
for ticker in all_tickers:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        info = stock.info
        
        # データが不足している銘柄はスキップ
        if hist.empty or len(hist) < 14:
            continue

        # 各種指標の取得（データがない場合は0を代入してエラー回避）
        price = hist['Close'].iloc[-1]
        roe = info.get('returnOnEquity', 0) or 0
        per = info.get('trailingPE', 0) or 0
        pbr = info.get('priceToBook', 0) or 0
        eps = info.get('trailingEps', 0) or 0

        # RSI(14日)の計算
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50
        
        # MA50(50日移動平均線)の計算
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else price

        # -----------------------------------
        # 【A】新規買い時スクリーニング（100ドル以下 ＆ 真の黄金銘柄）
        # -----------------------------------
        if ticker in screener_tickers:
            # 条件: 100ドル以下、黒字、高収益(ROE15%以上)、割安(PER20以下＆PBR3以下)、暴落中(RSI40未満)
            if price <= 100 and eps > 0 and roe >= 0.15 and 0 < per <= 20 and 0 < pbr <= 3 and rsi < 40:
                msg = f"\n■ {ticker} (${price:.2f})\nROE: {roe*100:.1f}% / PER: {per:.1f}倍 / PBR: {pbr:.2f}倍\nRSI: {rsi:.1f} (📉優良・割安チャンス)"
                buy_messages.append(msg)

        # -----------------------------------
        # 【B】お気に入り銘柄の売り時・警告監視（価格制限なし）
        # -----------------------------------
        if ticker in favorites:
            warnings = []
            if rsi >= 75:
                warnings.append(f"🔥 RSI {rsi:.1f} (買われすぎ/利益確定の検討)")
            if eps <= 0:
                warnings.append("⚠️ EPS赤字転落 (ファンダメンタルズ悪化)")
            if len(hist) >= 50 and price < ma50 * 0.95:
                warnings.append("📉 トレンド崩壊 (50日線から5%以上下落)")
            
            if warnings:
                warn_str = "\n".join([f"  {w}" for w in warnings])
                sell_messages.append(f"\n■ {ticker} (${price:.2f})\n{warn_str}")

    except Exception:
        pass

# ==========================================
# 3. LINEへの通知処理
# ==========================================
if buy_messages or sell_messages:
    final_message = ""
    
    if buy_messages:
        final_message += "\n\n🚨 【米国株 100ドル以下 黄金銘柄アラート】\n中長期の仕込み時（高収益＆安値）の銘柄を発見しました！" + "".join(buy_messages)
        
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
