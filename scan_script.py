import pandas as pd
import yfinance as yf
from textblob import TextBlob
import time
import requests

print("S&P500の生データ取得を開始します...")

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
all_tickers = [t.replace('.', '-') for t in pd.read_html(resp.text)[0]['Symbol'].tolist()]

raw_data = []

for ticker in all_tickers:
    try:
        s = yf.Ticker(ticker)
        info = s.info
        price = info.get('currentPrice', 0)
        
        # 最低限の価格がないものはスキップ
        if not price or price == 0:
            continue
            
        per = info.get('trailingPE', 0)
        roe = info.get('returnOnEquity', 0)
        margin = info.get('profitMargins', 0)
        div = info.get('dividendYield', 0)
        ma50 = info.get('fiftyDayAverage', 0)
        
        # AI感情分析（ニュースタイトル）
        news = s.news
        sentiment_val = 0
        if news:
            s_scores = [TextBlob(n['title']).sentiment.polarity for n in news[:5]]
            if len(s_scores) > 0:
                sentiment_val = sum(s_scores) / len(s_scores)

        raw_data.append({
            '記号': ticker,
            '銘柄': info.get('shortName', ticker),
            '株価': price,
            'PER': per if per else 0,
            'ROE': roe if roe else 0,
            '利益率': margin if margin else 0,
            '配当利回り': div if div else 0,
            'MA50': ma50 if ma50 else 0,
            'AI感情': sentiment_val
        })
        print(f"取得成功: {ticker}")
        time.sleep(0.5) # ブロック回避のための丁寧な待機
        
    except Exception as e:
        print(f"取得エラー {ticker}: {e}")
        continue

# 生データをCSVとして保存
df = pd.DataFrame(raw_data)
df.to_csv('raw_stock_data.csv', index=False)
print("データ取得完了、CSVを保存しました。")
