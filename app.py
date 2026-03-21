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

st.set_page_config(page_title=“米国株スコアリング”, layout=“wide”)

# ==========================================

# 0. GitHub連携

# ==========================================

try:
GITHUB_TOKEN = st.secrets[“GITHUB_TOKEN”]
GITHUB_REPO = st.secrets[“GITHUB_REPO”]
except:
GITHUB_TOKEN = os.environ.get(“GITHUB_TOKEN”, “”)
GITHUB_REPO = os.environ.get(“GITHUB_REPO”, “”)

# ==========================================

# 1. 状態管理

# ==========================================

if ‘selected_stock’ not in st.session_state:
st.session_state.selected_stock = None
FAV_FILE = ‘favorites.json’
SETTINGS_FILE = ‘settings.json’

def load_favs():
if GITHUB_TOKEN and GITHUB_REPO:
url = f”https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}”
headers = {“Authorization”: f”token {GITHUB_TOKEN}”,
“Accept”: “application/vnd.github.v3+json”}
res = requests.get(url, headers=headers)
if res.status_code == 200:
try:
return json.loads(base64.b64decode(res.json().get(“content”, “”)).decode(“utf-8”))
except:
pass
if os.path.exists(FAV_FILE):
try:
with open(FAV_FILE, ‘r’) as f: return json.load(f)
except:
pass
return []

def save_favs(favs):
with open(FAV_FILE, ‘w’) as f: json.dump(favs, f)
if GITHUB_TOKEN and GITHUB_REPO:
url = f”https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}”
headers = {“Authorization”: f”token {GITHUB_TOKEN}”,
“Accept”: “application/vnd.github.v3+json”}
res_get = requests.get(url, headers=headers)
sha = res_get.json().get(“sha”) if res_get.status_code == 200 else None
content_b64 = base64.b64encode(json.dumps(favs, indent=2).encode(“utf-8”)).decode(“utf-8”)
data = {“message”: “Update favorites”, “content”: content_b64}
if sha: data[“sha”] = sha
r = requests.put(url, headers=headers, json=data)
st.toast(“✅ GitHub同期” if r.status_code in [200, 201] else “⚠️ 同期失敗”)

def load_settings():
if os.path.exists(SETTINGS_FILE):
try:
with open(SETTINGS_FILE, ‘r’) as f: return json.load(f)
except: pass
return {“search_query”: “”, “show_only_favs”: False, “max_p”: 150,
“strategy”: “👑 究極の聖杯 (新旧融合)”}

def save_settings(s):
with open(SETTINGS_FILE, ‘w’) as f: json.dump(s, f)

if ‘fav_list’ not in st.session_state:
st.session_state.fav_list = load_favs()
app_settings = load_settings()

# ==========================================

# 2. データ読み込み

# ==========================================

file_path = ‘raw_stock_data.csv’
if not os.path.exists(file_path):
st.warning(“データ収集中です。数分後にリロードしてください。”)
st.stop()

df = pd.read_csv(file_path)
df.fillna(0, inplace=True)

for col in [‘PBR’, ‘ROA’, ‘予想PER’, ‘FCFマージン’, ‘粗利率’, ‘アクルーアル’,
‘MACD_GC’, ‘MACD_DC’, ‘次回決算日’, ‘決算猶予日数’, ‘出来高’,
‘平均出来高50日’, ‘200日MA’, ‘20日高値’, ‘配当日’,
‘52週高値’, ‘52週下落率’, ‘静寂後急増’, ‘BBスクイーズ’, ‘RSIダイバージェンス’]:
if col not in df.columns:
df[col] = 0 if col not in [‘次回決算日’, ‘配当日’] else “-”

# ==========================================

# 3. サイドバー

# ==========================================

st.sidebar.markdown(”**🔍 銘柄検索**”)
search_query = st.sidebar.text_input(“記号・名前”, value=app_settings.get(“search_query”, “”),
key=“sq”, label_visibility=“collapsed”)
st.sidebar.markdown(”—”)
show_only_favs = st.sidebar.checkbox(“⭐ お気に入りのみ”,
value=app_settings.get(“show_only_favs”, False), key=“fc”)
st.sidebar.markdown(”—”)
st.sidebar.markdown(”**🕹️ 戦略設定**”)
max_p = st.sidebar.slider(“予算上限 ($)”, 10, 500, app_settings.get(“max_p”, 150), key=“bd”)

