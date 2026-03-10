import pandas as pd
import requests
import os
import yfinance as yf
import numpy as np
from io import StringIO

# 金庫（GitHub Secrets）からAPIキーを安全に呼び出す
API_KEY = os.environ.get("FMP_API_KEY")

print("【真・プロ仕様】S&P500の確実なデータ取得を開始します...")

# 1. S&P500のリスト取得
url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
# 警告が出ないように StringIO で囲んで読み込む
all_tickers = [t.replace('.', '-') for t in pd.read_html(StringIO(resp.text))[0]['Symbol'].tolist()]

# 2. FMP APIで「バルク（一括）取得」（ブロック回避の極意）
fundamental_data = []
# 500社を100社ずつのグループに分けて、たった5回の通信で全データをもぎ取る
for i in range(0, len(all_tickers), 100):
    batch_tickers = ",".join(all_tickers[i:i+100])
    fmp_url = f"https://financialmodelingprep.com/api/v3/quote/{batch_tickers}?apikey={API_KEY}"
    
    res = requests.get(fmp_url)
    if res.status_code == 200:
        fundamental_data.extend(res.json())
        print(f"{i+1}〜{i+100}件目の取得成功")
    else:
        print(f"エラー発生: {res.status_code}")

df_fmp = pd.DataFrame(fundamental_data)

# 3. yfinanceの「一括ダウンロード機能」でRSI（買われすぎ指標）を計算
print("テクニカル指標（RSI）の計算中...")
hist_data = yf.download(all_tickers, period="3mo", group_by='ticker', threads=True, progress=False)

rsi_dict = {}
for ticker in all_tickers:
    try:
        # 終値のデータを取り出す
        if len(all_tickers) == 1:
            close_prices = hist_data['Close']
        else:
            close_prices = hist_data[ticker]['Close']
            
        # RSIの計算（プロが使う14日間）
        delta = close_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_dict[ticker] = rsi.iloc[-1] # 最新のRSIを保存
    except:
        rsi_dict[ticker] = 50 # エラー時はニュートラル(50)とする

# 4. データの結合と保存
df_fmp['RSI'] = df_fmp['symbol'].map(rsi_dict)

# 必要な列だけを整理
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
print("全工程完了！盤石なデータをCSVに保存しました。")
