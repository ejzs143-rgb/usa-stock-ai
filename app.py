import streamlit as st
import pandas as pd
import os
import datetime

st.set_page_config(page_title="米国株 フルスペックAI格付け", layout="wide")
st.title("📱 米国株 自分専用リモコン (フルスペック版)")
st.write("裏側で収集した全8指標（業績・割安性・過熱感・配当など）をフル稼働し、最適な銘柄を算出します。")

# データ読み込みと欠損エラー防止の安全処理
file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在、裏側のシステムでデータを収集中です。")
    st.stop()

# --- 【追加】データの最終更新日時（タイムスタンプ）を日本時間で表示 ---
timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
# 日本時間（+9時間）に変換して表示
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
last_updated = jst_time.strftime('%Y年%m月%d日 %H:%M')

st.caption(f"🕒 データの最終更新: **{last_updated}**")
st.caption("※もしこの日時が昨日から止まっている場合は、裏側（GitHub）でエラーが起きている可能性があります。")
# -------------------------------------------------------------------

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) # データが無い項目は0として計算エラーを防ぐ

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
        "⚖️ 王道バランス（業績が良くて普通の株）"
    ]
)

# --- 瞬時スコアリング ---
filtered_df = df[df['株価'] <= max_p].copy()

# 検索処理
if search_query:
    filtered_df = filtered_df[
        filtered_df['記号'].str.contains(search_query.upper(), na=False) | 
        filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
    ]

# 8軸フルスペック計算エンジン
def calculate_score(row):
    score = 0
    per = row['PER']
    eps = row['EPS']
    rsi = row['RSI']
    roe = row['ROE']
    margin = row['利益率']
    div = row['配当利回り']
    price = row['株価']
    ma50 = row['MA50']
    
    # 【1. 絶対条件】
    if eps > 0: score += 20
    else: score -= 50 
    
    # 【2. 割安度】
    if 0 < per < 15: score += 20
    elif 15 <= per < 25: score += 10

    # 【3. 経営の上手さ】
    if roe > 0.20: score += 20
    elif roe > 0.10: score += 10

    # 【4. ビジネスの強さ】
    if margin > 0.20: score += 20
    elif margin > 0.10: score += 10

    # 【5. 不労所得】
    if div > 0.04: score += 15
    elif div > 0.02: score += 5

    # 【6,7,8. 戦略別のプロ思考AI配点】
    if strategy == "📈 勢いに乗る（みんなが買ってる人気株）":
        if 50 <= rsi <= 70: score += 30 
        elif rsi > 75: score -= 30 
        elif rsi < 40: score -= 20 
        if price > ma50 * 1.05: score += 15 

    elif strategy == "📉 暴落を拾う（パニックで売られたお買い得株）":
        if rsi < 30: score += 30 
        elif rsi < 40: score += 15 
        elif rsi > 60: score -= 20 
        if price < ma50 * 0.90: score += 15 

    elif strategy == "⚖️ 王道バランス（業績が良くて普通の株）":
        if 40 <= rsi <= 60: score += 20 
        if rsi > 70 or rsi < 30: score -= 10 
        if roe > 0.15 and margin > 0.15: score += 20 

    return score

# 点数計算と並び替え
filtered_df['オススメ度(点数)'] = filtered_df.apply(calculate_score, axis=1)
filtered_df = filtered_df.sort_values(by='オススメ度(点数)', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)

# 見た目の整形（％やドル表記）
filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
filtered_df['配当%'] = filtered_df['配当利回り'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['ROE%'] = filtered_df['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")

def rsi_status(rsi):
    if rsi < 30: return "🧊底値圏(大バーゲン)"
    elif rsi < 40: return "📉下落中(お買い得)"
    elif rsi < 60: return "⚪️安定"
    elif rsi < 70: return "📈上昇中(人気)"
    else: return "🔥過熱(高値掴み注意)"

filtered_df['今の状態'] = filtered_df['RSI'].apply(rsi_status)

# フルスペック版の表示項目
display_df = filtered_df[['順位', '記号', '銘柄', 'オススメ度(点数)', '今の状態', '株価', 'PER', 'ROE%', '配当%']]

if search_query and display_df.empty:
    st.warning("見つかりませんでした。（予算オーバーか、S&P500外の銘柄の可能性があります）")
else:
    st.dataframe(display_df.set_index('順位'), use_container_width=True)
