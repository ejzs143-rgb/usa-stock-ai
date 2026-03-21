"""
auto_screener.py v4
追加:
  - 52週下落率スコア
  - 「大変動予兆」カテゴリ（BBスクイーズ/出来高静寂→急増/RSIダイバージェンス）
"""

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
    print("エラー: raw_stock_data.csv が見つかりません")
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

# ===================================================
# スコアリング
# ===================================================
def calc_score(row):
    s = 10 if row.get('EPS', 0) > 0 else -50
    per = row.get('PER', 0)
    s += max(0, min(15, (25 - per) / 15 * 15)) if per > 0 else 0
    s += max(0, min(15, (row.get('ROE', 0) - 0.05) / 0.15 * 15))
    s += max(0, min(15, (row.get('利益率', 0) - 0.05) / 0.15 * 15))
    s += max(0, min(10, row.get('FCFマージン', 0) / 0.15 * 10))
    if row.get('MACD_GC', 0) == 1: s += 15
    if row.get('RSI', 50) < 50: s += 10
    if row.get('アクルーアル', 0) < 0: s += 5
    # 52週割安ボーナス
    drop = row.get('52週下落率', 0)
    if 0.15 <= drop <= 0.40: s += min(15, (drop - 0.10) / 0.30 * 15)
    elif drop > 0.40: s += 10
    # 決算ペナルティ
    d = row.get('決算猶予日数', 999)
    if d != 999:
        if 0 <= d <= 3: s -= 20
        elif 4 <= d <= 7: s -= 15
        elif 8 <= d <= 14: s -= 10
        elif 15 <= d <= 30: s -= 5
        elif 31 <= d <= 45: s -= 2
        elif d > 60: s += 5
    return s

df['スコア'] = df.apply(calc_score, axis=1)
df = df.sort_values('スコア', ascending=False).reset_index(drop=True)

today = datetime.date.today()
today_str = today.strftime('%m/%d')

# ===================================================
# 買い候補（3種類）
# ===================================================
buy_value = []
buy_fundamental = []
buy_momentum = []

for _, row in df.iterrows():
    ticker = row['記号']
    price = row['株価']
    score = row['スコア']
    rsi = row.get('RSI', 50)
    d = row.get('決算猶予日数', 999)
    eps = row.get('EPS', 0)
    ma50 = row.get('MA50', 0)
    ma200 = row.get('200日MA', 0)
    vol = row.get('出来高', 0)
    avg_vol = row.get('平均出来高50日', 0)
    high20 = row.get('20日高値', 0)
    drop = row.get('52週下落率', 0)
    week52h = row.get('52週高値', 0)

    if eps <= 0 or (0 <= d <= 14) or price > 200:
        continue

    vol_ratio = vol / avg_vol if avg_vol > 0 else 0
    roe_pct = row.get('ROE', 0) * 100

    # 割安好業績
    if drop >= 0.15 and row.get('ROE', 0) >= 0.10 and row.get('利益率', 0) >= 0.05 and score >= 40:
        buy_value.append(
            f"  {ticker} ${price:.0f}"
            f" (高値${week52h:.0f}から-{drop*100:.0f}%)"
            f" {score:.0f}点 ROE:{roe_pct:.0f}%"
        )

    # 中長期（FCFマイナスは除外）
    fcf_val = row.get('FCFマージン', 0)
    if score >= 55 and row.get('MACD_GC', 0) == 1 and rsi < 50 and fcf_val >= 0:
        fcf_pct = fcf_val * 100
        buy_fundamental.append(
            f"  {ticker} ${price:.0f} ({score:.0f}点)"
            f" ROE:{roe_pct:.0f}% FCF:{fcf_pct:.0f}% RSI:{rsi:.0f}"
        )

    # 短期モメンタム
    if (vol_ratio >= 1.5 and price > ma50 > ma200
            and high20 > 0 and price >= high20 * 0.98 and rsi < 85):
        buy_momentum.append(
            f"  {ticker} ${price:.0f} 出来高{vol_ratio:.1f}倍 RSI:{rsi:.0f}"
        )

