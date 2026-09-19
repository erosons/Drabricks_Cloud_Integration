"""
Nigeria Financial Intelligence Dashboard
Grafana-style Streamlit dashboard for Nigerian market opportunities.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import importlib
import importlib.util

from config import WAT

# Force fresh import — prevents stale cached module from previous Streamlit sessions
import storage.database as _db_module
importlib.reload(_db_module)
from storage import database as db

from storage.database import init_db

# Ensure all tables exist (safe to call multiple times — uses CREATE IF NOT EXISTS)
init_db()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🇳🇬 Nigeria Financial Intelligence",
    page_icon="🇳🇬",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "Nigeria Financial Intelligence Dashboard — powered by live web scraping"},
)

# ── Theme & CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Grafana-like panel cards */
  .metric-panel {
    background: #1a1e2e;
    border: 1px solid #2d3250;
    border-radius: 8px;
    padding: 18px 20px 14px;
    margin-bottom: 4px;
  }
  .metric-label {
    font-size: 11px;
    color: #8b92a5;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 6px;
  }
  .metric-value {
    font-size: 28px;
    font-weight: 700;
    color: #e2e8f0;
    font-family: monospace;
  }
  .metric-delta-pos { color: #00d084; font-size: 13px; }
  .metric-delta-neg { color: #f05252; font-size: 13px; }
  .metric-delta-neu { color: #8b92a5; font-size: 13px; }

  /* Section headers */
  .panel-header {
    font-size: 13px;
    color: #8b92a5;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    border-bottom: 1px solid #2d3250;
    padding-bottom: 6px;
    margin-bottom: 12px;
  }

  /* Alert badges */
  .badge-critical { background:#7b0000; color:#ff6b6b; border-radius:4px; padding:2px 8px; font-size:11px; }
  .badge-high     { background:#5c3a00; color:#ffa500; border-radius:4px; padding:2px 8px; font-size:11px; }
  .badge-medium   { background:#1a3a5c; color:#63b3ed; border-radius:4px; padding:2px 8px; font-size:11px; }
  .badge-low      { background:#1a2e1a; color:#68d391; border-radius:4px; padding:2px 8px; font-size:11px; }

  /* News item */
  .news-item {
    border-left: 3px solid #2d3250;
    padding: 8px 12px;
    margin-bottom: 8px;
    background: #12151f;
    border-radius: 0 4px 4px 0;
  }
  .news-positive { border-left-color: #00d084; }
  .news-negative { border-left-color: #f05252; }
  .news-source { font-size: 10px; color: #6b7280; text-transform: uppercase; }
  .news-title  { font-size: 13px; color: #d1d5db; }
  .news-time   { font-size: 10px; color: #4b5563; }

  /* Opportunity row */
  .opp-row { padding: 10px 12px; margin-bottom: 6px; background: #12151f; border-radius: 6px; }

  /* Sidebar */
  section[data-testid="stSidebar"] { background: #0d1117; }

  /* Hide Streamlit toolbar */
  #MainMenu, footer, header { visibility: hidden; }

  /* Scrollable news */
  .news-scroll { max-height: 450px; overflow-y: auto; }

  /* Score bar */
  .score-bar-bg { background:#2d3250; border-radius:4px; height:6px; width:100%; }
  .score-bar-fill { background:#00d084; border-radius:4px; height:6px; }
</style>
""", unsafe_allow_html=True)

# ── Auto-refresh every 5 minutes ──────────────────────────────────────────────
_refresh_count = st_autorefresh(interval=300_000, key="auto_refresh")

# ── Helpers ───────────────────────────────────────────────────────────────────
PLOTLY_DARK = dict(
    template="plotly_dark",
    paper_bgcolor="#1a1e2e",
    plot_bgcolor="#1a1e2e",
    font=dict(family="monospace", color="#c5c6c7", size=11),
    margin=dict(l=10, r=10, t=30, b=10),
)

