"""
scan_script.py — S&P500 データ収集スクリプト（GitHub Actions用）
修正内容:
  - period="6mo" → "1y"（200日MA計算に必要）
  - app.pyが必要とする全列を出力（FCFマージン,粗利率,アクルーアル,MACD_GC,MACD_DC,決算日,出来高等）
  - エラー時もスキップして継続（既存動作を維持）
"""

import pandas as pd
import yfinance as yf
import numpy as np
import time
import datetime
import requests

# ===================================================
# 1. S&P500 銘柄リスト取得（Wikipedia、403対策済み）
# ===================================================
print("S&P500銘柄リストを取得中...")
url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36'
}
response = requests.get(url, headers=headers)
df_tickers = pd.read_html(response.text)[0]
tickers = df_tickers['Symbol'].str.replace('.', '-', regex=False).tolist()
print(f"取得完了: {len(tickers)}銘柄")

# ===================================================
# 2. 各銘柄のデータ収集
# ===================================================
data = []
total = len(tickers)
errors = 0

for i, ticker in enumerate(tickers):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y")  # 200日MA計算に1年分必要

        if hist.empty or len(hist) < 30:
            continue

        price = hist['Close'].iloc[-1]
        vol = hist['Volume'].iloc[-1]
        avg_vol_50 = hist['Volume'].tail(50).mean() if len(hist) >= 50 else vol
        ma50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else price
        ma200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else price
        high_20 = hist['Close'].tail(20).max() if len(hist) >= 20 else price

        # --- 基本指標 ---
        eps = info.get('trailingEps', 0) or 0
        per = info.get('trailingPE', 0) or 0
        f_per = info.get('forwardPE', 0) or 0
        roe = info.get('returnOnEquity', 0) or 0
        margin = info.get('profitMargins', 0) or 0
        div = info.get('dividendYield', 0) or 0
        pbr = info.get('priceToBook', 0) or 0
        roa = info.get('returnOnAssets', 0) or 0

        # --- RSI ---
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if len(hist) > 14 and not pd.isna(rs.iloc[-1]) else 50

        # --- MACD ---
        exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
        exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        is_macd_gc = 0
        is_macd_dc = 0
        if len(macd_hist) > 2:
            if (macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0):
                is_macd_gc = 1
            if (macd_hist.iloc[-1] < 0) and (macd_hist.iloc[-2] >= 0):
                is_macd_dc = 1

        # --- 決算日 ---
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

        # --- 配当日（権利落ち日）---
        div_date_str = "-"
        try:
            ex_div_ts = info.get('exDividendDate')
            if ex_div_ts:
                div_date_str = datetime.datetime.fromtimestamp(ex_div_ts).strftime('%Y/%m/%d')
        except:
            pass

        # --- 財務データ（FCF、粗利率、アクルーアル）---
        fcf_margin_val, gross_margin_val, accruals_val = 0, 0, 0
        try:
            financials = stock.financials
            cashflow = stock.cashflow
            balance_sheet = stock.balance_sheet

            if not financials.empty and not cashflow.empty and not balance_sheet.empty:
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

        # --- 1行分のデータを追加 ---
        data.append({
            '記号': ticker,
            '銘柄': info.get('shortName', ticker),
            '株価': price,
            'PER': per,
            '予想PER': f_per,
            'EPS': eps,
            'ROE': roe,
            '利益率': margin,
            '配当利回り': div,
            'PBR': pbr,
            'ROA': roa,
            'RSI': rsi,
            'MA50': ma50,
            'FCFマージン': fcf_margin_val,
            '粗利率': gross_margin_val,
            'アクルーアル': accruals_val,
            'MACD_GC': is_macd_gc,
            'MACD_DC': is_macd_dc,
            '次回決算日': earnings_str,
            '決算猶予日数': days_to_earn,
            '出来高': vol,
            '平均出来高50日': avg_vol_50,
            '200日MA': ma200,
            '20日高値': high_20,
            '配当日': div_date_str
        })

    except Exception as e:
        errors += 1
        if errors <= 10:  # 最初の10件だけログ出力
            print(f"  スキップ: {ticker} ({e})")
        continue

    # 進捗表示 + API負荷軽減
    if (i + 1) % 50 == 0 or i == total - 1:
        print(f"  進捗: {i+1}/{total}社完了 (成功: {len(data)}社)")
    time.sleep(0.25)

# ===================================================
# 3. CSV保存
# ===================================================
df_res = pd.DataFrame(data)
df_res.fillna(0, inplace=True)
df_res.to_csv('raw_stock_data.csv', index=False)
print(f"\n完了: {len(data)}社のデータを raw_stock_data.csv に保存（エラー: {errors}社スキップ）")
