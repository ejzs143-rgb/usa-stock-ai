import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="米国株 AI格付け", layout="wide")
st.title("📱 米国株 自分専用リモコン・ランキング")
st.write("専門知識は不要です。あなたの好みに合わせて、AIが全米500社を瞬時に並び替えます。")

# データ読み込み（裏で集めた確実なデータを使います）
if not os.path.exists('raw_stock_data.csv'):
    st.warning("現在、裏側のシステムでデータを収集中です。")
    st.stop()
df = pd.read_csv('raw_stock_data.csv')

# --- サイドメニュー（あなたの専用リモコン） ---
st.sidebar.header("🕹️ あなたの好みを設定")

max_p = st.sidebar.slider("1株の予算 (ドル)", 10, 500, 150)

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 どんな株を狙う？")
# ここが初心者に優しいUI！ボタン一つで裏の計算式が切り替わります
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

def calculate_score(row):
    score = 0
    per = row['PER']
    eps = row['EPS']
    rsi = row['RSI']
    
    # 1. 絶対条件（ちゃんと利益を出している会社か？）
    if eps > 0: score += 20
    else: score -= 50 # 赤字の会社は問答無用で減点
    
    # 2. 割安度（PER：本来の価値より安いか？）
    if 0 < per < 15: score += 20
    elif 15 <= per < 25: score += 10

    # 3. 戦略によるAI配点の変化（ここでプロの思考回路を切り替えます）
    if strategy == "📈 勢いに乗る（みんなが買ってる人気株）":
        if 50 <= rsi <= 70: score += 30 # 順調に上がっている株にボーナス
        elif rsi > 75: score -= 30 # さすがに上がりすぎ（バブル）は危険回避
        elif rsi < 40: score -= 20 # 下がっている株は容赦なく切り捨て

    elif strategy == "📉 暴落を拾う（パニックで売られたお買い得株）":
        if rsi < 30: score += 30 # 超売られすぎ（大バーゲン）に大ボーナス
        elif rsi < 40: score += 15 # やや売られすぎも加点
        elif rsi > 60: score -= 20 # すでに上がっている株は買わない

    elif strategy == "⚖️ 王道バランス（業績が良くて普通の株）":
        if 40 <= rsi <= 60: score += 20 # 安定飛行している株を加点
        if rsi > 70 or rsi < 30: score -= 10 # 極端に上がったり下がったりしている株は避ける
        if eps > 0 and 0 < per < 15: score += 20 # 業績と安さをさらに手厚く評価

    return score

# AIが採点した結果を「あなたへのオススメ度」として記録
filtered_df['あなたへのオススメ度'] = filtered_df.apply(calculate_score, axis=1)

# 表示用の整形（点数が高い順に並び替え）
filtered_df = filtered_df.sort_values(by='あなたへのオススメ度', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)
filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")

# 専門用語（RSI）を、誰でもわかる日本語に変換
def rsi_status(rsi):
    if rsi < 30: return "🧊底値圏(大バーゲン)"
    elif rsi < 40: return "📉下落中(お買い得)"
    elif rsi < 60: return "⚪️安定"
    elif rsi < 70: return "📈上昇中(人気上昇)"
    else: return "🔥過熱(高値掴み注意)"

filtered_df['今の状態'] = filtered_df['RSI'].apply(rsi_status)

# 見やすいように、必要な列だけを抜き出して表示
display_df = filtered_df[['順位', '銘柄', 'あなたへのオススメ度', '今の状態', '株価', 'PER']]

st.dataframe(display_df.set_index('順位'), use_container_width=True)
