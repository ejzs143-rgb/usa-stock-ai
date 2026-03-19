import streamlit as st
import pandas as pd
import os
import json
import datetime
import yfinance as yf
import plotly.graph_objects as go
import time

st.set_page_config(page_title="米国株AI格付け", layout="wide")

# ==========================================
# 1. 状態管理（前回設定の記憶機能）
# ==========================================
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = None

FAV_FILE = 'favorites.json'
SETTINGS_FILE = 'settings.json'

def load_favs():
    if os.path.exists(FAV_FILE):
        try:
            with open(FAV_FILE, 'r') as f: return json.load(f)
        except: pass
    return []

def save_favs(favs):
    with open(FAV_FILE, 'w') as f: json.dump(favs, f)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"search_query": "", "show_only_favs": False, "max_p": 150, "strategy": "👑 究極の聖杯 (新旧融合)"}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f: json.dump(settings, f)

fav_list = load_favs()
app_settings = load_settings()

# ==========================================
# 2. データ読み込みと不足列の補完
# ==========================================
file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在データを収集中です。数分後にリロードしてください。")
    st.stop()

df = pd.read_csv(file_path)
df.fillna(0, inplace=True) 

new_cols = ['PBR', 'ROA', '予想PER', 'FCFマージン', '粗利率', 'アクルーアル', 'MACD_GC']
for col in new_cols:
    if col not in df.columns: df[col] = 0

# ==========================================
# 3. グローバルサイドバー
# ==========================================
st.sidebar.markdown("**🔍 銘柄検索**")
search_query = st.sidebar.text_input("記号・名前", value=app_settings.get("search_query", ""), key="search_q", label_visibility="collapsed", placeholder="例: AAPL")

st.sidebar.markdown("---")
show_only_favs = st.sidebar.checkbox("⭐ お気に入り銘柄のみ表示", value=app_settings.get("show_only_favs", False), key="fav_check")

st.sidebar.markdown("---")
st.sidebar.markdown("**🕹️ 戦略設定 (採点ロジック)**")
max_p = st.sidebar.slider("予算上限 ($)", 10, 500, app_settings.get("max_p", 150), key="budget")

strategies = ["👑 究極の聖杯 (新旧融合)", "📈 勢いに乗る (モメンタム)", "📉 暴落を拾う (逆張り)", "⚖️ 王道バランス (業績重視)", "🏛️ 伝統的割安 (バフェット流)"]
saved_strat = app_settings.get("strategy", strategies[0])
strat_idx = strategies.index(saved_strat) if saved_strat in strategies else 0

strategy = st.sidebar.radio("判定ロジック", strategies, index=strat_idx, label_visibility="collapsed", key="strat")

if (search_query != app_settings.get("search_query") or 
    show_only_favs != app_settings.get("show_only_favs") or 
    max_p != app_settings.get("max_p") or 
    strategy != app_settings.get("strategy")):
    new_settings = {"search_query": search_query, "show_only_favs": show_only_favs, "max_p": max_p, "strategy": strategy}
    save_settings(new_settings)

st.sidebar.markdown("---")
st.sidebar.markdown("**🔄 データの最新化**")

