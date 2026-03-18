import streamlit as st
import pandas as pd
import os
import datetime
import yfinance as yf
import plotly.graph_objects as go # 【新機能】プロ仕様のチャート描画エンジン

st.set_page_config(page_title="米国株AI格付け", layout="wide")

# タイトルを最小限にスリム化
st.subheader("🇺🇸 米国株AI格付け")

file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("データ収集中...")
    st.stop()

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

for col in ['PBR', 'ROA', '予想PER']:
    if col not in df.columns:
        df[col] = 0

# --- サイドメニュー（文字サイズ縮小・極限までシンプル化） ---
st.sidebar.markdown("**🔍 銘柄検索**")
search_query = st.sidebar.text_input("記号・名前", "", label_visibility="collapsed", placeholder="例: AAPL")

st.sidebar.markdown("---")
st.sidebar.markdown("**🕹️ 戦略設定**")
max_p = st.sidebar.slider("予算上限 ($)", 10, 500, 150)

strategy = st.sidebar.radio(
    "判定ロジック", 
    [
        "📈 勢いに乗る (モメンタム)", 
        "📉 暴落を拾う (逆張り)", 
        "⚖️ 王道バランス (業績重視)",
        "🏛️ 伝統的割安 (バフェット流)"
    ],
    label_visibility="collapsed"
)

# ランキングデータの最終更新日時をサイドバー下部にひっそりと配置
st.sidebar.markdown("---")
timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
st.sidebar.caption(f"ランキング更新: {jst_time.strftime('%Y/%m/%d %H:%M')}")


filtered_df = df[df['株価'] <= max_p].copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df['記号'].str.contains(search_query.upper(), na=False) | 
        filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
    ]

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
    
    if strategy == "📈 勢いに乗る (モメンタム)":
        if 50 <= rsi <= 70: score_rsi = 20 
        elif rsi > 75: score_rsi = -20 
        elif rsi < 40: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        if price > ma50 * 1.05: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "📉 暴落を拾う (逆張り)":
        if rsi < 30: score_rsi = 20 
        elif rsi < 40: score_rsi = 10 
        elif rsi > 60: score_rsi = -10 
        str_rsi = f"{score_rsi}/20"
        if price < ma50 * 0.90: score_trend = 10 
        str_trend = f"{score_trend}/10"

    elif strategy == "⚖️ 王道バランス (業績重視)":
        if 40 <= rsi <= 60: score_rsi = 15 
        if rsi > 70 or rsi < 30: score_rsi = -10 
        str_rsi = f"{score_rsi}/15"
        if row['ROE'] > 0.15 and row['利益率'] > 0.15: score_bonus = 15 
        str_bonus = f"{score_bonus}/15"

    elif strategy == "🏛️ 伝統的割安 (バフェット流)":
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
    'EPS', 'EPS点', 
    'PER', '割安点', 
    'ROE%', 'ROE点', 
    '利益率%', '利益点', 
    '配当%', '配当点',
    '過熱感', 'RSI点', 
    '株価', 'MA50', 'トレンド点',
    '業績ボーナス',
    '予想PER', '予想PER点', 
    'PBR', 'PBR点', 
    'ROA%', 'ROA点'
]]

display_df = display_df.rename(columns={
    'EPS': '┃EPS', 'EPS点': 'EPS点(/10)',
    'PER': '┃PER', '割安点': '割安点(/15)',
    'ROE%': '┃ROE', 'ROE点': 'ROE点(/15)',
    '利益率%': '┃利益率', '利益点': '利益点(/15)',
    '配当%': '┃配当', '配当点': '配当点(/15)',
    '過熱感': '┃RSI', 'RSI点': 'RSI点(/20)',
    'MA50': '50日平均線', 'トレンド点': 'トレンド点(/10)',
    '業績ボーナス': '┃業績加点',
    '予想PER': '┃予想PER', '予想PER点': '予想PER点(/10)',
    'PBR': '┃PBR', 'PBR点': 'PBR点(/10)',
    'ROA%': '┃ROA', 'ROA点': 'ROA点(/10)'
})

if search_query and display_df.empty:
    st.warning("条件に一致する銘柄が見つかりません。")
else:
    st.caption("👇 銘柄の行をクリックすると、リアルタイムの株価チャートが表示されます")
    event = st.dataframe(
        display_df.set_index('順位'),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # 銘柄クリック時の最新チャート描画処理
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        selected_row = display_df.iloc[selected_idx]
        selected_ticker = selected_row['記号']
        
        st.markdown("---")
        
        # チャートの期間と足の長さを選ぶボタン
        col1, col2 = st.columns(2)
        with col1:
            period_choice = st.radio("表示期間", ["3ヶ月", "6ヶ月", "1年", "5年"], horizontal=True)
        with col2:
            interval_choice = st.radio("足の長さ", ["日足", "週足", "月足"], horizontal=True)

        period_map = {"3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "5年": "5y"}
        interval_map = {"日足": "1d", "週足": "1wk", "月足": "1mo"}

        now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        current_time_str = now_jst.strftime('%Y/%m/%d %H:%M:%S 取得')

        with st.spinner("米国市場から最新データを取得中..."):
            try:
                stock_data = yf.Ticker(selected_ticker)
                hist = stock_data.history(period=period_map[period_choice], interval=interval_map[interval_choice])
                
                if not hist.empty:
                    latest_price = hist['Close'].iloc[-1]
                    st.markdown(f"**{selected_ticker} ({selected_row['銘柄']})**　現在の最新株価: **${latest_price:.2f}** 🕒 {current_time_str}")
                    
                    # Plotlyを使った高品質・安定操作のラインチャート
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=hist.index, 
                        y=hist['Close'], 
                        mode='lines', 
                        name='終値',
                        line=dict(color='#1f77b4', width=2)
                    ))
                    
                    # チャートのレイアウト調整（暴発ズームを抑える設定）
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="",
                        yaxis_title="株価 (USD)",
                        height=400,
                        dragmode="pan", # デフォルトを移動モードにし、過敏なズームを防ぐ
                        hovermode="x unified"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("チャートデータが取得できませんでした。")
            except Exception:
                st.error("データの取得に失敗しました。")