# ===================================================
# ⚡ 大変動予兆（先行指標）
# ===================================================
alert_precursor = []

for _, row in df.iterrows():
    ticker = row['記号']
    price = row['株価']
    eps = row.get('EPS', 0)
    d = row.get('決算猶予日数', 999)

    if eps <= 0 or price > 200:
        continue

    signals = []
    if row.get('静寂後急増', 0) == 1:
        signals.append("出来高:静寂→急増")
    if row.get('BBスクイーズ', 0) == 1:
        signals.append("BB:スクイーズ")
    if row.get('RSIダイバージェンス', 0) == 1:
        signals.append("RSI:強気乖離")

    if signals:
        sig_str = " / ".join(signals)
        # 決算接近の場合は決算起因の可能性が高いので注記
        earn_note = f" ⚠️決算{d}日後" if 0 <= d <= 14 else ""
        score = row.get('スコア', 0)
        alert_precursor.append(
            f"  {ticker} ${price:.0f} ({score:.0f}点) {sig_str}{earn_note}"
        )

# ===================================================
# お気に入り銘柄の診断
# ===================================================
fav_hold = []
fav_take_profit = []
fav_warning = []
fav_dividend = []

for _, row in df[df['記号'].isin(favorites)].iterrows():
    ticker = row['記号']
    price = row['株価']
    score = row['スコア']
    rsi = row.get('RSI', 50)
    d = row.get('決算猶予日数', 999)
    eps = row.get('EPS', 0)
    ma50 = row.get('MA50', 0)
    drop = row.get('52週下落率', 0)

    warnings = []
    if 0 <= d <= 3: warnings.append(f"💀決算{d}日後！")
    elif 4 <= d <= 7: warnings.append(f"⚠️決算{d}日後")
    elif 8 <= d <= 14: warnings.append(f"⚡決算{d}日後")
    if rsi >= 75: warnings.append(f"🔥RSI{rsi:.0f}(過熱)")
    if row.get('MACD_DC', 0) == 1: warnings.append("📉MACDデッドクロス")
    if ma50 > 0 and price < ma50 * 0.95: warnings.append("📉50MA-5%割れ")
    if eps <= 0: warnings.append("☠️赤字")

    # 先行指標がお気に入りに出ている場合も注記
    fav_signals = []
    if row.get('静寂後急増', 0) == 1: fav_signals.append("出来高異変")
    if row.get('BBスクイーズ', 0) == 1: fav_signals.append("BB煮詰まり")
    if row.get('RSIダイバージェンス', 0) == 1: fav_signals.append("RSI反転兆候")
    signal_note = f" 💡{'/'.join(fav_signals)}" if fav_signals else ""

    # 配当日チェック
    div_date_str = row.get('配当日', '-')
    if isinstance(div_date_str, str) and div_date_str not in ['-', '0', '0.0']:
        try:
            div_date = datetime.datetime.strptime(div_date_str, '%Y/%m/%d').date()
            days_to_div = (div_date - today).days
            if 0 <= days_to_div <= 7:
                fav_dividend.append(
                    f"  {ticker} 配当日{div_date_str}({days_to_div}日後)"
                    f"\n    → 売却注意！配当権利を失います"
                )
            elif 8 <= days_to_div <= 30:
                fav_dividend.append(f"  {ticker} 配当日{div_date_str}({days_to_div}日後)")
        except:
            pass

    pos_str = f" (高値比-{drop*100:.0f}%)" if drop >= 0.05 else ""

    if warnings:
        warn_str = " / ".join(warnings)
        fav_warning.append(f"  {ticker} ${price:.0f}{pos_str} ({score:.0f}点) → {warn_str}{signal_note}")
    elif rsi >= 70 or (0 <= d <= 14):
        fav_take_profit.append(
            f"  {ticker} ${price:.0f}{pos_str} ({score:.0f}点)"
            f" RSI:{rsi:.0f} → 利確検討{signal_note}"
        )
    else:
        st = "✅" if score >= 40 else "⚪️"
        fav_hold.append(f"  {st} {ticker} ${price:.0f}{pos_str} ({score:.0f}点) RSI:{rsi:.0f}{signal_note}")

