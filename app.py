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

st.set_page_config(page_title="Stock Scoring", layout="wide")

try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = None
FAV_FILE = 'favorites.json'
SETTINGS_FILE = 'settings.json'
PURCHASES_FILE = 'purchases.json'


def load_favs():
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FAV_FILE}"
        h = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=h)
        if r.status_code == 200:
            try: return json.loads(base64.b64decode(r.json().get("content", "")).decode("utf-8"))
            except: pass
    if os.path.exists(FAV_FILE):
        try:
            with open(FAV_FILE, 'r') as f: return json.load(f)
        except: pass
    return []


def save_favs(favs):
    with open(FAV_FILE, 'w') as f: json.dump(favs, f)
    if GITHUB_TOKEN and GITHUB_REPO:
        _github_save(FAV_FILE, json.dumps(favs, indent=2), "Update favorites")


def load_purchases():
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PURCHASES_FILE}"
        h = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=h)
        if r.status_code == 200:
            try: return json.loads(base64.b64decode(r.json().get("content", "")).decode("utf-8"))
            except: pass
    if os.path.exists(PURCHASES_FILE):
        try:
            with open(PURCHASES_FILE, 'r') as f: return json.load(f)
        except: pass
    return {}


def save_purchases(purch):
    with open(PURCHASES_FILE, 'w') as f: json.dump(purch, f)
    if GITHUB_TOKEN and GITHUB_REPO:
        _github_save(PURCHASES_FILE, json.dumps(purch, indent=2), "Update purchases")


def _github_save(filename, content_str, message):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    h = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    rg = requests.get(url, headers=h)
    sha = rg.json().get("sha") if rg.status_code == 200 else None
    b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    d = {"message": message, "content": b64}
    if sha: d["sha"] = sha
    rp = requests.put(url, headers=h, json=d)
    st.toast("GitHub同期OK" if rp.status_code in [200, 201] else "GitHub同期失敗")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"search_query": "", "show_only_favs": False, "max_p": 200, "mode": "short"}


def save_settings(s):
    with open(SETTINGS_FILE, 'w') as f: json.dump(s, f)


if 'fav_list' not in st.session_state:
    st.session_state.fav_list = load_favs()
if 'purchases' not in st.session_state:
    st.session_state.purchases = load_purchases()
app_s = load_settings()

fp = 'raw_stock_data.csv'
if not os.path.exists(fp):
    st.warning("データ収集中です。数分後にリロードしてください。")
    st.stop()
df = pd.read_csv(fp)
df.fillna(0, inplace=True)

for col in ['PBR', 'ROA', 'FCFマージン', '粗利率', 'アクルーアル',
            'MACD_GC', 'MACD_DC', '次回決算日', '決算猶予日数', '出来高',
            '平均出来高50日', '200日MA', '20日高値', '配当日',
            '52週高値', '52週下落率', '静寂後急増', 'BBスクイーズ', 'RSIダイバージェンス']:
    if col not in df.columns:
        df[col] = 0 if col not in ['次回決算日', '配当日'] else "-"

# === Sidebar ===
st.sidebar.markdown("**検索**")
sq = st.sidebar.text_input("記号・名前", value=app_s.get("search_query", ""), key="sq", label_visibility="collapsed")
st.sidebar.markdown("---")
fav_only = st.sidebar.checkbox("お気に入りのみ", value=app_s.get("show_only_favs", False), key="fo")
st.sidebar.markdown("---")
st.sidebar.markdown("**モード**")
modes = ["⚡ 短期トレード", "👑 中長期投資"]
mode_keys = {"⚡ 短期トレード": "short", "👑 中長期投資": "long"}
saved_mode = app_s.get("mode", "short")
mode_idx = 0 if saved_mode == "short" else 1
mode = st.sidebar.radio("評価モード", modes, index=mode_idx, key="md", label_visibility="collapsed")
is_short = mode_keys[mode] == "short"
st.sidebar.markdown("---")
max_p = st.sidebar.slider("予算上限 ($)", 10, 500, app_s.get("max_p", 200), key="mp")

