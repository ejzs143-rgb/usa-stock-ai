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
    except:
        pass

CSV_PATH = 'raw_stock_data.csv'
if not os.path.exists(CSV_PATH):
    print("raw_stock_data.csv not found")
    exit(1)

df = pd.read_csv(CSV_PATH)
df.fillna(0, inplace=True)
print(f"data: {len(df)}")

for col in ['FCFマージン', '粗利率', 'アクルーアル', 'MACD_GC', 'MACD_DC',
            '決算猶予日数', '次回決算日', '出来高', '平均出来高50日', '200日MA',
            '20日高値', '配当日', '52週高値', '52週下落率',
            '静寂後急増', 'BBスクイーズ', 'RSIダイバージェンス']:
    if col not in df.columns:
        df[col] = 0 if col not in ['次回決算日', '配当日'] else "-"

# =============================================================================
# 線形補間スコアリング関数
# value が floor_val のとき 0点、ceil_val のとき max_pts 点。その間は直線。
# PER のように「低い方が良い」場合は floor_val > ceil_val で呼ぶ。
# =============================================================================
def linear(value, floor_val, ceil_val, max_pts):
    if ceil_val == floor_val:
        return max_pts if value == ceil_val else 0
    ratio = (value - floor_val) / (ceil_val - floor_val)
    return round(max(0, min(max_pts, ratio * max_pts)), 1)

# =============================================================================
# 短期トレードモード（100点満点）
# =============================================================================
def score_short(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    vol = row.get('出来高', 0)
    avg_vol = row.get('平均出来高50日', 0)
    vol_ratio = vol / avg_vol if avg_vol > 0 else 0
    price = row.get('株価', 0)
    ma50 = row.get('MA50', 0)
    ma200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)

    # RSI: 30以下=15点, 60以上=0点（低いほど良い）
    s_rsi = linear(rsi, 60, 30, 15)

    # MACD: GC点灯=15点, なし=0点
    s_macd = 15 if row.get('MACD_GC', 0) == 1 else 0

    # 52週下落率: -30%以上=15点, -5%未満=0点
    s_drop = linear(drop, 0.05, 0.30, 15)

    # 出来高変化: 2倍以上=10点, 1倍以下=0点
    s_vol = linear(vol_ratio, 1.0, 2.0, 10)

    # 先行指標: 3つ全点灯=10点
    precursor_count = (int(row.get('静寂後急増', 0))
                       + int(row.get('BBスクイーズ', 0))
                       + int(row.get('RSIダイバージェンス', 0)))
    s_precursor = linear(precursor_count, 0, 3, 10)

    # トレンド: 完全順配列=10点
    s_trend = 10 if price > ma50 > ma200 and ma50 > 0 and ma200 > 0 else 0

    # 決算距離: 60日以上=10点, 45日=7.5点, 14日=0点, 7日以内=-10点
    if d == 999:
        s_earn = 5  # データなしは中立
    elif d > 60:
        s_earn = 10
    elif d >= 14:
        s_earn = linear(d, 14, 60, 10)
    elif d >= 7:
        s_earn = linear(d, 14, 7, -5)  # 7日で-5点
    else:
        s_earn = -10

    # EPS: 黒字=5点, 赤字=0点
    s_eps = 5 if row.get('EPS', 0) > 0 else 0

    # ROE: 15%以上=5点, 5%以下=0点
    s_roe = linear(row.get('ROE', 0), 0.05, 0.15, 5)

    # 利益率: 15%以上=5点, 5%以下=0点
    s_margin = linear(row.get('利益率', 0), 0.05, 0.15, 5)

    total = s_rsi + s_macd + s_drop + s_vol + s_precursor + s_trend + s_earn + s_eps + s_roe + s_margin
    return round(total, 1)

