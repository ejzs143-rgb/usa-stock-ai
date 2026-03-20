"""
auto_screener.py — LINE通知スクリプト（GitHub Actions用）
修正内容:
  - yfinanceへの重複APIコールを排除 → scan_script.pyが生成したCSVを読み込む
  - app.pyと同一のスコアリング関数を使用（判断基準の統一）
  - 通知を3段階化:
      🟢 買い候補（スコア高 + MACD GC + 決算安全）
      🟡 ウォッチリスト（スコア上位）
      🔴 保有株アラート（危険シグナル）
  - 毎朝必ず通知を送信（該当なしの日も生存報告）
"""

import pandas as pd
import requests
import os
import json
import datetime

# ===================================================
# 1. LINE設定
# ===================================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

# ===================================================
# 2. お気に入り銘柄読み込み
# ===================================================
favorites = []
if os.path.exists('favorites.json'):
    try:
        with open('favorites.json', 'r') as f:
            favorites = json.load(f)
    except:
        pass

# ===================================================
# 3. CSVデータ読み込み（scan_script.pyが生成したもの）
# ===================================================
CSV_PATH = 'raw_stock_data.csv'
if not os.path.exists(CSV_PATH):
    print("エラー: raw_stock_data.csv が見つかりません。scan_script.py を先に実行してください。")
    exit(1)

df = pd.read_csv(CSV_PATH)
df.fillna(0, inplace=True)
print(f"CSVデータ読み込み完了: {len(df)}銘柄")

# 欠損列の安全装置（古いCSVとの互換性）
for col in ['FCFマージン', '粗利率', 'アクルーアル', 'MACD_GC', 'MACD_DC',
            '決算猶予日数', '次回決算日', '出来高', '平均出来高50日', '200日MA', '20日高値']:
    if col not in df.columns:
        df[col] = 0

# ===================================================
# 4. スコアリング関数（app.pyの聖杯モードと完全同一）
# ===================================================
def calculate_score(row):
    # EPS: 黒字=+10, 赤字=-50
    score_eps = 10 if row.get('EPS', 0) > 0 else -50

    # PER: 低いほど高得点（0〜15点）
    per = row.get('PER', 0)
    score_per = max(0, min(15, (25 - per) / 15 * 15)) if per > 0 else 0

    # ROE: 高いほど高得点（0〜15点）
    score_roe = max(0, min(15, (row.get('ROE', 0) - 0.05) / 0.15 * 15))

    # 利益率:（0〜15点）
    score_margin = max(0, min(15, (row.get('利益率', 0) - 0.05) / 0.15 * 15))

    # 決算ペナルティ
    days_to_earn = row.get('決算猶予日数', 999)
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

    # FCFマージン（0〜10点）
    score_fcf = max(0, min(10, row.get('FCFマージン', 0) / 0.15 * 10))

    # MACDゴールデンクロス（0 or 15点）
    score_macd = 15 if row.get('MACD_GC', 0) == 1 else 0

    # 戦略加点（RSI低め + アクルーアル健全）
    rsi = row.get('RSI', 50)
    score_strat = 0
    if rsi < 50:
        score_strat += 10
    if row.get('アクルーアル', 0) < 0:
        score_strat += 5

    total = (score_eps + score_per + score_roe + score_margin
             + score_fcf + score_macd + score_strat + earn_penalty)
    return total


# ===================================================
# 5. 全銘柄にスコア計算
# ===================================================
df['スコア'] = df.apply(calculate_score, axis=1)
df = df.sort_values('スコア', ascending=False).reset_index(drop=True)

# 上位10%のスコア閾値
top_10pct = df['スコア'].quantile(0.9) if len(df) > 10 else 999

# ===================================================
# 6. 通知判定（3段階）
# ===================================================
buy_messages = []       # 🟢 買い候補
watch_messages = []     # 🟡 ウォッチリスト
sell_messages = []      # 🔴 保有株アラート

