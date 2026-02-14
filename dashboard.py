import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import json
import base64

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "card_prices_summary.csv")

# Import scraper functions
sys.path.insert(0, SCRIPT_DIR)
from scrape_card_prices import (
    create_driver, search_ebay_sold, calculate_fair_price,
    build_simplified_query, get_grade_info, title_matches_grade
)
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from datetime import datetime
from config import DEFAULT_PRICE

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def analyze_card_images(front_image_bytes, back_image_bytes=None):
    """Use Claude vision to extract card details from front/back photos."""
    if not HAS_ANTHROPIC:
        return None, "anthropic package not installed. Run: pip install anthropic"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set. Add it to your environment."

    client = anthropic.Anthropic(api_key=api_key)

    content = []

    # Add front image
    front_b64 = base64.standard_b64encode(front_image_bytes).decode("utf-8")
    content.append({"type": "text", "text": "FRONT OF CARD:"})
    content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": front_b64}
    })

    # Add back image if provided
    if back_image_bytes:
        back_b64 = base64.standard_b64encode(back_image_bytes).decode("utf-8")
        content.append({"type": "text", "text": "BACK OF CARD:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": back_b64}
        })

    content.append({
        "type": "text",
        "text": """Analyze this hockey/sports card and extract the following details.
Look at BOTH the front and back of the card carefully.

The back typically has: card number, set name, year, manufacturer info.
The front typically has: player name, team, photo.

Return ONLY valid JSON with these exact keys:
{
    "player_name": "Full player name",
    "card_number": "Just the number (e.g. 201, not #201)",
    "card_set": "Set name with subset (e.g. Upper Deck Series 1 Young Guns)",
    "year": "Card year or season (e.g. 2023-24)",
    "variant": "Parallel or variant name if any, empty string if base card",
    "grade": "Grade if in a graded slab (e.g. PSA 10), empty string if raw",
    "confidence": "high, medium, or low"
}

Be precise. If you can't determine a field, use your best guess based on card design, logos, and text visible."""
    })

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": content}]
        )

        response_text = response.content[0].text.strip()
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            card_info = json.loads(json_match.group())
            return card_info, None
        else:
            return None, f"Could not parse response: {response_text[:200]}"
    except Exception as e:
        return None, str(e)


def scrape_single_card(card_name):
    """Scrape eBay for a single card and return result dict."""
    driver = create_driver()
    try:
        sales = search_ebay_sold(driver, card_name, max_results=50)

        # Retry with simplified query if no results
        if not sales:
            simplified = build_simplified_query(card_name)
            grade_str, grade_num = get_grade_info(card_name)
            encoded = urllib.parse.quote(simplified)
            url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"
            try:
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
                )
                items = driver.find_elements(By.CSS_SELECTOR, '.s-card')
                for item in items:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, '.s-card__title')
                        title = title_elem.text.strip()
                        if not title or not title_matches_grade(title, grade_str, grade_num):
                            continue
                        price_elem = item.find_element(By.CSS_SELECTOR, '.s-card__price')
                        price_text = price_elem.text.strip().replace('Opens in a new window', '')
                        price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                        if not price_match:
                            continue
                        price_val = float(price_match.group(1).replace(',', ''))
                        shipping_val = 0.0
                        try:
                            ship_elems = item.find_elements(By.XPATH,
                                './/*[contains(text(),"delivery") or contains(text(),"shipping")]')
                            for se in ship_elems:
                                se_text = se.text.strip().lower()
                                if 'free' in se_text:
                                    break
                                sm = re.search(r'\$([\d,]+\.?\d*)', se_text)
                                if sm:
                                    shipping_val = float(sm.group(1).replace(',', ''))
                                    break
                        except Exception:
                            pass
                        sold_date = None
                        try:
                            caption = item.find_element(By.CSS_SELECTOR, '.s-card__caption')
                            dm = re.search(r'Sold\s+(\w+\s+\d+,?\s*\d*)', caption.text.strip())
                            if dm:
                                try:
                                    sold_date = datetime.strptime(dm.group(1), '%b %d, %Y')
                                except ValueError:
                                    try:
                                        sold_date = datetime.strptime(dm.group(1) + f', {datetime.now().year}', '%b %d, %Y')
                                    except ValueError:
                                        pass
                        except Exception:
                            pass
                        sales.append({
                            'title': title,
                            'item_price': price_match.group(0),
                            'shipping': f"${shipping_val}" if shipping_val > 0 else 'Free',
                            'price_val': round(price_val + shipping_val, 2),
                            'sold_date': sold_date.strftime('%Y-%m-%d') if sold_date else None,
                            'days_ago': (datetime.now() - sold_date).days if sold_date else None,
                            'search_url': url
                        })
                        if len(sales) >= 50:
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if sales:
            fair_price, stats = calculate_fair_price(sales)
            return stats
        return None
    finally:
        driver.quit()

