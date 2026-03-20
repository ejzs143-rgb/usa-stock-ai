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

st.set_page_config(page_title="米国株スコアリング", layout="wide")

# ==========================================
# 0. GitHub連携の合鍵設定
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

# ==========================================
# 1. 状態管理
# ==========================================
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = None
FAV_FILE = 'favorites.json'
SETTINGS_FILE = 'settings.json'


def load_favs():
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            try:
                content_b64 = res.json().get("content", "")
                decoded = base64.b64decode(content_b64).decode("utf-8")
                return json.loads(decoded)
            except:
                pass
    if os.path.exists(FAV_FILE):
        try:
            with open(FAV_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []


def save_favs(favs):
    with open(FAV_FILE, 'w') as f:
        json.dump(favs, f)
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        res_get = requests.get(url, headers=headers)
        sha = res_get.json().get("sha") if res_get.status_code == 200 else None

        content_str = json.dumps(favs, indent=2)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        data = {"message": "Update favorites via Streamlit App", "content": content_b64}
        if sha:
            data["sha"] = sha

        res_put = requests.put(url, headers=headers, json=data)
        if res_put.status_code in [200, 201]:
            st.toast("✅ GitHubのお気に入りリストを同期しました！")
        else:
            st.toast("⚠️ GitHubへの同期に失敗しました。")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"search_query": "", "show_only_favs": False, "max_p": 150,
            "strategy": "👑 究極の聖杯 (新旧融合)"}


def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)


if 'fav_list' not in st.session_state:
    st.session_state.fav_list = load_favs()

app_settings = load_settings()

# ==========================================
# 2. データ読み込み
# ==========================================
file_path = 'raw_stock_data.csv'
if not os.path.exists(file_path):
    st.warning("現在データを収集中です。数分後にリロードしてください。")
    st.stop()

df = pd.read_csv(file_path)
df.fillna(0, inplace=True)

# 欠損列の安全装置（古いCSVとの互換性）
expected_cols = ['PBR', 'ROA', '予想PER', 'FCFマージン', '粗利率', 'アクルーアル',
                 'MACD_GC', 'MACD_DC', '次回決算日', '決算猶予日数', '出来高',
                 '平均出来高50日', '200日MA', '20日高値', '配当日']
for col in expected_cols:
    if col not in df.columns:
        df[col] = 0 if col not in ['次回決算日', '配当日'] else "-"

# ==========================================
# 3. サイドバー
# ==========================================
st.sidebar.markdown("**🔍 銘柄検索**")
search_query = st.sidebar.text_input("記号・名前", value=app_settings.get("search_query", ""),
                                     key="search_q", label_visibility="collapsed")

st.sidebar.markdown("---")
show_only_favs = st.sidebar.checkbox("⭐ お気に入り銘柄のみ表示",
                                     value=app_settings.get("show_only_favs", False), key="fav_check")

st.sidebar.markdown("---")
st.sidebar.markdown("**🕹️ 戦略設定 (採点ロジック)**")
max_p = st.sidebar.slider("予算上限 ($)", 10, 500, app_settings.get("max_p", 150), key="budget")

strategies = [
    "👑 究極の聖杯 (新旧融合)",
    "🚀 大化け狙い (出来高急増・モメンタム)",
    "📉 暴落を拾う (逆張り)",
    "⚖️ 王道バランス (業績重視)",
    "🏛️ 伝統的割安 (バフェット流)"
]
saved_strat = app_settings.get("strategy", strategies[0])
strat_idx = strategies.index(saved_strat) if saved_strat in strategies else 0
strategy = st.sidebar.radio("判定ロジック", strategies, index=strat_idx,
                            label_visibility="collapsed", key="strat")

