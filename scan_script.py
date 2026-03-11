import pandas as pd
import yfinance as yf
import numpy as np
import time
import requests # 【追加】人間を装うための通信ライブラリ

# S&P500の銘柄を取得（Wikipediaのブロック回避版）
url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
# 【追加】「私はWindowsのChromeブラウザから見ている人間ですよ」という偽装パスポート
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# 偽装パスポートを使ってWikipediaにアクセス
response = requests.get(url, headers=headers)
df_tickers = pd.read_html(response.text)[0]
tickers = df_tickers['Symbol'].str.replace('.', '-').tolist()

data = []
for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="6mo")
        if hist.empty: continue
        
        price = hist['Close'].iloc[-1]
        eps = info.get('trailingEps', 0)
        per = info.get('trailingPE', 0)
        f_per = info.get('forwardPE', 0)
        roe = info.get('returnOnEquity', 0)
        margin = info.get('profitMargins', 0)
        div = info.get('dividendYield', 0)
        pbr = info.get('priceToBook', 0)
        roa = info.get('returnOnAssets', 0)
        
        # RSI計算
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if not np.isnan(rs.iloc[-1]) else 50
        
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        
        data.append({
            '記号': ticker,
            '銘柄': info.get('shortName', ticker),
            '株価': price,
            'PER': per if per is not None else 0,
            '予想PER': f_per if f_per is not None else 0,
            'EPS': eps if eps is not None else 0,
            'ROE': roe if roe is not None else 0,
            '利益率': margin if margin is not None else 0,
            '配当利回り': div if div is not None else 0,
            'PBR': pbr if pbr is not None else 0,
            'ROA': roa if roa is not None else 0,
            'RSI': rsi,
            'MA50': ma50
        })
    except Exception:
        continue
    time.sleep(0.1)

df_res = pd.DataFrame(data)
df_res.fillna(0, inplace=True)
df_res.to_csv('raw_stock_data.csv', index=False)