st.set_page_config(
    page_title="Southwest Sports Cards",
    page_icon="https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f3d2.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CUSTOM CSS - Modern dark theme
# ============================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Global */
    .stApp { background-color: #0a0e17; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Hide default Streamlit header/footer */
    #MainMenu, footer { visibility: hidden; }

    /* Hero header */
    .hero-header {
        background: linear-gradient(135deg, #1a1f35 0%, #0d1b2a 50%, #1b2838 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 1.5rem;
    }
    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: #f0f2f6;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.5px;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #8892a4;
        margin: 0;
        font-weight: 400;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(145deg, #141b2d 0%, #0f1623 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        text-align: center;
    }
    .metric-card.accent-green { border-left: 3px solid #00CC96; }
    .metric-card.accent-red { border-left: 3px solid #EF553B; }
    .metric-card.accent-blue { border-left: 3px solid #636EFA; }
    .metric-card.accent-gray { border-left: 3px solid #555; }
    .metric-card.accent-gold { border-left: 3px solid #f0b429; }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 500;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 0.4rem;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #f0f2f6;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #6b7280;
        margin-top: 0.2rem;
    }

    /* Trend cards */
    .trend-card {
        background: linear-gradient(145deg, #141b2d 0%, #0f1623 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        text-align: center;
    }
    .trend-card .trend-icon { font-size: 1.5rem; margin-bottom: 0.3rem; }
    .trend-card .trend-label {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.3rem;
    }
    .trend-card .trend-value {
        font-size: 1.3rem;
        font-weight: 700;
        color: #f0f2f6;
    }
    .trend-card .trend-count {
        font-size: 0.75rem;
        color: #6b7280;
        margin-top: 0.15rem;
    }
    .trend-up .trend-label { color: #00CC96; }
    .trend-down .trend-label { color: #EF553B; }
    .trend-stable .trend-label { color: #636EFA; }
    .trend-nodata .trend-label { color: #6b7280; }

    /* Section headers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #c9d1d9;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background-color: #141b2d;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #8892a4;
        font-weight: 500;
        font-size: 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e2a3a;
        color: #f0f2f6;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0d1117;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stSidebar"] .stMarkdown h2 {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8892a4;
        font-weight: 600;
    }

    /* Data editor */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
    }

    /* Buttons */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #00CC96 0%, #00a67d 100%);
        border: none;
        border-radius: 8px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }

    /* Clean up default metric styling */
    [data-testid="stMetric"] { display: none; }

    /* Plotly chart containers */
    .stPlotlyChart {
        border-radius: 12px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

TREND_COLORS = {"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA", "no data": "#555555"}
CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(20,27,45,0.8)",
    plot_bgcolor="rgba(15,22,35,0.9)",
    font=dict(family="Inter, sans-serif", color="#c9d1d9"),
    margin=dict(l=20, r=20, t=40, b=20),
    title_font=dict(size=14, color="#8892a4"),
)

MONEY_COLS = ['Fair Value', 'Median (All)', 'Min', 'Max']

def load_data():
    df = pd.read_csv(CSV_PATH)
    for col in MONEY_COLS:
        df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Num Sales'] = pd.to_numeric(df['Num Sales'], errors='coerce').fillna(0).astype(int)
    df['Trend'] = df['Trend'].replace({'insufficient data': 'no data', 'unknown': 'no data'})
    return df

def save_data(df):
    save_df = df.copy()
    for col in MONEY_COLS:
        save_df[col] = save_df[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "$0.00")
    save_df.to_csv(CSV_PATH, index=False)

# --- Load or initialize data ---
if 'df' not in st.session_state:
    st.session_state.df = load_data()
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

df = st.session_state.df

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("Filters")
min_sales = st.sidebar.slider("Minimum Sales Count", 0, max(int(df['Num Sales'].max()), 1), 0)
trend_options = sorted(df['Trend'].unique().tolist())
trend_filter = st.sidebar.multiselect("Trend Direction", options=trend_options, default=trend_options)

st.sidebar.divider()
st.sidebar.header("Scan Card")

front_img = st.sidebar.file_uploader("Front of card", type=["jpg", "jpeg", "png", "webp"], key="front_img")
back_img = st.sidebar.file_uploader("Back of card (optional)", type=["jpg", "jpeg", "png", "webp"], key="back_img")

if st.sidebar.button("Analyze Card", disabled=front_img is None):
    with st.sidebar:
        with st.spinner("Analyzing card with AI..."):
            front_bytes = front_img.getvalue()
            back_bytes = back_img.getvalue() if back_img else None
            card_info, error = analyze_card_images(front_bytes, back_bytes)

    if error:
        st.sidebar.error(f"Analysis failed: {error}")
    elif card_info:
        st.session_state.scanned_card = card_info
        confidence = card_info.get('confidence', 'unknown')
        if confidence == 'high':
            st.sidebar.success("Card identified with high confidence!")
        elif confidence == 'medium':
            st.sidebar.warning("Card identified - please verify the details below.")
        else:
            st.sidebar.warning("Low confidence - review and correct the fields below.")
        st.rerun()

# Pre-fill from scan if available
scanned = st.session_state.get('scanned_card', {})

st.sidebar.divider()
st.sidebar.header("Add New Card")

with st.sidebar.form("add_card_form", clear_on_submit=True):
    player_name = st.text_input("Player Name *", value=scanned.get('player_name', ''), placeholder="e.g. Connor McDavid")
    card_number = st.text_input("Card Number *", value=scanned.get('card_number', ''), placeholder="e.g. 201")
    card_set = st.text_input("Card Set *", value=scanned.get('card_set', ''), placeholder="e.g. Upper Deck Series 1 Young Guns")
    card_year = st.text_input("Year *", value=scanned.get('year', ''), placeholder="e.g. 2023-24")
    variant = st.text_input("Variant / Parallel", value=scanned.get('variant', ''), placeholder="e.g. Red Prism, Arctic Freeze (optional)")
    grade = st.text_input("Grade", value=scanned.get('grade', ''), placeholder="e.g. PSA 10 (optional)")
    scrape_prices = st.checkbox("Scrape eBay for prices", value=True)
    add_submitted = st.form_submit_button("Add Card")

if add_submitted:
    missing = []
    if not player_name.strip():
        missing.append("Player Name")
    if not card_number.strip():
        missing.append("Card Number")
    if not card_set.strip():
        missing.append("Card Set")
    if not card_year.strip():
        missing.append("Year")

    if missing:
        st.sidebar.error(f"Missing required fields: {', '.join(missing)}")
    else:
        card_name_parts = [f"{card_year.strip()} {card_set.strip()}"]
        if variant.strip():
            card_name_parts.append(variant.strip())
        card_name_parts.append(f"#{card_number.strip()} - {player_name.strip()}")
        if grade.strip():
            card_name_parts.append(f"[{grade.strip()}]")
        card_name = ' - '.join(card_name_parts)

        if scrape_prices:
            with st.sidebar:
                with st.spinner(f"Scraping eBay for {player_name.strip()}..."):
                    stats = scrape_single_card(card_name)

            if stats and stats.get('num_sales', 0) > 0:
                trend = stats['trend']
                if trend in ('insufficient data', 'unknown'):
                    trend = 'no data'
                new_row = pd.DataFrame([{
                    'Card Name': card_name,
                    'Fair Value': stats['fair_price'],
                    'Trend': trend,
                    'Top 3 Prices': ' | '.join(stats.get('top_3_prices', [])),
                    'Median (All)': stats['median_all'],
                    'Min': stats['min'],
                    'Max': stats['max'],
                    'Num Sales': stats['num_sales']
                }])
                st.sidebar.success(f"Found {stats['num_sales']} sales! Fair value: ${stats['fair_price']:.2f}")
            else:
                new_row = pd.DataFrame([{
                    'Card Name': card_name, 'Fair Value': DEFAULT_PRICE, 'Trend': 'no data',
                    'Top 3 Prices': '', 'Median (All)': DEFAULT_PRICE, 'Min': DEFAULT_PRICE, 'Max': DEFAULT_PRICE, 'Num Sales': 0
                }])
                st.sidebar.warning(f"No sales found. Defaulted to ${DEFAULT_PRICE:.2f}.")
        else:
            new_row = pd.DataFrame([{
                'Card Name': card_name, 'Fair Value': DEFAULT_PRICE, 'Trend': 'no data',
                'Top 3 Prices': '', 'Median (All)': DEFAULT_PRICE, 'Min': DEFAULT_PRICE, 'Max': DEFAULT_PRICE, 'Num Sales': 0
            }])

        st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
        save_data(st.session_state.df)
        st.session_state.df = load_data()
        st.session_state.pop('scanned_card', None)
        st.rerun()

# ============================================================
# Apply filters
# ============================================================
mask = (df['Num Sales'] >= min_sales) & (df['Trend'].isin(trend_filter))
filtered_df = df[mask].copy()

# ============================================================
# HERO HEADER
# ============================================================
found_df = df[df['Num Sales'] > 0]
not_found_df = df[df['Num Sales'] == 0]
total_value = found_df['Fair Value'].sum()
total_all = df['Fair Value'].sum()

st.markdown("""
<div class="hero-header">
    <p class="hero-title">Southwest Sports Cards</p>
    <p class="hero-subtitle">Collection Analytics & Price Tracking</p>
</div>
""", unsafe_allow_html=True)

# --- Top metrics row ---
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(f"""<div class="metric-card accent-blue">
        <div class="metric-label">Total Cards</div>
        <div class="metric-value">{len(df)}</div>
    </div>""", unsafe_allow_html=True)
with m2:
    st.markdown(f"""<div class="metric-card accent-green">
        <div class="metric-label">Cards with Data</div>
        <div class="metric-value">{len(found_df)}</div>
    </div>""", unsafe_allow_html=True)
with m3:
    st.markdown(f"""<div class="metric-card accent-red">
        <div class="metric-label">Not Found</div>
        <div class="metric-value">{len(not_found_df)}</div>
    </div>""", unsafe_allow_html=True)
with m4:
    st.markdown(f"""<div class="metric-card accent-gold">
        <div class="metric-label">Collection Value</div>
        <div class="metric-value">${total_value:,.2f}</div>
    </div>""", unsafe_allow_html=True)
with m5:
    st.markdown(f"""<div class="metric-card accent-gray">
        <div class="metric-label">Total (incl. defaults)</div>
        <div class="metric-value">${total_all:,.2f}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

# ============================================================
# TABS
# ============================================================
tab_charts, tab_table, tab_not_found = st.tabs(["Analytics", "Card Ledger", "Not Found"])

with tab_charts:
    # --- Trend cards ---
    st.markdown('<div class="section-header">Market Trends</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.columns(4)
    trend_config = [
        (t1, "up", "trend-up", "Trending Up"),
        (t2, "down", "trend-down", "Trending Down"),
        (t3, "stable", "trend-stable", "Stable"),
        (t4, "no data", "trend-nodata", "No Data"),
    ]
    for col_w, trend_key, css_class, label in trend_config:
        t_cards = filtered_df[filtered_df['Trend'] == trend_key]
        t_value = t_cards['Fair Value'].sum()
        pct = (len(t_cards) / len(filtered_df) * 100) if len(filtered_df) > 0 else 0
        with col_w:
            st.markdown(f"""<div class="trend-card {css_class}">
                <div class="trend-label">{label}</div>
                <div class="trend-value">${t_value:,.2f}</div>
                <div class="trend-count">{len(t_cards)} cards ({pct:.0f}%)</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # --- Charts row 1: Donut + Value bar ---
    c1, c2 = st.columns((1, 2))

    with c1:
        st.markdown('<div class="section-header">Value by Trend</div>', unsafe_allow_html=True)
        value_by_trend = filtered_df.groupby('Trend')['Fair Value'].sum().reset_index()
        fig_donut = px.pie(
            value_by_trend, names='Trend', values='Fair Value', color='Trend',
            color_discrete_map=TREND_COLORS, hole=0.55
        )
        fig_donut.update_traces(
            textinfo='percent+label', textposition='outside',
            textfont_size=11, pull=[0.02]*len(value_by_trend),
            marker=dict(line=dict(color='#0a0e17', width=2))
        )
        fig_donut.update_layout(**CHART_LAYOUT, height=380, showlegend=False)
        st.plotly_chart(fig_donut, use_container_width=True)

    with c2:
        st.markdown('<div class="section-header">Value Distribution</div>', unsafe_allow_html=True)
        trend_order = ['up', 'stable', 'down', 'no data']
        trend_agg = filtered_df.groupby('Trend').agg(
            Count=('Fair Value', 'count'),
            Total=('Fair Value', 'sum'),
            Avg=('Fair Value', 'mean')
        ).reindex(trend_order).dropna().reset_index()
        trend_agg['Avg'] = trend_agg['Avg'].round(2)

        fig_vbar = go.Figure()
        for _, row in trend_agg.iterrows():
            fig_vbar.add_trace(go.Bar(
                x=[row['Trend'].title()], y=[row['Total']],
                marker_color=TREND_COLORS.get(row['Trend'], '#555'),
                text=f"${row['Total']:,.0f}<br><span style='font-size:10px'>{int(row['Count'])} cards | avg ${row['Avg']:,.0f}</span>",
                textposition='outside',
                hovertemplate=f"<b>{row['Trend'].title()}</b><br>Total: ${row['Total']:,.2f}<br>Cards: {int(row['Count'])}<br>Avg: ${row['Avg']:,.2f}<extra></extra>",
                showlegend=False,
            ))
        fig_vbar.update_layout(**CHART_LAYOUT, height=380, yaxis_title="", xaxis_title="",
                                bargap=0.4, yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.04)'))
        st.plotly_chart(fig_vbar, use_container_width=True)

    # --- Charts row 2: Scatter ---
    st.markdown('<div class="section-header">Price vs. Sales Volume</div>', unsafe_allow_html=True)
    scatter_df = filtered_df[filtered_df['Num Sales'] > 0]
    if len(scatter_df) > 0:
        fig_scatter = px.scatter(
            scatter_df, x="Num Sales", y="Fair Value", color="Trend",
            hover_name="Card Name", size="Fair Value", size_max=25,
            color_discrete_map=TREND_COLORS,
        )
        fig_scatter.update_traces(marker=dict(line=dict(width=1, color='rgba(255,255,255,0.15)')))
        fig_scatter.update_layout(**CHART_LAYOUT, height=420,
                                   xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.04)'),
                                   yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.04)'),
                                   xaxis_title="Number of Sales", yaxis_title="Fair Value ($)")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- Charts row 3: Top 20 ---
    st.markdown('<div class="section-header">Top 20 Most Valuable Cards</div>', unsafe_allow_html=True)
    top20 = filtered_df.nlargest(20, 'Fair Value').copy()
    top20['Short Name'] = top20['Card Name'].apply(lambda x: x[:55] + '...' if len(x) > 55 else x)
    fig_bar = px.bar(
        top20, x='Fair Value', y='Short Name', orientation='h', color='Trend',
        color_discrete_map=TREND_COLORS,
        hover_data={'Card Name': True, 'Short Name': False}
    )
    fig_bar.update_traces(marker_line_width=0, texttemplate='$%{x:,.2f}', textposition='outside',
                          textfont_size=11)
    fig_bar.update_layout(**CHART_LAYOUT, height=650,
                           yaxis={'categoryorder': 'total ascending'},
                           xaxis_title="Fair Value ($)", yaxis_title="",
                           xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.04)'))
    st.plotly_chart(fig_bar, use_container_width=True)

# ============================================================
# EDITABLE TABLE
# ============================================================
with tab_table:
    st.markdown('<div class="section-header">Card Ledger</div>', unsafe_allow_html=True)

    search_query = st.text_input("Search cards", placeholder="Filter by name (e.g. Bedard, PSA 10, Young Guns)...",
                                  label_visibility="collapsed")

    display_cols = ['Card Name', 'Fair Value', 'Trend', 'Num Sales', 'Min', 'Max', 'Top 3 Prices']
    edit_df = filtered_df[display_cols].copy()

    if search_query.strip():
        terms = search_query.strip().lower().split()
        mask = edit_df['Card Name'].apply(
            lambda name: all(t in name.lower() for t in terms)
        )
        edit_df = edit_df[mask].copy()

    st.caption(f"Showing {len(edit_df)} cards")

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Card Name": st.column_config.TextColumn("Card Name", width="large"),
            "Fair Value": st.column_config.NumberColumn("Fair Value ($)", format="$%.2f", min_value=0),
            "Trend": st.column_config.SelectboxColumn("Trend", options=["up", "down", "stable", "no data"]),
            "Num Sales": st.column_config.NumberColumn("Sales", disabled=True),
            "Min": st.column_config.NumberColumn("Min ($)", format="$%.2f", disabled=True),
            "Max": st.column_config.NumberColumn("Max ($)", format="$%.2f", disabled=True),
            "Top 3 Prices": st.column_config.TextColumn("Top 3 Prices", disabled=True),
        },
        key="card_editor"
    )

    st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

    bcol1, bcol2, bcol3 = st.columns([1, 1, 4])
    with bcol1:
        if st.button("Save Changes", type="primary"):
            for i, row in edited.iterrows():
                idx = edit_df.index[i] if i < len(edit_df.index) else None
                if idx is not None and idx in st.session_state.df.index:
                    st.session_state.df.at[idx, 'Fair Value'] = row['Fair Value']
                    st.session_state.df.at[idx, 'Trend'] = row['Trend']
                    st.session_state.df.at[idx, 'Card Name'] = row['Card Name']
            if len(edited) > len(edit_df):
                for i in range(len(edit_df), len(edited)):
                    new_row = {
                        'Card Name': edited.iloc[i]['Card Name'],
                        'Fair Value': edited.iloc[i]['Fair Value'],
                        'Trend': edited.iloc[i]['Trend'],
                        'Top 3 Prices': '',
                        'Median (All)': edited.iloc[i]['Fair Value'],
                        'Min': edited.iloc[i]['Fair Value'],
                        'Max': edited.iloc[i]['Fair Value'],
                        'Num Sales': 0
                    }
                    st.session_state.df = pd.concat(
                        [st.session_state.df, pd.DataFrame([new_row])], ignore_index=True
                    )
            if len(edited) < len(edit_df):
                edited_names = set(edited['Card Name'].tolist())
                filtered_names = set(edit_df['Card Name'].tolist())
                removed = filtered_names - edited_names
                if removed:
                    st.session_state.df = st.session_state.df[
                        ~st.session_state.df['Card Name'].isin(removed)
                    ].reset_index(drop=True)

            save_data(st.session_state.df)
            st.success("Saved to CSV!")
            st.rerun()

    with bcol2:
        if st.button("Reload from File"):
            st.session_state.df = load_data()
            st.rerun()

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # Summary row
    edited_total = edited['Fair Value'].sum()
    edited_found = edited[edited['Num Sales'] > 0]['Fair Value'].sum()
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(f"""<div class="metric-card accent-gold">
            <div class="metric-label">Filtered Total</div>
            <div class="metric-value">${edited_total:,.2f}</div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown(f"""<div class="metric-card accent-green">
            <div class="metric-label">Found Cards Total</div>
            <div class="metric-value">${edited_found:,.2f}</div>
        </div>""", unsafe_allow_html=True)
    with s3:
        st.markdown(f"""<div class="metric-card accent-blue">
            <div class="metric-label">Cards Shown</div>
            <div class="metric-value">{len(edited)}</div>
        </div>""", unsafe_allow_html=True)

# ============================================================
# NOT FOUND
# ============================================================
with tab_not_found:
    st.markdown(f'<div class="section-header">Cards Not Found ({len(not_found_df)} cards, defaulted to ${DEFAULT_PRICE:.2f})</div>',
                unsafe_allow_html=True)
    if len(not_found_df) > 0:
        st.dataframe(
            not_found_df[['Card Name', 'Fair Value']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Card Name": st.column_config.TextColumn("Card Name", width="large"),
                "Fair Value": st.column_config.NumberColumn("Default Value", format="$%.2f"),
            }
        )
    else:
        st.info("All cards have sales data!")
