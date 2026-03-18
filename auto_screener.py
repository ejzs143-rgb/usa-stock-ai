import pandas as pd
import yfinance as yf
import requests
import os

# GitHubの金庫からLINEの鍵を取り出す
LINE_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

# アプリのデータファイルから銘柄リストを読み込む
try:
    df = pd.read_csv('raw_stock_data.csv')
    tickers = df['記号'].dropna().tolist()
except:
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']

hit_messages = []
print("スクリーニングを開始します...")

for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        info = stock.info
        if hist.empty: continue

        price = hist['Close'].iloc[-1]
        roe = info.get('returnOnEquity', 0) or 0
        per = info.get('trailingPE', 0) or 0
        eps = info.get('trailingEps', 0) or 0

        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50

        # 【中長期の黄金条件】黒字 かつ 高収益(ROE15%超) かつ 割安(PER25倍以下) かつ 現在暴落中(RSI40未満)
        if eps > 0 and roe > 0.15 and 0 < per < 25 and rsi < 40:
            msg = f"\n■ {ticker} (${price:.2f})\nROE: {roe*100:.1f}% / PER: {per:.1f}倍\nRSI: {rsi:.1f} (📉お買い得チャンス)"
            hit_messages.append(msg)
    except Exception:
        pass

# 条件に合うお宝銘柄があればLINEに送信！
if hit_messages:
    final_message = "\n\n🚨 【米国株 黄金銘柄アラート】\n中長期の仕込み時（高収益＆現在安値）の銘柄を発見しました！" + "".join(hit_messages)
    
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
    print("本日は条件に合致するお宝銘柄はありませんでした。")