if st.sidebar.button("最新ランキングを取得 (約1〜3分)", use_container_width=True):
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    tickers = df['記号'].tolist()
    updated_data = []
    total = len(tickers)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="6mo")
            if not hist.empty and len(hist) >= 50:
                price = hist['Close'].iloc[-1]
                eps = info.get('trailingEps', 0)
                per = info.get('trailingPE', 0)
                f_per = info.get('forwardPE', 0)
                roe = info.get('returnOnEquity', 0)
                margin = info.get('profitMargins', 0)
                div = info.get('dividendYield', 0)
                pbr = info.get('priceToBook', 0)
                roa = info.get('returnOnAssets', 0)
                
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50
                ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]

                exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
                exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                macd_signal = macd.ewm(span=9, adjust=False).mean()
                macd_hist = macd - macd_signal
                is_macd_gc = 1 if (macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0) else 0

                financials = stock.financials
                cashflow = stock.cashflow
                balance_sheet = stock.balance_sheet
                fcf_margin_val = 0
                gross_margin_val = 0
                accruals_val = 0

                if not financials.empty and not cashflow.empty and not balance_sheet.empty:
                    try:
                        net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                        op_cf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
                        total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
                        gross_profit = financials.loc['Gross Profit'].iloc[0] if 'Gross Profit' in financials.index else 0
                        total_revenue = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else 1
                        fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0

                        if total_assets > 0: accruals_val = (net_income - op_cf) / total_assets
                        if total_revenue > 0: gross_margin_val = gross_profit / total_revenue
                        if total_revenue > 0: fcf_margin_val = fcf / total_revenue
                    except Exception:
                        pass
                
                updated_data.append({
                    '記号': ticker, '銘柄': info.get('shortName', ticker), '株価': price,
                    'PER': per or 0, '予想PER': f_per or 0, 'EPS': eps or 0,
                    'ROE': roe or 0, '利益率': margin or 0, '配当利回り': div or 0,
                    'PBR': pbr or 0, 'ROA': roa or 0, 'RSI': rsi, 'MA50': ma50,
                    'FCFマージン': fcf_margin_val, '粗利率': gross_margin_val, 'アクルーアル': accruals_val, 'MACD_GC': is_macd_gc
                })
        except Exception: pass
        
        if i % 5 == 0 or i == total - 1:
            progress_bar.progress((i + 1) / total)
            status_text.text(f"高度データ取得中... {i+1} / {total}社完了")
            
    if updated_data:
        new_df = pd.DataFrame(updated_data)
        new_df.fillna(0, inplace=True)
        new_df.to_csv(file_path, index=False)
        status_text.text("✅ 更新完了！画面を再読み込みします...")
        time.sleep(1.5)
        st.rerun()

timestamp = os.path.getmtime(file_path)
utc_time = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
jst_time = utc_time.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
st.sidebar.caption(f"最終取得: {jst_time.strftime('%Y/%m/%d %H:%M')}")


# ==========================================
# 4. 画面ルーティング
# ==========================================

