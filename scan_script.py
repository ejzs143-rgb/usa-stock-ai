import pandas as pd
import yfinance as yf
from textblob import TextBlob
import time
import requests
from datetime import datetime
import pytz

def run_scan():
    # 銘柄リスト取得
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    all_tickers = [t.replace('.', '-') for t in pd.read_html(resp.text)[0]['Symbol'].tolist()]
    
    results = []
    for ticker in all_tickers:
        try:
            s = yf.Ticker(ticker)
            i = s.info
            p = i.get('currentPrice', 0)
            if p == 0 or p > 200: continue # 予算200ドル以内

            # スコア計算
            score = 0
            # 1. ファンダメンタル(最大60点)
            if i.get('trailingPE', 100) < 20: score += 20
            if i.get('returnOnEquity', 0) > 0.18: score += 20
            if i.get('profitMargins', 0) > 0.15: score += 20
            
            # 2. AI感情分析(最大20点)
            news = s.news
            sent = 0
            if news:
                s_list = [TextBlob(n['title']).sentiment.polarity for n in news[:5]]
                sent = sum(s_list) / len(s_list)
                score += (sent * 50) # -25〜+25点の幅

            # 3. 高値掴みガード(最大20点)
            ma50 = i.get('fiftyDayAverage')
            dev = 0
            if ma50:
                dev = (p - ma50) / ma50
                if dev > 0.15: score -= 30 # 過熱は大幅減点
                elif dev < 0.05: score += 20 # 押し目は加点

            results.append({
                '銘柄': i.get('shortName', ticker), '記号': ticker, 'スコア': round(score, 1),
                '株価': f"${p:.2f}", 'AI判断': "😊" if sent > 0.1 else "😨" if sent < -0.1 else "😐",
                'ROE%': round(i.get('returnOnEquity', 0)*100, 1), '過熱度%': round(dev*100, 1)
            })
            time.sleep(0.1)
        except: continue

    df = pd.DataFrame(results).sort_values('スコア', ascending=False)
    df['順位'] = range(1, len(df) + 1)
    # 日本時間の更新時間を記録
    jst = pytz.timezone('Asia/Tokyo')
    df['更新日'] = datetime.now(jst).strftime('%Y/%m/%d %H:%M')
    df.to_csv('sp500_ranking.csv', index=False)

if __name__ == "__main__":
    run_scan()