new_s = {"search_query": sq, "show_only_favs": fav_only, "max_p": max_p,
         "mode": "short" if is_short else "long"}
if new_s != app_s:
    save_settings(new_s)

# === スコア判定凡例 ===
st.sidebar.markdown("---")
st.sidebar.markdown("**判定基準**")
st.sidebar.markdown("80点以上 = 買い検討◎\n\n60-79点 = 監視\n\n40-59点 = 様子見\n\n40点未満 = 見送り")

# =============================================================================
# Scoring
# =============================================================================
def linear(value, floor_val, ceil_val, max_pts):
    if ceil_val == floor_val:
        return max_pts if value == ceil_val else 0
    ratio = (value - floor_val) / (ceil_val - floor_val)
    return round(max(0, min(max_pts, ratio * max_pts)), 1)

def earn_score(d, max_pts):
    if d == 999: return round(max_pts * 0.5, 1)
    if d > 60: return max_pts
    if d >= 14: return linear(d, 14, 60, max_pts)
    if d >= 7: return round(linear(d, 14, 7, -max_pts * 0.5), 1)
    return -max_pts

def ma50_gap_score(p, m50, max_pts):
    if m50 <= 0: return 0
    gap = (p - m50) / m50
    if -0.08 <= gap <= -0.03: return max_pts
    elif -0.12 <= gap < -0.03: return linear(gap, -0.12, -0.08, max_pts)
    elif -0.03 < gap <= 0: return linear(gap, 0, -0.03, max_pts)
    return 0

def dryup_score(vr, max_pts):
    if vr <= 0: return 0
    return linear(vr, 1.5, 0.7, max_pts)

def action_label(score):
    if score >= 80: return "買い検討◎"
    elif score >= 60: return "監視"
    elif score >= 40: return "様子見"
    else: return "見送り"

# 用語説明辞書
TERM_HELP = {
    "RSI": "売られすぎ度。低いほど反発しやすい（30以下が狙い目）",
    "MACD": "トレンド転換シグナル。GC(ゴールデンクロス)点灯で底打ちの兆候",
    "52w下落": "52週高値からの下落率。大きいほど割安な位置にいる",
    "MA50乖離": "50日移動平均線からの距離。-3%〜-8%が押し目の好位置",
    "出来高": "売買の活発さ。平均の2倍以上なら大口が動いた可能性",
    "売り枯れ": "出来高が平均より少ない状態。売りが枯れれば反転が近い",
    "予兆": "大変動の先行指標(BB煮詰まり/出来高異変/RSI乖離)の検知数",
    "トレンド": "株価>50日線>200日線なら上昇トレンド",
    "決算": "次回決算日までの距離。近いとギャンブル性が高まる",
    "EPS": "1株あたり利益。黒字は大前提",
    "ROE": "株主のお金でどれだけ稼いだか。高いほど経営が上手い",
    "利益率": "売上に対する利益の割合。高いほど儲かる体質",
    "PER": "株価が利益の何倍か。低いほど割安(お買い得)",
    "FCF": "事業で実際に残った現金。利益より信頼できる指標",
    "粗利率": "売値と原価の差。高い=競争に強いブランド力がある",
    "利益質": "利益が本物の現金か(アクルーアル)。マイナスなら健全",
}


def score_short_detail(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    vol = row.get('出来高', 0); avg_vol = row.get('平均出来高50日', 0)
    vr = vol / avg_vol if avg_vol > 0 else 0
    p = row.get('株価', 0); m50 = row.get('MA50', 0); m200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)
    pc = int(row.get('静寂後急増', 0)) + int(row.get('BBスクイーズ', 0)) + int(row.get('RSIダイバージェンス', 0))
    return [
        ("RSI", linear(rsi, 60, 30, 12), 12),
        ("MACD", 12 if row.get('MACD_GC', 0) == 1 else 0, 12),
        ("52w下落", linear(drop, 0.05, 0.30, 10), 10),
        ("MA50乖離", ma50_gap_score(p, m50, 10), 10),
        ("出来高", linear(vr, 1.0, 2.0, 8), 8),
        ("売り枯れ", dryup_score(vr, 8), 8),
        ("予兆", linear(pc, 0, 3, 8), 8),
        ("トレンド", 8 if p > m50 > m200 and m50 > 0 else 0, 8),
        ("決算", earn_score(d, 8), 8),
        ("EPS", 5 if row.get('EPS', 0) > 0 else 0, 5),
        ("ROE", linear(row.get('ROE', 0), 0.05, 0.15, 5), 5),
        ("利益率", linear(row.get('利益率', 0), 0.05, 0.15, 6), 6),
    ]