if st.session_state.selected_stock is not None:
    # --------------------------------------------------
    # 【個別詳細画面】
    # --------------------------------------------------
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

        st.markdown("##### 🏆 AI格付けスコア情報（グラデーション精密採点）")
        
        score_eps = 10 if row['EPS'] > 0 else -50
        score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
        score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
        score_margin = max(0, min(15, (row['利益率'] - 0.05) / 0.15 * 15))
        score_fcf = max(0, min(10, (row['FCFマージン']) / 0.15 * 10))
        score_gross = max(0, min(10, (row['粗利率'] - 0.20) / 0.20 * 10))

        str_eps = f"{score_eps:.1f}/10点 (黒字)" if score_eps > 0 else f"{score_eps:.1f}/10点 (赤字)"
        str_per = f"{score_per:.1f}/15点 (10倍で満点、25倍で0点)" if row['PER'] > 0 else "0.0/15点 (データなし/赤字)"
        str_roe = f"{score_roe:.1f}/15点 (20%で満点、5%で0点)"
        str_margin = f"{score_margin:.1f}/15点 (純利益率の連続評価)"
        
        str_fcf = f"{score_fcf:.1f}/10点 (現金の創出力)" if strategy == "👑 究極の聖杯 (新旧融合)" else "-"
        str_gross = f"{score_gross:.1f}/10点 (ブランド力・堀)" if strategy == "👑 究極の聖杯 (新旧融合)" else "-"
        macd_status = "✨ 反発初動 (ゴールデンクロス)" if row['MACD_GC'] == 1 else "待機中"
        accruals_status = "✅ 健全 (マイナス)" if row['アクルーアル'] < 0 else ("⚠️ 警戒" if row['アクルーアル'] > 0 else "データなし")

        val_fcf = f"{row['FCFマージン']*100:.1f}%" if row['FCFマージン'] != 0 else "-"
        val_gross = f"{row['粗利率']*100:.1f}%" if row['粗利率'] != 0 else "-"
        val_per = f"{row['PER']:.1f}倍" if row['PER'] > 0 else "-"

        info_df = pd.DataFrame({
            "指標": ["現在の株価", "EPS(黒字か)", "PER(割安さ)", "ROE(稼ぐ力)", "FCFマージン(現金創出)", "粗利率(価格決定力)", "アクルーアル(利益真贋)", "MACD(底打ち反発)"],
            "数値": [f"${row['株価']:.2f}", f"${row['EPS']:.2f}", val_per, f"{row['ROE']*100:.1f}%", val_fcf, val_gross, f"{row['アクルーアル']:.3f}", macd_status],
            "精密採点 / AIの評価": ["-", str_eps, str_per, str_roe, str_fcf, str_gross, accruals_status, "※聖杯モードでは反発時+15点加算"]
        })
        st.table(info_df.set_index("指標"))

        st.markdown("---")
        st.markdown("##### 📈 テクニカルチャート")
        
        col1, col2 = st.columns(2)
        with col1:
            period_choice = st.radio("表示期間", ["3ヶ月", "6ヶ月", "1年", "5年"], horizontal=True, key="p_choice")
        with col2:
            interval_choice = st.radio("足の長さ", ["日足", "週足", "月足"], horizontal=True, key="i_choice")

        interval_map = {"日足": "1d", "週足": "1wk", "月足": "1mo"}

        with st.spinner("最新チャートを描画中..."):
            try:
                stock_data = yf.Ticker(selected_ticker)
                hist_full = stock_data.history(period="10y", interval=interval_map[interval_choice])
                
                if not hist_full.empty:
                    hist_full['MA5'] = hist_full['Close'].rolling(window=5).mean()
                    hist_full['MA25'] = hist_full['Close'].rolling(window=25).mean()
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
                    st.markdown(f"🕒 リアルタイム価格: **${latest_price:.2f}**")
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                        name='ローソク足', increasing_line_color='#ff4b4b', decreasing_line_color='#0068c9'
                    ))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA5'], mode='lines', name='MA5(短期)', line=dict(color='yellow', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA25'], mode='lines', name='MA25(中期)', line=dict(color='#2ca02c', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA75'], mode='lines', name='MA75(長期)', line=dict(color='white', width=1.5)))
                    
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", height=450,
                        hovermode="x unified", xaxis_rangeslider_visible=True, dragmode="pan"
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                else:
                    st.warning("チャートデータがありません。")
            except Exception:
                st.error("データの取得に失敗しました。")

else:
    # --------------------------------------------------
    # 【一覧画面】
    # --------------------------------------------------
    st.subheader(f"🇺🇸 米国株AI格付け - {strategy}")
    
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
            score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
            score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
            score_margin = max(0, min(15, (row['利益率'] - 0.05) / 0.15 * 15))
            score_div = max(0, min(10, (row['配当利回り']) / 0.05 * 10))
            
            score_strat, score_fcf, score_gross, score_macd = 0, 0, 0, 0
            rsi, price, ma50 = row['RSI'], row['株価'], row['MA50']
            
            if strategy == "👑 究極の聖杯 (新旧融合)":
                score_fcf = max(0, min(10, (row['FCFマージン']) / 0.15 * 10))
                score_gross = max(0, min(10, (row['粗利率'] - 0.20) / 0.20 * 10))
                if row['MACD_GC'] == 1: score_macd = 15
                if rsi < 50: score_strat += 10
                if row['アクルーアル'] < 0: score_strat += 5
            elif strategy == "📈 勢いに乗る (モメンタム)":
                if 50 <= rsi <= 70: score_strat = 20 
                elif rsi > 75: score_strat = -20 
                if price > ma50 * 1.05: score_strat += 10 
            elif strategy == "📉 暴落を拾う (逆張り)":
                score_strat = max(0, min(20, (50 - rsi) / 20 * 20))
                if price < ma50 * 0.90: score_strat += 10 
            elif strategy == "⚖️ 王道バランス (業績重視)":
                if 40 <= rsi <= 60: score_strat = 15 
            elif strategy == "🏛️ 伝統的割安 (バフェット流)":
                if 0 < row['PBR'] <= 1.5: score_strat += 15
                elif 1.5 < row['PBR'] <= 3.0: score_strat += 5
                score_strat += max(0, min(10, (row['ROA']) / 0.05 * 10))

            total_score = score_eps + score_per + score_roe + score_margin + score_div + score_strat + score_fcf + score_gross + score_macd
            
            # 一覧画面でのスコア表示用文字列（例: "15.0点"）
            return pd.Series([
                total_score, f"{score_eps:.1f}", f"{score_per:.1f}", f"{score_roe:.1f}", 
                f"{score_fcf:.1f}", f"{score_gross:.1f}", f"{score_macd:.1f}"
            ])

        filtered_df[['💯総合点', 'EPS点', 'PER点', 'ROE点', 'FCF点', '粗利点', 'MACD点']] = filtered_df.apply(calculate_scores, axis=1)
        filtered_df = filtered_df.sort_values(by='💯総合点', ascending=False)
        filtered_df['順位'] = range(1, len(filtered_df) + 1)
        
        filtered_df['💯総合点'] = filtered_df['💯総合点'].apply(lambda x: f"{x:.1f}点")
        filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
        # 赤字やデータがない場合はハイフンにする
        filtered_df['PER'] = filtered_df['PER'].apply(lambda x: f"{x:.1f}倍" if x > 0 else "-")
        filtered_df['ROE%'] = filtered_df['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
        filtered_df['FCFマージン%'] = filtered_df['FCFマージン'].apply(lambda x: f"{x*100:.1f}%" if x != 0 else "-")
        filtered_df['粗利率%'] = filtered_df['粗利率'].apply(lambda x: f"{x*100:.1f}%" if x != 0 else "-")
        
        filtered_df['アクルーアル'] = filtered_df.apply(lambda row: "✅健全" if row['アクルーアル'] < 0 else ("⚠️警戒" if row['アクルーアル'] > 0 else "-"), axis=1)
        filtered_df['MACD反発'] = filtered_df['MACD_GC'].apply(lambda x: "🚀点灯" if x == 1 else "-")

        def rsi_status(rsi):
            if rsi < 30: return "🧊暴落"
            elif rsi < 40: return "📉下落"
            elif rsi < 60: return "⚪️平常"
            elif rsi < 70: return "📈上昇"
            else: return "🔥過熱"

        filtered_df['過熱感(RSI)'] = filtered_df['RSI'].apply(rsi_status)
        
        # モードによって表示する列とスコアの内訳をしっかり見せる
        if strategy == "👑 究極の聖杯 (新旧融合)":
            display_df = filtered_df[[
                '順位', '記号', '銘柄', '💯総合点', '過熱感(RSI)', 'MACD反発', 'MACD点', 'FCFマージン%', 'FCF点', '粗利率%', '粗利点', 'アクルーアル', 'PER', 'PER点', 'ROE%', 'ROE点', '株価'
            ]]
        else:
            display_df = filtered_df[[
                '順位', '記号', '銘柄', '💯総合点', '過熱感(RSI)', 'PER', 'PER点', 'ROE%', 'ROE点', '株価'
            ]]

        st.markdown("👇 **気になる銘柄の行をタップすると詳細（なぜその点数になったか）が開きます**")
        event = st.dataframe(display_df.set_index('順位'), use_container_width=True, on_select="rerun", selection_mode="single-row")

        if len(event.selection.rows) > 0:
            st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
            st.rerun()