strategies = [“👑 究極の聖杯 (新旧融合)”, “🚀 大化け狙い (モメンタム)”,
“📉 暴落を拾う (逆張り)”, “⚖️ 王道バランス (業績重視)”,
“🏛️ 伝統的割安 (バフェット流)”]
saved_strat = app_settings.get(“strategy”, strategies[0])
strat_idx = strategies.index(saved_strat) if saved_strat in strategies else 0
strategy = st.sidebar.radio(“判定ロジック”, strategies, index=strat_idx,
label_visibility=“collapsed”, key=“st”)

if (search_query != app_settings.get(“search_query”)
or show_only_favs != app_settings.get(“show_only_favs”)
or max_p != app_settings.get(“max_p”)
or strategy != app_settings.get(“strategy”)):
save_settings({“search_query”: search_query, “show_only_favs”: show_only_favs,
“max_p”: max_p, “strategy”: strategy})

st.sidebar.markdown(”—”)
if st.sidebar.button(“🔄 最新データ取得 (約2〜3分)”, use_container_width=True):
progress_bar = st.sidebar.progress(0)
status_text = st.sidebar.empty()
tickers = df[‘記号’].tolist()
updated_data = []
total = len(tickers)

```
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
            w52h = info.get('fiftyTwoWeekHigh', 0) or hist['Close'].max()
            w52drop = (w52h - price) / w52h if w52h > 0 else 0

            eps = info.get('trailingEps', 0); per = info.get('trailingPE', 0)
            f_per = info.get('forwardPE', 0); roe = info.get('returnOnEquity', 0)
            margin = info.get('profitMargins', 0); div = info.get('dividendYield', 0)
            pbr = info.get('priceToBook', 0); roa = info.get('returnOnAssets', 0)

            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if len(hist) > 14 and not pd.isna(rs.iloc[-1]) else 50

            e1 = hist['Close'].ewm(span=12, adjust=False).mean()
            e2 = hist['Close'].ewm(span=26, adjust=False).mean()
            mh = (e1 - e2) - (e1 - e2).ewm(span=9, adjust=False).mean()
            mgc = 1 if len(mh) > 2 and mh.iloc[-1] > 0 and mh.iloc[-2] <= 0 else 0
            mdc = 1 if len(mh) > 2 and mh.iloc[-1] < 0 and mh.iloc[-2] >= 0 else 0

            dte = 999; es = "-"
            try:
                cal = stock.calendar
                if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
                    ed = cal['Earnings Date'][0].date() if hasattr(cal['Earnings Date'][0], 'date') else pd.to_datetime(cal['Earnings Date'][0]).date()
                    dte = (ed - datetime.date.today()).days
                    if dte >= 0: es = ed.strftime('%Y/%m/%d')
            except: pass

            dds = "-"
            try:
                exd = info.get('exDividendDate')
                if exd: dds = datetime.datetime.fromtimestamp(exd).strftime('%Y/%m/%d')
            except: pass

            fin = stock.financials; cf = stock.cashflow; bs = stock.balance_sheet
            fm, gm, ac = 0, 0, 0
            if not fin.empty and not cf.empty and not bs.empty:
                try:
                    ni = fin.loc['Net Income'].iloc[0] if 'Net Income' in fin.index else 0
                    ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
                    ta = bs.loc['Total Assets'].iloc[0] if 'Total Assets' in bs.index else 1
                    gp = fin.loc['Gross Profit'].iloc[0] if 'Gross Profit' in fin.index else 0
                    tr = fin.loc['Total Revenue'].iloc[0] if 'Total Revenue' in fin.index else 1
                    fcf = cf.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cf.index else 0
                    if ta > 0: ac = (ni - ocf) / ta
                    if tr > 0: gm = gp / tr; fm = fcf / tr
                except: pass

            # 先行指標（手動更新時も計算）
            vds = 0
            if len(hist) >= 50 and avg_vol_50 > 0:
                r5 = hist['Volume'].iloc[-6:-1]
                if len(r5) == 5 and r5.mean() < avg_vol_50 * 0.5 and vol >= avg_vol_50 * 1.5:
                    vds = 1
            bbs = 0
            if len(hist) >= 120:
                bw = (hist['Close'].rolling(20).std() * 2) / hist['Close'].rolling(20).mean()
                bw = bw.dropna()
                if len(bw) >= 120 and bw.iloc[-1] <= bw.tail(120).quantile(0.20):
                    bbs = 1
            rdiv = 0
            if len(hist) >= 40:
                rseries = 100 - (100 / (1 + ((delta.where(delta > 0, 0)).rolling(14).mean() / (-delta.where(delta < 0, 0)).rolling(14).mean())))
                rseries = rseries.dropna()
                c40 = hist['Close'].tail(40); r40 = rseries.tail(40)
                if len(c40) >= 40 and len(r40) >= 40:
                    i1 = c40.iloc[:20].idxmin(); i2 = c40.iloc[20:].idxmin()
                    if i1 in r40.index and i2 in r40.index:
                        if c40.iloc[20:].min() < c40.iloc[:20].min() and r40.loc[i2] > r40.loc[i1]:
                            rdiv = 1

            updated_data.append({
                '記号': ticker, '銘柄': info.get('shortName', ticker), '株価': price,
                'PER': per or 0, '予想PER': f_per or 0, 'EPS': eps or 0,
                'ROE': roe or 0, '利益率': margin or 0, '配当利回り': div or 0,
                'PBR': pbr or 0, 'ROA': roa or 0, 'RSI': rsi, 'MA50': ma50,
                'FCFマージン': fm, '粗利率': gm, 'アクルーアル': ac,
                'MACD_GC': mgc, 'MACD_DC': mdc,
                '次回決算日': es, '決算猶予日数': dte, '出来高': vol,
                '平均出来高50日': avg_vol_50, '200日MA': ma200, '20日高値': high_20,
                '配当日': dds, '52週高値': w52h, '52週下落率': w52drop,
                '静寂後急増': vds, 'BBスクイーズ': bbs, 'RSIダイバージェンス': rdiv
            })
    except: pass
    if i % 5 == 0 or i == total - 1:
        progress_bar.progress((i + 1) / total)
        status_text.text(f"取得中... {i+1}/{total}社")

if updated_data:
    pd.DataFrame(updated_data).fillna(0).to_csv(file_path, index=False)
    status_text.text("✅ 更新完了！")
    time.sleep(1.5)
    st.rerun()
```

