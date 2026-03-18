import streamlit as st
import pandas as pd
import os
import json
import datetime
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="米国株AI格付け", layout="wide")

if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = None

FAV_FILE = 'favorites.json'
def load_favs():
    if os.path.exists(FAV_FILE):
        with open(FAV_FILE, 'r') as f:
            return json.load(f)
    return []

def save_favs(favs):
    with open(FAV_FILE, 'w') as f:
        json.dump(favs, f)

fav_list = load_favs()

file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在データを収集中です。数分後にリロードしてください。")
    st.stop()

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

for col in ['PBR', 'ROA', '予想PER']:
    if col not in df.columns:
        df[col] = 0

if st.session_state.selected_stock is not None:
    # --- 個別詳細画面 ---
    selected_ticker = st.session_state.selected_stock
    
    if st.button("🔙 銘柄一覧に戻る", use_container_width=True):
        st.session_state.selected_stock = None
        st.rerun()

    raw_row = df[df['記号'] == selected_ticker]
    if not raw_row.empty:
        row = raw_row.iloc[0]
        
        col_title, col_fav = st.columns([3, 1])
        with col_title:
            st.markdown(f"## {selected_ticker} ({row['銘柄']})")
        with col_fav:
            if selected_ticker in fav_list:
                if st.button("★ お気に入り解除", use_container_width=True):
                    fav_list.remove(selected_ticker)
                    save_favs(fav_list)
                    st.rerun()
            else:
                if st.button("⭐ お気に入り追加", use_container_width=True):
                    fav_list.append(selected_ticker)
                    save_favs(fav_list)
                    st.rerun()

        st.markdown("##### 🏆 AI格付けスコア情報")
        score_eps = 10 if row['EPS'] > 0 else -50
        score_per = 15 if 0 < row['PER'] < 15 else (8 if 15 <= row['PER'] < 25 else 0)
        score_roe = 15 if row['ROE'] > 0.20 else (8 if row['ROE'] > 0.10 else 0)
        score_margin = 15 if row['利益率'] > 0.20 else (8 if row['利益率'] > 0.10 else 0)
        score_div = 15 if row['配当利回り'] > 0.04 else (8 if row['配当利回り'] > 0.02 else 0)
        
        info_df = pd.DataFrame({
            "指標": ["現在の株価", "EPS(黒字)", "PER(割安)", "ROE(稼ぐ力)", "利益率", "配当利回り"],
            "数値": [f"${row['株価']:.2f}", f"${row['EPS']:.2f}", f"{row['PER']:.1f}倍", f"{row['ROE']*100:.1f}%", f"{row['利益率']*100:.1f}%", f"{row['配当利回り']*100:.1f}%"],
            "獲得点": [f"-", f"{score_eps}/10点", f"{score_per}/15点", f"{score_roe}/15点", f"{score_margin}/15点", f"{score_div}/15点"]
        })
        st.table(info_df.set_index("指標"))

        st.markdown("---")
        st.markdown("##### 📈 テクニカルチャート (ローソク足 ＆ 移動平均線)")
        
        col1, col2 = st.columns(2)
        with col1:
            period_choice = st.radio("表示期間", ["3ヶ月", "6ヶ月", "1年", "5年"], horizontal=True)
        with col2:
            interval_choice = st.radio("足の長さ", ["日足", "週足", "月足"], horizontal=True)

        interval_map = {"日足": "1d", "週足": "1wk", "月足": "1mo"}
        now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        current_time_str = now_jst.strftime('%m/%d %H:%M:%S 取得')

        with st.spinner("最新チャートを描画中..."):
            try:
                stock_data = yf.Ticker(selected_ticker)
                # 移動平均の計算不足を防ぐため、裏で10年分の生データを取得
                hist_full = stock_data.history(period="10y", interval=interval_map[interval_choice])
                
                if not hist_full.empty:
                    hist_full['MA25'] = hist_full['Close'].rolling(window=25).mean()
                    hist_full['MA50'] = hist_full['Close'].rolling(window=50).mean()
                    hist_full['MA75'] = hist_full['Close'].rolling(window=75).mean()

                    if interval_choice == "日足":
                        days = {"3ヶ月": 63, "6ヶ月": 126, "1年": 252, "5年": 1260}[period_choice]
                        hist = hist_full.tail(days)
                    elif interval_choice == "週足":
                        weeks = {"3ヶ月": 13, "6ヶ月": 26, "1年": 52, "5年": 260}[period_choice]
                        hist = hist_full.tail(weeks)
                    else:
                        months = {"3ヶ月": 3, "6ヶ月": 6, "1年": 12, "5年": 60}[period_choice]
                        hist = hist_full.tail(months)

                    latest_price = hist['Close'].iloc[-1]
                    st.markdown(f"🕒 リアルタイム価格: **${latest_price:.2f}** ({current_time_str})")
                    st.caption("💡 【ズーム方法】チャート下の「専用バー（ツマミ）」を左右にスライドさせてください。")
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                        name='ローソク足', increasing_line_color='#ff4b4b', decreasing_line_color='#0068c9'
                    ))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA25'], mode='lines', name='MA25', line=dict(color='orange', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], mode='lines', name='MA50', line=dict(color='green', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA75'], mode='lines', name='MA75', line=dict(color='purple', width=1.5)))
                    
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="", yaxis_title="", height=450,
                        hovermode="x unified",
                        xaxis_rangeslider_visible=True, # ズームバー表示
                        dragmode="pan"
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                else:
                    st.warning("チャートデータがありません。")
            except Exception:
                st.error("データの取得に失敗しました。")

