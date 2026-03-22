import pandas as pd
import requests
import os
import json
import datetime

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

favorites = []
if os.path.exists('favorites.json'):
    try:
        with open('favorites.json', 'r') as f:
            favorites = json.load(f)
    except: pass

# 購入価格データ読み込み
purchases = {}
if os.path.exists('purchases.json'):
    try:
        with open('purchases.json', 'r') as f:
            purchases = json.load(f)
    except: pass

CSV_PATH = 'raw_stock_data.csv'
if not os.path.exists(CSV_PATH):
    print("raw_stock_data.csv not found")
    exit(1)

df = pd.read_csv(CSV_PATH)
df.fillna(0, inplace=True)
print(f"データ読み込み: {len(df)}銘柄")

for col in ['FCFマージン', '粗利率', 'アクルーアル', 'MACD_GC', 'MACD_DC',
            '決算猶予日数', '次回決算日', '出来高', '平均出来高50日', '200日MA',
            '20日高値', '配当日', '52週高値', '52週下落率',
            '静寂後急増', 'BBスクイーズ', 'RSIダイバージェンス']:
    if col not in df.columns:
        df[col] = 0 if col not in ['次回決算日', '配当日'] else "-"

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

# アクション判定
def action_label(score):
    if score >= 80: return "買い検討◎"
    elif score >= 60: return "監視"
    elif score >= 40: return "様子見"
    else: return "見送り"

# === 短期スコア ===
def score_short(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    vol = row.get('出来高', 0); avg_vol = row.get('平均出来高50日', 0)
    vr = vol / avg_vol if avg_vol > 0 else 0
    p = row.get('株価', 0); m50 = row.get('MA50', 0); m200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)
    pc = int(row.get('静寂後急増', 0)) + int(row.get('BBスクイーズ', 0)) + int(row.get('RSIダイバージェンス', 0))
    s = linear(rsi, 60, 30, 12)
    s += 12 if row.get('MACD_GC', 0) == 1 else 0
    s += linear(drop, 0.05, 0.30, 10)
    s += ma50_gap_score(p, m50, 10)
    s += linear(vr, 1.0, 2.0, 8)
    s += dryup_score(vr, 8)
    s += linear(pc, 0, 3, 8)
    s += 8 if p > m50 > m200 and m50 > 0 else 0
    s += earn_score(d, 8)
    s += 5 if row.get('EPS', 0) > 0 else 0
    s += linear(row.get('ROE', 0), 0.05, 0.15, 5)
    s += linear(row.get('利益率', 0), 0.05, 0.15, 6)
    return round(s, 1)

# === 中長期スコア ===
def score_long(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    p = row.get('株価', 0); m50 = row.get('MA50', 0); m200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)
    per = row.get('PER', 0)
    vol = row.get('出来高', 0); avg_vol = row.get('平均出来高50日', 0)
    vr = vol / avg_vol if avg_vol > 0 else 0
    s = linear(row.get('ROE', 0), 0.05, 0.20, 10)
    s += linear(per, 25, 10, 10) if per > 0 else 0
    s += linear(row.get('利益率', 0), 0.05, 0.20, 8)
    s += linear(row.get('FCFマージン', 0), 0, 0.15, 8)
    s += linear(drop, 0.05, 0.35, 8)
    s += ma50_gap_score(p, m50, 8)
    s += linear(row.get('粗利率', 0), 0.20, 0.50, 7)
    s += linear(rsi, 60, 30, 7)
    s += 7 if row.get('MACD_GC', 0) == 1 else 0
    s += dryup_score(vr, 6)
    s += earn_score(d, 6)
    s += 5 if row.get('EPS', 0) > 0 else 0
    s += 5 if row.get('アクルーアル', 0) < 0 else 0
    s += 5 if p > m50 > m200 and m50 > 0 else 0
    return round(s, 1)

df['短期'] = df.apply(score_short, axis=1)
df['中長期'] = df.apply(score_long, axis=1)

today = datetime.date.today()
today_str = today.strftime('%m/%d')

