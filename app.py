import streamlit as st
import pandas as pd

st.set_page_config(page_title="米国株AIナビ", layout="wide")
st.title("🤖 米国株 AI格付けランキング")

try:
    df = pd.read_csv('sp500_ranking.csv')
    st.info(f"最終更新(日本時間): {df['更新日'].iloc[0]}")
    
    # 予算フィルタ
    budget = st.sidebar.slider("予算(ドル)", 10, 500, 200)
    filtered_df = df[df['株価'].str.replace('$', '').astype(float) <= budget]
    
    st.dataframe(filtered_df[['順位', '銘柄', '記号', 'スコア', '株価', 'AI判断', 'ROE%', '過熱度%']], use_container_width=True)
except:
    st.error("現在データを集計中です。数分後に再度ご確認ください。")
