import streamlit as st
import pandas as pd
import os
import json
import datetime
import yfinance as yf
import plotly.graph_objects as go
import time
import base64
import requests

st.set_page_config(page_title="米国株AI格付け", layout="wide")

# ==========================================
# 0. GitHub連携の合鍵設定（Secretsから取得）
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

# ==========================================
# 1. 状態管理（前回設定の記憶機能 ＆ GitHub通信）
# ==========================================
if 'selected_stock' not in st.session_state: st.session_state.selected_stock = None
FAV_FILE = 'favorites.json'
SETTINGS_FILE = 'settings.json'

def load_favs():
    # GitHubから直接最新のお気に入りを取得する
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            try:
                content_b64 = res.json().get("content", "")
                decoded = base64.b64decode(content_b64).decode("utf-8")
                return json.loads(decoded)
            except: pass
    
    # 失敗した場合はローカルから読み込む（フォールバック）
    if os.path.exists(FAV_FILE):
        try:
            with open(FAV_FILE, 'r') as f: return json.load(f)
        except: pass
    return []

def save_favs(favs):
    # まずローカルに保存
    with open(FAV_FILE, 'w') as f: json.dump(favs, f)
    
    # GitHubのファイルを直接上書き更新する
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        
        # 現在のファイルのSHA（更新用パスワード）を取得
        res_get = requests.get(url, headers=headers)
        sha = res_get.json().get("sha") if res_get.status_code == 200 else None
        
        content_str = json.dumps(favs, indent=2)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        
        data = {"message": "Update favorites via Streamlit App", "content": content_b64}
        if sha: data["sha"] = sha
            
        res_put = requests.put(url, headers=headers, json=data)
        if res_put.status_code in [200, 201]:
            st.toast("✅ GitHubのお気に入りリストを同期しました！(明日のLINEに反映されます)")
        else:
            st.toast("⚠️ GitHubへの同期に失敗しました。設定を確認してください。")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"search_query": "", "show_only_favs": False, "max_p": 150, "strategy": "👑 究極の聖杯 (新旧融合)"}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f: json.dump(settings, f)

# 初回のみロード
if 'fav_list' not in st.session_state:
    st.session_state.fav_list = load_favs()

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

new_cols = ['PBR', 'ROA', '予想PER', 'FCFマージン', '粗利率', 'アクルーアル', 'MACD_GC', '次回決算日', '決算猶予日数', '出来高', '平均出来高50日', '200日MA', '20日高値']
for col in new_cols:
    if col not in df.columns: df[col] = 0

if '決算猶予日数' not in df.columns or df['出来高'].sum() == 0:
    st.info("💡 【AIからのお知らせ】最新データがありません。左のメニューから「最新ランキングを取得」を実行してください。")

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

strategies = ["👑 究極の聖杯 (新旧融合)", "🚀 大化け狙い (出来高急増・モメンタム)", "📉 暴落を拾う (逆張り)", "⚖️ 王道バランス (業績重視)", "🏛️ 伝統的割安 (バフェット流)"]
saved_strat = app_settings.get("strategy", strategies[0])
strat_idx = strategies.index(saved_strat) if saved_strat in strategies else 0

strategy = st.sidebar.radio("判定ロジック", strategies, index=strat_idx, label_visibility="collapsed", key="strat")

if (search_query != app_settings.get("search_query") or show_only_favs != app_settings.get("show_only_favs") or max_p != app_settings.get("max_p") or strategy != app_settings.get("strategy")):
    new_settings = {"search_query": search_query, "show_only_favs": show_only_favs, "max_p": max_p, "strategy": strategy}
    save_settings(new_settings)

st.sidebar.markdown("---")
st.sidebar.markdown("**🔄 データの最新化**")

