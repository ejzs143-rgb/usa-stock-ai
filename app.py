import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="米国株 クオンツ格付け", layout="wide")
st.title("📈 米国株 プロ仕様・クオンツ格付け")

# 裏側でデータが作られているかチェック
if not os.path.exists('raw_stock_data.csv'):
    st.warning("現在、初回データを収集中です。GitHub Actionsでの実行が完了するまでお待ちください。")
    st.stop()

# 爆速でデータを読み込む
df = pd.read_csv('raw_stock_data.csv')

# --- サイドメニュー ---
st.sidebar.header("⚙️ 投資戦略の調整")
max_p = st.sidebar.slider("1株の予算 (ドル)", 10, 500, 150)
strategy = st.sidebar.radio("戦略の選択", ["バランス型", "逆張り（売られすぎ狙い）", "王道（割安＆黒字）"])

# --- 瞬時スコアリング ---
filtered_df = df[df['株価'] <= max_p].copy()

def calculate_score(row):
    score = 0
    per = row['PER']
    eps = row['EPS']
    rsi = row['RSI']
    ma50 = row['MA50']
    price = row['株価']
    
    # 1. 絶対条件（黒字企業か？）
    if eps > 0: score += 20
    else: score -= 50 # 赤字は大幅減点
    
    # 2. 割安性（PER）
    if per > 0 and per < 15: score += 20
    elif per >= 15 and per < 25: score += 10
    
    # 3. テクニカル指標（RSI）: プロが重視する「買われすぎ/売られすぎ」
    if rsi < 30: score += 30 # 売られすぎ（大チャンス）
    elif rsi < 40: score += 15 # やや売られすぎ（買い場）
    elif rsi > 70: score -= 30 # 買われすぎ（高値掴み危険）
    
    # 4. トレンド乖離（MA50）
    if ma50 > 0:
        dev = (price - ma50) / ma50
        if dev > 0.15: score -= 20 # 移動平均から上に離れすぎ
        elif dev < 0.05: score += 10 # 移動平均付近で安全
        
    # 戦略ボーナス
    if strategy == "逆張り（売られすぎ狙い）" and rsi < 35: score += 30
    if strategy == "王道（割安＆黒字）" and eps > 0 and per > 0 and per < 15: score += 30
        
    return score

filtered_df['総合スコア'] = filtered_df.apply(calculate_score, axis=1)

# 表示用の整形
filtered_df = filtered_df.sort_values(by='総合スコア', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)
filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")

# RSIの状態を日本語でわかりやすく
def rsi_status(rsi):
    if rsi < 30: return "🔥超・売られすぎ"
    elif rsi < 40: return "🟢買い場"
    elif rsi > 70: return "⚠️買われすぎ(危険)"
    else: return "⚪️中立"

filtered_df['RSI(過熱感)'] = filtered_df['RSI'].apply(rsi_status)

# 表示する列の絞り込み
display_df = filtered_df[['順位', '銘柄', '記号', '総合スコア', '株価', 'PER', 'EPS', 'RSI(過熱感)']]

st.success("最新データの分析が完了しました！")
st.dataframe(display_df.set_index('順位'), use_container_width=True)