# =============================================================================
# 中長期投資モード（100点満点）
# =============================================================================
def score_long(row):
    rsi = row.get('RSI', 50)
    drop = row.get('52週下落率', 0)
    price = row.get('株価', 0)
    ma50 = row.get('MA50', 0)
    ma200 = row.get('200日MA', 0)
    d = row.get('決算猶予日数', 999)

    # ROE: 20%以上=12点, 5%以下=0点
    s_roe = linear(row.get('ROE', 0), 0.05, 0.20, 12)

    # PER: 10倍以下=12点, 25倍以上=0点（低いほど良い）
    per = row.get('PER', 0)
    s_per = linear(per, 25, 10, 12) if per > 0 else 0

    # 利益率: 20%以上=10点, 5%以下=0点
    s_margin = linear(row.get('利益率', 0), 0.05, 0.20, 10)

    # FCFマージン: 15%以上=10点, 0%以下=0点
    s_fcf = linear(row.get('FCFマージン', 0), 0, 0.15, 10)

    # 52週下落率: -35%以上=10点, -5%未満=0点
    s_drop = linear(drop, 0.05, 0.35, 10)

    # 粗利率: 50%以上=8点, 20%以下=0点
    s_gross = linear(row.get('粗利率', 0), 0.20, 0.50, 8)

    # RSI: 30以下=8点, 60以上=0点
    s_rsi = linear(rsi, 60, 30, 8)

    # MACD: GC点灯=8点
    s_macd = 8 if row.get('MACD_GC', 0) == 1 else 0

    # 決算距離: 60日以上=7点, 14日=0点, 7日以内=-7点
    if d == 999:
        s_earn = 3.5
    elif d > 60:
        s_earn = 7
    elif d >= 14:
        s_earn = linear(d, 14, 60, 7)
    elif d >= 7:
        s_earn = linear(d, 14, 7, -3.5)
    else:
        s_earn = -7

    # EPS: 黒字=5点
    s_eps = 5 if row.get('EPS', 0) > 0 else 0

    # アクルーアル: マイナス=5点, プラス=0点
    s_accrual = 5 if row.get('アクルーアル', 0) < 0 else 0

    # トレンド: 完全順配列=5点
    s_trend = 5 if price > ma50 > ma200 and ma50 > 0 and ma200 > 0 else 0

    total = (s_roe + s_per + s_margin + s_fcf + s_drop + s_gross
             + s_rsi + s_macd + s_earn + s_eps + s_accrual + s_trend)
    return round(total, 1)

# =============================================================================
# 全銘柄スコア計算
# =============================================================================
df['短期スコア'] = df.apply(score_short, axis=1)
df['中長期スコア'] = df.apply(score_long, axis=1)

today = datetime.date.today()
today_str = today.strftime('%m/%d')