else:
    # --- 一覧画面 ---
    st.subheader("🇺🇸 米国株AI格付け")
    timestamp = os.path.getmtime(file_path)
    utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    st.caption(f"最終データ更新: {jst_time.strftime('%Y/%m/%d %H:%M')}")

    search_query = st.sidebar.text_input("🔍 銘柄検索 (例: AAPL)", "")
    st.sidebar.markdown("---")
    show_only_favs = st.sidebar.checkbox("⭐ お気に入り銘柄のみ表示", value=False)
    st.sidebar.markdown("---")
    max_p = st.sidebar.slider("予算上限 ($)", 10, 500, 150)
    strategy = st.sidebar.radio("判定ロジック", ["📈 勢いに乗る (モメンタム)", "📉 暴落を拾う (逆張り)", "⚖️ 王道バランス (業績重視)", "🏛️ 伝統的割安 (バフェット流)"], label_visibility="collapsed")

    filtered_df = df[df['株価'] <= max_p].copy()
    if search_query:
        filtered_df = filtered_df[filtered_df['記号'].str.contains(search_query.upper(), na=False) | filtered_df['銘柄'].str.contains(search_query, case=False, na=False)]

    if show_only_favs:
        if fav_list:
            filtered_df = filtered_df[filtered_df['記号'].isin(fav_list)]
        else:
            st.info("お気に入りに登録されている銘柄がありません。")
            filtered_df = pd.DataFrame(columns=filtered_df.columns)

    if not filtered_df.empty:
        def calculate_scores(row):
            score_eps = 10 if row['EPS'] > 0 else -50
            score_per = 15 if 0 < row['PER'] < 15 else (8 if 15 <= row['PER'] < 25 else 0)
            score_roe = 15 if row['ROE'] > 0.20 else (8 if row['ROE'] > 0.10 else 0)
            score_margin = 15 if row['利益率'] > 0.20 else (8 if row['利益率'] > 0.10 else 0)
            score_div = 15 if row['配当利回り'] > 0.04 else (8 if row['配当利回り'] > 0.02 else 0)
            score_rsi, score_trend, score_f_per, score_pbr, score_roa, score_bonus = 0, 0, 0, 0, 0, 0
            str_rsi, str_trend, str_f_per, str_pbr, str_roa, str_bonus = "-", "-", "-", "-", "-", "-"
            rsi, price, ma50 = row['RSI'], row['株価'], row['MA50']
            
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
                total_score, f"{score_eps}/10", f"{score_per}/15", f"{score_roe}/15", f"{score_margin}/15", f"{score_div}/15",
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
            '順位', '記号', '銘柄', '💯総合点', 'EPS', 'EPS点', 'PER', '割安点', 'ROE%', 'ROE点', '利益率%', '利益点', '配当%', '配当点',
            '過熱感', 'RSI点', '株価', 'MA50', 'トレンド点', '業績ボーナス', '予想PER', '予想PER点', 'PBR', 'PBR点', 'ROA%', 'ROA点'
        ]]
        display_df = display_df.rename(columns={
            'EPS': '┃EPS', 'EPS点': 'EPS点(/10)', 'PER': '┃PER', '割安点': '割安点(/15)', 'ROE%': '┃ROE', 'ROE点': 'ROE点(/15)',
            '利益率%': '┃利益率', '利益点': '利益点(/15)', '配当%': '┃配当', '配当点': '配当点(/15)', '過熱感': '┃RSI', 'RSI点': 'RSI点(/20)',
            'MA50': '50日平均線', 'トレンド点': 'トレンド点(/10)', '業績ボーナス': '┃業績加点',
            '予想PER': '┃予想PER', '予想PER点': '予想PER点(/10)', 'PBR': '┃PBR', 'PBR点': 'PBR点(/10)', 'ROA%': '┃ROA', 'ROA点': 'ROA点(/10)'
        })

        st.markdown("👇 **気になる銘柄の行をタップすると詳細画面が開きます**")
        event = st.dataframe(display_df.set_index('順位'), use_container_width=True, on_select="rerun", selection_mode="single-row")

        if len(event.selection.rows) > 0:
            st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
            st.rerun()
