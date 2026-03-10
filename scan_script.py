import pandas as pd
import yfinance as yf
from yahooquery import Ticker
from io import StringIO
import requests
import time

print("【真・プロ仕様】データ取得エンジン（YahooQueryバルク版）を起動します...")

# 1. S&P500のリスト取得
url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
all_tickers = [t.replace('.', '-') for t in pd.read_html(StringIO(resp.text))[0]['Symbol'].tolist()]

final_data = []

# 2. YahooQueryで「バルク（一括）取得」
# サーバーに負荷をかけないよう100件ずつ一気に取得します
for i in range(0, len(all_tickers), 100):
    batch = all_tickers[i:i+100]
    print(f"✅ {i+1}〜{i+len(batch)}件目のファンダメンタルズを取得中...")
    
    # ブロックされにくい非同期通信エンジン
    yq_tickers = Ticker(batch, asynchronous=True)
    
    summary = yq_tickers.summary_detail
    financials = yq_tickers.financial_data
    key_stats = yq_tickers.key_stats
    quote_type = yq_tickers.quote_type
    
    for ticker in batch:
        try:
            # データが存在しない場合の安全処理
            s_data = summary.get(ticker, {}) if isinstance(summary, dict) else {}
            f_data = financials.get(ticker, {}) if isinstance(financials, dict) else {}
            k_data = key_stats.get(ticker, {}) if isinstance(key_stats, dict) else {}
            q_data = quote_type.get(ticker, {}) if isinstance(quote_type, dict) else {}
            
            if isinstance(s_data, str): s_data = {}
            if isinstance(f_data, str): f_data = {}
            if isinstance(k_data, str): k_data = {}
            if isinstance(q_data, str): q_data = {}

            price = s_data.get('previousClose', 0)
            if not price or price == 0:
                continue

            final_data.append({
                '記号': ticker,
                '銘柄': q_data.get('shortName', ticker),
                '株価': price,
                'PER': s_data.get('trailingPE', 0),
                'EPS': k_data.get('trailingEps', 0),
                'MA50': s_data.get('fiftyDayAverage', 0),
                'ROE': f_data.get('returnOnEquity', 0),
                '利益率': f_data.get('profitMargins', 0),
                '配当利回り': s_data.get('dividendYield', 0)
            })
        except Exception:
            pass # エラー銘柄はスキップして止まらないようにする

df_fmp = pd.DataFrame(final_data)

if df_fmp.empty:
    print("🚨 エラー: データを取得できませんでした。")
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
df_fmp['RSI'] = df_fmp['記号'].map(rsi_dict)

df_fmp.to_csv('raw_stock_data.csv', index=False)
print("✨ 全工程完了！盤石なデータをCSVに保存しました。")
