import streamlit as st
import pandas as pd
import yfinance as yf
from textblob import TextBlob
import time
import requests

st.set_page_config(page_title="米国株 AI格付けナビ", layout="wide")
st.title("🤖 米国株 AI格付けランキング")

# サイドメニュー
st.sidebar.header("⚙️ 調整")
max_p = st.sidebar.slider("1株予算 (ドル)", 10, 500, 150)
ai_weight = st.sidebar.select_slider("AI感情分析の重要度", options=["低", "中", "高"], value="中")

if st.button("S&P500 フルスキャン開始"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 銘柄リスト取得
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    all_tickers = [t.replace('.', '-') for t in pd.read_html(resp.text)[0]['Symbol'].tolist()]
    
    results = []
    # 本番は all_tickers ですが、最初はテスト用に [:50] (50社) で動かすのがおすすめ
    target_tickers = all_tickers 

    for i, ticker in enumerate(target_tickers):
        progress_bar.progress((i + 1) / len(target_tickers))
        status_text.text(f"分析中: {ticker} ({i}/{len(target_tickers)})")
        try:
            s = yf.Ticker(ticker)
            info = s.info
            price = info.get('currentPrice', 0)
            if price == 0 or price > max_p: continue

            # 指標取得
            per, roe, margin, growth, div, ma50 = info.get('trailingPE'), info.get('returnOnEquity'), info.get('profitMargins'), info.get('revenueGrowth'), info.get('dividendYield'), info.get('fiftyDayAverage')

            # スコア計算
            score = 0
            if per and 0 < per < 20: score += 15
            if roe and roe > 0.18: score += 20
            if margin and margin > 0.15: score += 15
            if growth and growth > 0.10: score += 10
            
            # AI感情分析
            news = s.news
            sentiment_val = 0
            if news:
                s_scores = [TextBlob(n['title']).sentiment.polarity for n in news[:5]]
                sentiment_val = sum(s_scores) / len(s_scores)
                s_points = sentiment_val * 50
                if ai_weight == "高": s_points *= 1.5
                score += s_points

            # 高値掴みガード
            if ma50 and price:
                dev = (price - ma50) / ma50
                if dev > 0.15: score -= 30
                elif dev < 0.05: score += 20

            results.append({
                '順位': 0, '銘柄': info.get('shortName', ticker), '記号': ticker, 'スコア': round(score, 1),
                '株価': f"${price:.2f}", 'AI判断': "😊強気" if sentiment_val > 0.1 else "😨弱気" if sentiment_val < -0.1 else "😐中立",
                'ROE%': round(roe * 100, 1) if roe else "-", '過熱度%': round(dev * 100, 1) if ma50 else "-"
            })
            time.sleep(0.05)
        except: continue

    final_df = pd.DataFrame(results).sort_values(by='スコア', ascending=False)
    final_df['順位'] = range(1, len(final_df) + 1)
    st.success("完了！")
    st.dataframe(final_df, use_container_width=True)