CATEGORY_COLORS = {
    "STOCKS": "#00d084",
    "TREASURY": "#63b3ed",
    "POLICY": "#ffa500",
    "FOREX": "#f6e05e",
    "GENERAL": "#a0aec0",
    "IPO": "#b794f4",
}


def _fmt_number(val, decimals=2, prefix=""):
    if val is None:
        return "N/A"
    if abs(val) >= 1_000_000_000:
        return f"{prefix}{val/1_000_000_000:.1f}B"
    if abs(val) >= 1_000_000:
        return f"{prefix}{val/1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"{prefix}{val/1_000:.1f}K"
    return f"{prefix}{val:,.{decimals}f}"


def _delta_html(val, suffix="%"):
    if val is None:
        return ""
    cls = "metric-delta-pos" if val > 0 else ("metric-delta-neg" if val < 0 else "metric-delta-neu")
    arrow = "▲" if val > 0 else ("▼" if val < 0 else "—")
    return f'<span class="{cls}">{arrow} {abs(val):.2f}{suffix}</span>'


def _badge(level: str) -> str:
    cls = f"badge-{level.lower()}"
    return f'<span class="{cls}">{level}</span>'


def _sentiment_border(score: float) -> str:
    if score > 0.05:
        return "news-positive"
    if score < -0.05:
        return "news-negative"
    return ""


# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title, col_time = st.columns([0.5, 3, 2])
with col_logo:
    st.markdown("## 🇳🇬")
with col_title:
    st.markdown("## Nigeria Financial Intelligence Dashboard")
    st.markdown('<span style="color:#6b7280;font-size:12px;">Live market data · Treasury · Fund Managers · IPOs · Government Signals</span>', unsafe_allow_html=True)
with col_time:
    now_wat = datetime.now(WAT)
    st.markdown(f'<div style="text-align:right;margin-top:16px;color:#6b7280;font-size:12px;">Last refresh: {now_wat.strftime("%d %b %Y %H:%M")} WAT</div>', unsafe_allow_html=True)

st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
ngx_idx       = db.latest_ngx_index()
treasury      = db.latest_treasury_rates()
fund_rates    = db.latest_fund_rates()
policy_events = db.latest_policy_events(20)
ipos          = db.all_ipos()
news          = db.latest_news(60)
opportunities = db.active_opportunities()
opp_counts    = db.opportunity_counts_by_level()
mpr           = db.latest_mpr()
stock_picks   = db.latest_stock_picks()
picks_summary = db.stock_picks_summary()

# ── Panel 1: KPI Metric Cards ─────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    idx_val = ngx_idx.get("index_value", 0)
    idx_chg = ngx_idx.get("change_pct", 0)
    st.markdown(f"""
    <div class="metric-panel">
      <div class="metric-label">NGX All-Share Index</div>
      <div class="metric-value">{_fmt_number(idx_val, 0)}</div>
      {_delta_html(idx_chg)}
    </div>""", unsafe_allow_html=True)

with c2:
    tbill_364 = next((r["rate"] for r in treasury if "364" in r.get("instrument","") or "364-day" in r.get("tenor","")), None)
    if tbill_364 is None and treasury:
        tbill_364 = max(r["rate"] for r in treasury if r.get("rate"))
    st.markdown(f"""
    <div class="metric-panel">
      <div class="metric-label">364-Day T-Bill Rate</div>
      <div class="metric-value">{f'{tbill_364:.2f}%' if tbill_364 else 'N/A'}</div>
      <span class="metric-delta-neu">DMO auction</span>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-panel">
      <div class="metric-label">CBN MPR (Policy Rate)</div>
      <div class="metric-value">{mpr:.1f}%</div>
      <span class="metric-delta-neu">Monetary Policy Rate</span>
    </div>""", unsafe_allow_html=True)

