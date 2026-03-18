import streamlit as st
import pandas as pd
import os
import datetime
import yfinance as yf
import plotly.graph_objects as go # 【新規】本格チャート描画用ライブラリ

st.set_page_config(page_title="米国株AI格付け", layout="wide")

# タイトルを小型化、無駄な説明文は全削除
st.markdown("#### 📱 米国株AI格付け")

file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("データ収集中...")
    st.stop()

# 更新日時の表示も最小限に
timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
st.caption(f"更新: {jst_time.strftime('%Y/%m/%d %H:%M')}")

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

for col in ['PBR', 'ROA', '予想PER']:
    if col not in df.columns:
        df[col] = 0

# --- サイドメニュー（文字サイズ最小化） ---
st.sidebar.markdown("**🔍 検索**")
search_query = st.sidebar.text_input("記号や名前 (例: AAPL)", "", label_visibility="collapsed", placeholder="銘柄を検索 (例: AAPL)")

st.sidebar.markdown("---")
st.sidebar.markdown("**🕹️ 戦略**")
max_p = st.sidebar.slider("予算上限($)", 10, 500, 150)

strategy = st.sidebar.radio(
    "判定ロジック", 
    [
        "📈 勢い重視", 
        "📉 逆張り拾い", 
        "⚖️ 王道業績",
        "🏛️ バフェット流"
    ],
    label_visibility="collapsed"
)

filtered_df = df[df['株価'] <= max_p].copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df['記号'].str.contains(search_query.upper(), na=False) | 
        filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
    ]

# 点数計算エンジン（ロジック維持・重複エラー排除済み）
def calculate_scores(row):
    score_eps = 10 if row['EPS'] > 0 else -50
    score_per = 15 if 0 < row['PER'] < 15 else (8 if 15 <= row['PER'] < 25 else 0)
    score_roe = 15 if row['ROE'] > 0.20 else (8 if row['ROE'] > 0.10 else 0)
    score_margin = 15 if row['利益率'] > 0.20 else (8 if row['利益率'] > 0.10 else 0)
    score_div = 15 if row['配当利回り'] > 0.04 else (8 if row['配当利回り'] > 0.02 else 0)

    score_rsi, score_trend, score_f_per, score_pbr, score_roa, score_bonus = 0, 0, 0, 0, 0, 0
    str_rsi, str_trend, str_f_per, str_pbr, str_roa, str_bonus = "-", "-", "-", "-", "-", "-"

    rsi = row['RSI']
    price = row['株価']
    ma50 = row['MA50']
    
    if strategy == "📈 勢い重視":
        if 50 <= rsi <= 70: score_rsi = 20 
        elif rsi > 75: score_rsi = -20 
        elif rsi < 40: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        if price > ma50 * 1.05: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "📉 逆張り拾い":
        if rsi < 30: score_rsi = 20 
        elif rsi < 40: score_rsi = 10 
        elif rsi > 60: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        if price < ma50 * 0.90: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "⚖️ 王道業績":
        if 40 <= rsi <= 60: score_rsi = 15 
        if rsi > 70 or rsi < 30: score_rsi = -10 
        str_rsi = f"{score_rsi}/15"
        if row['ROE'] > 0.15 and row['利益率'] > 0.15: score_bonus = 15 
        str_bonus = f"{score_bonus}/15"

    elif strategy == "🏛️ バフェット流":
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

filtered_df[['💯総合点', 'EPS点', '割安点', 'ROE点', '利益点', '配当点', 'RSI点', 'トレンド点', '業績ボーナス', '予想PER点', 'PBR点', 'ROA点']] = filtered_df.apply(calculate_scores, axis=1)
filtered_df = filtered_df.sort_values(by='💯総合点', ascending=False)
filtered_df['順位'] = range(1, len(filtered_df) + 1)

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
    if rsi < 30: return "🧊暴落"
    elif rsi < 40: return "📉下落"
    elif rsi < 60: return "⚪️平常"
    elif rsi < 70: return "📈上昇"
    else: return "🔥過熱"

filtered_df['過熱感'] = filtered_df['RSI'].apply(rsi_status)

display_df = filtered_df[[
    '順位', '記号', '銘柄', '💯総合点', 
    'EPS', 'EPS点', 'PER', '割安点', 'ROE%', 'ROE点', 
    '利益率%', '利益点', '配当%', '配当点', '過熱感', 'RSI点', 
    '株価', 'MA50', 'トレンド点', '業績ボーナス',
    '予想PER', '予想PER点', 'PBR', 'PBR点', 'ROA%', 'ROA点'
]]

display_df = display_df.rename(columns={
    'EPS': '┃EPS', 'EPS点': 'EPS点(/10)',
    'PER': '┃PER', '割安点': '割安点(/15)',
    'ROE%': '┃ROE', 'ROE点': 'ROE点(/15)',
    '利益率%': '┃利益率', '利益点': '利益点(/15)',
    '配当%': '┃配当', '配当点': '配当点(/15)',
    '過熱感': '┃RSI', 'RSI点': 'RSI点(/20)',
    'MA50': '50日線', 'トレンド点': 'トレンド点(/10)',
    '業績ボーナス': '┃業績加点',
    '予想PER': '┃予想PER', '予想PER点': '予想PER点(/10)',
    'PBR': '┃PBR', 'PBR点': 'PBR点(/10)',
    'ROA%': '┃ROA', 'ROA点': 'ROA点(/10)'
})

if search_query and display_df.empty:
    st.warning("該当なし")
else:
    event = st.dataframe(
        display_df.set_index('順位'),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # 銘柄クリック時のチャート描画（ローソク足 ＋ 短期線20日 ＋ 中期線50日）
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        selected_row = display_df.iloc[selected_idx]
        selected_ticker = selected_row['記号']
        
        st.markdown(f"**📈 {selected_ticker} ({selected_row['銘柄']}) - 過去6ヶ月チャート**")
        
        with st.spinner("チャート読込中..."):
            try:
                stock_data = yf.Ticker(selected_ticker)
                hist = stock_data.history(period="6mo")
                if not hist.empty:
                    # 移動平均線の計算
                    hist['MA20'] = hist['Close'].rolling(window=20).mean()
                    hist['MA50'] = hist['Close'].rolling(window=50).mean()

                    # Plotlyによる本格チャート作成
                    fig = go.Figure()

                    # ローソク足
                    fig.add_trace(go.Candlestick(
                        x=hist.index,
                        open=hist['Open'],
                        high=hist['High'],
                        low=hist['Low'],
                        close=hist['Close'],
                        name='ローソク足'
                    ))

                    # 短期線（20日）
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=hist['MA20'],
                        line=dict(color='orange', width=1.5),
                        name='短期線(20日)'
                    ))

                    # 中期線（50日）
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=hist['MA50'],
                        line=dict(color='blue', width=1.5),
                        name='中期線(50日)'
                    ))

                    # チャートのレイアウト調整（下の余白を削りスッキリさせる）
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_rangeslider_visible=False,
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )

                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("チャートデータがありません。")
            except Exception:
                st.error("データの取得に失敗しました。")