if st.sidebar.button("最新ランキングを取得 (約2〜3分)", use_container_width=True):
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    tickers = df['記号'].tolist()
    updated_data = []
    total = len(tickers)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1y") 
            if not hist.empty and len(hist) >= 200:
                price = hist['Close'].iloc[-1]
                vol = hist['Volume'].iloc[-1]
                avg_vol_50 = hist['Volume'].tail(50).mean()
                ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
                ma200 = hist['Close'].rolling(window=200).mean().iloc[-1]
                high_20 = hist['Close'].tail(20).max()

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

                exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
                exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                macd_signal = macd.ewm(span=9, adjust=False).mean()
                macd_hist = macd - macd_signal
                is_macd_gc = 1 if (macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0) else 0

                days_to_earn = 999
                earnings_str = "-"
                try:
                    cal = stock.calendar
                    if isinstance(cal, dict) and 'Earnings Date' in cal:
                        e_dates = cal['Earnings Date']
                        if len(e_dates) > 0:
                            e_date = e_dates[0].date()
                            days_to_earn = (e_date - datetime.date.today()).days
                            if days_to_earn >= 0: earnings_str = e_date.strftime('%Y/%m/%d')
                except: pass

                financials, cashflow, balance_sheet = stock.financials, stock.cashflow, stock.balance_sheet
                fcf_margin_val, gross_margin_val, accruals_val = 0, 0, 0

                if not financials.empty and not cashflow.empty and not balance_sheet.empty:
                    try:
                        ni = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                        ocf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
                        ta = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
                        gp = financials.loc['Gross Profit'].iloc[0] if 'Gross Profit' in financials.index else 0
                        tr = financials.loc['Total Revenue'].iloc[0] if 'Total Revenue' in financials.index else 1
                        fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0

                        if ta > 0: accruals_val = (ni - ocf) / ta
                        if tr > 0: gross_margin_val = gp / tr
                        if tr > 0: fcf_margin_val = fcf / tr
                    except: pass
                
                updated_data.append({
                    '記号': ticker, '銘柄': info.get('shortName', ticker), '株価': price,
                    'PER': per or 0, '予想PER': f_per or 0, 'EPS': eps or 0,
                    'ROE': roe or 0, '利益率': margin or 0, '配当利回り': div or 0,
                    'PBR': pbr or 0, 'ROA': roa or 0, 'RSI': rsi, 'MA50': ma50,
                    'FCFマージン': fcf_margin_val, '粗利率': gross_margin_val, 'アクルーアル': accruals_val, 'MACD_GC': is_macd_gc,
                    '次回決算日': earnings_str, '決算猶予日数': days_to_earn,
                    '出来高': vol, '平均出来高50日': avg_vol_50, '200日MA': ma200, '20日高値': high_20
                })
        except: pass
        
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
        with col_title: st.markdown(f"## {selected_ticker} ({row['銘柄']})")
        with col_fav:
            if selected_ticker in st.session_state.fav_list:
                if st.button("★ お気に入り解除", use_container_width=True):
                    st.session_state.fav_list.remove(selected_ticker)
                    save_favs(st.session_state.fav_list)
                    st.rerun()
            else:
                if st.button("⭐ お気に入り追加", use_container_width=True):
                    st.session_state.fav_list.append(selected_ticker)
                    save_favs(st.session_state.fav_list)
                    st.rerun()

        st.markdown("##### 🏆 AI格付けスコア情報（グラデーション精密採点）")
        
        score_eps = 10 if row['EPS'] > 0 else -50
        score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
        score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
        
        days_to_earn = row['決算猶予日数']
        if days_to_earn == 999:
            earn_penalty, earn_status = 0, "➖ データなし (評価除外)"
        elif 0 <= days_to_earn <= 3:
            earn_penalty, earn_status = -20, f"💀 超危険 ({days_to_earn}日後) 完全ギャンブル状態。絶対回避！ (-20点)"
        elif 4 <= days_to_earn <= 7:
            earn_penalty, earn_status = -15, f"⚠️ 危険水域 ({days_to_earn}日後) 乱高下リスク増大 (-15点)"
        elif 8 <= days_to_earn <= 14:
            earn_penalty, earn_status = -10, f"⚡️ 警戒 ({days_to_earn}日後) 機関の警戒が高まる時期 (-10点)"
        elif 15 <= days_to_earn <= 30:
            earn_penalty, earn_status = -5, f"🟠 やや警戒 ({days_to_earn}日後) 決算が意識され始める (-5点)"
        elif 31 <= days_to_earn <= 45:
            earn_penalty, earn_status = -2, f"🟡 微警戒 ({days_to_earn}日後) アナリスト予想変動期 (-2点)"
        elif 46 <= days_to_earn <= 60:
            earn_penalty, earn_status = 0, f"✅ 安全圏 ({days_to_earn}日後) 決算ノイズなし (±0点)"
        else:
            earn_penalty, earn_status = 5, f"🌟 ゴールデンタイム ({days_to_earn}日後) 決算通過直後の最も安全な時期 (+5点)"

        vol_ratio = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0
        vol_status = f"{vol_ratio:.1f}倍 (1.5倍以上で大口参入の兆候)"
        trend_status = "✅ パーフェクトオーダー" if row['株価'] > row['MA50'] > row['200日MA'] else "❌ 上昇トレンド未達"

        str_eps = f"{score_eps:.1f}/10点 (黒字)" if score_eps > 0 else f"{score_eps:.1f}/10点 (赤字)"
        str_per = f"{score_per:.1f}/15点 (10倍で満点、25倍で0点)" if row['PER'] > 0 else "0.0/15点 (データなし/赤字)"
        
        info_df = pd.DataFrame({
            "指標": ["現在の株価", "🎯 次回決算日 (リスク)", "EPS(黒字か)", "PER(割安さ)", "ROE(稼ぐ力)", "📊 出来高急増(前日比)", "📈 トレンド(MA配列)"],
            "数値": [f"${row['株価']:.2f}", row['次回決算日'], f"${row['EPS']:.2f}", f"{row['PER']:.1f}倍" if row['PER']>0 else "-", f"{row['ROE']*100:.1f}%", f"平均の {vol_ratio:.1f}倍", "株価 > 50MA > 200MA"],
            "精密採点 / AIの評価": ["-", earn_status, str_eps, str_per, f"{score_roe:.1f}/15点", vol_status, trend_status]
        })
        st.table(info_df.set_index("指標"))

        st.markdown("---")
        st.markdown("##### 📈 テクニカルチャート")
        
        with st.spinner("最新チャートを描画中..."):
            try:
                stock_data = yf.Ticker(selected_ticker)
                hist = stock_data.history(period="1y", interval="1d")
                if not hist.empty:
                    hist['MA50'] = hist['Close'].rolling(window=50).mean()
                    hist['MA200'] = hist['Close'].rolling(window=200).mean()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='日足'))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], mode='lines', name='MA50(中期)', line=dict(color='yellow', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], mode='lines', name='MA200(長期)', line=dict(color='white', width=1.5)))
                    
                    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=450, hovermode="x unified", xaxis_rangeslider_visible=True)
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            except: st.error("データの取得に失敗しました。")