for _, row in df.iterrows():
    ticker = row['記号']
    price = row['株価']
    score = row['スコア']
    days_to_earn = row.get('決算猶予日数', 999)
    rsi = row.get('RSI', 50)
    earnings_str = row.get('次回決算日', '-')

    # --- 🟢 買い候補 ---
    # スコア55以上 + MACD GC + 決算14日以上先 + 黒字 + 予算内
    if (score >= 55
            and row.get('MACD_GC', 0) == 1
            and (days_to_earn == 999 or days_to_earn > 14)
            and row.get('EPS', 0) > 0
            and price <= 200):
        roe_pct = row.get('ROE', 0) * 100
        buy_messages.append(
            f"\n■ {ticker} ${price:.2f} (スコア:{score:.0f}点)"
            f"\n  ROE:{roe_pct:.0f}% RSI:{rsi:.0f} 決算:{earnings_str}"
        )

    # --- 🟡 ウォッチリスト ---
    # スコア上位10% + 決算14日以上先 + 黒字（MACDは不問）
    elif (score >= top_10pct
            and (days_to_earn == 999 or days_to_earn > 14)
            and row.get('EPS', 0) > 0
            and price <= 200):
        watch_messages.append(
            f"\n  {ticker} ${price:.2f} ({score:.0f}点)"
        )

    # --- 🔴 保有株アラート ---
    if ticker in favorites:
        warnings = []

        # 決算接近
        if 0 <= days_to_earn <= 3:
            warnings.append(f"💀決算{days_to_earn}日後")
        elif 4 <= days_to_earn <= 7:
            warnings.append(f"⚠️決算{days_to_earn}日後")
        elif 8 <= days_to_earn <= 14:
            warnings.append(f"⚡決算{days_to_earn}日後")

        # 過熱
        if rsi >= 75:
            warnings.append(f"🔥RSI{rsi:.0f}")

        # MACDデッドクロス
        if row.get('MACD_DC', 0) == 1:
            warnings.append("📉MACDデッドクロス")

        # トレンド崩壊
        ma50 = row.get('MA50', 0)
        if ma50 > 0 and price < ma50 * 0.95:
            warnings.append("⚠️50MA-5%割れ")

        # 赤字
        if row.get('EPS', 0) <= 0:
            warnings.append("☠️赤字")

        if warnings:
            warn_str = " / ".join(warnings)
            sell_messages.append(f"\n■ {ticker} ${price:.2f} → {warn_str}")

# ===================================================
# 7. メッセージ組み立て
# ===================================================
today_str = datetime.date.today().strftime('%m/%d')
final_message = f"📊 スクリーニング完了 ({today_str})"

if buy_messages:
    final_message += "\n\n👑【買い候補】MACD反転+高スコア"
    final_message += "".join(buy_messages[:5])  # 最大5銘柄

if watch_messages:
    final_message += "\n\n🟡【注目】スコア上位"
    final_message += "".join(watch_messages[:5])  # 最大5銘柄

if sell_messages:
    final_message += "\n\n🔴【保有株 警告】"
    final_message += "".join(sell_messages)

# 何もない日も生存報告
if not buy_messages and not watch_messages and not sell_messages:
    final_message += "\n\n✅ 特筆すべきシグナルなし。資金温存。"

# お気に入り銘柄の現状サマリ（常に表示）
if favorites:
    fav_rows = df[df['記号'].isin(favorites)]
    if not fav_rows.empty:
        final_message += f"\n\n📋 お気に入り({len(fav_rows)}銘柄):"
        for _, r in fav_rows.head(10).iterrows():
            s = r['スコア']
            p = r['株価']
            rsi_val = r.get('RSI', 0)
            final_message += f"\n  {r['記号']} ${p:.2f} ({s:.0f}点/RSI:{rsi_val:.0f})"

# ===================================================
# 8. LINE送信
# ===================================================
print(final_message)
print(f"\n--- 集計: 買い候補{len(buy_messages)} / 注目{len(watch_messages)} / 警告{len(sell_messages)} ---")

if LINE_ACCESS_TOKEN and LINE_USER_ID:
    # LINE Messaging APIは5000文字制限
    msg_text = final_message[:4900]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": msg_text}]
    }
    res = requests.post(LINE_API_URL, headers=headers, json=data)
    if res.status_code == 200:
        print("✅ LINE通知成功")
    else:
        print(f"❌ LINE通知失敗: {res.status_code} {res.text}")
else:
    print("⚠️ LINE認証情報が未設定のため通知スキップ")