with c4:
    fx_event = next((e for e in policy_events if e.get("event_type") == "FX_RATE"), None)
    fx_rate = fx_event["value"] if fx_event else None
    st.markdown(f"""
    <div class="metric-panel">
      <div class="metric-label">USD/NGN Rate</div>
      <div class="metric-value">{'₦' + _fmt_number(fx_rate, 0) if fx_rate else 'N/A'}</div>
      <span class="metric-delta-neu">CBN official</span>
    </div>""", unsafe_allow_html=True)

with c5:
    total_opps = sum(opp_counts.values())
    critical   = opp_counts.get("CRITICAL", 0)
    high       = opp_counts.get("HIGH", 0)
    st.markdown(f"""
    <div class="metric-panel">
      <div class="metric-label">Active Opportunities</div>
      <div class="metric-value">{total_opps}</div>
      <span class="badge-critical">{critical} CRIT</span>&nbsp;
      <span class="badge-high">{high} HIGH</span>
    </div>""", unsafe_allow_html=True)

st.markdown("")

# ── Panel 2 & 3: Stocks + Treasury ────────────────────────────────────────────
col_stocks, col_treasury = st.columns([3, 2])

with col_stocks:
    st.markdown('<div class="panel-header">📈 NGX Stock Market</div>', unsafe_allow_html=True)

    # Index history chart
    history = db.ngx_index_history(48)
    if history:
        df_hist = pd.DataFrame(history)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist["timestamp"], y=df_hist["index_value"],
            mode="lines", line=dict(color="#00d084", width=2),
            fill="tozeroy", fillcolor="rgba(0,208,132,0.08)",
            name="NGX ASI",
        ))
        fig.update_layout(
            **PLOTLY_DARK,
            height=220,
            xaxis_title=None, yaxis_title="Index",
            showlegend=False,
        )
        st.plotly_chart(fig, width="stretch")

    # Top equities table
    equities = db.latest_equities(100)
    if equities:
        df_eq = pd.DataFrame(equities)
        tab_gain, tab_lose, tab_vol = st.tabs(["Top Gainers", "Top Losers", "High Volume"])
        with tab_gain:
            df_g = df_eq[df_eq["change_pct"] > 0].sort_values("change_pct", ascending=False).head(10)
            if not df_g.empty:
                st.dataframe(
                    df_g[["symbol","name","price","change_pct","volume","sector"]].rename(columns={
                        "symbol":"Symbol","name":"Company","price":"Price (₦)",
                        "change_pct":"Chg %","volume":"Volume","sector":"Sector",
                    }),
                    width="stretch", hide_index=False,
                )
        with tab_lose:
            df_l = df_eq[df_eq["change_pct"] < 0].sort_values("change_pct").head(10)
            if not df_l.empty:
                st.dataframe(
                    df_l[["symbol","name","price","change_pct","volume","sector"]].rename(columns={
                        "symbol":"Symbol","name":"Company","price":"Price (₦)",
                        "change_pct":"Chg %","volume":"Volume","sector":"Sector",
                    }),
                    width="stretch", hide_index=False,
                )
        with tab_vol:
            df_v = df_eq.sort_values("volume", ascending=False).head(10)
            if not df_v.empty:
                st.dataframe(
                    df_v[["symbol","name","price","change_pct","volume"]].rename(columns={
                        "symbol":"Symbol","name":"Company","price":"Price (₦)",
                        "change_pct":"Chg %","volume":"Volume",
                    }),
                    width="stretch", hide_index=False,
                )
    else:
        st.info("Waiting for NGX data… (market hours 10am–2:30pm WAT weekdays)")