if (search_query != app_settings.get("search_query")
        or show_only_favs != app_settings.get("show_only_favs")
        or max_p != app_settings.get("max_p")
        or strategy != app_settings.get("strategy")):
    new_settings = {"search_query": search_query, "show_only_favs": show_only_favs,
                    "max_p": max_p, "strategy": strategy}
    save_settings(new_settings)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 最新ランキングを取得 (約2〜3分)", use_container_width=True):
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

            if not hist.empty:
                price = hist['Close'].iloc[-1]
                vol = hist['Volume'].iloc[-1]
                avg_vol_50 = hist['Volume'].tail(50).mean() if len(hist) >= 50 else vol
                ma50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else price
                ma200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else price
                high_20 = hist['Close'].tail(20).max() if len(hist) >= 20 else price

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
                rsi = 100 - (100 / (1 + rs.iloc[-1])) if len(hist) > 14 and not pd.isna(rs.iloc[-1]) else 50

                exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
                exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                macd_signal = macd.ewm(span=9, adjust=False).mean()
                macd_hist_val = macd - macd_signal
                is_macd_gc = 1 if len(macd_hist_val) > 2 and (macd_hist_val.iloc[-1] > 0) and (macd_hist_val.iloc[-2] <= 0) else 0
                is_macd_dc = 1 if len(macd_hist_val) > 2 and (macd_hist_val.iloc[-1] < 0) and (macd_hist_val.iloc[-2] >= 0) else 0

                days_to_earn = 999
                earnings_str = "-"
                try:
                    cal = stock.calendar
                    if isinstance(cal, dict) and 'Earnings Date' in cal:
                        e_dates = cal['Earnings Date']
                        if len(e_dates) > 0:
                            e_date = e_dates[0].date() if hasattr(e_dates[0], 'date') else pd.to_datetime(e_dates[0]).date()
                            days_to_earn = (e_date - datetime.date.today()).days
                            if days_to_earn >= 0:
                                earnings_str = e_date.strftime('%Y/%m/%d')
                    elif isinstance(cal, pd.DataFrame) and not cal.empty and 'Earnings Date' in cal.index:
                        e_date = pd.to_datetime(cal.loc['Earnings Date'].iloc[0]).date()
                        days_to_earn = (e_date - datetime.date.today()).days
                        if days_to_earn >= 0:
                            earnings_str = e_date.strftime('%Y/%m/%d')
                except:
                    pass

                div_date_str = "-"
                try:
                    ex_div_ts = info.get('exDividendDate')
                    if ex_div_ts:
                        div_date_str = datetime.datetime.fromtimestamp(ex_div_ts).strftime('%Y/%m/%d')
                except:
                    pass

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
                        if ta > 0:
                            accruals_val = (ni - ocf) / ta
                        if tr > 0:
                            gross_margin_val = gp / tr
                            fcf_margin_val = fcf / tr
                    except:
                        pass

                updated_data.append({
                    '記号': ticker, '銘柄': info.get('shortName', ticker), '株価': price,
                    'PER': per or 0, '予想PER': f_per or 0, 'EPS': eps or 0,
                    'ROE': roe or 0, '利益率': margin or 0, '配当利回り': div or 0,
                    'PBR': pbr or 0, 'ROA': roa or 0, 'RSI': rsi, 'MA50': ma50,
                    'FCFマージン': fcf_margin_val, '粗利率': gross_margin_val,
                    'アクルーアル': accruals_val, 'MACD_GC': is_macd_gc, 'MACD_DC': is_macd_dc,
                    '次回決算日': earnings_str, '決算猶予日数': days_to_earn,
                    '出来高': vol, '平均出来高50日': avg_vol_50, '200日MA': ma200,
                    '20日高値': high_20, '配当日': div_date_str
                })
        except:
            pass

        if i % 5 == 0 or i == total - 1:
            progress_bar.progress((i + 1) / total)
            status_text.text(f"データ取得中... {i+1} / {total}社完了")

    if updated_data:
        new_df = pd.DataFrame(updated_data)
        new_df.fillna(0, inplace=True)
        new_df.to_csv(file_path, index=False)
        status_text.text("✅ 更新完了！画面を再読み込みします...")
        time.sleep(1.5)
        st.rerun()

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

        st.markdown("##### 🏆 全指標の精密データ")

        score_eps = 10 if row['EPS'] > 0 else -50
        score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
        score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))

        days_to_earn = row['決算猶予日数']
        if days_to_earn == 999:
            earn_status = "➖ データなし"
        elif 0 <= days_to_earn <= 3:
            earn_status = f"💀 超危険 ({days_to_earn}日後)"
        elif 4 <= days_to_earn <= 7:
            earn_status = f"⚠️ 危険水域 ({days_to_earn}日後)"
        elif 8 <= days_to_earn <= 14:
            earn_status = f"⚡️ 警戒 ({days_to_earn}日後)"
        elif 15 <= days_to_earn <= 30:
            earn_status = f"🟠 やや警戒 ({days_to_earn}日後)"
        elif 31 <= days_to_earn <= 45:
            earn_status = f"🟡 微警戒 ({days_to_earn}日後)"
        elif 46 <= days_to_earn <= 60:
            earn_status = f"✅ 安全圏 ({days_to_earn}日後)"
        else:
            earn_status = f"🌟 ゴールデンタイム ({days_to_earn}日後)"

        vol_ratio = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0
        trend_status = "✅ 上昇(Pオーダー)" if row['株価'] > row['MA50'] > row['200日MA'] else "❌ 未達"
        accruals_status = "✅ 健全 (マイナス)" if row['アクルーアル'] < 0 else "⚠️ 警戒"
        macd_status = "✨ ゴールデンクロス点灯" if row['MACD_GC'] == 1 else "待機中"

        def rsi_status(rsi):
            if rsi < 30:
                return "🧊 暴落圏"
            elif rsi < 40:
                return "📉 安値圏"
            elif rsi < 70:
                return "⚪️ 平常"
            else:
                return "🔥 過熱圏"

        # --- 詳細画面: 15項目（配当日追加）---
        info_df = pd.DataFrame({
            "指標": [
                "1. 🎯 次回決算日 (リスク)",
                "2. 📅 配当日 (権利落ち日)",
                "3. EPS (利益)",
                "4. PER (利益からの割安度)",
                "5. PBR (資産からの割安度)",
                "6. 配当利回り",
                "7. ROE (稼ぐ力)",
                "8. ROA (資産効率)",
                "9. FCFマージン (現金創出力)",
                "10. 粗利率 (ブランド力)",
                "11. アクルーアル (利益の真贋)",
                "12. RSI (過熱感)",
                "13. MACD (底打ち反発)",
                "14. 出来高急増 (大口参入)",
                "15. トレンド (MA配列)"
            ],
            "数値": [
                row['次回決算日'],
                row.get('配当日', '-') if isinstance(row.get('配当日', '-'), str) else "-",
                f"${row['EPS']:.2f}",
                f"{row['PER']:.1f}倍" if row['PER'] > 0 else "-",
                f"{row['PBR']:.2f}倍" if row['PBR'] > 0 else "-",
                f"{row['配当利回り']*100:.2f}%" if row['配当利回り'] > 0 else "-",
                f"{row['ROE']*100:.1f}%",
                f"{row['ROA']*100:.1f}%" if row['ROA'] != 0 else "-",
                f"{row['FCFマージン']*100:.1f}%" if row['FCFマージン'] != 0 else "-",
                f"{row['粗利率']*100:.1f}%" if row['粗利率'] != 0 else "-",
                f"{row['アクルーアル']:.3f}",
                f"{row['RSI']:.1f}",
                "-",
                f"平均の {vol_ratio:.1f}倍",
                "株価 > 50MA > 200MA"
            ],
            "評価": [
                earn_status,
                "-",
                "✅ 黒字" if row['EPS'] > 0 else "❌ 赤字",
                "割安" if 0 < row['PER'] <= 20 else ("-" if row['PER'] == 0 else "割高"),
                "割安" if 0 < row['PBR'] <= 3 else ("-" if row['PBR'] == 0 else "割高"),
                "高配当" if row['配当利回り'] >= 0.03 else "-",
                "超高収益" if row['ROE'] >= 0.15 else "標準",
                "優秀" if row['ROA'] >= 0.05 else "-",
                "優秀" if row['FCFマージン'] >= 0.15 else "-",
                "強い堀" if row['粗利率'] >= 0.40 else "-",
                accruals_status,
                rsi_status(row['RSI']),
                macd_status,
                "大化け兆候" if vol_ratio >= 1.5 else "-",
                trend_status
            ]
        })
        st.table(info_df.set_index("指標"))

        st.markdown("---")
        st.markdown("##### 📈 テクニカルチャート")
        col1, col2 = st.columns(2)
        with col1:
            period_choice = st.radio("表示期間", ["3ヶ月", "6ヶ月", "1年", "5年"],
                                     horizontal=True, key="p_choice")
        with col2:
            interval_choice = st.radio("足の長さ", ["日足", "週足", "月足"],
                                       horizontal=True, key="i_choice")

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
                        x=hist.index, open=hist['Open'], high=hist['High'],
                        low=hist['Low'], close=hist['Close'],
                        name='ローソク足', increasing_line_color='#ff4b4b',
                        decreasing_line_color='#0068c9'
                    ))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA5'], mode='lines',
                                            name='短期線', line=dict(color='yellow', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA25'], mode='lines',
                                            name='中期線', line=dict(color='#2ca02c', width=1.5)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA75'], mode='lines',
                                            name='長期線', line=dict(color='white', width=1.5)))

                    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=450,
                                      hovermode="x unified", xaxis_rangeslider_visible=True)
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            except:
                st.error("チャートデータの取得に失敗しました。")

