import streamlit as st
import pandas as pd
import os
import datetime

st.set_page_config(page_title="米国株 フルスペックAI格付け", layout="wide")
st.title("📱 米国株 自分専用リモコン (フルスペック版)")
st.write("すべての指標の横に点数を完全配置！選んだ戦略によって、どの指標で点数を稼いだかが丸わかりです。")

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

# 安全装置
for col in ['PBR', 'ROA', '予想PER']:
    if col not in df.columns:
        df[col] = 0

# --- サイドメニュー ---
st.sidebar.header("🔍 持ち株の健康診断")
search_query = st.sidebar.text_input("銘柄を探す (記号や名前 例: AAPL, Apple)", "")

st.sidebar.markdown("---")
st.sidebar.header("🕹️ あなたの好みを設定")
max_p = st.sidebar.slider("1株の予算 (ドル)", 10, 500, 150)

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

# すべての指標の点数をバラバラに計算するエンジン
def calculate_scores(row):
    # ベースの70点分
    score_eps = 10 if row['EPS'] > 0 else -50
    score_per = 15 if 0 < row['PER'] < 15 else (8 if 15 <= row['PER'] < 25 else 0)
    score_roe = 15 if row['ROE'] > 0.20 else (8 if row['ROE'] > 0.10 else 0)
    score_margin = 15 if row['利益率'] > 0.20 else (8 if row['利益率'] > 0.10 else 0)
    score_div = 15 if row['配当利回り'] > 0.04 else (8 if row['配当利回り'] > 0.02 else 0)

    # 戦略の30点分（選択した戦略に応じて各指標に点数を振り分ける）
    score_rsi, score_trend, score_f_per, score_pbr, score_roa, score_bonus = 0, 0, 0, 0, 0, 0
    str_rsi, str_trend, str_f_per, str_pbr, str_roa, str_bonus = "-", "-", "-", "-", "-", "-"

    rsi = row['RSI']
    price = row['株価']
    ma50 = row['MA50']
    
    if strategy == "📈 勢いに乗る（みんなが買ってる人気株）":
        if 50 <= rsi <= 70: score_rsi = 20 
        elif rsi > 75: score_rsi = -20 
        elif rsi < 40: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        
        if price > ma50 * 1.05: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "📉 暴落を拾う（パニックで売られたお買い得株）":
        if rsi < 30: score_rsi = 20 
        elif rsi < 40: score_rsi = 10 
        elif rsi > 60: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        
        if price < ma50 * 0.90: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "⚖️ 王道バランス（業績が良くて普通の株）":
        if 40 <= rsi <= 60: score_rsi = 15 
        if rsi > 70 or rsi < 30: score_rsi = -10 
        str_rsi = f"{score_rsi}/15"
        
        if row['ROE'] > 0.15 and row['利益率'] > 0.15: score_bonus = 15 
        str_bonus = f"{score_bonus}/15"

    elif strategy == "🏛️ 伝統的割安（バフェット流・PBR/ROA特化）":
        if 0 < row['予想PER'] <= 15: score_f_per = 10
        elif 15 < row['予想PER'] <= 20: score_f_per = 5
        str_f_per = f"{score_f_per}/10"
        
        if 0 < row['PBR'] <= 1.5: score_pbr = 10
        elif 1.5 < row['PBR'] <= 3.0: score_pbr = 5
        str_pbr = f"{score_pbr}/10"
        
        if row['ROA'] >= 0.03: score_roa = 10
        elif row['ROA'] > 0.01: score_roa = 5
        str_roa = f"{score_roa}/10"

    total_score = score_eps + score_per + score_roe + score_margin + score_div + score_rsi + score_trend + score_f_per + score_pbr + score_roa + score_bonus
    
    return pd.Series([
        total_score,
        f"{score_eps}/10", f"{score_per}/15", f"{score_roe}/15", f"{score_margin}/15", f"{score_div}/15",
        str_rsi, str_trend, str_bonus, str_f_per, str_pbr, str_roa
    ])

filtered_df[['💯総合スコア', 'EPS点', '割安点', 'ROE点', '利益率点', '配当点', 'RSI点', 'トレンド点', '王道ボーナス', '予想PER点', 'PBR点', 'ROA点']] = filtered_df.apply(calculate_scores, axis=1)
filtered_df = filtered_df.sort_values(by='💯総合スコア', ascending=False)
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

# 各指標の「すぐ右隣」に点数用の列をセット！
display_df = filtered_df[[
    '順位', '記号', '銘柄', '💯総合スコア', 
    'EPS', 'EPS点', 
    'PER', '割安点', 
    'ROE%', 'ROE点', 
    '利益率%', '利益率点', 
    '配当%', '配当点',
    '今の株価の勢い', 'RSI点', 
    '株価', 'MA50', 'トレンド点',
    '王道ボーナス',
    '予想PER', '予想PER点', 
    'PBR', 'PBR点', 
    'ROA%', 'ROA点'
]]

# 【修正箇所】名前が一切重複しないように、すべて個別の名前を振りました
display_df = display_df.rename(columns={
    'EPS': '┃EPS(1株の利益)',
    'EPS点': 'EPS点(/10)',
    'PER': '┃PER(実績の割安さ)',
    '割安点': '割安点(/15)',
    'ROE%': '┃ROE(稼ぐ力)',
    'ROE点': 'ROE点(/15)',
    '利益率%': '┃利益率(儲かりやすさ)',
    '利益率点': '利益率点(/15)',
    '配当%': '┃配当(もらえる現金)',
    '配当点': '配当点(/15)',
    '今の株価の勢い': '┃RSI(株価の過熱感)',
    'RSI点': 'RSI点(/20)',
    'MA50': '50日平均線(MA50)',
    'トレンド点': 'トレンド点(/10)',
    '王道ボーナス': '┃業績ボーナス加点',
    '予想PER': '┃予想PER(来年の割安さ)',
    '予想PER点': '予想PER点(/10)',
    'PBR': '┃PBR(解散価値)',
    'PBR点': 'PBR点(/10)',
    'ROA%': '┃ROA(総資産の稼ぐ力)',
    'ROA点': 'ROA点(/10)'
})

if search_query and display_df.empty:
    st.warning("見つかりませんでした。（予算オーバーか、S&P500外の銘柄の可能性があります）")
else:
    st.dataframe(display_df.set_index('順位'), use_container_width=True)
