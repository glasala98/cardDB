import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import base64
import json
import re
from datetime import datetime
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "card_prices_summary.csv")

# Import scraper functions
sys.path.insert(0, SCRIPT_DIR)
from scrape_card_prices import (
    create_driver, search_ebay_sold, calculate_fair_price,
    build_simplified_query, get_grade_info, title_matches_grade
)

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

st.set_page_config(
    page_title="Card Collection Dashboard",
    page_icon="hockey",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; padding: 15px; border-radius: 5px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
""", unsafe_allow_html=True)

MONEY_COLS = ['Fair Value', 'Median (All)', 'Min', 'Max']

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
    "confidence": "high, medium, or low",
    "is_sports_card": true,
    "validation_reason": "Explain why this is or isn't a valid sports card"
}

Be precise. If the image is not a sports card, set "is_sports_card" to false and explain why in "validation_reason".
If you can't determine a field, use your best guess based on card design, logos, and text visible."""
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

# --- Load or initialize data in session state ---
if 'df' not in st.session_state:
    st.session_state.df = load_data()
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

df = st.session_state.df

# ============================================================
# SIDEBAR - Filters & Add Card
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
        is_valid = card_info.get("is_sports_card", True)
        validation_reason = card_info.get("validation_reason", "Image does not appear to be a valid sports card.")

        if not is_valid:
            st.sidebar.error(f"Invalid Card: {validation_reason}")
        else:
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
                    'Card Name': card_name, 'Fair Value': 5.0, 'Trend': 'no data',
                    'Top 3 Prices': '', 'Median (All)': 5.0, 'Min': 5.0, 'Max': 5.0, 'Num Sales': 0
                }])
                st.sidebar.warning("No sales found. Defaulted to $5.00.")
        else:
            new_row = pd.DataFrame([{
                'Card Name': card_name, 'Fair Value': 5.0, 'Trend': 'no data',
                'Top 3 Prices': '', 'Median (All)': 5.0, 'Min': 5.0, 'Max': 5.0, 'Num Sales': 0
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
# HEADER & METRICS
# ============================================================
st.title("Hockey Card Collection Dashboard")

found_df = df[df['Num Sales'] > 0]
not_found_df = df[df['Num Sales'] == 0]
total_value = found_df['Fair Value'].sum()
total_all = df['Fair Value'].sum()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Cards", len(df))
with col2:
    st.metric("Cards with Data", len(found_df))
with col3:
    st.metric("Not Found", len(not_found_df))
with col4:
    st.metric("Collection Value", f"${total_value:,.2f}")
with col5:
    st.metric("Total (incl. defaults)", f"${total_all:,.2f}")

st.divider()

# ============================================================
# CHARTS
# ============================================================
tab_charts, tab_table, tab_not_found = st.tabs(["Charts", "Card Ledger (Editable)", "Not Found Cards"])

with tab_charts:
    c1, c2 = st.columns((2, 1))

    with c1:
        st.subheader("Price vs. Volume")
        fig_scatter = px.scatter(
            filtered_df,
            x="Num Sales", y="Fair Value", color="Trend",
            hover_name="Card Name", size="Fair Value",
            color_discrete_map={"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA",
                                "no data": "gray"},
            title="Fair Value by Sales Volume"
        )
        fig_scatter.update_layout(template="plotly_dark", height=420)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with c2:
        st.subheader("Trend Breakdown")
        fig_pie = px.pie(
            filtered_df, names='Trend', title="Trend Share", color='Trend',
            color_discrete_map={"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA",
                                "no data": "gray"},
            hole=0.4
        )
        fig_pie.update_layout(template="plotly_dark", height=420)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Top 20 bar chart
    st.subheader("Top 20 Most Valuable Cards")
    top20 = filtered_df.nlargest(20, 'Fair Value').copy()
    top20['Short Name'] = top20['Card Name'].apply(
        lambda x: x[:60] + '...' if len(x) > 60 else x
    )
    fig_bar = px.bar(
        top20, x='Fair Value', y='Short Name', orientation='h', color='Trend',
        color_discrete_map={"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA",
                            "unknown": "gray", "insufficient data": "#FFA15A"},
        hover_data={'Card Name': True, 'Short Name': False}
    )
    fig_bar.update_layout(template="plotly_dark", height=600, yaxis={'categoryorder': 'total ascending'})
    fig_bar.update_xaxes(title="Fair Value ($)")
    fig_bar.update_yaxes(title="")
    st.plotly_chart(fig_bar, use_container_width=True)

# ============================================================
# EDITABLE TABLE
# ============================================================
with tab_table:
    st.subheader("Edit Card Values")

    search_query = st.text_input("Search cards", placeholder="Type to filter by card name (e.g. Bedard, PSA 10, Young Guns)...")

    display_cols = ['Card Name', 'Fair Value', 'Trend', 'Num Sales', 'Min', 'Max', 'Top 3 Prices']
    edit_df = filtered_df[display_cols].copy()

    if search_query.strip():
        terms = search_query.strip().lower().split()
        mask = edit_df['Card Name'].apply(
            lambda name: all(t in name.lower() for t in terms)
        )
        edit_df = edit_df[mask].copy()

    st.caption(f"Showing {len(edit_df)} cards. Edit Fair Value or Trend directly in the table.")

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

    st.divider()
    edited_total = edited['Fair Value'].sum()
    edited_found = edited[edited['Num Sales'] > 0]['Fair Value'].sum()
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        st.metric("Filtered Total", f"${edited_total:,.2f}")
    with tc2:
        st.metric("Found Cards Total", f"${edited_found:,.2f}")
    with tc3:
        st.metric("Cards Shown", len(edited))

# ============================================================
# NOT FOUND LIST
# ============================================================
with tab_not_found:
    st.subheader(f"Cards Not Found ({len(not_found_df)} cards, defaulted to $5.00)")
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