def score_long_detail(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    p = row.get('株価', 0); m50 = row.get('MA50', 0); m200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)
    per = row.get('PER', 0)
    vol = row.get('出来高', 0); avg_vol = row.get('平均出来高50日', 0)
    vr = vol / avg_vol if avg_vol > 0 else 0
    return [
        ("ROE", linear(row.get('ROE', 0), 0.05, 0.20, 10), 10),
        ("PER", linear(per, 25, 10, 10) if per > 0 else 0, 10),
        ("利益率", linear(row.get('利益率', 0), 0.05, 0.20, 8), 8),
        ("FCF", linear(row.get('FCFマージン', 0), 0, 0.15, 8), 8),
        ("52w下落", linear(drop, 0.05, 0.35, 8), 8),
        ("MA50乖離", ma50_gap_score(p, m50, 8), 8),
        ("粗利率", linear(row.get('粗利率', 0), 0.20, 0.50, 7), 7),
        ("RSI", linear(rsi, 60, 30, 7), 7),
        ("MACD", 7 if row.get('MACD_GC', 0) == 1 else 0, 7),
        ("売り枯れ", dryup_score(vr, 6), 6),
        ("決算", earn_score(d, 6), 6),
        ("EPS", 5 if row.get('EPS', 0) > 0 else 0, 5),
        ("利益質", 5 if row.get('アクルーアル', 0) < 0 else 0, 5),
        ("トレンド", 5 if p > m50 > m200 and m50 > 0 else 0, 5),
    ]


def calc_total(items):
    return round(sum(s for _, s, _ in items), 1)

def get_detail_func():
    return score_short_detail if is_short else score_long_detail


# === Manual refresh ===
st.sidebar.markdown("---")
if st.sidebar.button("🔄 最新データ取得", use_container_width=True):
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    tickers = df['記号'].tolist()
    updated = []
    total = len(tickers)
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1y")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                vol = hist['Volume'].iloc[-1]
                av50 = hist['Volume'].tail(50).mean() if len(hist) >= 50 else vol
                ma50 = hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else price
                ma200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else price
                h20 = hist['Close'].tail(20).max() if len(hist) >= 20 else price
                w52h = info.get('fiftyTwoWeekHigh', 0) or hist['Close'].max()
                w52d = (w52h - price) / w52h if w52h > 0 else 0
                eps = info.get('trailingEps', 0); per = info.get('trailingPE', 0)
                fper = info.get('forwardPE', 0); roe = info.get('returnOnEquity', 0)
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
                dte = 999; es_str = "-"
                try:
                    cal = stock.calendar
                    if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
                        ed = cal['Earnings Date'][0].date() if hasattr(cal['Earnings Date'][0], 'date') else pd.to_datetime(cal['Earnings Date'][0]).date()
                        dte = (ed - datetime.date.today()).days
                        if dte >= 0: es_str = ed.strftime('%Y/%m/%d')
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
                vds = 0
                if len(hist) >= 50 and av50 > 0:
                    r5 = hist['Volume'].iloc[-6:-1]
                    if len(r5) == 5 and r5.mean() < av50 * 0.5 and vol >= av50 * 1.5: vds = 1
                bbs = 0
                if len(hist) >= 120:
                    bw = (hist['Close'].rolling(20).std() * 2) / hist['Close'].rolling(20).mean()
                    bw = bw.dropna()
                    if len(bw) >= 120 and bw.iloc[-1] <= bw.tail(120).quantile(0.20): bbs = 1
                rdiv = 0
                if len(hist) >= 40:
                    rseries = 100 - (100 / (1 + ((delta.where(delta > 0, 0)).rolling(14).mean() / (-delta.where(delta < 0, 0)).rolling(14).mean())))
                    rseries = rseries.dropna()
                    c40 = hist['Close'].tail(40); r40 = rseries.tail(40)
                    if len(c40) >= 40 and len(r40) >= 40:
                        i1 = c40.iloc[:20].idxmin(); i2 = c40.iloc[20:].idxmin()
                        if i1 in r40.index and i2 in r40.index:
                            if c40.iloc[20:].min() < c40.iloc[:20].min() and r40.loc[i2] > r40.loc[i1]: rdiv = 1
                updated.append({
                    '記号': ticker, '銘柄': info.get('shortName', ticker), '株価': price,
                    'PER': per or 0, '予想PER': fper or 0, 'EPS': eps or 0,
                    'ROE': roe or 0, '利益率': margin or 0, '配当利回り': div or 0,
                    'PBR': pbr or 0, 'ROA': roa or 0, 'RSI': rsi, 'MA50': ma50,
                    'FCFマージン': fm, '粗利率': gm, 'アクルーアル': ac,
                    'MACD_GC': mgc, 'MACD_DC': mdc,
                    '次回決算日': es_str, '決算猶予日数': dte, '出来高': vol,
                    '平均出来高50日': av50, '200日MA': ma200, '20日高値': h20,
                    '配当日': dds, '52週高値': w52h, '52週下落率': w52d,
                    '静寂後急増': vds, 'BBスクイーズ': bbs, 'RSIダイバージェンス': rdiv
                })
        except: pass
        if i % 5 == 0 or i == total - 1:
            progress_bar.progress((i + 1) / total)
            status_text.text(f"{i+1}/{total}")
    if updated:
        pd.DataFrame(updated).fillna(0).to_csv(fp, index=False)
        status_text.text("完了!")
        time.sleep(1)
        st.rerun()