# ==========================================

# 4. 画面ルーティング

# ==========================================

if st.session_state.selected_stock is not None:
selected_ticker = st.session_state.selected_stock
if st.button(“🔙 一覧に戻る”, use_container_width=True):
st.session_state.selected_stock = None
st.rerun()

```
raw_row = df[df['記号'] == selected_ticker]
if not raw_row.empty:
    row = raw_row.iloc[0]
    col_t, col_f = st.columns([3, 1])
    with col_t: st.markdown(f"## {selected_ticker} ({row['銘柄']})")
    with col_f:
        if selected_ticker in st.session_state.fav_list:
            if st.button("★ 解除", use_container_width=True):
                st.session_state.fav_list.remove(selected_ticker)
                save_favs(st.session_state.fav_list); st.rerun()
        else:
            if st.button("⭐ 追加", use_container_width=True):
                st.session_state.fav_list.append(selected_ticker)
                save_favs(st.session_state.fav_list); st.rerun()

    st.markdown("##### 🏆 全指標データ")

    d = row['決算猶予日数']
    if d == 999: es = "➖ データなし"
    elif 0 <= d <= 3: es = f"💀 超危険 ({d}日後)"
    elif 4 <= d <= 7: es = f"⚠️ 危険水域 ({d}日後)"
    elif 8 <= d <= 14: es = f"⚡️ 警戒 ({d}日後)"
    elif 15 <= d <= 30: es = f"🟠 やや警戒 ({d}日後)"
    elif 31 <= d <= 45: es = f"🟡 微警戒 ({d}日後)"
    elif 46 <= d <= 60: es = f"✅ 安全圏 ({d}日後)"
    else: es = f"🌟 ゴールデンタイム ({d}日後)"

    vr = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0
    drop = row['52週下落率']; w52h = row['52週高値']
    if drop >= 0.30: de = "🏷️ 大幅割安圏"
    elif drop >= 0.15: de = "🏷️ 割安圏"
    elif drop >= 0.05: de = "⚪️ 適正圏"
    else: de = "🔺 高値圏"

    def rs(r):
        if r < 30: return "🧊 暴落圏"
        elif r < 40: return "📉 安値圏"
        elif r < 70: return "⚪️ 平常"
        else: return "🔥 過熱圏"

    # 先行指標まとめ
    precursors = []
    if row.get('静寂後急増', 0) == 1: precursors.append("出来高:静寂→急増")
    if row.get('BBスクイーズ', 0) == 1: precursors.append("BB:スクイーズ")
    if row.get('RSIダイバージェンス', 0) == 1: precursors.append("RSI:強気乖離")
    precursor_str = " / ".join(precursors) if precursors else "なし"
    precursor_eval = "⚡ 大変動の可能性あり" if precursors else "-"

    info_df = pd.DataFrame({
        "指標": [
            "1. 🎯 次回決算日", "2. 📅 配当日(権利落ち)",
            "3. 📍 52週高値からの位置",
            "4. ⚡ 大変動予兆",
            "5. EPS(利益)", "6. PER(割安度)", "7. PBR(資産割安度)",
            "8. 配当利回り", "9. ROE(稼ぐ力)", "10. ROA(資産効率)",
            "11. FCFマージン", "12. 粗利率", "13. アクルーアル",
            "14. RSI(過熱感)", "15. MACD", "16. 出来高", "17. トレンド"
        ],
        "数値": [
            row['次回決算日'],
            row.get('配当日', '-') if isinstance(row.get('配当日', '-'), str) else "-",
            f"高値${w52h:.0f} → 現在${row['株価']:.0f} (-{drop*100:.1f}%)" if w52h > 0 else "-",
            precursor_str,
            f"${row['EPS']:.2f}",
            f"{row['PER']:.1f}倍" if row['PER'] > 0 else "-",
            f"{row['PBR']:.2f}倍" if row['PBR'] > 0 else "-",
            f"{row['配当利回り']*100:.2f}%" if row['配当利回り'] > 0 else "-",
            f"{row['ROE']*100:.1f}%",
            f"{row['ROA']*100:.1f}%" if row['ROA'] != 0 else "-",
            f"{row['FCFマージン']*100:.1f}%" if row['FCFマージン'] != 0 else "-",
            f"{row['粗利率']*100:.1f}%" if row['粗利率'] != 0 else "-",
            f"{row['アクルーアル']:.3f}",
            f"{row['RSI']:.1f}", "-",
            f"平均の {vr:.1f}倍", "株価 > 50MA > 200MA"
        ],
        "評価": [
            es, "-", de, precursor_eval,
            "✅ 黒字" if row['EPS'] > 0 else "❌ 赤字",
            "割安" if 0 < row['PER'] <= 20 else ("-" if row['PER'] == 0 else "割高"),
            "割安" if 0 < row['PBR'] <= 3 else ("-" if row['PBR'] == 0 else "割高"),
            "高配当" if row['配当利回り'] >= 0.03 else "-",
            "超高収益" if row['ROE'] >= 0.15 else "標準",
            "優秀" if row['ROA'] >= 0.05 else "-",
            "優秀" if row['FCFマージン'] >= 0.15 else "-",
            "強い堀" if row['粗利率'] >= 0.40 else "-",
            "✅ 健全" if row['アクルーアル'] < 0 else "⚠️ 警戒",
            rs(row['RSI']),
            "✨ GC点灯" if row['MACD_GC'] == 1 else "待機中",
            "大化け兆候" if vr >= 1.5 else "-",
            "✅ 上昇" if row['株価'] > row['MA50'] > row['200日MA'] else "❌ 未達"
        ]
    })
    st.table(info_df.set_index("指標"))

    st.markdown("---")
    st.markdown("##### 📈 テクニカルチャート")
    c1, c2 = st.columns(2)
    with c1: pc = st.radio("期間", ["3ヶ月", "6ヶ月", "1年", "5年"], horizontal=True, key="pc")
    with c2: ic = st.radio("足", ["日足", "週足", "月足"], horizontal=True, key="ic")
    im = {"日足": "1d", "週足": "1wk", "月足": "1mo"}

    with st.spinner("チャート描画中..."):
        try:
            hf = yf.Ticker(selected_ticker).history(period="10y", interval=im[ic])
            if not hf.empty:
                hf['MA5'] = hf['Close'].rolling(5).mean()
                hf['MA25'] = hf['Close'].rolling(25).mean()
                hf['MA75'] = hf['Close'].rolling(75).mean()
                nm = {"日足": {"3ヶ月": 63, "6ヶ月": 126, "1年": 252, "5年": 1260},
                      "週足": {"3ヶ月": 13, "6ヶ月": 26, "1年": 52, "5年": 260},
                      "月足": {"3ヶ月": 3, "6ヶ月": 6, "1年": 12, "5年": 60}}
                h = hf.tail(nm[ic][pc])
                st.markdown(f"🕒 最新: **${h['Close'].iloc[-1]:.2f}**")
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=h.index, open=h['Open'], high=h['High'],
                    low=h['Low'], close=h['Close'], name='価格',
                    increasing_line_color='#ff4b4b', decreasing_line_color='#0068c9'))
                for n, c, cl in [('短期', 'MA5', 'yellow'), ('中期', 'MA25', '#2ca02c'), ('長期', 'MA75', 'white')]:
                    fig.add_trace(go.Scatter(x=h.index, y=h[c], mode='lines', name=n, line=dict(color=cl, width=1.5)))
                fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=450,
                                  hovermode="x unified", xaxis_rangeslider_visible=True)
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        except: st.error("チャート取得失敗")
```