else:
    # --------------------------------------------------
    # 【一覧画面】
    # --------------------------------------------------
    st.subheader(f"🇺🇸 米国株AI格付け - {strategy}")
    
    filtered_df = df[df['株価'] <= max_p].copy()
    if search_query: filtered_df = filtered_df[filtered_df['記号'].str.contains(search_query.upper(), na=False) | filtered_df['銘柄'].str.contains(search_query, case=False, na=False)]
    if show_only_favs:
        filtered_df = filtered_df[filtered_df['記号'].isin(st.session_state.fav_list)] if st.session_state.fav_list else pd.DataFrame(columns=filtered_df.columns)

    if not filtered_df.empty:
        def calculate_scores(row):
            score_eps = 10 if row['EPS'] > 0 else -50
            score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
            score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
            score_margin = max(0, min(15, (row['利益率'] - 0.05) / 0.15 * 15))
            
            days_to_earn = row['決算猶予日数']
            earn_penalty = 0
            if days_to_earn != 999:
                if 0 <= days_to_earn <= 3: earn_penalty = -20
                elif 4 <= days_to_earn <= 7: earn_penalty = -15
                elif 8 <= days_to_earn <= 14: earn_penalty = -10
                elif 15 <= days_to_earn <= 30: earn_penalty = -5
                elif 31 <= days_to_earn <= 45: earn_penalty = -2
                elif 46 <= days_to_earn <= 60: earn_penalty = 0
                else: earn_penalty = 5 

            score_strat, score_fcf, score_macd, score_rocket = 0, 0, 0, 0
            rsi, price, ma50, ma200 = row['RSI'], row['株価'], row['MA50'], row['200日MA']
            vol_ratio = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0
            
            if strategy == "👑 究極の聖杯 (新旧融合)":
                score_fcf = max(0, min(10, (row['FCFマージン']) / 0.15 * 10))
                if row['MACD_GC'] == 1: score_macd = 15
                if rsi < 50: score_strat += 10
                if row['アクルーアル'] < 0: score_strat += 5
            elif strategy == "🚀 大化け狙い (出来高急増・モメンタム)":
                if price > ma50 > ma200: score_rocket += 10
                if vol_ratio >= 1.5: score_rocket += max(0, min(10, (vol_ratio - 1.0) * 5))
                if row['20日高値'] > 0 and price >= row['20日高値'] * 0.98: score_rocket += 10
                if rsi >= 85: score_rocket -= 20
                score_strat = score_rocket
            elif strategy == "📉 暴落を拾う (逆張り)":
                score_strat = max(0, min(20, (50 - rsi) / 20 * 20))
                if price < ma50 * 0.90: score_strat += 10 
            else:
                score_strat = 10 

            total_score = score_eps + score_per + score_roe + score_margin + score_strat + score_fcf + score_macd + earn_penalty
            
            return pd.Series([
                total_score, f"{score_eps:.1f}", f"{score_per:.1f}", f"{score_roe:.1f}", f"{score_rocket:.1f}", earn_penalty, vol_ratio, days_to_earn
            ])

        filtered_df[['💯総合点', 'EPS点', 'PER点', 'ROE点', '🚀急騰点', '決算減点', '出来高倍率', '決算猶予日数']] = filtered_df.apply(calculate_scores, axis=1)
        filtered_df = filtered_df.sort_values(by='💯総合点', ascending=False)
        filtered_df['順位'] = range(1, len(filtered_df) + 1)
        
        filtered_df['💯総合点'] = filtered_df['💯総合点'].apply(lambda x: f"{x:.1f}点")
        filtered_df['株価'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
        filtered_df['PER'] = filtered_df['PER'].apply(lambda x: f"{x:.1f}倍" if x > 0 else "-")
        filtered_df['出来高倍率'] = filtered_df['出来高倍率'].apply(lambda x: f"{x:.1f}倍")
        
        def format_risk(days):
            if days == 999: return "➖"
            elif 0 <= days <= 3: return "💀 直前回避"
            elif 4 <= days <= 7: return "⚠️ 危険水域"
            elif 8 <= days <= 14: return "⚡️ 警戒"
            elif 15 <= days <= 30: return "🟠 やや警戒"
            elif 31 <= days <= 45: return "🟡 微警戒"
            elif 46 <= days <= 60: return "✅ 安全"
            else: return "🌟 ｺﾞｰﾙﾃﾞﾝ"
            
        filtered_df['決算リスク'] = filtered_df['決算猶予日数'].apply(format_risk)

        if strategy == "🚀 大化け狙い (出来高急増・モメンタム)":
            display_df = filtered_df[['順位', '記号', '銘柄', '💯総合点', '決算リスク', '🚀急騰点', '出来高倍率', 'PER', '株価']]
        else:
            display_df = filtered_df[['順位', '記号', '銘柄', '💯総合点', '決算リスク', 'PER', 'PER点', 'ROE点', '株価']]

        st.markdown("👇 **気になる銘柄の行をタップすると詳細（なぜその点数になったか）が開きます**")
        event = st.dataframe(display_df.set_index('順位'), use_container_width=True, on_select="rerun", selection_mode="single-row")

        if len(event.selection.rows) > 0:
            st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
            st.rerun()