# =============================================================================
# DETAIL VIEW
# =============================================================================
if st.session_state.selected_stock is not None:
    sel = st.session_state.selected_stock
    if st.button("一覧に戻る", use_container_width=True):
        st.session_state.selected_stock = None
        st.rerun()

    rr = df[df['記号'] == sel]
    if not rr.empty:
        row = rr.iloc[0]
        ct, cf2 = st.columns([3, 1])
        with ct: st.markdown(f"## {sel} ({row['銘柄']})")
        with cf2:
            if sel in st.session_state.fav_list:
                if st.button("★ お気に入り解除", use_container_width=True):
                    st.session_state.fav_list.remove(sel)
                    save_favs(st.session_state.fav_list)
                    st.rerun()
            else:
                if st.button("⭐ お気に入り追加", use_container_width=True):
                    st.session_state.fav_list.append(sel)
                    save_favs(st.session_state.fav_list)
                    st.rerun()

        # === 購入価格の管理 ===
        st.markdown("---")
        st.markdown("##### 💰 購入管理")
        current_purchase = st.session_state.purchases.get(sel, {})
        buy_price = current_purchase.get('price', 0)

        if buy_price > 0:
            pl_pct = (row['株価'] - buy_price) / buy_price * 100
            pl_dollar = row['株価'] - buy_price
            if pl_pct >= 0:
                st.success(f"購入価格: ${buy_price:.2f} → 現在${row['株価']:.2f}  **含み益 +{pl_pct:.1f}% (+${pl_dollar:.2f})**")
            else:
                st.error(f"購入価格: ${buy_price:.2f} → 現在${row['株価']:.2f}  **含み損 {pl_pct:.1f}% (${pl_dollar:.2f})**")
            if pl_pct <= -8:
                st.warning("⚠️ 損切りライン(-8%)に到達しています！")
            elif pl_pct >= 20:
                st.info("💡 +20%到達。利確を検討してもよいタイミングです")

        col_buy1, col_buy2 = st.columns([2, 1])
        with col_buy1:
            new_price = st.number_input("購入価格を入力 ($)", min_value=0.0, value=float(buy_price), step=0.01, key="bp")
        with col_buy2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("登録", key="bp_save", use_container_width=True):
                if new_price > 0:
                    st.session_state.purchases[sel] = {"price": new_price, "date": datetime.date.today().strftime('%Y/%m/%d')}
                else:
                    st.session_state.purchases.pop(sel, None)
                save_purchases(st.session_state.purchases)
                st.rerun()
            if buy_price > 0:
                if st.button("削除", key="bp_del", use_container_width=True):
                    st.session_state.purchases.pop(sel, None)
                    save_purchases(st.session_state.purchases)
                    st.rerun()

        # === スコアとアクション判定 ===
        st.markdown("---")
        detail_func = get_detail_func()
        items = detail_func(row)
        total_score = calc_total(items)
        ml = "⚡短期" if is_short else "👑中長期"
        act = action_label(total_score)
        st.markdown(f"### {ml} 総合スコア: **{total_score}/100点** → **{act}**")

        # 押し目判定
        m50 = row['MA50']
        gap_pct = ((row['株価'] - m50) / m50 * 100) if m50 > 0 else 0
        if -8 <= gap_pct <= -3:
            st.info(f"🎯 押し目 (MA50から{gap_pct:+.1f}%) — 上昇トレンド中の一時的な調整位置です")

        # === スコア内訳（用語説明付き）===
        score_data = []
        for name, s, m in items:
            help_text = TERM_HELP.get(name, "")
            score_data.append({"項目": name, "得点": f"{s}/{m}", "意味": help_text})
        score_df = pd.DataFrame(score_data)
        st.dataframe(score_df.set_index("項目"), use_container_width=True)

        # === 基礎データ ===
        st.markdown("---")
        st.markdown("##### 📋 基礎データ")
        drop = row['52週下落率']; w52h = row['52週高値']
        vr = row['出来高'] / row['平均出来高50日'] if row['平均出来高50日'] > 0 else 0
        data_df = pd.DataFrame({
            "項目": ["株価", "52週高値", "52週下落率", "MA50乖離", "PER", "PBR", "ROE", "利益率",
                     "FCFマージン", "粗利率", "配当利回り", "RSI", "出来高(対平均)",
                     "次回決算日", "配当日"],
            "値": [
                f"${row['株価']:.2f}",
                f"${w52h:.2f}" if w52h > 0 else "-",
                f"-{drop*100:.1f}%" if drop > 0 else "高値圏",
                f"{gap_pct:+.1f}%",
                f"{row['PER']:.1f}倍" if row['PER'] > 0 else "-",
                f"{row['PBR']:.2f}倍" if row['PBR'] > 0 else "-",
                f"{row['ROE']*100:.1f}%",
                f"{row['利益率']*100:.1f}%",
                f"{row['FCFマージン']*100:.1f}%" if row['FCFマージン'] != 0 else "-",
                f"{row['粗利率']*100:.1f}%" if row['粗利率'] != 0 else "-",
                f"{row['配当利回り']*100:.2f}%" if row['配当利回り'] > 0 else "-",
                f"{row['RSI']:.1f}",
                f"{vr:.1f}倍",
                row['次回決算日'], row.get('配当日', '-')
            ]
        })
        st.table(data_df.set_index("項目"))

        # === チャート ===
        st.markdown("---")
        st.markdown("##### 📈 チャート")
        c1, c2 = st.columns(2)
        with c1: pc = st.radio("期間", ["3ヶ月", "6ヶ月", "1年", "5年"], horizontal=True, key="pc")
        with c2: ic = st.radio("足", ["日足", "週足", "月足"], horizontal=True, key="ic")
        im = {"日足": "1d", "週足": "1wk", "月足": "1mo"}
        with st.spinner("..."):
            try:
                hf = yf.Ticker(sel).history(period="10y", interval=im[ic])
                if not hf.empty:
                    hf['MA5'] = hf['Close'].rolling(5).mean()
                    hf['MA25'] = hf['Close'].rolling(25).mean()
                    hf['MA75'] = hf['Close'].rolling(75).mean()
                    nm = {"日足": {"3ヶ月": 63, "6ヶ月": 126, "1年": 252, "5年": 1260},
                          "週足": {"3ヶ月": 13, "6ヶ月": 26, "1年": 52, "5年": 260},
                          "月足": {"3ヶ月": 3, "6ヶ月": 6, "1年": 12, "5年": 60}}
                    h = hf.tail(nm[ic][pc])
                    st.markdown(f"最新: **${h['Close'].iloc[-1]:.2f}**")
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


