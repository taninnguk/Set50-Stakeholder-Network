from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from network_analysis import (
    SHAREHOLDER_COLUMNS,
    build_company_projection,
    build_company_summary,
    build_graph_metrics,
    build_shareholder_summary,
    filter_shared_holders,
    make_pyvis_network,
    records_to_dataframe,
)
from set_scraper import BrowserFetchError, SetScraper, StockInfo, parse_symbol_input


st.set_page_config(
    page_title="SET50 Shareholder Network",
    page_icon="SET50",
    layout="wide",
)


def reset_results() -> None:
    for key in ("shareholders_df", "scrape_errors", "selected_symbols"):
        st.session_state.pop(key, None)


def scrape_data(
    index_symbol: str,
    manual_symbols: str,
    company_limit: int,
    top_n: int,
    lang: str,
    browser: str,
    headless: bool,
    delay_seconds: float,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    errors: list[str] = []
    records = []
    selected_symbols: list[str] = []

    status = st.empty()
    progress = st.progress(0)

    with SetScraper(
        browser=browser,
        headless=headless,
        lang=lang,
        delay_seconds=delay_seconds,
    ) as scraper:
        manual = parse_symbol_input(manual_symbols)
        if manual:
            stocks = [StockInfo(symbol=symbol) for symbol in manual]
        else:
            status.info(f"กำลังดึงรายชื่อหุ้นใน {index_symbol} จาก SET")
            stocks = scraper.get_index_symbols(index_symbol)

        stocks = stocks[:company_limit]
        selected_symbols = [stock.symbol for stock in stocks]

        if not stocks:
            raise BrowserFetchError("ไม่พบรายชื่อหุ้นจาก SET")

        for idx, stock in enumerate(stocks, start=1):
            status.info(f"กำลังดึงผู้ถือหุ้น {stock.symbol} ({idx}/{len(stocks)})")
            try:
                records.extend(
                    scraper.get_shareholders(
                        stock.symbol,
                        company_name=stock.name,
                        top_n=top_n,
                    )
                )
            except Exception as exc:  # keep the batch moving for one bad symbol
                errors.append(f"{stock.symbol}: {exc}")
            progress.progress(idx / len(stocks))

    status.success(f"ดึงข้อมูลเสร็จ {len(records)} รายการ")
    return records_to_dataframe(records), errors, selected_symbols


st.title("SET50 Shareholder Network")
st.caption("Social network analysis จากผู้ถือหุ้นรายใหญ่ของบริษัทใน SET50 โดยดึงข้อมูลจากเว็บไซต์ตลาดหลักทรัพย์แห่งประเทศไทยผ่าน Selenium")

with st.sidebar:
    st.header("ตั้งค่าการดึงข้อมูล")
    index_symbol = st.selectbox("ดัชนี", ["SET50", "SET100"], index=0)
    top_n = st.slider("จำนวนผู้ถือหุ้นต่อบริษัท", min_value=1, max_value=10, value=5)
    company_limit = st.slider("จำนวนบริษัทสูงสุด", min_value=1, max_value=100, value=50)
    lang = st.selectbox("ภาษาข้อมูลจาก SET", ["th", "en"], index=0)
    browser = st.selectbox("Selenium browser", ["chrome", "edge"], index=0)
    headless = st.toggle("Headless browser", value=True)
    delay_seconds = st.slider("หน่วงเวลาระหว่าง request (วินาที)", 0.0, 2.0, 0.2, 0.1)
    manual_symbols = st.text_area(
        "ระบุ symbol เอง (ไม่บังคับ)",
        placeholder="เช่น PTT, PTTEP, AOT",
        help="ถ้าใส่รายการนี้ แอปจะข้ามการดึงรายชื่อ SET50/SET100 และใช้ symbol ที่ระบุแทน",
    )

    run = st.button("ดึงข้อมูลและสร้างกราฟ", type="primary", width="stretch")
    clear = st.button("ล้างผลลัพธ์", width="stretch")

if clear:
    reset_results()

if run:
    reset_results()
    try:
        df, errors, selected_symbols = scrape_data(
            index_symbol=index_symbol,
            manual_symbols=manual_symbols,
            company_limit=company_limit,
            top_n=top_n,
            lang=lang,
            browser=browser,
            headless=headless,
            delay_seconds=delay_seconds,
        )
        st.session_state["shareholders_df"] = df
        st.session_state["scrape_errors"] = errors
        st.session_state["selected_symbols"] = selected_symbols
    except Exception as exc:
        st.error(str(exc))

df = st.session_state.get(
    "shareholders_df",
    pd.DataFrame(columns=SHAREHOLDER_COLUMNS),
)
errors = st.session_state.get("scrape_errors", [])
selected_symbols = st.session_state.get("selected_symbols", [])

if df.empty:
    st.info("กดปุ่มดึงข้อมูลเพื่อสร้าง network ของบริษัทและผู้ถือหุ้นรายใหญ่")
    st.stop()

company_count = df["symbol"].nunique()
holder_count = df["shareholder"].nunique()
edge_count = len(df)
shared_holder_count = (df.groupby("shareholder")["symbol"].nunique() > 1).sum()

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("บริษัท", f"{company_count:,}")
metric_2.metric("ผู้ถือหุ้นไม่ซ้ำ", f"{holder_count:,}")
metric_3.metric("ความสัมพันธ์", f"{edge_count:,}")
metric_4.metric("ผู้ถือหุ้นร่วมหลายบริษัท", f"{shared_holder_count:,}")

st.caption(f"Symbols: {', '.join(selected_symbols)}")

graph_tab, holder_tab, company_tab, raw_tab = st.tabs(
    ["Network", "ผู้ถือหุ้นร่วม", "บริษัทเชื่อมโยง", "ข้อมูลดิบ"]
)

with graph_tab:
    left, right = st.columns([1, 1])
    with left:
        min_percent = st.slider("กรองสัดส่วนถือหุ้นขั้นต่ำ (%)", 0.0, 80.0, 0.0, 0.5)
    with right:
        shared_only = st.toggle("แสดงเฉพาะผู้ถือหุ้นที่ถือมากกว่า 1 บริษัท", value=False)

    graph_df = df[df["percent"].fillna(0) >= min_percent].copy()
    if shared_only:
        graph_df = filter_shared_holders(graph_df)

    if graph_df.empty:
        st.warning("ไม่มีข้อมูลหลังการกรอง")
    else:
        html = make_pyvis_network(graph_df)
        components.html(html, height=760, scrolling=True)

    metrics = build_graph_metrics(graph_df)
    if not metrics.empty:
        st.subheader("Node centrality")
        st.dataframe(metrics, width="stretch", hide_index=True)

with holder_tab:
    holder_summary = build_shareholder_summary(df)
    st.dataframe(holder_summary, width="stretch", hide_index=True)

with company_tab:
    company_summary = build_company_summary(df)
    projection = build_company_projection(df)

    st.subheader("สรุปบริษัท")
    st.dataframe(company_summary, width="stretch", hide_index=True)

    st.subheader("Company projection จากผู้ถือหุ้นร่วม")
    st.dataframe(projection, width="stretch", hide_index=True)

with raw_tab:
    st.download_button(
        "ดาวน์โหลด CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="set_shareholder_network.csv",
        mime="text/csv",
    )
    st.dataframe(df, width="stretch", hide_index=True)

    if errors:
        st.subheader("รายการที่ดึงไม่สำเร็จ")
        st.write("\n".join(errors))
