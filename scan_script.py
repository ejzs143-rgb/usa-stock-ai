import pandas as pd
import requests
import os
import yfinance as yf
import numpy as np
from io import StringIO

# 金庫（GitHub Secrets）からAPIキーを呼び出す
API_KEY = os.environ.get("FMP_API_KEY")

# [安全装置1]
if not API_KEY:
    print("🚨 致命的エラー: GitHubの金庫から APIキー が見つかりませんでした。")
    exit(1)
else:
    API_KEY = API_KEY.strip()
    print(f"🔑 APIキー読み込み成功 (末尾: ...{API_KEY[-4:]})")

print("【真・プロ仕様】S&P500の確実なデータ取得を開始します...")

# 1. S&P500のリスト取得
url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
all_tickers = [t.replace('.', '-') for t in pd.read_html(StringIO(resp.text))[0]['Symbol'].tolist()]

# 2. FMP APIで「バルク（一括）取得」
fundamental_data = []
for i in range(0, len(all_tickers), 50):
    batch_tickers = ",".join(all_tickers[i:i+50])
    # 【修正箇所】FMPの最新エンドポイント（/stable/quote）に変更！
    fmp_url = f"https://financialmodelingprep.com/stable/quote?symbol={batch_tickers}&apikey={API_KEY}"
    
    res = requests.get(fmp_url)
    if res.status_code == 200:
        fundamental_data.extend(res.json())
        print(f"✅ {i+1}〜{i+50}件目の取得成功")
    else:
        print(f"❌ エラー発生: HTTP {res.status_code}")
        print(f"📝 拒否された理由: {res.text}")

df_fmp = pd.DataFrame(fundamental_data)

# [安全装置2]
if df_fmp.empty or 'symbol' not in df_fmp.columns:
    print("🚨 エラー: FMP APIからデータを取得できませんでした。")
    exit(1)

# 3. yfinanceでRSI（買われすぎ指標）を計算
print("テクニカル指標（RSI）の計算中...")
hist_data = yf.download(all_tickers, period="3mo", group_by='ticker', threads=True, progress=False, ignore_tz=True)

rsi_dict = {}
for ticker in all_tickers:
    try:
        if len(all_tickers) == 1:
            close_prices = hist_data['Close']
        else:
            close_prices = hist_data[ticker]['Close']
            
        close_prices = close_prices.dropna()
        if len(close_prices) < 15:
            rsi_dict[ticker] = 50
            continue
            
        delta = close_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_dict[ticker] = rsi.iloc[-1]
    except Exception:
        rsi_dict[ticker] = 50

# 4. データの結合と保存
df_fmp['RSI'] = df_fmp['symbol'].map(rsi_dict)

final_data = []
for index, row in df_fmp.iterrows():
    final_data.append({
        '記号': row.get('symbol', ''),
        '銘柄': row.get('name', ''),
        '株価': row.get('price', 0),
        'PER': row.get('pe', 0),
        'EPS': row.get('eps', 0),
        'MA50': row.get('priceAvg50', 0),
        'RSI': row.get('RSI', 50)
    })

df_final = pd.DataFrame(final_data)
df_final.to_csv('raw_stock_data.csv', index=False)
print("✨ 全工程完了！盤石なデータをCSVに保存しました。")