# === 短期 買い候補 ===
buy_short = []
for _, row in df.sort_values('短期', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; ss = row['短期']
    d = row.get('決算猶予日数', 999); eps = row.get('EPS', 0)
    if eps <= 0 or (0 <= d <= 14) or p > 200: continue
    if ss >= 55:
        rsi = row.get('RSI', 50); drop = row.get('52週下落率', 0)
        m50 = row.get('MA50', 0)
        gap = ((p - m50) / m50 * 100) if m50 > 0 else 0
        oshime = " [押し目]" if -8 <= gap <= -3 else ""
        act = action_label(ss)
        buy_short.append(f"  {t} ${p:.0f} {ss:.0f}/100 [{act}]{oshime} RSI:{rsi:.0f} 52w:-{drop*100:.0f}%")
    if len(buy_short) >= 5: break

# === 中長期 買い候補 ===
buy_long = []
for _, row in df.sort_values('中長期', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; ls = row['中長期']
    d = row.get('決算猶予日数', 999); eps = row.get('EPS', 0)
    fcf = row.get('FCFマージン', 0)
    if eps <= 0 or (0 <= d <= 14) or p > 200 or fcf < 0: continue
    if ls >= 55:
        roe_pct = row.get('ROE', 0) * 100; drop = row.get('52週下落率', 0)
        m50 = row.get('MA50', 0)
        gap = ((p - m50) / m50 * 100) if m50 > 0 else 0
        oshime = " [押し目]" if -8 <= gap <= -3 else ""
        act = action_label(ls)
        buy_long.append(f"  {t} ${p:.0f} {ls:.0f}/100 [{act}]{oshime} ROE:{roe_pct:.0f}% 52w:-{drop*100:.0f}%")
    if len(buy_long) >= 5: break

# === 大変動予兆 ===
alert_precursor = []
for _, row in df.sort_values('短期', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; eps = row.get('EPS', 0)
    if eps <= 0 or p > 200: continue
    sigs = []
    if row.get('静寂後急増', 0) == 1: sigs.append("出来高:静寂後急増")
    if row.get('BBスクイーズ', 0) == 1: sigs.append("BB:煮詰まり")
    if row.get('RSIダイバージェンス', 0) == 1: sigs.append("RSI:反転兆候")
    if sigs:
        ss = row['短期']
        alert_precursor.append(f"  {t} ${p:.0f} ({ss:.0f}/100) {' / '.join(sigs)}")
    if len(alert_precursor) >= 5: break

# === お気に入り診断 ===
fav_hold = []; fav_take_profit = []; fav_warning = []; fav_dividend = []
fav_stoploss = []  # 損切りアラート

for _, row in df[df['記号'].isin(favorites)].iterrows():
    t = row['記号']; p = row['株価']
    ss = row['短期']; ls = row['中長期']
    rsi = row.get('RSI', 50); d = row.get('決算猶予日数', 999)
    eps = row.get('EPS', 0); ma50 = row.get('MA50', 0)
    drop = row.get('52週下落率', 0)

    # 含み損益計算
    pl_str = ""
    if t in purchases:
        buy_price = purchases[t].get('price', 0)
        if buy_price > 0:
            pl_pct = (p - buy_price) / buy_price * 100
            pl_dollar = p - buy_price
            if pl_pct >= 0:
                pl_str = f" [含み益+{pl_pct:.1f}% (+${pl_dollar:.1f})]"
            else:
                pl_str = f" [含み損{pl_pct:.1f}% (${pl_dollar:.1f})]"
            # 損切りアラート（-8%以下）
            if pl_pct <= -8:
                fav_stoploss.append(f"  {t} 購入${buy_price:.0f} -> 現在${p:.0f} ({pl_pct:.1f}%) 損切りライン!")
            # 利確検討（+20%以上）
            elif pl_pct >= 20:
                fav_take_profit.append(f"  {t} ${p:.0f} 購入${buy_price:.0f} (+{pl_pct:.1f}%) -> 利確検討")

    warnings = []
    if 0 <= d <= 3: warnings.append(f"決算{d}日後!!")
    elif 4 <= d <= 7: warnings.append(f"決算{d}日後!")
    elif 8 <= d <= 14: warnings.append(f"決算{d}日後 注意")
    if rsi >= 75: warnings.append(f"RSI{rsi:.0f} 過熱")
    if row.get('MACD_DC', 0) == 1: warnings.append("MACDデッドクロス")
    if ma50 > 0 and p < ma50 * 0.95: warnings.append("50MA割れ")
    if eps <= 0: warnings.append("赤字")

    fsigs = []
    if row.get('静寂後急増', 0) == 1: fsigs.append("Vol")
    if row.get('BBスクイーズ', 0) == 1: fsigs.append("BB")
    if row.get('RSIダイバージェンス', 0) == 1: fsigs.append("Div")
    sig_note = f" [{'/'.join(fsigs)}]" if fsigs else ""

    div_str = row.get('配当日', '-')
    if isinstance(div_str, str) and div_str not in ['-', '0', '0.0']:
        try:
            dd = datetime.datetime.strptime(div_str, '%Y/%m/%d').date()
            dtd = (dd - today).days
            if 0 <= dtd <= 7:
                fav_dividend.append(f"  {t} 配当日{div_str}({dtd}日後) -> 売却すると配当を逃します")
            elif 8 <= dtd <= 30:
                fav_dividend.append(f"  {t} 配当日{div_str}({dtd}日後)")
        except: pass

    pos = f"(-{drop*100:.0f}%)" if drop >= 0.05 else ""
    gap_pct = ((p - ma50) / ma50 * 100) if ma50 > 0 else 0
    oshime = " [押し目]" if -8 <= gap_pct <= -3 else ""
    score_str = f"短期{ss:.0f} 中長期{ls:.0f}/100"

    if warnings:
        fav_warning.append(f"  {t} ${p:.0f}{pos} {score_str}{pl_str} -> {' / '.join(warnings)}{sig_note}")
    elif rsi >= 70 or (0 <= d <= 14):
        if not any(t in m for m in fav_take_profit):  # 利確検討で既に追加済みなら重複回避
            fav_take_profit.append(f"  {t} ${p:.0f}{pos} {score_str}{pl_str} -> 利確検討{sig_note}")
    else:
        act_s = action_label(ss); act_l = action_label(ls)
        fav_hold.append(f"  {t} ${p:.0f}{pos} {score_str}{pl_str}{oshime}{sig_note}")

# === 配当狙い ===
div_opportunity = []
for _, row in df.iterrows():
    if row['記号'] in favorites: continue
    div_str = row.get('配当日', '-')
    if isinstance(div_str, str) and div_str not in ['-', '0', '0.0']:
        try:
            dd = datetime.datetime.strptime(div_str, '%Y/%m/%d').date()
            dtd = (dd - today).days
            dy = row.get('配当利回り', 0)
            if 0 <= dtd <= 7 and 0.03 <= dy <= 0.10:
                div_opportunity.append(f"  {row['記号']} ${row['株価']:.0f} 利回り{dy*100:.1f}% 配当日{div_str}")
        except: pass

# === メッセージ組み立て（全日本語）===
msg = f"📊 {today_str} スクリーニング結果 (100点満点)"

# 損切りアラート（最優先）
if fav_stoploss:
    msg += "\n\n🚨【損切りライン到達】"
    for m in fav_stoploss: msg += f"\n{m}"

if fav_warning:
    msg += "\n\n🔴【要注意】保有株に危険シグナル"
    for m in fav_warning: msg += f"\n{m}"
if fav_dividend:
    msg += "\n\n📅【配当日接近】"
    for m in fav_dividend: msg += f"\n{m}"
if fav_take_profit:
    msg += "\n\n🟡【利確検討】"
    for m in fav_take_profit: msg += f"\n{m}"
if fav_hold:
    msg += "\n\n✅【保有継続】"
    for m in fav_hold: msg += f"\n{m}"
if favorites and not fav_warning and not fav_take_profit and not fav_hold and not fav_dividend and not fav_stoploss:
    msg += "\n\n📋 お気に入り: データなし"

if buy_long:
    msg += "\n\n👑【中長期 買い候補】"
    for m in buy_long: msg += f"\n{m}"
if buy_short:
    msg += "\n\n⚡【短期 買い候補】"
    for m in buy_short: msg += f"\n{m}"
if alert_precursor:
    msg += "\n\n🔮【大変動予兆】上下どちらかは不明・監視用"
    for m in alert_precursor: msg += f"\n{m}"
if div_opportunity:
    msg += "\n\n💰【配当狙い】権利落ち日7日以内"
    for m in div_opportunity[:3]: msg += f"\n{m}"
if (not buy_long and not buy_short and not alert_precursor
        and not fav_warning and not fav_take_profit and not fav_stoploss
        and not fav_dividend and not div_opportunity):
    msg += "\n\n特筆すべきシグナルなし。資金温存。"

# 判定基準の凡例（毎回末尾に）
msg += "\n\n---\n80点以上=買い検討 60-79=監視 40-59=様子見 40未満=見送り"

print(msg)
if LINE_ACCESS_TOKEN and LINE_USER_ID:
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    data = {"to": LINE_USER_ID,
            "messages": [{"type": "text", "text": msg[:4900]}]}
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    print("LINE送信OK" if res.status_code == 200 else f"LINE送信失敗: {res.status_code}")
else:
    print("LINE認証情報が未設定です")