# =============================================================================
# 短期 買い候補（短期スコア60以上 + EPS黒字 + 決算安全）
# =============================================================================
buy_short = []
for _, row in df.sort_values('短期スコア', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; ss = row['短期スコア']
    d = row.get('決算猶予日数', 999); eps = row.get('EPS', 0)
    if eps <= 0 or (0 <= d <= 14) or p > 200:
        continue
    if ss >= 60:
        rsi = row.get('RSI', 50)
        drop = row.get('52週下落率', 0)
        buy_short.append(f"  {t} ${p:.0f} {ss:.0f}/100 RSI:{rsi:.0f} 52w:-{drop*100:.0f}%")
    if len(buy_short) >= 5:
        break

# =============================================================================
# 中長期 買い候補（中長期スコア60以上 + EPS黒字 + FCF>=0）
# =============================================================================
buy_long = []
for _, row in df.sort_values('中長期スコア', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; ls = row['中長期スコア']
    d = row.get('決算猶予日数', 999); eps = row.get('EPS', 0)
    fcf = row.get('FCFマージン', 0)
    if eps <= 0 or (0 <= d <= 14) or p > 200 or fcf < 0:
        continue
    if ls >= 60:
        roe_pct = row.get('ROE', 0) * 100
        drop = row.get('52週下落率', 0)
        buy_long.append(f"  {t} ${p:.0f} {ls:.0f}/100 ROE:{roe_pct:.0f}% 52w:-{drop*100:.0f}%")
    if len(buy_long) >= 5:
        break

# =============================================================================
# 大変動予兆
# =============================================================================
alert_precursor = []
for _, row in df.sort_values('短期スコア', ascending=False).iterrows():
    t = row['記号']; p = row['株価']; eps = row.get('EPS', 0)
    if eps <= 0 or p > 200:
        continue
    sigs = []
    if row.get('静寂後急増', 0) == 1: sigs.append("Vol静寂→急増")
    if row.get('BBスクイーズ', 0) == 1: sigs.append("BB煮詰まり")
    if row.get('RSIダイバージェンス', 0) == 1: sigs.append("RSI反転兆候")
    if sigs:
        ss = row['短期スコア']
        alert_precursor.append(f"  {t} ${p:.0f} ({ss:.0f}/100) {' / '.join(sigs)}")
    if len(alert_precursor) >= 5:
        break

# =============================================================================
# お気に入り銘柄診断
# =============================================================================
fav_hold = []; fav_take_profit = []; fav_warning = []; fav_dividend = []

for _, row in df[df['記号'].isin(favorites)].iterrows():
    t = row['記号']; p = row['株価']
    ss = row['短期スコア']; ls = row['中長期スコア']
    rsi = row.get('RSI', 50); d = row.get('決算猶予日数', 999)
    eps = row.get('EPS', 0); ma50 = row.get('MA50', 0)
    drop = row.get('52週下落率', 0)

    warnings = []
    if 0 <= d <= 3: warnings.append(f"💀決算{d}日後！")
    elif 4 <= d <= 7: warnings.append(f"⚠️決算{d}日後")
    elif 8 <= d <= 14: warnings.append(f"⚡決算{d}日後")
    if rsi >= 75: warnings.append(f"🔥RSI{rsi:.0f}")
    if row.get('MACD_DC', 0) == 1: warnings.append("📉MACD DC")
    if ma50 > 0 and p < ma50 * 0.95: warnings.append("📉50MA割れ")
    if eps <= 0: warnings.append("☠️赤字")

    # 先行指標
    fsigs = []
    if row.get('静寂後急増', 0) == 1: fsigs.append("Vol")
    if row.get('BBスクイーズ', 0) == 1: fsigs.append("BB")
    if row.get('RSIダイバージェンス', 0) == 1: fsigs.append("Div")
    sig_note = f" [{'/'.join(fsigs)}]" if fsigs else ""

    # 配当日
    div_str = row.get('配当日', '-')
    if isinstance(div_str, str) and div_str not in ['-', '0', '0.0']:
        try:
            dd = datetime.datetime.strptime(div_str, '%Y/%m/%d').date()
            dtd = (dd - today).days
            if 0 <= dtd <= 7:
                fav_dividend.append(f"  {t} 配当日{div_str}({dtd}日後) → 売却注意！")
            elif 8 <= dtd <= 30:
                fav_dividend.append(f"  {t} 配当日{div_str}({dtd}日後)")
        except: pass

    pos = f"(-{drop*100:.0f}%)" if drop >= 0.05 else ""
    score_str = f"短期{ss:.0f} 中長期{ls:.0f}/100"

    if warnings:
        fav_warning.append(f"  {t} ${p:.0f}{pos} {score_str} → {' / '.join(warnings)}{sig_note}")
    elif rsi >= 70 or (0 <= d <= 14):
        fav_take_profit.append(f"  {t} ${p:.0f}{pos} {score_str} → 利確検討{sig_note}")
    else:
        st = "✅" if ls >= 50 else "⚪️"
        fav_hold.append(f"  {st} {t} ${p:.0f}{pos} {score_str}{sig_note}")

# =============================================================================
# 配当狙い
# =============================================================================
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
                div_opportunity.append(
                    f"  {row['記号']} ${row['株価']:.0f} 利回り{dy*100:.1f}% 配当日{div_str}")
        except: pass

# =============================================================================
# メッセージ
# =============================================================================
msg = f"📊 {today_str} スクリーニング (100点満点)"

if fav_warning:
    msg += "\n\n🔴【要注意】"
    for m in fav_warning: msg += f"\n{m}"
if fav_dividend:
    msg += "\n\n📅【配当日接近】"
    for m in fav_dividend: msg += f"\n{m}"
if fav_take_profit:
    msg += "\n\n🟡【利確検討】"
    for m in fav_take_profit: msg += f"\n{m}"
if fav_hold:
    msg += "\n\n✅【保有OK】"
    for m in fav_hold: msg += f"\n{m}"
if favorites and not fav_warning and not fav_take_profit and not fav_hold and not fav_dividend:
    msg += "\n\n📋 お気に入り: データなし"

if buy_long:
    msg += "\n\n👑【中長期 買い候補】"
    for m in buy_long: msg += f"\n{m}"
if buy_short:
    msg += "\n\n⚡【短期 買い候補】"
    for m in buy_short: msg += f"\n{m}"
if alert_precursor:
    msg += "\n\n🔮【大変動予兆】上下不明・監視用"
    for m in alert_precursor: msg += f"\n{m}"
if div_opportunity:
    msg += "\n\n💰【配当狙い】7日以内"
    for m in div_opportunity[:3]: msg += f"\n{m}"
if (not buy_long and not buy_short and not alert_precursor
        and not fav_warning and not fav_take_profit
        and not fav_dividend and not div_opportunity):
    msg += "\n\nシグナルなし。資金温存。"

print(msg)
if LINE_ACCESS_TOKEN and LINE_USER_ID:
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    data = {"to": LINE_USER_ID,
            "messages": [{"type": "text", "text": msg[:4900]}]}
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    print("LINE OK" if res.status_code == 200 else f"LINE NG: {res.status_code}")
else:
    print("LINE credentials not set")
