import streamlit as st
import pandas as pd
import os
import datetime

st.set_page_config(page_title="米国株 フルスペックAI格付け", layout="wide")
st.title("📱 米国株 自分専用リモコン (フルスペック版)")
st.write("裏側で収集した全8指標をフル稼働！AIの「採点内訳」もすべてガラス張りで公開します。")

# データ読み込みと欠損エラー防止の安全処理
file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在、裏側のシステムでデータを収集中です。")
    st.stop()

# データの最終更新日時（日本時間）
timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
last_updated = jst_time.strftime('%Y年%m月%d日 %H:%M')

st.caption(f"🕒 データの最終更新: **{last_updated}**")
st.caption("※この日時が昨日から止まっている場合は、裏側でエラーが起きている可能性があります。")

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

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

filtered_df = df[df['株価'] <= max_p].copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df['記号'].str.contains(search_query.upper(), na=False) | 
        filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
    ]

# 8軸フルスペック計算エンジン（採点内訳も出力するよう進化）
def calculate_score_and_breakdown(row):
    score_eps = 20 if row['EPS'] > 0 else -50
    
    score_per = 0
    if 0 < row['PER'] < 15: score_per = 20
    elif 15 <= row['PER'] < 25: score_per = 10

    score_biz = 0
    if row['ROE'] > 0.20: score_biz += 20
    elif row['ROE'] > 0.10: score_biz += 10
    if row['利益率'] > 0.20: score_biz += 20
    elif row['利益率'] > 0.10: score_biz += 10

    score_div = 0
    if row['配当利回り'] > 0.04: score_div = 15
    elif row['配当利回り'] > 0.02: score_div = 5

    score_strat = 0
    rsi = row['RSI']
    price = row['株価']
    ma50 = row['MA50']
    
    if strategy == "📈 勢いに乗る（みんなが買ってる人気株）":
        if 50 <= rsi <= 70: score_strat += 30 
        elif rsi > 75: score_strat -= 30 
        elif rsi < 40: score_strat -= 20 
        if price > ma50 * 1.05: score_strat += 15 

    elif strategy == "📉 暴落を拾う（パニックで売られたお買い得株）":
        if rsi < 30: score_strat += 30 
        elif rsi < 40: score_strat += 15 
        elif rsi > 60: score_strat -= 20 
        if price < ma50 * 0.90: score_strat += 15 

    elif strategy == "⚖️ 王道バランス（業績が良くて普通の株）":
        if 40 <= rsi <= 60: score_strat += 20 
        if rsi > 70 or rsi < 30: score_strat -= 10 
        if row['ROE'] > 0.15 and row['利益率'] > 0.15: score_strat += 20 

    total_score = score_eps + score_per + score_biz + score_div + score_strat
    
    # ここで採点の内訳テキストを作成！
    breakdown = f"黒字:{score_eps} 割安:{score_per} 稼ぐ力:{score_biz} 配当:{score_div} 戦略:{score_strat}"
    
    return pd.Series([total_score, breakdown])

# 点数と内訳をデータに追加
filtered_df[['オススメ度(点数)', '採点内訳']] = filtered_df.apply(calculate_score_and_breakdown, axis=1)
filtered_df = filtered_df.sort_values(by='オススメ度(点数)', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)

# 見た目の整形（％やドル表記）
filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
filtered_df['EPS'] = filtered_df['EPS'].apply(lambda x: f"${x:.2f}")
filtered_df['利益率%'] = filtered_df['利益率'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['配当%'] = filtered_df['配当利回り'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
filtered_df['ROE%'] = filtered_df['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")

def rsi_status(rsi):
    if rsi < 30: return "🧊底値圏(大バーゲン)"
    elif rsi < 40: return "📉下落中(お買い得)"
    elif rsi < 60: return "⚪️安定"
    elif rsi < 70: return "📈上昇中(人気)"
    else: return "🔥過熱(危険)"

filtered_df['今の状態'] = filtered_df['RSI'].apply(rsi_status)

# すべての指標と内訳をフル表示
display_df = filtered_df[['順位', '記号', '銘柄', 'オススメ度(点数)', '採点内訳', '今の状態', '株価', 'PER', 'EPS', 'ROE%', '利益率%', '配当%']]

if search_query and display_df.empty:
    st.warning("見つかりませんでした。（予算オーバーか、S&P500外の銘柄の可能性があります）")
else:
    st.dataframe(display_df.set_index('順位'), use_container_width=True)
