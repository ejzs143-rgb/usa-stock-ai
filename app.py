import streamlit as st
import pandas as pd
import os
import datetime

st.set_page_config(page_title="米国株 フルスペックAI格付け", layout="wide")
st.title("📱 米国株 自分専用リモコン (フルスペック版)")
st.write("100点満点のスコア形式！各指標が「何点満点中、何点か」をすべて透明化しました。")

file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在、裏側のシステムでデータを収集中です。")
    st.stop()

timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
last_updated = jst_time.strftime('%Y年%m月%d日 %H:%M')

st.caption(f"🕒 データの最終更新: **{last_updated}**")

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

# 【安全装置】裏側の更新が終わる前にアプリを開いてもエラーで落ちないようにする
for col in ['PBR', 'ROA', '予想PER']:
    if col not in df.columns:
        df[col] = 0

# --- サイドメニュー ---
st.sidebar.header("🔍 持ち株の健康診断")
search_query = st.sidebar.text_input("銘柄を探す (記号や名前 例: AAPL, Apple)", "")

st.sidebar.markdown("---")
st.sidebar.header("🕹️ あなたの好みを設定")
max_p = st.sidebar.slider("1株の予算 (ドル)", 10, 500, 150)

# 【ここに追加！】ワンタッチボタンに4つ目のクラシック戦略を追加
strategy = st.sidebar.radio(
    "AIに探させる戦略を選んでください", 
    [
        "📈 勢いに乗る（みんなが買ってる人気株）", 
        "📉 暴落を拾う（パニックで売られたお買い得株）", 
        "⚖️ 王道バランス（業績が良くて普通の株）",
        "🏛️ 伝統的割安（バフェット流・PBR/ROA特化）"
    ]
)

filtered_df = df[df['株価'] <= max_p].copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df['記号'].str.contains(search_query.upper(), na=False) | 
        filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
    ]

def calculate_score_and_breakdown(row):
    score_eps = 10 if row['EPS'] > 0 else -50
    
    score_per = 0
    if 0 < row['PER'] < 15: score_per = 15
    elif 15 <= row['PER'] < 25: score_per = 8
    
    score_roe = 0
    if row['ROE'] > 0.20: score_roe = 15
    elif row['ROE'] > 0.10: score_roe = 8
    
    score_margin = 0
    if row['利益率'] > 0.20: score_margin = 15
    elif row['利益率'] > 0.10: score_margin = 8
    
    score_div = 0
    if row['配当利回り'] > 0.04: score_div = 15
    elif row['配当利回り'] > 0.02: score_div = 8

    # 30点満点の戦略別ボーナス
    score_strat = 0
    rsi = row['RSI']
    price = row['株価']
    ma50 = row['MA50']
    
    if strategy == "📈 勢いに乗る（みんなが買ってる人気株）":
        if 50 <= rsi <= 70: score_strat += 20 
        elif rsi > 75: score_strat -= 20 
        elif rsi < 40: score_strat -= 10 
        if price > ma50 * 1.05: score_strat += 10 

    elif strategy == "📉 暴落を拾う（パニックで売られたお買い得株）":
        if rsi < 30: score_strat += 20 
        elif rsi < 40: score_strat += 10 
        elif rsi > 60: score_strat -= 10 
        if price < ma50 * 0.90: score_strat += 10 

    elif strategy == "⚖️ 王道バランス（業績が良くて普通の株）":
        if 40 <= rsi <= 60: score_strat += 15 
        if rsi > 70 or rsi < 30: score_strat -= 10 
        if row['ROE'] > 0.15 and row['利益率'] > 0.15: score_strat += 15 

    # 【追加】4つ目の戦略の配点（ご提示いただいた指標で30点満点を計算）
    elif strategy == "🏛️ 伝統的割安（バフェット流・PBR/ROA特化）":
        if 0 < row['予想PER'] <= 15: score_strat += 10
        elif 15 < row['予想PER'] <= 20: score_strat += 5
        
        if 0 < row['PBR'] <= 1.5: score_strat += 10
        elif 1.5 < row['PBR'] <= 3.0: score_strat += 5
        
        if row['ROA'] >= 0.03: score_strat += 10
        elif row['ROA'] > 0.01: score_strat += 5

    total_score = score_eps + score_per + score_roe + score_margin + score_div + score_strat
    breakdown = f"黒字:{score_eps}/10 割安:{score_per}/15 ROE:{score_roe}/15 利益率:{score_margin}/15 配当:{score_div}/15 戦略:{score_strat}/30"
    
    return pd.Series([total_score, breakdown])

filtered_df[['総合スコア(100点満点)', '採点内訳(横スクロール)']] = filtered_df.apply(calculate_score_and_breakdown, axis=1)
filtered_df = filtered_df.sort_values(by='総合スコア(100点満点)', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)

# 表示項目の整形
filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
filtered_df['EPS'] = filtered_df['EPS'].apply(lambda x: f"${x:.2f}")
filtered_df['MA50'] = filtered_df['MA50'].apply(lambda x: f"${x:.2f}")
filtered_df['利益率%'] = filtered_df['利益率'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['配当%'] = filtered_df['配当利回り'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['ROE%'] = filtered_df['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['PBR'] = filtered_df['PBR'].apply(lambda x: f"{x:.2f}倍" if x > 0 else "-")
filtered_df['ROA%'] = filtered_df['ROA'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['予想PER'] = filtered_df['予想PER'].apply(lambda x: f"{x:.1f}倍" if x > 0 else "-")

def rsi_status(rsi):
    if rsi < 30: return "🧊大暴落セール"
    elif rsi < 40: return "📉値下がり中"
    elif rsi < 60: return "⚪️平常運転"
    elif rsi < 70: return "📈値上がり中"
    else: return "🔥高騰しすぎ"

filtered_df['今の株価の勢い'] = filtered_df['RSI'].apply(rsi_status)

# 表に新指標（予想PER、PBR、ROA）を追加して全出し
display_df = filtered_df[['順位', '記号', '銘柄', '総合スコア(100点満点)', '採点内訳(横スクロール)', '今の株価の勢い', '株価', '予想PER', 'PBR', 'ROA%', 'PER', 'EPS', 'ROE%', '利益率%', '配当%']]

display_df = display_df.rename(columns={
    '予想PER': '予想PER(来年の割安さ)',
    'PBR': 'PBR(解散価値の割安さ)',
    'ROA%': 'ROA(総資産の稼ぐ力)',
    'MA50': 'MA50(50日平均線)',
    'PER': 'PER(実績の割安さ)',
    'EPS': 'EPS(1株の利益)',
    'ROE%': 'ROE(稼ぐ力)',
    '利益率%': '利益率(儲かりやすさ)',
    '配当%': '配当(もらえる現金)'
})

if search_query and display_df.empty:
    st.warning("見つかりませんでした。（予算オーバーか、S&P500外の銘柄の可能性があります）")
else:
    st.dataframe(display_df.set_index('順位'), use_container_width=True)