# ===================================================
# 高配当 配当日接近
# ===================================================
div_opportunity = []
for _, row in df.iterrows():
    if row['記号'] in favorites:
        continue
    div_date_str = row.get('配当日', '-')
    if isinstance(div_date_str, str) and div_date_str not in ['-', '0', '0.0']:
        try:
            div_date = datetime.datetime.strptime(div_date_str, '%Y/%m/%d').date()
            days_to_div = (div_date - today).days
            div_yield = row.get('配当利回り', 0)
            score = row.get('スコア', 0)
            if 0 <= days_to_div <= 7 and 0.03 <= div_yield <= 0.10 and score >= 30:
                div_opportunity.append(
                    f"  {row['記号']} ${row['株価']:.0f}"
                    f" 利回り{div_yield*100:.1f}% 配当日{div_date_str}"
                )
        except:
            pass

# ===================================================
# メッセージ組み立て
# ===================================================
msg = f"📊 {today_str} スクリーニング結果"

if fav_warning:
    msg += "\n\n🔴【要注意】保有株に危険シグナル"
    for m in fav_warning: msg += f"\n{m}"

if fav_dividend:
    msg += "\n\n📅【配当日接近】売却に注意"
    for m in fav_dividend: msg += f"\n{m}"

if fav_take_profit:
    msg += "\n\n🟡【利確検討】"
    for m in fav_take_profit: msg += f"\n{m}"

if fav_hold:
    msg += "\n\n✅【保有継続OK】"
    for m in fav_hold: msg += f"\n{m}"

if favorites and not fav_warning and not fav_take_profit and not fav_hold and not fav_dividend:
    msg += "\n\n📋 お気に入り: データなし"

if buy_value:
    msg += "\n\n🏷️【割安好業績】高値から下落中の優良株"
    for m in buy_value[:5]: msg += f"\n{m}"

if buy_fundamental:
    msg += "\n\n👑【中長期 買い候補】MACD底打ち"
    for m in buy_fundamental[:5]: msg += f"\n{m}"

# ★新設：大変動予兆
if alert_precursor:
    msg += "\n\n⚡【大変動予兆】近日中に大きく動く可能性"
    msg += "\n※上下どちらに動くかは不明。監視用"
    for m in alert_precursor[:5]: msg += f"\n{m}"

if buy_momentum:
    msg += "\n\n🚀【短期 注目】出来高急増"
    for m in buy_momentum[:3]: msg += f"\n{m}"

if div_opportunity:
    msg += "\n\n💰【配当狙い】権利落ち日7日以内"
    for m in div_opportunity[:3]: msg += f"\n{m}"

if (not buy_value and not buy_fundamental and not buy_momentum
        and not alert_precursor
        and not fav_warning and not fav_take_profit
        and not fav_dividend and not div_opportunity):
    msg += "\n\n特筆すべきシグナルなし。資金温存。"

# ===================================================
# LINE送信
# ===================================================
print(msg)
counts = (f"要注意:{len(fav_warning)} 利確:{len(fav_take_profit)}"
          f" ホールド:{len(fav_hold)} 配当:{len(fav_dividend)}"
          f" 割安好業績:{len(buy_value)} 中長期:{len(buy_fundamental)}"
          f" 予兆:{len(alert_precursor)} 短期:{len(buy_momentum)}"
          f" 配当狙い:{len(div_opportunity)}")
print(f"\n--- {counts} ---")

if LINE_ACCESS_TOKEN and LINE_USER_ID:
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    data = {"to": LINE_USER_ID,
            "messages": [{"type": "text", "text": msg[:4900]}]}
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    if res.status_code == 200:
        print("✅ LINE通知成功")
    else:
        print(f"❌ LINE通知失敗: {res.status_code} {res.text}")
else:
    print("⚠️ LINE認証情報が未設定")