# =============================================================================
# LIST VIEW
# =============================================================================
else:
    ml = "⚡ 短期トレード" if is_short else "👑 中長期投資"
    st.subheader(f"米国株スコアリング ({ml} / 100点満点)")

    fdf = df[df['株価'] <= max_p].copy()
    if sq:
        fdf = fdf[fdf['記号'].str.contains(sq.upper(), na=False)
                  | fdf['銘柄'].str.contains(sq, case=False, na=False)]
    if fav_only:
        fdf = fdf[fdf['記号'].isin(st.session_state.fav_list)] if st.session_state.fav_list else pd.DataFrame(columns=fdf.columns)

    if not fdf.empty:
        detail_func = get_detail_func()

        def calc_row(row):
            items = detail_func(row)
            total = calc_total(items)
            score_strs = {name: f"{s}/{m}" for name, s, m in items}
            act = action_label(total)

            d = row.get('52週下落率', 0)
            drop_str = f"-{d*100:.0f}%" if d >= 0.01 else "高値圏"

            rsi = row.get('RSI', 50)
            rsi_str = "暴落" if rsi < 30 else ("安値" if rsi < 40 else ("平常" if rsi < 70 else "過熱"))

            dte = row.get('決算猶予日数', 999)
            if dte == 999: er = "-"
            elif 0 <= dte <= 3: er = "!!直前"
            elif 4 <= dte <= 7: er = "!危険"
            elif 8 <= dte <= 14: er = "警戒"
            elif 15 <= dte <= 30: er = "注意"
            elif 31 <= dte <= 45: er = "微注意"
            elif 46 <= dte <= 60: er = "安全"
            else: er = "好機"

            p = row.get('株価', 0); m50 = row.get('MA50', 0)
            gap_pct = ((p - m50) / m50 * 100) if m50 > 0 else 0
            oshime = "◎押し目" if -8 <= gap_pct <= -3 else "-"

            # 含み損益
            t = row.get('記号', '')
            pl_str = "-"
            if t in st.session_state.purchases:
                bp = st.session_state.purchases[t].get('price', 0)
                if bp > 0:
                    pl_pct = (p - bp) / bp * 100
                    pl_str = f"{pl_pct:+.1f}%"

            item_names = [name for name, _, _ in items]
            vals = [total, act, drop_str, oshime, rsi_str, er, pl_str] + [score_strs.get(n, "") for n in item_names]
            return pd.Series(vals)

        items_template = detail_func(fdf.iloc[0])
        item_names = [name for name, _, _ in items_template]
        item_headers = [f"{name} /{m}" for name, _, m in items_template]

        col_names = ['スコア', '判定', '52w位置', '押し目', '過熱感', '決算', '損益'] + item_headers
        fdf[col_names] = fdf.apply(calc_row, axis=1)
        fdf = fdf.sort_values('スコア', ascending=False)
        fdf['順位'] = range(1, len(fdf) + 1)
        fdf['スコア'] = fdf['スコア'].apply(lambda x: f"{x:.0f}/100")
        fdf['株価'] = fdf['株価'].apply(lambda x: f"${x:.2f}")

        display_cols = (['順位', '記号', '銘柄', 'スコア', '判定', '52w位置', '押し目',
                         '過熱感', '決算', '損益', '次回決算日', '配当日']
                        + item_headers
                        + ['株価'])

        display_df = fdf[display_cols]

        st.markdown("行タップで詳細（全項目の得点内訳+用語説明+購入管理）")
        event = st.dataframe(display_df.set_index('順位'), use_container_width=True,
                             on_select="rerun", selection_mode="single-row")
        if len(event.selection.rows) > 0:
            st.session_state.selected_stock = display_df.iloc[event.selection.rows[0]]['記号']
            st.rerun()