else:
    # --------------------------------------------------
    # 【一覧画面】
    # --------------------------------------------------
    st.subheader(f"🇺🇸 米国株スコアリング - {strategy}")

    filtered_df = df[df['株価'] <= max_p].copy()
    if search_query:
        filtered_df = filtered_df[
            filtered_df['記号'].str.contains(search_query.upper(), na=False)
            | filtered_df['銘柄'].str.contains(search_query, case=False, na=False)
        ]
    if show_only_favs:
        if st.session_state.fav_list:
            filtered_df = filtered_df[filtered_df['記号'].isin(st.session_state.fav_list)]
        else:
            filtered_df = pd.DataFrame(columns=filtered_df.columns)

    if not filtered_df.empty:
        def calculate_scores(row):
            score_eps = 10 if row['EPS'] > 0 else -50
            score_per = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
            score_roe = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
            score_margin = max(0, min(15, (row['利益率'] - 0.05) / 0.15 * 15))

            days_to_earn = row['決算猶予日数']
            earn_penalty = 0
            if days_to_earn != 999:
                if 0 <= days_to_earn <= 3:
                    earn_penalty = -20
                elif 4 <= days_to_earn <= 7:
                    earn_penalty = -15
                elif 8 <= days_to_earn <= 14:
                    earn_penalty = -10
                elif 15 <= days_to_earn <= 30:
                    earn_penalty = -5
                elif 31 <= days_to_earn <= 45:
                    earn_penalty = -2
                elif 46 <= days_to_earn <= 60:
                    earn_penalty = 0
                else:
                    earn_penalty = 5

            score_strat, score_fcf, score_macd, score_rocket = 0, 0, 0, 0
            score_pbr, score_roa = 0, 0
            rsi = row['RSI']
            price = row['株価']
            ma50 = row['MA50']
            ma200 = row['200日MA']
            vol_ratio = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0

            if strategy == "👑 究極の聖杯 (新旧融合)":
                score_fcf = max(0, min(10, row['FCFマージン'] / 0.15 * 10))
                if row['MACD_GC'] == 1:
                    score_macd = 15
                if rsi < 50:
                    score_strat += 10
                if row['アクルーアル'] < 0:
                    score_strat += 5

            elif strategy == "🚀 大化け狙い (出来高急増・モメンタム)":
                if price > ma50 > ma200:
                    score_rocket += 10
                if vol_ratio >= 1.5:
                    score_rocket += max(0, min(10, (vol_ratio - 1.0) * 5))
                if row['20日高値'] > 0 and price >= row['20日高値'] * 0.98:
                    score_rocket += 10
                if rsi >= 85:
                    score_rocket -= 20
                score_strat = score_rocket

            elif strategy == "📉 暴落を拾う (逆張り)":
                score_strat = max(0, min(20, (50 - rsi) / 20 * 20))
                if ma50 > 0 and price < ma50 * 0.90:
                    score_strat += 10

            elif strategy == "⚖️ 王道バランス (業績重視)":
                # RSIが中間帯なら加点
                if 40 <= rsi <= 60:
                    score_strat += 15
                # ROEと利益率の両方が高い企業を評価
                if row['ROE'] > 0.15 and row['利益率'] > 0.15:
                    score_strat += 10

            elif strategy == "🏛️ 伝統的割安 (バフェット流)":
                # PBR評価（0〜15点）
                pbr = row['PBR']
                if 0 < pbr <= 1.5:
                    score_pbr = 15
                elif 1.5 < pbr <= 3.0:
                    score_pbr = 5
                # ROA評価（0〜10点）
                score_roa = max(0, min(10, row['ROA'] / 0.05 * 10))
                score_strat = score_pbr + score_roa

            total_score = (score_eps + score_per + score_roe + score_margin
                           + score_strat + score_fcf + score_macd + earn_penalty)

            # RSIステータス
            if rsi < 30:
                rsi_st = "🧊暴落圏"
            elif rsi < 40:
                rsi_st = "📉安値圏"
            elif rsi < 70:
                rsi_st = "⚪️平常"
            else:
                rsi_st = "🔥過熱圏"

            trend_str = "✅上昇" if price > ma50 > ma200 else "❌未達"

            return pd.Series([
                total_score, f"{score_eps:.0f}", f"{score_per:.0f}", f"{score_roe:.0f}",
                f"{score_margin:.0f}", f"{score_fcf:.0f}", f"{score_macd:.0f}",
                f"{score_rocket:.0f}", f"{score_pbr:.0f}", f"{score_roa:.0f}",
                earn_penalty, vol_ratio, days_to_earn, rsi_st, trend_str
            ])

        result_cols = ['💯総合点', 'EPS点', 'PER点', 'ROE点', '利益点', 'FCF点',
                       'MACD点', '🚀急騰点', 'PBR点', 'ROA点',
                       '決算減点', '出来高倍率', '決算猶予日数_calc', '過熱感', 'トレンド']
        filtered_df[result_cols] = filtered_df.apply(calculate_scores, axis=1)
        filtered_df = filtered_df.sort_values(by='💯総合点', ascending=False)
        filtered_df['順位'] = range(1, len(filtered_df) + 1)

        # 表示用フォーマット
        filtered_df['💯総合点'] = filtered_df['💯総合点'].apply(lambda x: f"{x:.0f}点")
        filtered_df['株価表示'] = filtered_df['株価'].apply(lambda x: f"${x:.2f}")
        filtered_df['PER表示'] = filtered_df['PER'].apply(lambda x: f"{x:.1f}倍" if x > 0 else "-")
        filtered_df['PBR表示'] = filtered_df['PBR'].apply(lambda x: f"{x:.2f}倍" if x > 0 else "-")
        filtered_df['ROE表示'] = filtered_df['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
        filtered_df['ROA表示'] = filtered_df['ROA'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
        filtered_df['利益率表示'] = filtered_df['利益率'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
        filtered_df['FCM表示'] = filtered_df['FCFマージン'].apply(lambda x: f"{x*100:.1f}%" if x != 0 else "-")
        filtered_df['粗利表示'] = filtered_df['粗利率'].apply(lambda x: f"{x*100:.1f}%" if x != 0 else "-")
        filtered_df['AC表示'] = filtered_df['アクルーアル'].apply(lambda x: "✅健全" if x < 0 else ("⚠️警戒" if x > 0 else "-"))
        filtered_df['MACD表示'] = filtered_df['MACD_GC'].apply(lambda x: "🚀点灯" if x == 1 else "-")
        filtered_df['出来高表示'] = filtered_df['出来高倍率'].apply(lambda x: f"{x:.1f}倍")

        def format_risk(days):
            if days == 999:
                return "➖"
            elif 0 <= days <= 3:
                return "💀直前"
            elif 4 <= days <= 7:
                return "⚠️危険"
            elif 8 <= days <= 14:
                return "⚡警戒"
            elif 15 <= days <= 30:
                return "🟠注意"
            elif 31 <= days <= 45:
                return "🟡微注意"
            elif 46 <= days <= 60:
                return "✅安全"
            else:
                return "🌟好機"

        filtered_df['決算リスク'] = filtered_df['決算猶予日数_calc'].apply(format_risk)

        # --- 戦略別の表示列 ---
        # 共通列: 順位, 記号, 銘柄, 総合点, 過熱感, トレンド, 決算リスク, 次回決算日, 配当日, 株価
        common_left = ['順位', '記号', '銘柄', '💯総合点', '過熱感', 'トレンド', '決算リスク', '次回決算日', '配当日']
        common_right = ['株価表示']

        if strategy == "👑 究極の聖杯 (新旧融合)":
            mid = ['MACD表示', 'MACD点', 'FCM表示', 'FCF点', 'AC表示', '粗利表示',
                   'PER表示', 'PER点', 'ROE表示', 'ROE点', '利益率表示', '利益点', 'EPS点']
        elif strategy == "🚀 大化け狙い (出来高急増・モメンタム)":
            mid = ['🚀急騰点', '出来高表示', 'PER表示', 'PER点', 'ROE表示', 'ROE点']
        elif strategy == "📉 暴落を拾う (逆張り)":
            mid = ['PER表示', 'PER点', 'ROE表示', 'ROE点', '利益率表示', '利益点', 'EPS点']
        elif strategy == "⚖️ 王道バランス (業績重視)":
            mid = ['PER表示', 'PER点', 'ROE表示', 'ROE点', '利益率表示', '利益点', 'EPS点']
        elif strategy == "🏛️ 伝統的割安 (バフェット流)":
            mid = ['PBR表示', 'PBR点', 'ROA表示', 'ROA点', 'PER表示', 'PER点', 'ROE表示', 'ROE点']
        else:
            mid = ['PER表示', 'PER点', 'ROE表示', 'ROE点', 'EPS点']

        display_df = filtered_df[common_left + mid + common_right]

        st.markdown("👇 **気になる銘柄の行をタップすると詳細が開きます**")
        event = st.dataframe(display_df.set_index('順位'), use_container_width=True,
                             on_select="rerun", selection_mode="single-row")

        if len(event.selection.rows) > 0:
            st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
            st.rerun()