else:
# –––––––––––––––––––––––––
# 【一覧画面】
# –––––––––––––––––––––––––
st.subheader(f”🇺🇸 米国株スコアリング - {strategy}”)

```
fdf = df[df['株価'] <= max_p].copy()
if search_query:
    fdf = fdf[fdf['記号'].str.contains(search_query.upper(), na=False)
              | fdf['銘柄'].str.contains(search_query, case=False, na=False)]
if show_only_favs:
    fdf = fdf[fdf['記号'].isin(st.session_state.fav_list)] if st.session_state.fav_list else pd.DataFrame(columns=fdf.columns)

if not fdf.empty:
    def calc(row):
        se = 10 if row['EPS'] > 0 else -50
        sp = max(0, min(15, (25 - row['PER']) / 15 * 15)) if row['PER'] > 0 else 0
        sr = max(0, min(15, (row['ROE'] - 0.05) / 0.15 * 15))
        sm = max(0, min(15, (row['利益率'] - 0.05) / 0.15 * 15))

        d = row['決算猶予日数']
        ep = 0
        if d != 999:
            if 0 <= d <= 3: ep = -20
            elif 4 <= d <= 7: ep = -15
            elif 8 <= d <= 14: ep = -10
            elif 15 <= d <= 30: ep = -5
            elif 31 <= d <= 45: ep = -2
            elif d > 60: ep = 5

        drop = row.get('52週下落率', 0)
        sd = 0
        if 0.15 <= drop <= 0.40: sd = min(15, (drop - 0.10) / 0.30 * 15)
        elif drop > 0.40: sd = 10

        ss, sf, sma, sro, spb, sra = 0, 0, 0, 0, 0, 0
        rsi = row['RSI']; price = row['株価']; ma50 = row['MA50']; ma200 = row['200日MA']
        vr = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0

        if strategy == "👑 究極の聖杯 (新旧融合)":
            sf = max(0, min(10, row['FCFマージン'] / 0.15 * 10))
            if row['MACD_GC'] == 1: sma = 15
            if rsi < 50: ss += 10
            if row['アクルーアル'] < 0: ss += 5
        elif strategy == "🚀 大化け狙い (モメンタム)":
            if price > ma50 > ma200: sro += 10
            if vr >= 1.5: sro += max(0, min(10, (vr - 1.0) * 5))
            if row['20日高値'] > 0 and price >= row['20日高値'] * 0.98: sro += 10
            if rsi >= 85: sro -= 20
            ss = sro
        elif strategy == "📉 暴落を拾う (逆張り)":
            ss = max(0, min(20, (50 - rsi) / 20 * 20))
            if ma50 > 0 and price < ma50 * 0.90: ss += 10
        elif strategy == "⚖️ 王道バランス (業績重視)":
            if 40 <= rsi <= 60: ss += 15
            if row['ROE'] > 0.15 and row['利益率'] > 0.15: ss += 10
        elif strategy == "🏛️ 伝統的割安 (バフェット流)":
            pbr = row['PBR']
            if 0 < pbr <= 1.5: spb = 15
            elif 1.5 < pbr <= 3.0: spb = 5
            sra = max(0, min(10, row['ROA'] / 0.05 * 10))
            ss = spb + sra

        total = se + sp + sr + sm + ss + sf + sma + sd + ep
        ris = "🧊暴落" if rsi < 30 else ("📉安値" if rsi < 40 else ("⚪️平常" if rsi < 70 else "🔥過熱"))
        tr = "✅上昇" if price > ma50 > ma200 else "❌未達"
        ds = f"-{drop*100:.0f}%" if drop >= 0.01 else "高値圏"

        # 先行指標まとめ
        sigs = []
        if row.get('静寂後急増', 0) == 1: sigs.append("Vol")
        if row.get('BBスクイーズ', 0) == 1: sigs.append("BB")
        if row.get('RSIダイバージェンス', 0) == 1: sigs.append("Div")
        sig_str = "⚡" + "/".join(sigs) if sigs else "-"

        return pd.Series([
            total, f"{se:.0f}", f"{sp:.0f}", f"{sr:.0f}", f"{sm:.0f}",
            f"{sf:.0f}", f"{sma:.0f}", f"{sro:.0f}", f"{spb:.0f}",
            f"{sra:.0f}", f"{sd:.0f}",
            ep, vr, d, ris, tr, ds, sig_str
        ])

    cols = ['💯総合点', 'EPS点', 'PER点', 'ROE点', '利益点', 'FCF点',
            'MACD点', '🚀急騰点', 'PBR点', 'ROA点', '割安点',
            '決算減点', '出来高倍率', '決算猶予_c', '過熱感', 'トレンド', '52週位置', '予兆']
    fdf[cols] = fdf.apply(calc, axis=1)
    fdf = fdf.sort_values('💯総合点', ascending=False)
    fdf['順位'] = range(1, len(fdf) + 1)

    fdf['💯総合点'] = fdf['💯総合点'].apply(lambda x: f"{x:.0f}点")
    fdf['株価表示'] = fdf['株価'].apply(lambda x: f"${x:.2f}")
    fdf['PER表示'] = fdf['PER'].apply(lambda x: f"{x:.1f}倍" if x > 0 else "-")
    fdf['PBR表示'] = fdf['PBR'].apply(lambda x: f"{x:.2f}倍" if x > 0 else "-")
    fdf['ROE表示'] = fdf['ROE'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
    fdf['ROA表示'] = fdf['ROA'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
    fdf['利益率表示'] = fdf['利益率'].apply(lambda x: f"{x*100:.1f}%" if x > 0 else "-")
    fdf['FCM表示'] = fdf['FCFマージン'].apply(lambda x: f"{x*100:.1f}%" if x != 0 else "-")
    fdf['AC表示'] = fdf['アクルーアル'].apply(lambda x: "✅健全" if x < 0 else ("⚠️警戒" if x > 0 else "-"))
    fdf['MACD表示'] = fdf['MACD_GC'].apply(lambda x: "🚀点灯" if x == 1 else "-")
    fdf['出来高表示'] = fdf['出来高倍率'].apply(lambda x: f"{x:.1f}倍")

    def fr(d):
        if d == 999: return "➖"
        elif 0 <= d <= 3: return "💀直前"
        elif 4 <= d <= 7: return "⚠️危険"
        elif 8 <= d <= 14: return "⚡警戒"
        elif 15 <= d <= 30: return "🟠注意"
        elif 31 <= d <= 45: return "🟡微注意"
        elif 46 <= d <= 60: return "✅安全"
        else: return "🌟好機"

    fdf['決算リスク'] = fdf['決算猶予_c'].apply(fr)

    cl = ['順位', '記号', '銘柄', '💯総合点', '52週位置', '予兆', '過熱感', 'トレンド',
          '決算リスク', '次回決算日', '配当日']
    cr = ['株価表示']

    if strategy == "👑 究極の聖杯 (新旧融合)":
        mid = ['割安点', 'MACD表示', 'MACD点', 'FCM表示', 'FCF点', 'AC表示',
               'PER表示', 'PER点', 'ROE表示', 'ROE点', '利益点', 'EPS点']
    elif strategy == "🚀 大化け狙い (モメンタム)":
        mid = ['🚀急騰点', '出来高表示', 'PER表示', 'PER点', 'ROE表示', 'ROE点']
    elif strategy == "📉 暴落を拾う (逆張り)":
        mid = ['割安点', 'PER表示', 'PER点', 'ROE表示', 'ROE点', '利益点', 'EPS点']
    elif strategy == "⚖️ 王道バランス (業績重視)":
        mid = ['割安点', 'PER表示', 'PER点', 'ROE表示', 'ROE点', '利益率表示', '利益点', 'EPS点']
    elif strategy == "🏛️ 伝統的割安 (バフェット流)":
        mid = ['割安点', 'PBR表示', 'PBR点', 'ROA表示', 'ROA点', 'PER表示', 'PER点']
    else:
        mid = ['PER表示', 'PER点', 'ROE表示', 'ROE点', 'EPS点']

    display_df = fdf[cl + mid + cr]
    st.markdown("👇 **行タップで詳細表示**")
    event = st.dataframe(display_df.set_index('順位'), use_container_width=True,
                         on_select="rerun", selection_mode="single-row")
    if len(event.selection.rows) > 0:
        st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
        st.rerun()
```