with col_treasury:
    st.markdown('<div class="panel-header">🏦 Treasury & Fixed Income</div>', unsafe_allow_html=True)

    if treasury:
        df_tr = pd.DataFrame(treasury)
        df_tr = df_tr[df_tr["rate"].notna() & (df_tr["rate"] > 0)].copy()

        # Bar chart
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            y=df_tr["instrument"].str[:25],
            x=df_tr["rate"],
            orientation="h",
            marker_color="#63b3ed",
            text=[f"{r:.1f}%" for r in df_tr["rate"]],
            textposition="outside",
        ))
        # MPR reference line
        fig2.add_vline(x=mpr, line_dash="dash", line_color="#ffa500",
                       annotation_text=f"MPR {mpr}%", annotation_font_color="#ffa500")
        fig2.update_layout(
            **PLOTLY_DARK,
            height=300,
            xaxis_title="Rate (%)",
            yaxis_title=None,
            showlegend=False,
        )
        st.plotly_chart(fig2, width="stretch")

        # Table
        st.dataframe(
            df_tr[["instrument","rate","source"]].rename(columns={
                "instrument":"Instrument","rate":"Rate (%)","source":"Source",
            }),
            width="stretch", hide_index=False,
        )
    else:
        st.info("Treasury rate data loading…")

st.markdown("")

# ── Panel 4 & 5: Fund Managers + IPO Tracker ──────────────────────────────────
col_funds, col_ipo = st.columns([3, 2])

with col_funds:
    st.markdown('<div class="panel-header">💼 Fund Manager Rate Comparison</div>', unsafe_allow_html=True)

    if fund_rates:
        df_f = pd.DataFrame(fund_rates)
        df_f = df_f[df_f["rate"].notna()].copy()

        tab_ngn, tab_usd = st.tabs(["NGN Products", "USD Products"])
        with tab_ngn:
            df_ngn = df_f[df_f["currency"] == "NGN"].sort_values("rate", ascending=False)
            if not df_ngn.empty:
                fig_funds = px.bar(
                    df_ngn, x="rate", y="provider", color="product",
                    orientation="h",
                    labels={"rate": "Rate (% p.a.)", "provider": "Provider"},
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig_funds.add_vline(x=mpr, line_dash="dash", line_color="#ffa500",
                                    annotation_text=f"MPR {mpr}%")
                fig_funds.update_layout(**PLOTLY_DARK, height=260, showlegend=True,
                                        legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_funds, width="stretch")
                st.dataframe(
                    df_ngn[["provider","product","rate","duration","min_amount","description"]].rename(columns={
                        "provider":"Provider","product":"Product","rate":"Rate %",
                        "duration":"Term","min_amount":"Min (₦)","description":"Notes",
                    }),
                    width="stretch", hide_index=False,
                )
        with tab_usd:
            df_usd = df_f[df_f["currency"] == "USD"].sort_values("rate", ascending=False)
            if not df_usd.empty:
                fig_usd = px.bar(
                    df_usd, x="rate", y="provider", color="product",
                    orientation="h",
                    labels={"rate": "Rate (% p.a.)", "provider": "Provider"},
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                fig_usd.update_layout(**PLOTLY_DARK, height=220, showlegend=True,
                                      legend=dict(orientation="h", y=-0.3))
                st.plotly_chart(fig_usd, width="stretch")
                st.dataframe(
                    df_usd[["provider","product","rate","duration","min_amount","description"]].rename(columns={
                        "provider":"Provider","product":"Product","rate":"Rate %",
                        "duration":"Term","min_amount":"Min (USD)","description":"Notes",
                    }),
                    width="stretch", hide_index=False,
                )
    else:
        st.info("Fund rate data loading…")

with col_ipo:
    st.markdown('<div class="panel-header">🚀 IPO Tracker</div>', unsafe_allow_html=True)
    if ipos:
        df_ipo = pd.DataFrame(ipos)
        open_ipos_df = df_ipo[df_ipo["status"].isin(["OPEN", "UPCOMING"])].head(10)
        for _, row in open_ipos_df.iterrows():
            status_color = "#00d084" if row["status"] == "OPEN" else "#ffa500"
            price_str = f"₦{row['offer_price']:.2f}" if row.get("offer_price") else "TBD"
            st.markdown(f"""
            <div style="background:#12151f;border-radius:6px;padding:10px 14px;margin-bottom:8px;
                        border-left:3px solid {status_color};">
              <div style="font-size:11px;color:{status_color};text-transform:uppercase;
                          font-weight:600;letter-spacing:0.8px;">{row['status']} IPO</div>
              <div style="font-size:14px;color:#e2e8f0;margin:3px 0;">{row['company'][:60]}</div>
              <div style="font-size:11px;color:#6b7280;">
                Price: {price_str} &nbsp;|&nbsp; Sector: {row.get('sector','N/A')} &nbsp;|&nbsp;
                Closes: {row.get('closing_date','TBD')}
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No active IPOs found. SEC data loading…")

    st.markdown('<div class="panel-header" style="margin-top:16px;">🏛️ Government & Policy</div>', unsafe_allow_html=True)
    for ev in policy_events[:8]:
        ev_type = ev.get("event_type", "")
        title   = ev.get("title", "")[:80]
        val     = ev.get("value")
        ts      = ev.get("timestamp", "")[:16]
        color   = "#ffa500" if "MPR" in ev_type or "RATE" in ev_type else "#63b3ed"
        val_str = f" → {val:.2f}%" if val and ev_type in ("MPR","CRR") else ""
        st.markdown(f"""
        <div style="font-size:12px;color:#c5c6c7;padding:5px 0;
                    border-bottom:1px solid #1a1e2e;">
          <span style="color:{color};font-weight:600;">[{ev_type}]</span>
          {title}{val_str}
          <span style="color:#4b5563;float:right;">{ts}</span>
        </div>""", unsafe_allow_html=True)

st.markdown("")

# ── Panel 6 & 7: News + Opportunity Signals ────────────────────────────────────
col_news, col_opps = st.columns([2, 3])

with col_news:
    st.markdown('<div class="panel-header">📰 Financial News Feed</div>', unsafe_allow_html=True)
    if news:
        # Category filter
        cats = ["ALL"] + sorted(set(a.get("category","GENERAL") for a in news))
        sel_cat = st.selectbox("Filter category", cats, label_visibility="collapsed")

        filtered = news if sel_cat == "ALL" else [a for a in news if a.get("category") == sel_cat]

        st.markdown('<div class="news-scroll">', unsafe_allow_html=True)
        for article in filtered[:30]:
            sentiment = article.get("sentiment", 0) or 0
            border_cls = _sentiment_border(sentiment)
            pub = str(article.get("published_at",""))[:16]
            url = article.get("url","")
            title = article.get("title","")[:120]
            source = article.get("source","")
            cat = article.get("category","GENERAL")
            cat_color = CATEGORY_COLORS.get(cat, "#a0aec0")
            link = f'<a href="{url}" target="_blank" style="color:#d1d5db;text-decoration:none;">{title}</a>' if url else title
            st.markdown(f"""
            <div class="news-item {border_cls}">
              <div class="news-source">
                {source} &nbsp;<span style="color:{cat_color}">#{cat}</span>
              </div>
              <div class="news-title">{link}</div>
              <div class="news-time">{pub} WAT</div>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("News loading… (check back in 30 seconds)")

with col_opps:
    st.markdown('<div class="panel-header">⚡ Investment Opportunity Signals</div>', unsafe_allow_html=True)

    # Summary counts
    cnt_c1, cnt_c2, cnt_c3, cnt_c4 = st.columns(4)
    cnt_c1.metric("CRITICAL", opp_counts.get("CRITICAL", 0), delta=None)
    cnt_c2.metric("HIGH",     opp_counts.get("HIGH", 0),     delta=None)
    cnt_c3.metric("MEDIUM",   opp_counts.get("MEDIUM", 0),   delta=None)
    cnt_c4.metric("LOW",      opp_counts.get("LOW", 0),      delta=None)

    if opportunities:
        # Category filter
        opp_cats = ["ALL"] + sorted(set(o["category"] for o in opportunities))
        sel_opp_cat = st.selectbox("Filter signal type", opp_cats, key="opp_cat", label_visibility="collapsed")
        filtered_opps = opportunities if sel_opp_cat == "ALL" else [o for o in opportunities if o["category"] == sel_opp_cat]

        for opp in filtered_opps[:15]:
            score = opp.get("score", 0) or 0
            level = opp.get("alert_level", "LOW")
            cat   = opp.get("category", "")
            title = opp.get("title", "")[:100]
            desc  = opp.get("desc","") or opp.get("description","")
            ts    = str(opp.get("detected_at",""))[:16]
            score_pct = min(int(score), 100)
            bar_color = {"CRITICAL":"#f05252","HIGH":"#ffa500","MEDIUM":"#63b3ed","LOW":"#68d391"}.get(level,"#68d391")

            st.markdown(f"""
            <div class="opp-row">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                <div style="font-size:10px;color:#6b7280;">{cat}</div>
                {_badge(level)}
              </div>
              <div style="font-size:13px;color:#e2e8f0;font-weight:600;margin-bottom:4px;">{title}</div>
              <div style="font-size:11px;color:#9ca3af;margin-bottom:6px;">{desc[:160]}</div>
              <div style="display:flex;align-items:center;gap:8px;">
                <div class="score-bar-bg" style="flex:1;">
                  <div class="score-bar-fill" style="width:{score_pct}%;background:{bar_color};"></div>
                </div>
                <span style="font-size:10px;color:#6b7280;">{score_pct}/100</span>
                <span style="font-size:10px;color:#4b5563;">{ts}</span>
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No active signals yet. Engine runs every 30 min after data loads.")

# ── Panel 8: Stocks to Invest In ─────────────────────────────────────────────
st.markdown("")
st.markdown('<div class="panel-header">📊 NGX Stocks to Invest In — Screener Rankings</div>', unsafe_allow_html=True)

REC_COLOR = {
    "STRONG BUY": "#00d084",
    "BUY":        "#68d391",
    "WATCH":      "#f6e05e",
    "HOLD":       "#a0aec0",
    "AVOID":      "#f05252",
}
RISK_COLOR = {"LOW": "#68d391", "MEDIUM": "#f6e05e", "HIGH": "#f05252"}

if stock_picks:
    # Summary row
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    for col, rec, label in [
        (sc1, "STRONG BUY", "🟢 Strong Buy"),
        (sc2, "BUY",        "🟩 Buy"),
        (sc3, "WATCH",      "🟡 Watch"),
        (sc4, "HOLD",       "⚪ Hold"),
        (sc5, "AVOID",      "🔴 Avoid"),
    ]:
        col.metric(label, picks_summary.get(rec, 0))

    st.markdown("")

    # Filters
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        sel_rec = st.selectbox(
            "Recommendation", ["ALL", "STRONG BUY", "BUY", "WATCH", "HOLD", "AVOID"],
            key="pick_rec"
        )
    with f2:
        sectors = ["ALL"] + sorted(set(p["sector"] for p in stock_picks if p.get("sector")))
        sel_sec = st.selectbox("Sector", sectors, key="pick_sec")
    with f3:
        sel_cap = st.selectbox("Market Cap", ["ALL", "LARGE", "MID", "SMALL"], key="pick_cap")
    with f4:
        sel_div = st.selectbox("Dividends", ["ALL", "Dividend payers only"], key="pick_div")

    filtered_picks = stock_picks
    if sel_rec != "ALL":
        filtered_picks = [p for p in filtered_picks if p["recommendation"] == sel_rec]
    if sel_sec != "ALL":
        filtered_picks = [p for p in filtered_picks if p["sector"] == sel_sec]
    if sel_cap != "ALL":
        filtered_picks = [p for p in filtered_picks if p["cap_tier"] == sel_cap]
    if sel_div != "ALL":
        filtered_picks = [p for p in filtered_picks if p.get("dividend")]

    view_tab, chart_tab, detail_tab = st.tabs(["📋 Rankings Table", "📈 Score Chart", "🔍 Deep Dive"])

    with view_tab:
        # Build display table
        rows = []
        for p in filtered_picks[:40]:
            rec = p.get("recommendation", "HOLD")
            risk = p.get("risk_level", "MEDIUM")
            price_str = f"₦{p['price']:.2f}" if p.get("price") else p.get("price_ref", "—")
            chg_str = f"{p['change_pct']:+.1f}%" if p.get("change_pct") is not None else "—"
            div_str = f"{p['div_yield_est']:.1f}%" if p.get("div_yield_est") else "—"
            rows.append({
                "Symbol":    p["symbol"],
                "Company":   p["name"],
                "Sector":    p["sector"],
                "Cap":       p["cap_tier"],
                "Price":     price_str,
                "Chg%":      chg_str,
                "Div Yield": div_str,
                "P/E Band":  p.get("pe_band", "—"),
                "Score":     p["score"],
                "Pick":      rec,
                "Risk":      risk,
            })
        if rows:
            df_picks = pd.DataFrame(rows)
            st.dataframe(df_picks, width="stretch", hide_index=False, height=420)
        else:
            st.info("No stocks match the current filters.")

    with chart_tab:
        if filtered_picks:
            top30 = filtered_picks[:30]
            rec_labels = [p["recommendation"] for p in top30]
            colors     = [REC_COLOR.get(r, "#a0aec0") for r in rec_labels]

            fig_picks = go.Figure(go.Bar(
                x=[p["score"] for p in top30],
                y=[p["symbol"] for p in top30],
                orientation="h",
                marker_color=colors,
                text=[p["recommendation"] for p in top30],
                textposition="outside",
                hovertext=[
                    f"{p['name']}<br>Score: {p['score']}<br>{p['thesis']}"
                    for p in top30
                ],
                hoverinfo="text",
            ))
            fig_picks.update_layout(
                **PLOTLY_DARK,
                height=max(400, len(top30) * 22),
                xaxis_title="Screener Score (0–100)",
                yaxis=dict(autorange="reversed"),
                showlegend=False,
            )
            fig_picks.add_vline(x=75, line_dash="dash", line_color="#00d084",
                                annotation_text="Strong Buy", annotation_font_color="#00d084")
            fig_picks.add_vline(x=55, line_dash="dash", line_color="#68d391",
                                annotation_text="Buy", annotation_font_color="#68d391")
            st.plotly_chart(fig_picks, width="stretch")

            # Sector donut
            sec_counts = {}
            for p in filtered_picks:
                rec = p["recommendation"]
                if rec in ("STRONG BUY", "BUY"):
                    sec_counts[p["sector"]] = sec_counts.get(p["sector"], 0) + 1
            if sec_counts:
                fig_sec = go.Figure(go.Pie(
                    labels=list(sec_counts.keys()),
                    values=list(sec_counts.values()),
                    hole=0.5,
                    marker_colors=px.colors.qualitative.Set3,
                ))
                fig_sec.update_layout(
                    **PLOTLY_DARK, height=280,
                    title_text="Buy/Strong-Buy picks by sector",
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.1),
                )
                st.plotly_chart(fig_sec, width="stretch")

    with detail_tab:
        if filtered_picks:
            sel_sym = st.selectbox(
                "Select stock for detailed view",
                [p["symbol"] for p in filtered_picks[:40]],
                key="detail_sym",
            )
            pick = next((p for p in filtered_picks if p["symbol"] == sel_sym), None)
            if pick:
                rec   = pick.get("recommendation", "HOLD")
                risk  = pick.get("risk_level", "MEDIUM")
                score = pick.get("score", 0)
                rec_color  = REC_COLOR.get(rec, "#a0aec0")
                risk_color = RISK_COLOR.get(risk, "#f6e05e")

                d1, d2, d3, d4 = st.columns(4)
                d1.metric("Score", f"{score:.0f}/100")
                d2.metric("Recommendation", rec)
                d3.metric("Risk Level", risk)
                d4.metric("Div Yield (est)", f"{pick.get('div_yield_est', 0):.1f}%")

                st.markdown(f"""
                <div style="background:#12151f;border-radius:8px;padding:16px 20px;
                            border-left:4px solid {rec_color};margin:8px 0;">
                  <div style="font-size:18px;font-weight:700;color:#e2e8f0;">
                    {pick['symbol']} — {pick['name']}
                  </div>
                  <div style="font-size:12px;color:#6b7280;margin:4px 0;">
                    {pick['sector']} · {pick['cap_tier']} CAP · P/E: {pick.get('pe_band','—')} ·
                    Ref Price: {pick.get('price_ref','—')}
                  </div>
                  <div style="margin-top:10px;font-size:13px;color:#c5c6c7;">
                    <strong>Investment Thesis:</strong> {pick.get('thesis','')}
                  </div>
                  <div style="margin-top:8px;font-size:12px;color:#9ca3af;">
                    <strong>Score breakdown:</strong> {pick.get('rationale','').replace(' | ','  →  ')}
                  </div>
                  <div style="margin-top:8px;">
                    {'  '.join(f'<span style="background:#1a1e2e;border:1px solid #2d3250;border-radius:3px;padding:1px 6px;font-size:10px;color:#8b92a5;">#{t}</span>' for t in (pick.get('tags') or '').split(',') if t)}
                  </div>
                  <div style="margin-top:10px;">
                    <span style="color:{rec_color};font-weight:700;font-size:14px;">{rec}</span>
                    &nbsp;&nbsp;
                    <span style="color:{risk_color};font-size:12px;">Risk: {risk}</span>
                    &nbsp;&nbsp;
                    {'<span style="color:#ffa500;font-size:12px;">💰 Dividend payer</span>' if pick.get('dividend') else ''}
                  </div>
                </div>""", unsafe_allow_html=True)

                # Price history if available
                hist = db.query(
                    "SELECT timestamp, price, change_pct FROM ngx_equities "
                    "WHERE symbol=? ORDER BY timestamp DESC LIMIT 48",
                    (sel_sym,),
                )
                if hist:
                    df_h = pd.DataFrame([dict(r) for r in hist])
                    df_h["timestamp"] = pd.to_datetime(df_h["timestamp"])
                    fig_h = go.Figure(go.Scatter(
                        x=df_h["timestamp"], y=df_h["price"],
                        mode="lines+markers",
                        line=dict(color=rec_color, width=2),
                        name=sel_sym,
                    ))
                    fig_h.update_layout(**PLOTLY_DARK, height=200,
                                        xaxis_title=None, yaxis_title="Price (₦)")
                    st.plotly_chart(fig_h, width="stretch")
                else:
                    st.caption("No price history yet — will populate during market hours.")
else:
    st.info("Stock screener running… results appear after first scan completes.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
fc1, fc2, fc3 = st.columns(3)
with fc1:
    st.markdown('<span style="color:#4b5563;font-size:11px;">Data sources: NGX · CBN · DMO · SEC Nigeria · Nairametrics · BusinessDay · Proshare</span>', unsafe_allow_html=True)
with fc2:
    st.markdown('<span style="color:#4b5563;font-size:11px;">Scrapers: NGX (15min) · CBN (1hr) · DMO (daily) · Funds (6hr) · News (30min)</span>', unsafe_allow_html=True)
with fc3:
    st.markdown('<span style="color:#4b5563;font-size:11px;">⚠️ For informational purposes only. Not financial advice.</span>', unsafe_allow_html=True)
