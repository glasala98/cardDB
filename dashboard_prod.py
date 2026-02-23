import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import subprocess
from datetime import datetime

# Import utils
try:
    from dashboard_utils import (
        analyze_card_images, scrape_single_card, load_data, save_data, backup_data,
        parse_card_name, load_sales_history, append_price_history, load_price_history,
        append_portfolio_snapshot, load_portfolio_history, scrape_graded_comparison,
        archive_card, load_archive, restore_card,
        get_user_paths, load_users, verify_password, init_user_data,
        load_master_db, save_master_db,
        load_yg_price_history, load_yg_portfolio_history, load_yg_raw_sales, load_yg_market_timeline,
        load_nhl_player_stats, load_nhl_standings, get_player_stats_for_card,
        get_player_bio_for_card, get_all_player_bios,
        load_correlation_history, CANADIAN_TEAM_ABBREVS,
        TEAM_ABBREV_TO_NAME,
        get_market_alerts, get_card_of_the_day,
        compute_team_multipliers, compute_impact_scores,
        CSV_PATH, MONEY_COLS, PARSED_COLS
    )
except ImportError:
    st.error("dashboard_utils.py not found. Please ensure it exists in the same directory.")
    st.stop()

st.set_page_config(
    page_title="Card Collection Dashboard",
    page_icon="hockey",
    layout="wide",
    initial_sidebar_state="collapsed"
)


def _trend_badge(trend):
    """Return HTML for a colored trend badge."""
    t = trend.lower().strip() if isinstance(trend, str) else 'no data'
    cls = {'up': 'up', 'down': 'down', 'stable': 'stable'}.get(t, 'nodata')
    label = {'up': 'Trending Up', 'down': 'Trending Down', 'stable': 'Stable'}.get(t, 'No Data')
    return f'<span class="trend-badge {cls}">{label}</span>'


def _tier_badge(value):
    """Return HTML for a gold/silver/bronze value tier badge."""
    if value >= 100:
        return '<span class="tier-badge gold">GOLD</span>'
    elif value >= 25:
        return '<span class="tier-badge silver">SILVER</span>'
    elif value >= 5:
        return '<span class="tier-badge bronze">BRONZE</span>'
    return ''


def _mover_html(player, card_set, current, pct, is_gainer=True):
    """Return HTML for a styled mover item."""
    cls = 'gainer' if is_gainer else 'loser'
    pcls = 'positive' if is_gainer else 'negative'
    sign = '+' if pct >= 0 else ''
    return f'''<div class="mover-item {cls}">
        <div><div class="player-name">{player}</div><div class="set-name">{card_set[:35]}</div></div>
        <div class="price-change {pcls}">${current:.2f} <span style="font-size:0.8rem">({sign}{pct:.1f}%)</span></div>
    </div>'''


def _recent_html(player, value, trend, scraped_date):
    """Return HTML for a styled recently scraped item."""
    badge = _trend_badge(trend)
    return f'''<div class="recent-item">
        <div><span class="player-name">{player}</span> {badge}</div>
        <div><span class="price-tag">${value:.2f}</span> <span class="scraped-date">{scraped_date}</span></div>
    </div>'''

st.markdown("""
<style>
    /* ============================================
       GLOBAL THEME & CARD-STYLE METRICS
       ============================================ */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: rgba(0,0,0,0);}

    /* Metric card styling */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-left: 3px solid #636EFA;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem;
        font-weight: 700;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        opacity: 0.7;
    }

    /* Styled containers */
    div[data-testid="stExpander"] {
        border: 1px solid #333;
        border-radius: 8px;
        background: #1a1a2e;
    }

    /* Divider accent */
    hr { border-color: #636EFA !important; opacity: 0.3; }

    /* Button polish */
    button[kind="primary"] {
        background-color: #636EFA !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }
    button[kind="primary"]:hover { background-color: #4f5bd5 !important; }
    button[kind="secondary"] {
        border: 1px solid #636EFA !important;
        border-radius: 6px !important;
    }

    /* Sidebar navigation pills */
    div[data-testid="stSidebar"] div[role="radiogroup"] label {
        border-radius: 20px !important;
        padding: 6px 16px !important;
        margin: 2px 0 !important;
        transition: background 0.2s;
    }
    div[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background: rgba(99, 110, 250, 0.15);
    }

    /* Data table polish */
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

    /* Alert banners */
    div[data-testid="stAlert"] { border-radius: 8px !important; font-size: 0.9rem; }

    /* ============================================
       STYLED HTML CARDS & SECTIONS
       ============================================ */
    .section-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #2a2a4a;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .section-card h3 {
        margin-top: 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }
    /* Mover item rows */
    .mover-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        background: rgba(255,255,255,0.03);
        border-left: 3px solid transparent;
    }
    .mover-item.gainer { border-left-color: #00CC96; }
    .mover-item.loser { border-left-color: #EF553B; }
    .mover-item .player-name {
        font-weight: 600;
        font-size: 0.95rem;
    }
    .mover-item .set-name {
        font-size: 0.8rem;
        opacity: 0.6;
    }
    .mover-item .price-change {
        text-align: right;
        font-weight: 700;
    }
    .mover-item .price-change.positive { color: #00CC96; }
    .mover-item .price-change.negative { color: #EF553B; }

    /* Recent card items */
    .recent-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        background: rgba(255,255,255,0.03);
        border-left: 3px solid #636EFA;
    }
    .recent-item .player-name { font-weight: 600; }
    .recent-item .scraped-date { font-size: 0.8rem; opacity: 0.5; }
    .recent-item .price-tag { font-weight: 700; color: #636EFA; }

    /* Trend badges */
    .trend-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .trend-badge.up { background: rgba(0,204,150,0.15); color: #00CC96; }
    .trend-badge.down { background: rgba(239,85,59,0.15); color: #EF553B; }
    .trend-badge.stable { background: rgba(99,110,250,0.15); color: #636EFA; }
    .trend-badge.nodata { background: rgba(128,128,128,0.15); color: #888; }

    /* Value tier badges */
    .tier-badge {
        display: inline-block;
        padding: 3px 12px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .tier-badge.gold { background: linear-gradient(135deg, #b8860b, #ffd700); color: #1a1a2e; }
    .tier-badge.silver { background: linear-gradient(135deg, #808080, #c0c0c0); color: #1a1a2e; }
    .tier-badge.bronze { background: linear-gradient(135deg, #8b4513, #cd7f32); color: #1a1a2e; }

    /* Section headers with icon */
    .section-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        font-size: 1.1rem;
        font-weight: 600;
    }
    .section-header .icon {
        font-size: 1.3rem;
    }

    /* ============================================
       MOBILE RESPONSIVE (< 768px)
       ============================================ */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: 45% !important;
            flex: 1 1 45% !important;
        }
        div[data-testid="stMetricValue"] { font-size: 1.1rem; }
        div[data-testid="stMetricLabel"] { font-size: 0.7rem; }
        div[data-testid="stMetric"] { padding: 8px 12px; }
        button { width: 100% !important; }
        .main .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
        }
        h1 { font-size: 1.5rem !important; }
        h2, .stSubheader { font-size: 1.2rem !important; }
        div[data-testid="stDataFrame"] {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        div[data-testid="stDownloadButton"] button { width: 100% !important; }
    }

    /* TABLET (768px - 1024px) */
    @media (min-width: 769px) and (max-width: 1024px) {
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: 30% !important;
        }
        .main .block-container {
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    }

    /* SMALL PHONE (< 480px) */
    @media (max-width: 480px) {
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        div[data-testid="stMetricValue"] { font-size: 1rem; }
        h1 { font-size: 1.3rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# PUBLIC PROFILE CHECK (before auth)
# ============================================================
public_view = False
query_params = st.query_params
if 'user' in query_params:
    pub_username = query_params['user']
    users_config = load_users()
    if pub_username not in users_config:
        st.error("User not found.")
        st.stop()
    if not users_config[pub_username].get('public', False):
        st.error("This profile is private.")
        st.stop()
    public_view = True
    st.session_state.public_view = True
    st.session_state.username = pub_username
    st.session_state.display_name = users_config[pub_username].get('display_name', pub_username)
    user_paths = get_user_paths(pub_username)
    st.session_state.user_paths = user_paths

# ============================================================
# LOGIN GATE (Young Guns DB is public, other pages require auth)
# ============================================================
_needs_auth = False
if not public_view:
    users_config = load_users()

    if not st.session_state.get("authenticated"):
        # Show sidebar nav so users can access Young Guns DB without login
        _selected_page = st.sidebar.radio("Navigate", ["Young Guns DB", "Login"], key="_nav_preauth")

        if _selected_page == "Login":
            # If no users.yaml exists or is empty, fall back to env var password
            if not users_config:
                correct_pw = os.environ.get("DASHBOARD_PASSWORD", "")
                if correct_pw:
                    st.markdown("<div style='max-width:400px;margin:3rem auto;'>", unsafe_allow_html=True)
                    st.markdown("## Card Collection Dashboard")
                    password = st.text_input("Enter password to access the dashboard", type="password")
                    if st.button("Login", type="primary"):
                        if password == correct_pw:
                            st.session_state.authenticated = True
                            st.rerun()
                        else:
                            st.error("Incorrect password")
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.stop()
            else:
                st.markdown("<div style='max-width:400px;margin:3rem auto;'>", unsafe_allow_html=True)
                st.markdown("## Card Collection Dashboard")
                st.caption("Sign in to manage your collection")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.button("Login", type="primary", use_container_width=True):
                    if verify_password(username, password):
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.session_state.display_name = users_config[username].get('display_name', username)
                        st.session_state.pop('df', None)
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                st.markdown("</div>", unsafe_allow_html=True)
                st.stop()
        else:
            # Young Guns DB selected without auth — mark as public-like access
            _needs_auth = False
    else:
        _needs_auth = False

# ============================================================
# USER PATHS SETUP
# ============================================================
username = st.session_state.get('username', '')
if username and load_users():
    user_paths = get_user_paths(username)
    st.session_state.user_paths = user_paths
    init_user_data(user_paths['csv'])
    _csv_path = user_paths['csv']
    _results_path = user_paths['results']
    _history_path = user_paths['history']
    _portfolio_path = user_paths['portfolio']
    _archive_path = user_paths['archive']
    _backup_dir = user_paths['backup_dir']
else:
    # Legacy single-user mode (no users.yaml)
    _csv_path = CSV_PATH
    _results_path = None  # use defaults
    _history_path = None
    _portfolio_path = None
    _archive_path = None
    _backup_dir = None

# --- Load or initialize data in session state ---
if 'df' not in st.session_state:
    st.session_state.df = load_data(_csv_path, _results_path)
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

df = st.session_state.df

# ============================================================
# SIDEBAR - Navigation + Conditional Scan/Add Card
# ============================================================
# Show user info and logout in sidebar
display_name = st.session_state.get('display_name', '')
if display_name:
    st.sidebar.caption(f"Logged in as **{display_name}**")
if not public_view and st.session_state.get('authenticated') and load_users():
    if st.sidebar.button("Logout"):
        for key in ['authenticated', 'username', 'display_name', 'df', 'user_paths',
                     'inspect_card', 'pending_remove', 'scanned_card', 'public_view']:
            st.session_state.pop(key, None)
        st.rerun()

# Check for programmatic navigation (e.g. from View Card button)
_is_authenticated = st.session_state.get('authenticated', False)
if not _is_authenticated and not public_view:
    # Unauthenticated — only Young Guns DB is accessible (nav already shown in pre-auth block)
    page = "Young Guns DB"
else:
    if public_view:
        nav_pages = ["Young Guns DB", "Dashboard", "Charts", "Card Inspect"]
    else:
        nav_pages = ["Young Guns DB", "Dashboard", "Charts", "Card Ledger", "Card Inspect"]
    if 'nav_page' in st.session_state and st.session_state.nav_page in nav_pages:
        st.session_state['_nav_radio'] = st.session_state.nav_page
        del st.session_state.nav_page

    page = st.sidebar.radio("Navigate", nav_pages, key="_nav_radio")

# Site Guide
st.sidebar.divider()
with st.sidebar.expander("Site Guide", expanded=False):
    st.markdown("""
**Young Guns DB**
Browse 500+ Young Guns cards with daily-updated prices. Click any row to see full card detail: price history, NHL stats, trajectory chart, and ownership tracking. Filter by season, team, or price tier. Scroll down for analytics: Grading ROI, Player Compare, and Correlation Analytics.

**Dashboard**
Personal collection overview with total value, P&L summary, and portfolio value chart over time. Requires login.

**Charts**
Visual breakdowns of your personal collection: value distribution, trend analysis, and grading insights.

**Card Ledger**
Full editable table of your personal cards. Add new cards via the sidebar card scanner or manual entry. Track cost basis and tags.

**Card Inspect**
Deep-dive into any single card: price history chart, raw eBay sales data, and graded price comparisons.

---

**Inside Young Guns DB:**

*Correlation Analytics* — 9 tabs analyzing NHL performance vs card prices: regression scatter, price tiers, teams, positions, value finder (over/undervalued), goalies, nationality, draft position, and historical trends.

*Player Compare* — Pick two players for side-by-side stats comparison, price history overlay chart, and graded value comparison.

*Cost Basis / P&L* — Click a card and check "I own this" to track your cost basis and see profit/loss. Works in both YG DB and personal collection.

*Sidebar Scanner* — Upload a photo of your card to auto-identify it (Card Ledger page only).
""")

# Show Scan Card and Add New Card only on Card Ledger page (not in public view)
if page == "Card Ledger" and not public_view:
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

    # Accordion for Add New Card (progressive disclosure)
    with st.sidebar.expander("Add New Card", expanded=bool(scanned)):
        with st.form("add_card_form", clear_on_submit=True):
            player_name = st.text_input("Player Name *", value=scanned.get('player_name', ''), placeholder="e.g. Connor McDavid")
            card_number = st.text_input("Card Number *", value=scanned.get('card_number', ''), placeholder="e.g. 201")
            card_set = st.text_input("Card Set *", value=scanned.get('card_set', ''), placeholder="e.g. Upper Deck Series 1 Young Guns")
            card_year = st.text_input("Year *", value=scanned.get('year', ''), placeholder="e.g. 2023-24")
            variant = st.text_input("Subset / Variant", value=scanned.get('variant', ''), placeholder="e.g. Young Guns, Marquee Rookie, Violet Pixel")
            serial = st.text_input("Serial #", placeholder="e.g. 70/99, 1/250 (optional)")
            grade = st.text_input("Grade", value=scanned.get('grade', ''), placeholder="e.g. PSA 10 (optional)")
            cost_basis = st.number_input("Cost Basis ($)", min_value=0.0, step=0.01, value=0.0, help="What you paid (optional)")
            purchase_date = st.date_input("Purchase Date", value=None, help="When you bought it (optional)")
            scrape_prices = st.checkbox("Scrape eBay for prices", value=True)
            add_submitted = st.form_submit_button("Add Card")

    if page == "Card Ledger" and add_submitted:
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
            player_part = f"#{card_number.strip()} - {player_name.strip()}"
            if serial.strip():
                player_part += f" #{serial.strip()}"
            card_name_parts.append(player_part)
            if grade.strip():
                card_name_parts.append(f"[{grade.strip()}]")
            card_name = ' - '.join(card_name_parts)

            if scrape_prices:
                with st.sidebar:
                    with st.spinner(f"Scraping eBay for {player_name.strip()}..."):
                        stats = scrape_single_card(card_name, results_json_path=_results_path)

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
                        'Num Sales': stats['num_sales'],
                        'Cost Basis': cost_basis if cost_basis > 0 else None,
                        'Purchase Date': purchase_date.strftime('%Y-%m-%d') if purchase_date else '',
                    }])
                    append_price_history(card_name, stats['fair_price'], stats['num_sales'], history_path=_history_path)
                    st.sidebar.success(f"Found {stats['num_sales']} sales! Fair value: ${stats['fair_price']:.2f}")
                else:
                    new_row = pd.DataFrame([{
                        'Card Name': card_name, 'Fair Value': 5.0, 'Trend': 'no data',
                        'Top 3 Prices': '', 'Median (All)': 5.0, 'Min': 5.0, 'Max': 5.0, 'Num Sales': 0,
                        'Cost Basis': cost_basis if cost_basis > 0 else None,
                        'Purchase Date': purchase_date.strftime('%Y-%m-%d') if purchase_date else '',
                    }])
                    st.sidebar.warning("No sales found. Defaulted to $5.00.")
            else:
                new_row = pd.DataFrame([{
                    'Card Name': card_name, 'Fair Value': 5.0, 'Trend': 'no data',
                    'Top 3 Prices': '', 'Median (All)': 5.0, 'Min': 5.0, 'Max': 5.0, 'Num Sales': 0,
                    'Cost Basis': cost_basis if cost_basis > 0 else None,
                    'Purchase Date': purchase_date.strftime('%Y-%m-%d') if purchase_date else '',
                }])

            st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
            save_data(st.session_state.df, _csv_path)
            st.session_state.df = load_data(_csv_path, _results_path)
            st.session_state.pop('scanned_card', None)
            st.rerun()

    # Batch Upload CSV
    st.sidebar.divider()
    with st.sidebar.expander("Bulk Upload CSV"):
        st.caption("Upload a CSV with columns: Card Name, Fair Value, Trend, Num Sales, Min, Max, Top 3 Prices, Median (All)")
        bulk_file = st.file_uploader("Choose CSV file", type=["csv"], key="bulk_csv")
        if bulk_file is not None:
            if st.button("Import Cards"):
                try:
                    import_df = pd.read_csv(bulk_file)
                    required_cols = ['Card Name']
                    if not all(c in import_df.columns for c in required_cols):
                        st.sidebar.error("CSV must have at least a 'Card Name' column")
                    else:
                        for col in ['Fair Value', 'Median (All)', 'Min', 'Max']:
                            if col in import_df.columns:
                                import_df[col] = import_df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
                                import_df[col] = pd.to_numeric(import_df[col], errors='coerce').fillna(5.0)
                            else:
                                import_df[col] = 5.0
                        if 'Num Sales' not in import_df.columns:
                            import_df['Num Sales'] = 0
                        if 'Trend' not in import_df.columns:
                            import_df['Trend'] = 'no data'
                        if 'Top 3 Prices' not in import_df.columns:
                            import_df['Top 3 Prices'] = ''
                        st.session_state.df = pd.concat([st.session_state.df, import_df], ignore_index=True)
                        save_data(st.session_state.df, _csv_path)
                        st.session_state.df = load_data(_csv_path, _results_path)
                        st.sidebar.success(f"Imported {len(import_df)} cards!")
                        st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Import failed: {e}")

# ============================================================
# HEADER & METRICS
# ============================================================
if page == "Young Guns DB":
    st.title("Young Guns Master Database")
else:
    title = display_name if display_name else "Hockey Card Collection Dashboard"
    if public_view:
        title = f"{display_name}'s Collection" if display_name else "Public Collection"
    st.title(title)

    found_df = df[df['Num Sales'] > 0]
    not_found_df = df[df['Num Sales'] == 0]
    total_value = found_df['Fair Value'].sum()
    total_all = df['Fair Value'].sum()

    # Last Updated timestamp
    last_modified = ""
    try:
        mtime = os.path.getmtime(_csv_path)
        last_modified = datetime.fromtimestamp(mtime).strftime('%b %d, %Y %I:%M %p')
    except OSError:
        last_modified = "Unknown"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Cards", len(df))
    with col2:
        st.metric("Cards with Data", len(found_df))
    with col3:
        st.metric("Not Found", len(not_found_df))
    col4, col5 = st.columns(2)
    with col4:
        st.metric("Collection Value", f"${total_value:,.2f}")
    with col5:
        st.metric("Total (incl. defaults)", f"${total_all:,.2f}")

    st.caption(f"Data last updated: {last_modified}")
    st.divider()

# ============================================================
# DASHBOARD PAGE
# ============================================================
if page == "Dashboard":
    st.markdown('<div class="section-header"><span class="icon">&#x1F3C6;</span> Collection Overview</div>', unsafe_allow_html=True)

    # Quick stats
    total_cards = len(df)
    found_df = df[df['Num Sales'] > 0]
    total_value = found_df['Fair Value'].sum()
    avg_value = total_value / len(found_df) if len(found_df) > 0 else 0
    cards_up = len(df[df['Trend'] == 'up'])
    cards_down = len(df[df['Trend'] == 'down'])

    dc1, dc2, dc3 = st.columns(3)
    dc1.metric("Total Cards", total_cards)
    dc2.metric("Collection Value", f"${total_value:,.2f}")
    dc3.metric("Avg Card Value", f"${avg_value:,.2f}")
    dc4, dc5 = st.columns(2)
    dc4.metric("Trending Up", cards_up)
    dc5.metric("Trending Down", cards_down)

    # Portfolio P&L (if any cards have cost basis)
    if 'Cost Basis' in df.columns:
        invested_df = df[df['Cost Basis'].notna() & (df['Cost Basis'] > 0)]
        if len(invested_df) > 0:
            total_cost_basis = invested_df['Cost Basis'].sum()
            total_current = invested_df['Fair Value'].sum()
            total_pnl = total_current - total_cost_basis
            pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
            st.markdown("---")
            st.markdown("**Portfolio P&L**")
            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Invested", f"${total_cost_basis:,.2f}")
            pc2.metric("Current Value", f"${total_current:,.2f}")
            pc3.metric("Unrealized P&L", f"${total_pnl:+,.2f}", delta=f"{pnl_pct:+.1f}%")
            pc4.metric("Cards Tracked", len(invested_df))

    st.markdown("---")

    # Top Movers — cards with biggest value changes
    movers = []
    for _, row in df.iterrows():
        history = load_price_history(row['Card Name'], history_path=_history_path)
        if len(history) >= 2:
            curr = history[-1]['fair_value']
            prev = history[-2]['fair_value']
            change = curr - prev
            movers.append({
                'Player': row['Player'],
                'Set': row['Set'],
                'Current': curr,
                'Change': change,
                'Pct': (change / prev * 100) if prev > 0 else 0,
            })

    left_col, right_col = st.columns(2)

    with left_col:
        gainers_html = '<div class="section-card"><div class="section-header"><span class="icon">&#x25B2;</span> Top Gainers</div>'
        if movers:
            gainers = sorted([m for m in movers if m['Change'] > 0], key=lambda x: x['Change'], reverse=True)[:5]
            if gainers:
                for g in gainers:
                    gainers_html += _mover_html(g['Player'], g['Set'], g['Current'], g['Pct'], is_gainer=True)
            else:
                gainers_html += '<p style="opacity:0.5;font-size:0.85rem;">No gainers yet.</p>'
        else:
            gainers_html += '<p style="opacity:0.5;font-size:0.85rem;">Need 2+ scrapes for mover data.</p>'
        gainers_html += '</div>'
        st.markdown(gainers_html, unsafe_allow_html=True)

    with right_col:
        losers_html = '<div class="section-card"><div class="section-header"><span class="icon">&#x25BC;</span> Top Losers</div>'
        if movers:
            losers = sorted([m for m in movers if m['Change'] < 0], key=lambda x: x['Change'])[:5]
            if losers:
                for l in losers:
                    losers_html += _mover_html(l['Player'], l['Set'], l['Current'], l['Pct'], is_gainer=False)
            else:
                losers_html += '<p style="opacity:0.5;font-size:0.85rem;">No losers yet.</p>'
        else:
            losers_html += '<p style="opacity:0.5;font-size:0.85rem;">Need 2+ scrapes for mover data.</p>'
        losers_html += '</div>'
        st.markdown(losers_html, unsafe_allow_html=True)

    st.markdown("---")

    # Recently Scraped
    recent_html = '<div class="section-card"><div class="section-header"><span class="icon">&#x1F4C5;</span> Recently Scraped</div>'
    if 'Last Scraped' in df.columns:
        recent = df[df['Last Scraped'] != ''].sort_values('Last Scraped', ascending=False).head(5)
        if len(recent) > 0:
            for _, row in recent.iterrows():
                recent_html += _recent_html(row['Player'], row['Fair Value'], row['Trend'], row['Last Scraped'])
        else:
            recent_html += '<p style="opacity:0.5;font-size:0.85rem;">No scrape data yet.</p>'
    else:
        recent_html += '<p style="opacity:0.5;font-size:0.85rem;">No scrape data yet.</p>'
    recent_html += '</div>'
    st.markdown(recent_html, unsafe_allow_html=True)

    # Portfolio mini-chart
    portfolio_history = load_portfolio_history(_portfolio_path)
    if portfolio_history and len(portfolio_history) >= 2:
        st.markdown("---")
        st.subheader("Portfolio Trend")
        port_df = pd.DataFrame(portfolio_history)
        port_df['date'] = pd.to_datetime(port_df['date'])
        port_df = port_df.sort_values('date')
        fig_mini = px.line(port_df, x='date', y='total_value', markers=True,
                           labels={'date': 'Date', 'total_value': 'Value ($)'})
        fig_mini.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig_mini, use_container_width=True)

# ============================================================
# CHARTS PAGE
# ============================================================
elif page == "Charts":
    c1, c2 = st.columns((2, 1))

    with c1:
        st.subheader("Price vs. Volume")
        fig_scatter = px.scatter(
            df,
            x="Num Sales", y="Fair Value", color="Trend",
            hover_name="Card Name", size="Fair Value",
            color_discrete_map={"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA",
                                "no data": "gray"},
            title="Fair Value by Sales Volume"
        )
        # Annotate the highest value card
        if len(df) > 0:
            top_card = df.loc[df['Fair Value'].idxmax()]
            fig_scatter.add_annotation(
                x=top_card['Num Sales'], y=top_card['Fair Value'],
                text=top_card['Card Name'][:40],
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                ax=40, ay=-40,
                font=dict(size=10, color="white"),
                bgcolor="rgba(0,0,0,0.6)", borderpad=4
            )
        fig_scatter.update_layout(template="plotly_dark", height=420)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with c2:
        st.subheader("Trend Breakdown")
        fig_pie = px.pie(
            df, names='Trend', title="Trend Share", color='Trend',
            color_discrete_map={"up": "#00CC96", "down": "#EF553B", "stable": "#636EFA",
                                "no data": "gray"},
            hole=0.4
        )
        fig_pie.update_layout(template="plotly_dark", height=420)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Top 20 bar chart
    st.subheader("Top 20 Most Valuable Cards")
    top20 = df.nlargest(20, 'Fair Value').copy()
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

    # Portfolio Value Over Time
    st.divider()
    st.markdown('<div class="section-header"><span class="icon">&#x1F4CA;</span> Portfolio Value Over Time</div>', unsafe_allow_html=True)
    portfolio_history = load_portfolio_history(_portfolio_path)

    if portfolio_history and len(portfolio_history) >= 2:
        port_df = pd.DataFrame(portfolio_history)
        port_df['date'] = pd.to_datetime(port_df['date'])
        port_df = port_df.sort_values('date')

        latest = port_df.iloc[-1]
        previous = port_df.iloc[-2]
        value_change = latest['total_value'] - previous['total_value']

        # Find 7-day-ago snapshot
        seven_ago = port_df[port_df['date'] <= (pd.Timestamp.now() - pd.Timedelta(days=7))]
        weekly_change = (latest['total_value'] - seven_ago.iloc[-1]['total_value']) if len(seven_ago) > 0 else None

        pc1, pc2 = st.columns(2)
        pc1.metric("Current Value", f"${latest['total_value']:,.2f}",
                    delta=f"${value_change:+,.2f}")
        pc2.metric("Total Cards", int(latest['total_cards']))
        pc3, pc4 = st.columns(2)
        pc3.metric("Avg Card Value", f"${latest['avg_value']:,.2f}")
        if weekly_change is not None:
            pc4.metric("7-Day Change", f"${weekly_change:+,.2f}")
        else:
            pc4.metric("7-Day Change", "N/A")

        fig_port = px.line(
            port_df, x='date', y='total_value',
            markers=True, title="Collection Value Over Time",
            labels={'date': 'Date', 'total_value': 'Total Value ($)'}
        )
        fig_port.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_port, use_container_width=True)
    elif portfolio_history and len(portfolio_history) == 1:
        st.info("Portfolio tracking started. Chart appears after the next daily scrape.")
    else:
        st.caption("No portfolio history yet. Snapshots are recorded during the daily scrape.")

# ============================================================
# CARD LEDGER PAGE
# ============================================================
elif page == "Card Ledger":
    st.markdown('<div class="section-header"><span class="icon">&#x1F4DD;</span> Card Ledger</div>', unsafe_allow_html=True)

    # Collection summary metrics
    total_cards = len(df)
    total_value = df['Fair Value'].sum()
    avg_value = df['Fair Value'].mean() if total_cards > 0 else 0
    top_card_idx = df['Fair Value'].idxmax() if total_cards > 0 else None
    top_card_name = parse_card_name(df.at[top_card_idx, 'Card Name'])['Player'] if top_card_idx is not None else "N/A"
    top_card_val = df.at[top_card_idx, 'Fair Value'] if top_card_idx is not None else 0

    mcol1, mcol2 = st.columns(2)
    mcol1.metric("Total Cards", total_cards)
    mcol2.metric("Collection Value", f"${total_value:,.2f}")
    mcol3, mcol4 = st.columns(2)
    mcol3.metric("Avg Card Value", f"${avg_value:,.2f}")
    mcol4.metric("Most Valuable", f"{top_card_name}", delta=f"${top_card_val:,.2f}")

    # Export button
    export_cols = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade', 'Tags',
                   'Fair Value', 'Trend', 'Num Sales', 'Min', 'Max']
    export_df = df[[c for c in export_cols if c in df.columns]].copy()
    csv_bytes = export_df.to_csv(index=False).encode('utf-8')
    export_name = display_name.replace(' ', '_') if display_name else 'collection'
    st.download_button(
        "Export Collection CSV",
        data=csv_bytes,
        file_name=f"{export_name}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

    st.markdown("---")

    # Search bar (full width)
    search_query = st.text_input("Search cards", placeholder="Search by player, set, year, card number...")

    # Filter row (2x2 for mobile)
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        sets = sorted(df['Set'].dropna().unique().tolist())
        sets = [s for s in sets if s]
        set_filter = st.selectbox("Set", ["All Sets"] + sets)
    with fcol2:
        trend_options = sorted(df['Trend'].unique().tolist())
        trend_filter = st.multiselect("Trend", options=trend_options, default=trend_options)
    fcol3, fcol4 = st.columns(2)
    with fcol3:
        grade_filter = st.selectbox("Grade", ["All", "Raw", "Graded"])
    with fcol4:
        all_tags = sorted(set(t.strip() for tags in df['Tags'].dropna() for t in tags.split(',') if t.strip()))
        tag_filter = st.selectbox("Tag", ["All Tags"] + all_tags)

    # Price range filter
    _min_price = float(df['Fair Value'].min()) if len(df) > 0 else 0.0
    _max_price = float(df['Fair Value'].max()) if len(df) > 0 else 1000.0
    price_range = st.slider(
        "Price Range ($)",
        min_value=_min_price,
        max_value=_max_price,
        value=(_min_price, _max_price),
        format="$%.2f"
    )

    # Apply filters
    mask = df['Trend'].isin(trend_filter)
    if set_filter != "All Sets":
        mask &= df['Set'] == set_filter
    if grade_filter == "Raw":
        mask &= df['Grade'] == ''
    elif grade_filter == "Graded":
        mask &= df['Grade'] != ''
    if tag_filter != "All Tags":
        mask &= df['Tags'].str.contains(tag_filter, case=False, na=False)
    mask &= (df['Fair Value'] >= price_range[0]) & (df['Fair Value'] <= price_range[1])
    filtered_df = df[mask].copy()

    display_cols = ['Player', 'Set', 'Subset', 'Card #', 'Serial', 'Grade', 'Tags', 'Fair Value', 'Cost Basis', 'Trend', 'Num Sales', 'Min', 'Max', 'Top 3 Prices', 'Last Scraped']
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    edit_df = filtered_df[display_cols].copy()
    edit_df['Top 3 Prices'] = edit_df['Top 3 Prices'].fillna('')
    edit_df['Last Scraped'] = edit_df['Last Scraped'].fillna('')
    edit_df['Tags'] = edit_df['Tags'].fillna('')

    if search_query.strip():
        terms = search_query.strip().lower().split()
        searchable = filtered_df['Card Name'].str.lower()
        mask = searchable.apply(lambda name: all(t in name for t in terms))
        edit_df = edit_df[mask].copy()

    # Add View and Remove checkbox columns
    edit_df['View'] = False
    edit_df['Remove'] = False

    # Color-code the Trend column
    trend_map = {'up': '🟢 up', 'down': '🔴 down', 'stable': '⚪ stable', 'no data': '⚫ no data'}
    edit_df['Trend'] = edit_df['Trend'].map(trend_map).fillna('⚫ no data')

    # Reorder: card description → sales/value → actions
    col_order = ['View', 'Player', 'Set', 'Subset', 'Card #', 'Serial', 'Grade',
                 'Tags', 'Num Sales', 'Fair Value', 'Min', 'Max', 'Trend',
                 'Top 3 Prices', 'Last Scraped', 'Remove']
    col_order = [c for c in col_order if c in edit_df.columns]
    edit_df = edit_df[col_order]

    st.caption(f"Showing {len(edit_df)} of {len(df)} cards")

    editor_key = f"ledger_editor_{st.session_state.get('editor_reset', 0)}"
    edited = st.data_editor(
        edit_df,
        key=editor_key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Player": st.column_config.TextColumn("Player", width="medium"),
            "Set": st.column_config.TextColumn("Set", width="medium", disabled=True),
            "Subset": st.column_config.TextColumn("Subset", width="medium", disabled=True),
            "Card #": st.column_config.TextColumn("#", width="small", disabled=True),
            "Serial": st.column_config.TextColumn("Serial", width="small", disabled=True),
            "Grade": st.column_config.TextColumn("Grade", width="small", disabled=True),
            "Tags": st.column_config.TextColumn("Tags", width="medium"),
            "Num Sales": st.column_config.NumberColumn("Sales", disabled=True),
            "Fair Value": st.column_config.NumberColumn("Fair Value ($)", format="$%.2f", min_value=0),
            "Min": st.column_config.NumberColumn("Min ($)", format="$%.2f", disabled=True),
            "Max": st.column_config.NumberColumn("Max ($)", format="$%.2f", disabled=True),
            "Trend": st.column_config.TextColumn("Trend", disabled=True),
            "Top 3 Prices": st.column_config.TextColumn("Top 3 Prices", disabled=True),
            "Last Scraped": st.column_config.TextColumn("Last Scraped", disabled=True),
            "View": st.column_config.CheckboxColumn("View", width="small", default=False),
            "Remove": st.column_config.CheckboxColumn("Remove", width="small", default=False),
        },
    )

    # Auto-navigate to Card Inspect when a View checkbox is checked
    viewed_rows = edited[edited['View'] == True]
    if len(viewed_rows) > 0:
        viewed_idx = viewed_rows.index[0]
        if viewed_idx in edit_df.index and viewed_idx in filtered_df.index:
            card_name = filtered_df.at[viewed_idx, 'Card Name']
            st.session_state.inspect_card = card_name
            st.session_state.nav_page = "Card Inspect"
            st.rerun()

    # Handle Remove checkbox — stage card for deletion confirmation
    removed_rows = edited[edited['Remove'] == True]
    if len(removed_rows) > 0:
        removed_idx = removed_rows.index[0]
        if removed_idx in edit_df.index and removed_idx in filtered_df.index:
            st.session_state.pending_remove = filtered_df.at[removed_idx, 'Card Name']

    # Confirmation dialog for pending removal
    if st.session_state.get('pending_remove'):
        card_to_remove = st.session_state.pending_remove
        parsed = parse_card_name(card_to_remove)
        st.warning(f"Are you sure you want to archive **{parsed['Player']}** ({parsed['Set']} {parsed['Subset']})? This card will be moved to the archive.")
        rc1, rc2, rc3 = st.columns([1, 1, 4])
        with rc1:
            if st.button("Yes, Archive", type="primary"):
                st.session_state.df = archive_card(st.session_state.df, card_to_remove, archive_path=_archive_path)
                save_data(st.session_state.df, _csv_path)
                st.session_state.df = load_data(_csv_path, _results_path)
                del st.session_state.pending_remove
                st.success(f"Card archived.")
                st.rerun()
        with rc2:
            if st.button("Cancel"):
                del st.session_state.pending_remove
                st.session_state.editor_reset = st.session_state.get('editor_reset', 0) + 1
                st.rerun()

    bcol1, bcol2, bcol3 = st.columns([1, 1, 1])
    with bcol1:
        if st.button("Save Changes", type="primary"):
            for i, row in edited.iterrows():
                idx = edit_df.index[i] if i < len(edit_df.index) else None
                if idx is not None and idx in st.session_state.df.index:
                    st.session_state.df.at[idx, 'Fair Value'] = row['Fair Value']
                    # Strip emoji prefix from trend before saving
                    raw_trend = row['Trend'].split(' ', 1)[-1] if isinstance(row['Trend'], str) else row['Trend']
                    st.session_state.df.at[idx, 'Trend'] = raw_trend
                    st.session_state.df.at[idx, 'Tags'] = row.get('Tags', '')
                    if row['Player'] != edit_df.at[idx, 'Player']:
                        old_player = edit_df.at[idx, 'Player']
                        new_player = row['Player']
                        old_card_name = st.session_state.df.at[idx, 'Card Name']
                        if old_player and old_player in old_card_name:
                            st.session_state.df.at[idx, 'Card Name'] = old_card_name.replace(old_player, new_player)
                        st.session_state.df.at[idx, 'Player'] = new_player
            if len(edited) > len(edit_df):
                for i in range(len(edit_df), len(edited)):
                    r = edited.iloc[i]
                    card_name = r.get('Player', 'Unknown')
                    raw_t = r['Trend'].split(' ', 1)[-1] if isinstance(r.get('Trend'), str) else 'no data'
                    new_row = {
                        'Card Name': card_name,
                        'Fair Value': r['Fair Value'],
                        'Trend': raw_t,
                        'Top 3 Prices': '',
                        'Median (All)': r['Fair Value'],
                        'Min': r['Fair Value'],
                        'Max': r['Fair Value'],
                        'Num Sales': 0,
                        'Tags': r.get('Tags', '')
                    }
                    parsed = parse_card_name(card_name)
                    new_row.update(parsed)
                    st.session_state.df = pd.concat(
                        [st.session_state.df, pd.DataFrame([new_row])], ignore_index=True
                    )
            if len(edited) < len(edit_df):
                edited_players = set(edited['Player'].tolist())
                filtered_players = set(edit_df['Player'].tolist())
                removed = filtered_players - edited_players
                if removed:
                    st.session_state.df = st.session_state.df[
                        ~st.session_state.df['Player'].isin(removed)
                    ].reset_index(drop=True)

            save_data(st.session_state.df, _csv_path)
            st.success("Saved to CSV!")
            st.rerun()

    with bcol2:
        if st.button("Reload from File"):
            st.session_state.df = load_data(_csv_path, _results_path)
            st.rerun()

    with bcol3:
        card_count = len(st.session_state.df) if 'df' in st.session_state else 0
        if not public_view and st.button(f"Rescrape All ({card_count} cards)", type="secondary"):
            backup_data(label="rescrape_all", csv_path=_csv_path, results_path=_results_path, backup_dir=_backup_dir)
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_scrape.py")
            with st.spinner(f"Scraping all {card_count} cards from eBay — this may take several minutes..."):
                try:
                    result = subprocess.run(
                        [sys.executable, script_path, "--workers", "5"],
                        capture_output=True, text=True, timeout=1800
                    )
                    st.session_state.df = load_data(_csv_path, _results_path)
                    if result.returncode == 0:
                        st.success("All cards rescrapped! Prices updated.")
                    else:
                        st.warning(f"Scrape finished with warnings. Check logs.")
                        if result.stderr:
                            with st.expander("Scrape output"):
                                st.code(result.stderr[-3000:])
                except subprocess.TimeoutExpired:
                    st.error("Scrape timed out after 30 minutes.")
                except Exception as e:
                    st.error(f"Scrape failed: {e}")
            st.rerun()

    # Rescrape action (uses the View checkbox to identify selected card)
    st.caption("Check the **View** box on a row to inspect it. Use Rescrape on the Card Inspect page.")

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

    # Not Found section
    st.divider()
    st.subheader(f"Cards Not Found ({len(not_found_df)} cards, defaulted to $5.00)")
    if len(not_found_df) > 0:
        nf_display = not_found_df[['Player', 'Set', 'Subset', 'Card #', 'Serial', 'Fair Value']].reset_index(drop=True)
        edited_nf = st.data_editor(
            nf_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Player": st.column_config.TextColumn("Player", width="medium", disabled=True),
                "Set": st.column_config.TextColumn("Set", width="medium", disabled=True),
                "Card #": st.column_config.TextColumn("#", width="small", disabled=True),
                "Fair Value": st.column_config.NumberColumn("Manual Price ($)", format="$%.2f", min_value=0),
            },
            key="not_found_editor"
        )
        if st.button("Save Not Found Prices", type="primary"):
            nf_card_names = not_found_df['Card Name'].tolist()
            for i, row in edited_nf.iterrows():
                if i < len(nf_card_names):
                    mask = st.session_state.df['Card Name'] == nf_card_names[i]
                    if mask.any():
                        st.session_state.df.loc[mask, 'Fair Value'] = row['Fair Value']
                        st.session_state.df.loc[mask, 'Median (All)'] = row['Fair Value']
                        st.session_state.df.loc[mask, 'Min'] = row['Fair Value']
                        st.session_state.df.loc[mask, 'Max'] = row['Fair Value']
            save_data(st.session_state.df, _csv_path)
            st.success("Not Found prices saved!")
            st.rerun()
    else:
        st.info("All cards have sales data!")

    # Archived Cards section
    st.divider()
    archive_df = load_archive(archive_path=_archive_path)
    with st.expander(f"Archived Cards ({len(archive_df)})", expanded=False):
        if len(archive_df) > 0:
            st.dataframe(
                archive_df[['Card Name', 'Fair Value', 'Num Sales', 'Archived Date']].reset_index(drop=True)
                if 'Archived Date' in archive_df.columns
                else archive_df[['Card Name', 'Fair Value', 'Num Sales']].reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )
            restore_options = archive_df['Card Name'].tolist()
            restore_pick = st.selectbox("Select card to restore", [""] + restore_options,
                                        format_func=lambda x: "Choose a card..." if x == "" else x[:60],
                                        key="restore_pick")
            if st.button("Restore Card", disabled=restore_pick == ""):
                card_data = restore_card(restore_pick, archive_path=_archive_path)
                if card_data:
                    card_data.pop('Archived Date', None)
                    for col in MONEY_COLS:
                        if col in card_data:
                            val = str(card_data[col]).replace('$', '').replace(',', '')
                            card_data[col] = float(val) if val else 0.0
                    new_row = pd.DataFrame([card_data])
                    st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
                    save_data(st.session_state.df, _csv_path)
                    st.session_state.df = load_data(_csv_path, _results_path)
                    st.success(f"Restored: {restore_pick[:60]}")
                    st.rerun()
        else:
            st.caption("No archived cards.")

# ============================================================
# CARD INSPECT PAGE
# ============================================================
elif page == "Card Inspect":
    st.subheader("Card Inspect")

    # Pre-select from session state if navigated from ledger
    preselected = st.session_state.get('inspect_card', '')

    # Search bar to find a card
    inspect_search = st.text_input(
        "Search for a card",
        placeholder="Type player name, set, year...",
        key="inspect_search"
    )

    selected_card = preselected  # default to pre-selected card

    if inspect_search.strip():
        terms = inspect_search.strip().lower().split()
        matches = df[df['Card Name'].str.lower().apply(lambda name: all(t in name for t in terms))]
        if len(matches) > 0:
            # Show compact results list as buttons
            st.caption(f"{len(matches)} match{'es' if len(matches) != 1 else ''} found")
            for _, row in matches.head(10).iterrows():
                label = f"{row['Player']} — {row['Set']}"
                if row['Subset']:
                    label += f" {row['Subset']}"
                if row['Card #']:
                    label += f" #{row['Card #']}"
                if row['Grade']:
                    label += f" [{row['Grade']}]"
                if st.button(label, key=f"pick_{row['Card Name']}"):
                    st.session_state.inspect_card = row['Card Name']
                    st.rerun()
            if len(matches) > 10:
                st.caption(f"...and {len(matches) - 10} more. Narrow your search.")
        else:
            st.warning("No cards match your search.")

    if not selected_card:
        st.info("Use the **View** checkbox on the Card Ledger, or search above to find a card.")
    else:
        card_row = df[df['Card Name'] == selected_card].iloc[0]

        # Card details
        st.markdown("---")
        dc1, dc2 = st.columns(2)
        with dc1:
            st.metric("Player", card_row['Player'])
        with dc2:
            st.metric("Set", card_row['Set'] if card_row['Set'] else "N/A")
        dc3, dc4, dc5 = st.columns(3)
        with dc3:
            st.metric("Subset", card_row['Subset'] if card_row['Subset'] else "Base")
        with dc4:
            st.metric("Card #", card_row['Card #'] if card_row['Card #'] else "N/A")
        with dc5:
            st.metric("Serial / Grade",
                       f"{card_row['Serial'] if card_row['Serial'] else 'N/A'} | {card_row['Grade'] if card_row['Grade'] else 'Raw'}")

        # Value and trend with visual badges
        tier = _tier_badge(card_row['Fair Value'])
        trend = _trend_badge(card_row['Trend'])
        st.markdown(f'<div style="margin: 8px 0 16px 0;">{tier} {trend}</div>', unsafe_allow_html=True)

        vc1, vc2, vc3 = st.columns(3)
        with vc1:
            st.metric("Fair Value", f"${card_row['Fair Value']:.2f}")
        with vc2:
            st.metric("Sales Found", int(card_row['Num Sales']))
        with vc3:
            st.metric("Range", f"${card_row['Min']:.2f} — ${card_row['Max']:.2f}")

        # Rescrape button (hidden in public view)
        if not public_view and st.button("Rescrape Price", type="primary"):
            backup_data(label="rescrape", csv_path=_csv_path, results_path=_results_path, backup_dir=_backup_dir)
            with st.spinner(f"Scraping eBay for updated price..."):
                stats = scrape_single_card(selected_card, results_json_path=_results_path)
            if stats and stats.get('num_sales', 0) > 0:
                idx = st.session_state.df[st.session_state.df['Card Name'] == selected_card].index
                if len(idx) > 0:
                    i = idx[0]
                    trend = stats['trend']
                    if trend in ('insufficient data', 'unknown'):
                        trend = 'no data'
                    st.session_state.df.at[i, 'Fair Value'] = stats['fair_price']
                    st.session_state.df.at[i, 'Trend'] = trend
                    st.session_state.df.at[i, 'Median (All)'] = stats['median_all']
                    st.session_state.df.at[i, 'Min'] = stats['min']
                    st.session_state.df.at[i, 'Max'] = stats['max']
                    st.session_state.df.at[i, 'Num Sales'] = stats['num_sales']
                    st.session_state.df.at[i, 'Top 3 Prices'] = ' | '.join(stats.get('top_3_prices', []))
                    save_data(st.session_state.df, _csv_path)
                    append_price_history(selected_card, stats['fair_price'], stats['num_sales'], history_path=_history_path)
                    st.success(f"Updated! Fair value: ${stats['fair_price']:.2f} ({stats['num_sales']} sales)")
                    st.rerun()
            else:
                st.warning("No sales found for this card.")

        # Fair Value Over Time (from price_history.json)
        st.markdown("---")
        st.markdown('<div class="section-header"><span class="icon">&#x1F4C8;</span> Fair Value Tracking</div>', unsafe_allow_html=True)
        history = load_price_history(selected_card, history_path=_history_path)

        if history:
            hist_df = pd.DataFrame(history)
            hist_df['date'] = pd.to_datetime(hist_df['date'])
            hist_df = hist_df.sort_values('date')

            # Delta metrics when 2+ data points
            if len(hist_df) >= 2:
                latest_val = hist_df.iloc[-1]['fair_value']
                prev_val = hist_df.iloc[-2]['fair_value']
                change = latest_val - prev_val
                pct = (change / prev_val * 100) if prev_val > 0 else 0
                hc1, hc2, hc3 = st.columns(3)
                hc1.metric("Current", f"${latest_val:.2f}", delta=f"${change:+.2f}")
                hc2.metric("Change", f"{pct:+.1f}%")
                hc3.metric("Data Points", len(hist_df))

            # Dual-axis chart: fair value line + sales count bars
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Scatter(
                x=hist_df['date'], y=hist_df['fair_value'],
                mode='lines+markers', name='Fair Value',
                line=dict(color='#636EFA', width=2),
                hovertemplate='$%{y:.2f}<extra>Fair Value</extra>'
            ))
            if 'num_sales' in hist_df.columns:
                fig_hist.add_trace(go.Bar(
                    x=hist_df['date'], y=hist_df['num_sales'],
                    name='Sales Count', yaxis='y2',
                    marker_color='rgba(99, 110, 250, 0.3)',
                    hovertemplate='%{y} sales<extra>Sales Count</extra>'
                ))
            fig_hist.update_layout(
                template="plotly_dark", height=350,
                title="Fair Value Over Time",
                xaxis_title="Scrape Date",
                yaxis=dict(title="Fair Value ($)", side="left"),
                yaxis2=dict(title="Sales Count", side="right", overlaying="y", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.caption("No price history yet. Fair value tracking begins when you rescrape a card.")

        # Grading ROI Calculator
        if not public_view:
            st.markdown("---")
            st.markdown('<div class="section-header"><span class="icon">&#x1F4B0;</span> Grading ROI Calculator</div>', unsafe_allow_html=True)
            if not card_row['Grade']:
                gc1, gc2 = st.columns(2)
                with gc1:
                    grading_cost = st.number_input(
                        "Grading Cost ($)", min_value=10.0, max_value=200.0,
                        value=30.0, step=5.0, key="grading_cost"
                    )
                with gc2:
                    shipping_cost = st.number_input(
                        "Shipping Cost ($)", min_value=0.0, max_value=50.0,
                        value=10.0, step=2.5, key="shipping_cost"
                    )
                total_grading_cost = grading_cost + shipping_cost

                if st.button("Calculate Grading ROI", type="secondary"):
                    with st.spinner("Scraping raw & graded prices from eBay (~30s)..."):
                        comparison = scrape_graded_comparison(selected_card)

                    if comparison:
                        raw = comparison.get('raw')
                        psa9 = comparison.get('psa_9')
                        psa10 = comparison.get('psa_10')

                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            if raw:
                                st.metric("Raw Price", f"${raw['fair_price']:.2f}",
                                         help=f"{raw['num_sales']} sales found")
                            else:
                                st.metric("Raw Price", "No data")

                        with rc2:
                            if psa9 and raw:
                                roi_9 = psa9['fair_price'] - raw['fair_price'] - total_grading_cost
                                st.metric("PSA 9 Price", f"${psa9['fair_price']:.2f}",
                                         delta=f"ROI: ${roi_9:+,.2f}",
                                         help=f"{psa9['num_sales']} sales found")
                            elif psa9:
                                st.metric("PSA 9 Price", f"${psa9['fair_price']:.2f}")
                            else:
                                st.metric("PSA 9 Price", "No data")

                        with rc3:
                            if psa10 and raw:
                                roi_10 = psa10['fair_price'] - raw['fair_price'] - total_grading_cost
                                st.metric("PSA 10 Price", f"${psa10['fair_price']:.2f}",
                                         delta=f"ROI: ${roi_10:+,.2f}",
                                         help=f"{psa10['num_sales']} sales found")
                            elif psa10:
                                st.metric("PSA 10 Price", f"${psa10['fair_price']:.2f}")
                            else:
                                st.metric("PSA 10 Price", "No data")

                        # Summary recommendation
                        best_roi = None
                        if psa10 and raw:
                            best_roi = psa10['fair_price'] - raw['fair_price'] - total_grading_cost
                        elif psa9 and raw:
                            best_roi = psa9['fair_price'] - raw['fair_price'] - total_grading_cost

                        if best_roi is not None:
                            if best_roi > 20:
                                st.success(f"Worth grading! Best ROI is ${best_roi:,.2f} after ${total_grading_cost:.0f} grading costs.")
                            elif best_roi > 0:
                                st.info(f"Marginal gain. Best ROI is ${best_roi:,.2f} -- may be worth it for high-grade candidates.")
                            else:
                                st.warning(f"Not profitable. Best ROI is ${best_roi:,.2f} after ${total_grading_cost:.0f} grading costs.")
                    else:
                        st.error("Could not retrieve comparison data.")
            else:
                st.caption(f"This card is already graded: **{card_row['Grade']}**")

        # eBay Sales History
        st.markdown("---")
        st.markdown('<div class="section-header"><span class="icon">&#x1F6D2;</span> eBay Sales History</div>', unsafe_allow_html=True)
        sales = load_sales_history(selected_card, results_json_path=_results_path)

        if sales:
            # Build dataframe from raw sales
            sales_df = pd.DataFrame(sales)
            sales_df['sold_date'] = pd.to_datetime(sales_df['sold_date'], errors='coerce')

            # Prepare display table — make listing title a clickable link
            if 'listing_url' not in sales_df.columns:
                sales_df['listing_url'] = ''
            display_sales = sales_df[['sold_date', 'title', 'listing_url', 'item_price', 'shipping', 'price_val']].copy()
            display_sales.columns = ['Date', 'Listing Title', 'Listing URL', 'Item Price', 'Shipping', 'Total']
            display_sales = display_sales.sort_values('Date', ascending=False).reset_index(drop=True)
            display_sales['Date'] = display_sales['Date'].dt.strftime('%Y-%m-%d').fillna('Unknown')
            display_sales['Listing Title'] = display_sales['Listing Title'].str.replace(
                r'\nOpens in a new window or tab', '', regex=True
            ).str[:80]
            display_sales['Listing URL'] = display_sales['Listing URL'].fillna('')

            # Mark expired links (eBay removes sold listings after ~90 days)
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            display_sales['Listing'] = display_sales.apply(
                lambda r: r['Listing URL'] if r['Listing URL'] and r['Date'] >= cutoff
                else '' if not r['Listing URL']
                else r['Listing URL'],
                axis=1
            )
            display_sales['Status'] = display_sales.apply(
                lambda r: '' if not r['Listing URL']
                else 'Expired' if r['Date'] < cutoff and r['Date'] != 'Unknown'
                else '',
                axis=1
            )
            display_sales = display_sales.drop(columns=['Listing URL'])

            sale_config = {
                "Total": st.column_config.NumberColumn("Total ($)", format="$%.2f"),
                "Listing": st.column_config.LinkColumn("Listing", display_text="View"),
            }

            # Show last 5 sales
            st.caption(f"Last 5 of {len(display_sales)} sales")
            st.dataframe(
                display_sales.head(5),
                use_container_width=True,
                hide_index=True,
                column_config=sale_config,
            )

            # Full history in expander
            if len(display_sales) > 5:
                with st.expander(f"View all {len(display_sales)} sales"):
                    st.dataframe(
                        display_sales,
                        use_container_width=True,
                        hide_index=True,
                        column_config=sale_config,
                    )
        else:
            st.info("No eBay sales history available. Rescrape to populate data.")

# ============================================================
# MASTER DB PAGE
# ============================================================
elif page == "Young Guns DB":

    master_df = load_master_db()

    if master_df.empty:
        st.warning("No master database found. Upload a CSV to get started.")
    else:
        # Check if price data exists
        has_prices = 'FairValue' in master_df.columns and master_df['FairValue'].notna().any()
        total_value = master_df['FairValue'].sum() if has_prices else 0

        # ── Market Alerts Banner ──
        _yg_ph = load_yg_price_history()
        _alerts = get_market_alerts(_yg_ph, top_n=5) if _yg_ph else []

        if _alerts:
            gainers = [a for a in _alerts if a['direction'] == 'up'][:3]
            losers = [a for a in _alerts if a['direction'] == 'down'][:3]
            alert_html = '<div style="display:flex;gap:10px;overflow-x:auto;padding:6px 0;margin-bottom:8px;">'
            for a in gainers:
                # Parse player name from card_name
                parts = a['card_name'].split(' - ')
                pname = parts[-1] if len(parts) >= 3 else a['card_name']
                alert_html += (
                    f'<div style="background:linear-gradient(135deg,#0a2e0a,#1a4d1a);border:1px solid #2d7a2d;'
                    f'border-radius:8px;padding:8px 14px;min-width:180px;flex-shrink:0;">'
                    f'<div style="color:#5fdd5f;font-size:0.75rem;font-weight:600;">{pname}</div>'
                    f'<div style="color:#4ade80;font-size:1.1rem;font-weight:700;">+{a["pct_change"]}%</div>'
                    f'<div style="color:#888;font-size:0.7rem;">${a["old_price"]:.2f} &rarr; ${a["new_price"]:.2f}</div>'
                    f'</div>'
                )
            for a in losers:
                parts = a['card_name'].split(' - ')
                pname = parts[-1] if len(parts) >= 3 else a['card_name']
                alert_html += (
                    f'<div style="background:linear-gradient(135deg,#2e0a0a,#4d1a1a);border:1px solid #7a2d2d;'
                    f'border-radius:8px;padding:8px 14px;min-width:180px;flex-shrink:0;">'
                    f'<div style="color:#dd5f5f;font-size:0.75rem;font-weight:600;">{pname}</div>'
                    f'<div style="color:#f87171;font-size:1.1rem;font-weight:700;">{a["pct_change"]}%</div>'
                    f'<div style="color:#888;font-size:0.7rem;">${a["old_price"]:.2f} &rarr; ${a["new_price"]:.2f}</div>'
                    f'</div>'
                )
            alert_html += '</div>'
            st.markdown(alert_html, unsafe_allow_html=True)

        # ── Card of the Day ──
        _nhl_data_cotd = load_nhl_player_stats()
        _nhl_players_cotd = _nhl_data_cotd.get('players', {}) if _nhl_data_cotd else {}
        _corr_hist = load_correlation_history()
        _latest_corr_snap = _corr_hist.get(max(_corr_hist.keys()), {}) if _corr_hist else {}
        _cotd = get_card_of_the_day(master_df, _nhl_players_cotd, _yg_ph, _latest_corr_snap)

        if _cotd:
            _cotd_stats = _cotd.get('stats', {})
            _cotd_stat_line = ''
            if _cotd_stats:
                if 'points' in _cotd_stats:
                    _cotd_stat_line = f"{_cotd_stats.get('goals', 0)}G {_cotd_stats.get('assists', 0)}A {_cotd_stats.get('points', 0)}P in {_cotd_stats.get('games_played', 0)}GP"
                elif 'wins' in _cotd_stats:
                    _cotd_stat_line = f"{_cotd_stats.get('wins', 0)}W {_cotd_stats.get('losses', 0)}L {_cotd_stats.get('save_pct', 0):.3f}SV%"

            _cotd_pct_html = ''
            if _cotd['pct_change'] > 0:
                _cotd_pct_html = f'<span style="color:#4ade80;font-weight:700;margin-left:8px;">+{_cotd["pct_change"]}%</span>'

            st.markdown(
                f'<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #0f3460;'
                f'border-radius:10px;padding:12px 18px;margin-bottom:10px;">'
                f'<div style="color:#a78bfa;font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Card of the Day</div>'
                f'<div style="display:flex;align-items:center;gap:12px;margin-top:4px;">'
                f'<div style="font-size:1.15rem;font-weight:700;color:#e2e8f0;">{_cotd["player"]}'
                f'{_cotd_pct_html}</div>'
                f'<div style="color:#94a3b8;font-size:0.85rem;">{_cotd["team"]}</div>'
                f'<div style="color:#38bdf8;font-size:0.95rem;font-weight:600;">${_cotd["price"]:.2f}</div>'
                f'</div>'
                f'<div style="color:#64748b;font-size:0.75rem;margin-top:2px;">'
                f'{_cotd_stat_line} &mdash; {_cotd["reason"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Search + filters in one line
        seasons = sorted(master_df['Season'].unique().tolist(), reverse=True)
        teams = sorted([t for t in master_df['Team'].unique().tolist() if t])

        sf1, sf2, sf3, sf4 = st.columns([3, 1, 1, 1])
        with sf1:
            master_search = st.text_input("Search", placeholder="Search by player, team, season...", key="master_search", label_visibility="collapsed")
        with sf2:
            season_filter = st.selectbox("Season", ["All Seasons"] + seasons, key="master_season", label_visibility="collapsed")
        with sf3:
            team_filter = st.selectbox("Team", ["All Teams"] + teams, key="master_team", label_visibility="collapsed")
        with sf4:
            owned_only = st.checkbox("My Cards", key="owned_filter")
        # Unused filters — keep defaults
        positions = sorted([p for p in master_df['Position'].unique().tolist() if p])
        pos_filter = "All Positions"
        set_filter_master = "All Sets"
        set_names = sorted([s for s in master_df['Set'].unique().tolist() if s])

        # Apply filters
        filtered = master_df.copy()
        if season_filter != "All Seasons":
            filtered = filtered[filtered['Season'] == season_filter]
        if team_filter != "All Teams":
            filtered = filtered[filtered['Team'] == team_filter]
        if positions and pos_filter != "All Positions":
            filtered = filtered[filtered['Position'] == pos_filter]
        if set_filter_master != "All Sets":
            filtered = filtered[filtered['Set'] == set_filter_master]
        if master_search.strip():
            terms = master_search.strip().lower().split()
            searchable = (filtered['PlayerName'].fillna('') + ' ' + filtered['Team'].fillna('') + ' ' + filtered['Season'].fillna('')).str.lower()
            search_mask = searchable.apply(lambda x: all(t in x for t in terms))
            filtered = filtered[search_mask]
        if owned_only:
            filtered = filtered[filtered['Owned'] == 1]

        # Portfolio summary for owned cards
        if owned_only and len(filtered) > 0:
            _owned_invested = filtered['CostBasis'].sum()
            _owned_fair = filtered[filtered['FairValue'].notna() & (filtered['FairValue'] > 0)]['FairValue'].sum()
            _owned_pnl = _owned_fair - _owned_invested if _owned_invested > 0 else 0
            _owned_pct = (_owned_pnl / _owned_invested * 100) if _owned_invested > 0 else 0
            pm1, pm2, pm3, pm4 = st.columns(4)
            pm1.metric("Cards Owned", len(filtered))
            pm2.metric("Total Invested", f"${_owned_invested:,.2f}")
            pm3.metric("Current Value", f"${_owned_fair:,.2f}")
            pm4.metric("P&L", f"${_owned_pnl:+,.2f}", delta=f"{_owned_pct:+.1f}%")

        # Sort
        filtered = filtered.sort_values(['Season', 'CardNumber'], ascending=[False, True])

        # Build display dataframe
        display_cols = ['Season', 'CardNumber', 'PlayerName', 'Team']
        # Add price columns if they exist
        if has_prices:
            for pc in ['FairValue', 'NumSales', 'Min', 'Max', 'Trend', 'LastScraped']:
                if pc in filtered.columns:
                    display_cols.append(pc)
        else:
            display_cols.extend(['Position', 'Set'])
        # Add graded columns if they exist
        graded_col_names = ['PSA10_Value', 'PSA9_Value', 'PSA8_Value',
                            'BGS10_Value', 'BGS9_5_Value', 'BGS9_Value']
        has_graded = any(c in filtered.columns for c in graded_col_names)
        if has_graded:
            for gc in graded_col_names:
                if gc in filtered.columns:
                    display_cols.append(gc)
        display_cols = [c for c in display_cols if c in filtered.columns]
        edit_master = filtered[display_cols].copy()

        # Fill NAs for price columns
        if has_prices:
            for pc in ['FairValue', 'NumSales', 'Min', 'Max']:
                if pc in edit_master.columns:
                    edit_master[pc] = pd.to_numeric(edit_master[pc], errors='coerce').fillna(0)
        if has_graded:
            for gc in graded_col_names:
                if gc in edit_master.columns:
                    edit_master[gc] = pd.to_numeric(edit_master[gc], errors='coerce').fillna(0)
            if 'Trend' in edit_master.columns:
                trend_map = {'up': '🟢 up', 'down': '🔴 down', 'stable': '⚪ stable', 'no data': '⚫ no data'}
                edit_master['Trend'] = edit_master['Trend'].map(trend_map).fillna('⚫ no data')
            if 'LastScraped' in edit_master.columns:
                edit_master['LastScraped'] = edit_master['LastScraped'].fillna('')

        # Add View checkbox column
        edit_master['View'] = False

        # Reorder columns: View first
        col_order_master = ['View'] + [c for c in display_cols]
        col_order_master = [c for c in col_order_master if c in edit_master.columns]
        edit_master = edit_master[col_order_master]

        st.caption(f"Showing {len(edit_master):,} of {len(master_df):,} cards")

        master_editor_key = f"master_editor_{st.session_state.get('master_editor_reset', 0)}"
        col_config_master = {
            "View": st.column_config.CheckboxColumn("View", width="small", default=False),
            "Season": st.column_config.TextColumn("Season", width="small", disabled=True),
            "CardNumber": st.column_config.NumberColumn("#", width="small", disabled=True),
            "PlayerName": st.column_config.TextColumn("Player", width="medium", disabled=True),
            "Team": st.column_config.TextColumn("Team", width="medium", disabled=True),
        }
        if has_prices:
            col_config_master.update({
                "FairValue": st.column_config.NumberColumn("Fair Value ($)", format="$%.2f", disabled=True),
                "NumSales": st.column_config.NumberColumn("Sales", disabled=True),
                "Min": st.column_config.NumberColumn("Min ($)", format="$%.2f", disabled=True),
                "Max": st.column_config.NumberColumn("Max ($)", format="$%.2f", disabled=True),
                "Trend": st.column_config.TextColumn("Trend", disabled=True),
                "LastScraped": st.column_config.TextColumn("Last Scraped", disabled=True),
            })
        if has_graded:
            col_config_master.update({
                "PSA10_Value": st.column_config.NumberColumn("PSA 10", format="$%.2f", disabled=True),
                "PSA9_Value": st.column_config.NumberColumn("PSA 9", format="$%.2f", disabled=True),
                "PSA8_Value": st.column_config.NumberColumn("PSA 8", format="$%.2f", disabled=True),
                "BGS10_Value": st.column_config.NumberColumn("BGS 10", format="$%.2f", disabled=True),
                "BGS9_5_Value": st.column_config.NumberColumn("BGS 9.5", format="$%.2f", disabled=True),
                "BGS9_Value": st.column_config.NumberColumn("BGS 9", format="$%.2f", disabled=True),
            })
        if not has_prices:
            col_config_master.update({
                "Position": st.column_config.TextColumn("Pos", width="small", disabled=True),
                "Set": st.column_config.TextColumn("Set", width="medium", disabled=True),
            })

        edited_master = st.data_editor(
            edit_master,
            key=master_editor_key,
            use_container_width=True,
            hide_index=True,
            column_config=col_config_master,
            height=600,
        )

        # Handle View checkbox — show card detail + scrape section
        viewed_master = edited_master[edited_master['View'] == True]
        if len(viewed_master) > 0:
            viewed_idx = viewed_master.index[0]
            if viewed_idx in edit_master.index and viewed_idx in filtered.index:
                card_row_master = filtered.loc[viewed_idx]
                st.markdown("---")

                # ── Card Header ──
                _player = card_row_master['PlayerName']
                _team = card_row_master['Team'] if card_row_master['Team'] else "Unknown"
                _season = card_row_master['Season']
                _card_num = int(card_row_master['CardNumber'])
                _set = card_row_master['Set']
                _pos = card_row_master['Position'] if card_row_master['Position'] else "N/A"
                st.markdown(f"### {_player}")
                st.caption(f"{_season} {_set} #{_card_num}  |  {_team}  |  {_pos}")

                # Build eBay search query & history key
                ebay_query = f"{_season} Upper Deck Young Guns #{_card_num} {_player}"
                card_name_for_history = f"{_season} Upper Deck - Young Guns #{_card_num} - {_player}"

                # ── Build price modes map ──
                _raw_val = card_row_master.get('FairValue', 0)
                _raw_val = float(_raw_val) if pd.notna(_raw_val) else 0
                _num_sales = card_row_master.get('NumSales', 0)
                _num_sales = int(float(_num_sales)) if pd.notna(_num_sales) else 0
                _min_val = card_row_master.get('Min', 0)
                _min_val = float(_min_val) if pd.notna(_min_val) else 0
                _max_val = card_row_master.get('Max', 0)
                _max_val = float(_max_val) if pd.notna(_max_val) else 0
                _trend = card_row_master.get('Trend', '')
                _trend = str(_trend) if pd.notna(_trend) else ''
                _last_scraped = card_row_master.get('LastScraped', '')
                _last_scraped = str(_last_scraped) if pd.notna(_last_scraped) else ''

                # Build available price modes: Raw + any graded with data
                _price_modes = {}
                if _raw_val > 0:
                    _price_modes['Raw'] = {'value': _raw_val, 'sales': _num_sales, 'min': _min_val, 'max': _max_val, 'sales_key': card_name_for_history}
                for val_col, label, bracket in [
                    ('PSA10_Value', 'PSA 10', 'PSA 10'), ('PSA9_Value', 'PSA 9', 'PSA 9'), ('PSA8_Value', 'PSA 8', 'PSA 8'),
                    ('BGS10_Value', 'BGS 10', 'BGS 10'), ('BGS9_5_Value', 'BGS 9.5', 'BGS 9.5'), ('BGS9_Value', 'BGS 9', 'BGS 9'),
                ]:
                    sales_col = val_col.replace('_Value', '_Sales')
                    if val_col in card_row_master.index:
                        val = card_row_master.get(val_col, 0)
                        sales = card_row_master.get(sales_col, 0)
                        if pd.notna(val) and float(val) > 0:
                            _price_modes[label] = {
                                'value': float(val),
                                'sales': int(float(sales)) if pd.notna(sales) else 0,
                                'min': 0, 'max': 0,
                                'sales_key': f"{card_name_for_history} [{bracket}]",
                            }

                if _price_modes:
                    # ── Price Mode Selector ──
                    _mode_labels = list(_price_modes.keys())
                    _card_price_mode = st.radio(
                        "Price Mode", _mode_labels,
                        horizontal=True, index=0, key="card_detail_price_mode",
                    )
                    _active = _price_modes[_card_price_mode]

                    # ── Price Summary Metrics ──
                    if _card_price_mode == 'Raw':
                        rc1, rc2, rc3, rc4, rc5 = st.columns(5)
                        rc1.metric("Fair Value", f"${_active['value']:.2f}")
                        rc2.metric("Sales", _active['sales'])
                        rc3.metric("Min", f"${_active['min']:.2f}")
                        rc4.metric("Max", f"${_active['max']:.2f}")
                        _trend_icon = {"up": "+", "down": "-", "stable": "~"}.get(_trend, "")
                        rc5.metric("Trend", _trend.capitalize() if _trend else "N/A", delta=_trend_icon if _trend_icon else None)
                    else:
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric(f"{_card_price_mode} Value", f"${_active['value']:.2f}")
                        rc2.metric("Sales", _active['sales'])
                        mult = f"{_active['value'] / _raw_val:.1f}x raw" if _raw_val > 0 else ""
                        rc3.metric("Premium", mult if mult else "N/A")

                    # ── Sales History Chart ──
                    _sales_key = _active['sales_key']
                    card_raw = load_yg_raw_sales(_sales_key)
                    _has_raw_sales = card_raw and len(card_raw) >= 2

                    # Price history (only for raw mode)
                    card_history = load_yg_price_history(card_name_for_history) if _card_price_mode == 'Raw' else None
                    _has_history = card_history and len(card_history) > 0

                    if _has_history or _has_raw_sales:
                        st.markdown("---")

                    if _has_history and _has_raw_sales:
                        chart_col1, chart_col2 = st.columns(2)
                    elif _has_history:
                        chart_col1 = st.container()
                        chart_col2 = None
                    elif _has_raw_sales:
                        chart_col1 = None
                        chart_col2 = st.container()
                    else:
                        chart_col1 = chart_col2 = None

                    if _has_history and chart_col1:
                        with chart_col1:
                            hist_df = pd.DataFrame(card_history)
                            hist_df['date'] = pd.to_datetime(hist_df['date'])
                            hist_df = hist_df.sort_values('date')
                            fig_card_hist = px.line(
                                hist_df, x='date', y='fair_value',
                                markers=True,
                                labels={'date': 'Date', 'fair_value': 'Fair Value ($)'},
                                hover_data={'num_sales': True},
                                title="Fair Value Over Time",
                            )
                            fig_card_hist.update_layout(template="plotly_dark", height=350)
                            st.plotly_chart(fig_card_hist, use_container_width=True)

                            if len(hist_df) >= 2:
                                first_val = hist_df.iloc[0]['fair_value']
                                last_val = hist_df.iloc[-1]['fair_value']
                                change = last_val - first_val
                                pct = (change / first_val * 100) if first_val > 0 else 0
                                hc1, hc2, hc3 = st.columns(3)
                                hc1.metric("Current", f"${last_val:.2f}")
                                hc2.metric("Change", f"${change:+.2f}")
                                hc3.metric("% Change", f"{pct:+.1f}%")

                    if _has_raw_sales:
                        _chart_target = chart_col2 if chart_col2 else st.container()
                        with _chart_target:
                            raw_df = pd.DataFrame(card_raw)
                            raw_df['sold_date'] = pd.to_datetime(raw_df['sold_date'])
                            raw_df = raw_df.sort_values('sold_date')
                            fig_raw = px.scatter(
                                raw_df, x='sold_date', y='price_val',
                                hover_data={'title': True, 'price_val': ':.2f'},
                                labels={'sold_date': 'Sold Date', 'price_val': 'Sale Price ($)'},
                                title=f"{_card_price_mode} Sales ({len(raw_df)} listings)",
                            )
                            fig_raw.update_traces(marker=dict(size=8, color='#4CAF50'))
                            if len(raw_df) >= 5:
                                raw_df['rolling'] = raw_df['price_val'].rolling(window=5, min_periods=2).mean()
                                fig_raw.add_scatter(
                                    x=raw_df['sold_date'], y=raw_df['rolling'],
                                    mode='lines', name='5-Sale Avg',
                                    line=dict(width=2, dash='dash', color='#FFD700')
                                )
                            fig_raw.update_layout(template="plotly_dark", height=350)
                            st.plotly_chart(fig_raw, use_container_width=True)

                            _avg_sale = raw_df['price_val'].mean()
                            _median_sale = raw_df['price_val'].median()
                            _recent_5 = raw_df.tail(5)['price_val'].mean()
                            sc1, sc2, sc3 = st.columns(3)
                            sc1.metric("Avg Sale", f"${_avg_sale:.2f}")
                            sc2.metric("Median Sale", f"${_median_sale:.2f}")
                            sc3.metric("Last 5 Avg", f"${_recent_5:.2f}")
                    elif not _has_history:
                        st.caption(f"No sales data available for {_card_price_mode}")

                # ── NHL Player Stats ──
                _nhl_stats = get_player_stats_for_card(_player)
                if _nhl_stats:
                    st.markdown("---")
                    _nhl_team = TEAM_ABBREV_TO_NAME.get(_nhl_stats['current_team'], _nhl_stats['current_team'])
                    _nhl_pos = _nhl_stats['position']
                    st.markdown(f"**NHL Stats** — {_nhl_team} ({_nhl_pos})")
                    _bio = get_player_bio_for_card(_player)
                    if _bio:
                        _bio_parts = []
                        if _bio.get('birth_country'):
                            city = _bio.get('birth_city', '')
                            _bio_parts.append(f"Born: {city + ', ' if city else ''}{_bio['birth_country']}")
                        if _bio.get('draft_year'):
                            _bio_parts.append(f"Draft: {_bio['draft_year']} Rd {_bio['draft_round']}, #{_bio['draft_overall']}")
                        else:
                            _bio_parts.append("Undrafted")
                        if _bio_parts:
                            st.caption(" | ".join(_bio_parts))

                    if _nhl_stats['type'] == 'skater':
                        nc1, nc2, nc3, nc4, nc5, nc6 = st.columns(6)
                        nc1.metric("GP", _nhl_stats['games_played'])
                        nc2.metric("Goals", _nhl_stats['goals'])
                        nc3.metric("Assists", _nhl_stats['assists'])
                        nc4.metric("Points", _nhl_stats['points'])
                        nc5.metric("+/-", f"{_nhl_stats['plus_minus']:+d}")
                        nc6.metric("PPG", _nhl_stats.get('powerplay_goals', 0))
                    else:
                        nc1, nc2, nc3, nc4, nc5 = st.columns(5)
                        nc1.metric("GP", _nhl_stats['games_played'])
                        nc2.metric("Wins", _nhl_stats['wins'])
                        nc3.metric("Losses", _nhl_stats['losses'])
                        nc4.metric("SV%", f"{_nhl_stats['save_pct']:.3f}")
                        nc5.metric("GAA", f"{_nhl_stats['gaa']:.2f}")

                    # Stats trend chart if history exists
                    _nhl_history = _nhl_stats.get('history', [])
                    if len(_nhl_history) >= 2:
                        nhl_hist_df = pd.DataFrame(_nhl_history)
                        nhl_hist_df['date'] = pd.to_datetime(nhl_hist_df['date'])
                        nhl_hist_df = nhl_hist_df.sort_values('date')
                        if _nhl_stats['type'] == 'skater':
                            fig_nhl = px.line(
                                nhl_hist_df, x='date', y='points', markers=True,
                                title="Points Over Time",
                                labels={'date': 'Date', 'points': 'Points'},
                            )
                        else:
                            fig_nhl = px.line(
                                nhl_hist_df, x='date', y='wins', markers=True,
                                title="Wins Over Time",
                                labels={'date': 'Date', 'wins': 'Wins'},
                            )
                        fig_nhl.update_layout(template="plotly_dark", height=250)
                        st.plotly_chart(fig_nhl, use_container_width=True)

                    # ── Player Trajectory: Price + Stats Combined ──
                    if _has_history and len(_nhl_history) >= 2:
                        from plotly.subplots import make_subplots
                        st.markdown("**Player Trajectory** — Card Value vs On-Ice Performance")
                        traj_price_df = pd.DataFrame(card_history)
                        traj_price_df['date'] = pd.to_datetime(traj_price_df['date'])
                        traj_price_df = traj_price_df.sort_values('date')

                        traj_stats_df = pd.DataFrame(_nhl_history)
                        traj_stats_df['date'] = pd.to_datetime(traj_stats_df['date'])
                        traj_stats_df = traj_stats_df.sort_values('date')

                        if _nhl_stats['type'] == 'skater':
                            _stat_col, _stat_label = 'points', 'NHL Points'
                        else:
                            _stat_col, _stat_label = 'wins', 'Wins'

                        fig_traj = make_subplots(specs=[[{"secondary_y": True}]])
                        fig_traj.add_trace(
                            go.Scatter(
                                x=traj_price_df['date'], y=traj_price_df['fair_value'],
                                mode='lines+markers', name='Card Price ($)',
                                line=dict(color='#636EFA', width=2), marker=dict(size=5),
                            ), secondary_y=False,
                        )
                        fig_traj.add_trace(
                            go.Scatter(
                                x=traj_stats_df['date'], y=traj_stats_df[_stat_col],
                                mode='lines+markers', name=_stat_label,
                                line=dict(color='#00CC96', width=2), marker=dict(size=5),
                            ), secondary_y=True,
                        )
                        fig_traj.update_layout(
                            template="plotly_dark", height=350,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        fig_traj.update_yaxes(title_text="Card Price ($)", secondary_y=False)
                        fig_traj.update_yaxes(title_text=_stat_label, secondary_y=True)
                        st.plotly_chart(fig_traj, use_container_width=True)

                # ── Ownership / Cost Basis ──
                if not public_view:
                    st.markdown("---")
                    st.markdown("**Ownership**")
                    _cur_owned = bool(card_row_master.get('Owned', 0))
                    _cur_cost = float(card_row_master.get('CostBasis', 0) or 0)
                    _cur_pdate = str(card_row_master.get('PurchaseDate', '') or '')
                    if _cur_pdate == 'nan':
                        _cur_pdate = ''

                    oc1, oc2, oc3, oc4 = st.columns([1, 2, 2, 1])
                    with oc1:
                        owned = st.checkbox("I own this", value=_cur_owned, key="own_card_yg")
                    with oc2:
                        cost_input = st.number_input("Cost Basis ($)", value=_cur_cost,
                                                      min_value=0.0, step=0.01, key="cost_basis_yg")
                    with oc3:
                        pdate_input = st.text_input("Purchase Date", value=_cur_pdate,
                                                     placeholder="YYYY-MM-DD", key="pdate_yg")
                    with oc4:
                        st.markdown("")
                        if st.button("Save", key="save_ownership_yg"):
                            master_df.at[viewed_idx, 'Owned'] = 1 if owned else 0
                            master_df.at[viewed_idx, 'CostBasis'] = cost_input if cost_input > 0 else 0
                            master_df.at[viewed_idx, 'PurchaseDate'] = pdate_input
                            save_master_db(master_df)
                            st.success("Ownership saved!")
                            st.rerun()

                # ── eBay Scrape Button (admin only) ──
                if not public_view:
                    st.markdown("---")
                    st.caption(f"Search query: `{ebay_query}`")
                    if st.button("Scrape eBay Prices", type="primary", key="master_scrape"):
                        with st.spinner(f"Searching eBay for {_player}..."):
                            stats = scrape_single_card(ebay_query, results_json_path=_results_path)
                        if stats and stats.get('num_sales', 0) > 0:
                            st.success(f"Found {stats['num_sales']} sales — ${stats['fair_price']:.2f} fair value (${stats['min']:.2f} - ${stats['max']:.2f})")
                        else:
                            st.warning("No sales found on eBay for this card.")

                # ── Last Scraped ──
                if _last_scraped:
                    st.caption(f"Last scraped: {_last_scraped}")

        # Bottom summary
        st.divider()
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            st.metric("Cards Shown", len(edit_master))
        with tc2:
            st.metric("Seasons Shown", filtered['Season'].nunique())
        with tc3:
            st.metric("Teams Shown", filtered[filtered['Team'] != '']['Team'].nunique())

        # ============================================================
        # YOUNG GUNS ANALYTICS (only when price data exists)
        # ============================================================
        if has_prices:
            priced_df = master_df[master_df['FairValue'].notna() & (master_df['FairValue'] > 0)].copy()
            priced_df['FairValue'] = pd.to_numeric(priced_df['FairValue'], errors='coerce').fillna(0)
            priced_df['NumSales'] = pd.to_numeric(priced_df['NumSales'], errors='coerce').fillna(0)
            priced_df['Min'] = pd.to_numeric(priced_df['Min'], errors='coerce').fillna(0)
            priced_df['Max'] = pd.to_numeric(priced_df['Max'], errors='coerce').fillna(0)

            # Coerce graded columns to numeric
            graded_value_cols = ['PSA8_Value', 'PSA9_Value', 'PSA10_Value', 'BGS9_Value', 'BGS9_5_Value', 'BGS10_Value']
            graded_sales_cols = ['PSA8_Sales', 'PSA9_Sales', 'PSA10_Sales', 'BGS9_Sales', 'BGS9_5_Sales', 'BGS10_Sales']
            for gc in graded_value_cols + graded_sales_cols:
                if gc in priced_df.columns:
                    priced_df[gc] = pd.to_numeric(priced_df[gc], errors='coerce').fillna(0)

            if len(priced_df) > 0:
                st.divider()
                st.markdown('<div class="section-header"><span class="icon">&#x1F4CA;</span> Young Guns Analytics</div>', unsafe_allow_html=True)

                # Price Mode selector — switches all charts between raw and graded values
                price_col_map = {'Raw': 'FairValue'}
                for gc in graded_value_cols:
                    if gc in priced_df.columns and (priced_df[gc] > 0).any():
                        label = gc.replace('_Value', '').replace('PSA', 'PSA ').replace('BGS', 'BGS ').replace('9_5', '9.5')
                        price_col_map[label] = gc

                price_mode = st.radio(
                    "Price Mode", list(price_col_map.keys()),
                    horizontal=True, index=0, key="yg_price_mode",
                    help="Switch all charts between raw and graded price data"
                )
                price_col = price_col_map[price_mode]
                price_label = f"{price_mode} Value ($)"

                # Filter to cards with data for the selected mode
                if price_mode != 'Raw':
                    analytics_df = priced_df[priced_df[price_col] > 0].copy()
                    st.caption(f"Showing {len(analytics_df)} cards with {price_mode} data")
                else:
                    analytics_df = priced_df.copy()

                # ============================================================
                # MARKET OVERVIEW (grouped expander)
                # ============================================================
                market_timeline = load_yg_market_timeline()
                yg_portfolio = load_yg_portfolio_history()
                _has_market = market_timeline and len(market_timeline) >= 2
                _has_portfolio = yg_portfolio and len(yg_portfolio) > 0

                if _has_market or _has_portfolio:
                    with st.expander("Market Overview", expanded=True):
                        _mkt_tabs = []
                        _mkt_tab_names = []
                        if _has_market:
                            _mkt_tab_names.append("Sales History")
                        if _has_portfolio:
                            _mkt_tab_names.append("Market Trend")
                        _mkt_tab_names.append("Season Breakdown")
                        _mkt_tabs = st.tabs(_mkt_tab_names)
                        _tab_idx = 0

                        if _has_market:
                            with _mkt_tabs[_tab_idx]:
                                mt_df = pd.DataFrame(market_timeline)
                                mt_df['date'] = pd.to_datetime(mt_df['date'])
                                mt_df = mt_df.sort_values('date')
                                if len(mt_df) > 10:
                                    _vol = mt_df['total_volume'].values
                                    _dates = mt_df['date'].values
                                    for i in range(len(mt_df) - 2):
                                        window_vol = _vol[i] + _vol[i+1] + _vol[i+2]
                                        day_gap = (pd.Timestamp(_dates[i+2]) - pd.Timestamp(_dates[i])).days
                                        if window_vol >= 15 and day_gap <= 5:
                                            mt_df = mt_df.iloc[i:]
                                            break
                                _days_span = (mt_df['date'].max() - mt_df['date'].min()).days
                                st.caption(f"Individual eBay sold listings aggregated by date ({_days_span} days)")

                                mt_df['rolling_avg'] = mt_df['avg_price'].rolling(window=7, min_periods=1).mean().round(2)

                                hist_col1, hist_col2 = st.columns(2)
                                with hist_col1:
                                    fig_trend = px.line(
                                        mt_df, x='date', y='avg_price',
                                        labels={'date': 'Date', 'avg_price': 'Avg Sale Price ($)'},
                                        title="Average YG Sale Price by Day",
                                    )
                                    fig_trend.add_scatter(
                                        x=mt_df['date'], y=mt_df['rolling_avg'],
                                        mode='lines', name='7-Day Avg',
                                        line=dict(width=3, dash='dash', color='#FFD700')
                                    )
                                    fig_trend.update_layout(template="plotly_dark", height=350)
                                    st.plotly_chart(fig_trend, use_container_width=True)

                                with hist_col2:
                                    fig_vol = px.bar(
                                        mt_df, x='date', y='total_volume',
                                        labels={'date': 'Date', 'total_volume': 'Sales Count'},
                                        title="Daily Sales Volume",
                                    )
                                    fig_vol.update_layout(template="plotly_dark", height=350)
                                    fig_vol.update_traces(marker_color='#4CAF50')
                                    st.plotly_chart(fig_vol, use_container_width=True)

                                total_sales = mt_df['total_volume'].sum()
                                overall_avg = (mt_df['avg_price'] * mt_df['total_volume']).sum() / total_sales if total_sales > 0 else 0
                                recent_avg = mt_df.tail(7)['avg_price'].mean() if len(mt_df) >= 7 else mt_df['avg_price'].mean()
                                older_avg = mt_df.head(7)['avg_price'].mean() if len(mt_df) >= 14 else mt_df['avg_price'].mean()
                                trend_pct = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0

                                ms1, ms2, ms3, ms4 = st.columns(4)
                                ms1.metric("Total Sales Tracked", f"{int(total_sales):,}")
                                ms2.metric("Weighted Avg Price", f"${overall_avg:,.2f}")
                                ms3.metric("Recent 7-Day Avg", f"${recent_avg:,.2f}")
                                ms4.metric("7-Day Trend", f"{trend_pct:+.1f}%")
                            _tab_idx += 1

                        if _has_portfolio:
                            with _mkt_tabs[_tab_idx]:
                                port_df = pd.DataFrame(yg_portfolio)
                                port_df['date'] = pd.to_datetime(port_df['date'])
                                port_df = port_df.sort_values('date')

                                mkt_col1, mkt_col2 = st.columns(2)
                                with mkt_col1:
                                    fig_mkt_val = px.line(
                                        port_df, x='date', y='total_value',
                                        markers=True,
                                        labels={'date': 'Date', 'total_value': 'Total Market Value ($)'},
                                        title="Total YG Market Value",
                                    )
                                    fig_mkt_val.update_layout(template="plotly_dark", height=350)
                                    st.plotly_chart(fig_mkt_val, use_container_width=True)

                                with mkt_col2:
                                    fig_mkt_avg = px.line(
                                        port_df, x='date', y='avg_value',
                                        markers=True,
                                        labels={'date': 'Date', 'avg_value': 'Avg Card Value ($)'},
                                        title="Average Card Value Over Time",
                                    )
                                    fig_mkt_avg.update_layout(template="plotly_dark", height=350)
                                    st.plotly_chart(fig_mkt_avg, use_container_width=True)

                                if len(port_df) >= 2:
                                    latest = port_df.iloc[-1]
                                    first = port_df.iloc[0]
                                    val_change = latest['total_value'] - first['total_value']
                                    val_pct = (val_change / first['total_value'] * 100) if first['total_value'] > 0 else 0
                                    mt1, mt2, mt3, mt4 = st.columns(4)
                                    mt1.metric("Current Total", f"${latest['total_value']:,.2f}")
                                    mt2.metric("Value Change", f"${val_change:+,.2f}")
                                    mt3.metric("% Change", f"{val_pct:+.1f}%")
                                    mt4.metric("Cards Scraped", f"{int(latest.get('cards_scraped', 0)):,}")
                            _tab_idx += 1

                        # Season Breakdown tab (moved from bottom of page)
                        with _mkt_tabs[_tab_idx]:
                            season_counts = master_df.groupby('Season').size().reset_index(name='Cards')
                            season_counts = season_counts.sort_values('Season')
                            fig_seasons = px.bar(
                                season_counts, x='Season', y='Cards',
                                title="Cards per Season",
                                color_discrete_sequence=['#636EFA'],
                            )
                            fig_seasons.update_layout(template="plotly_dark", height=400)
                            st.plotly_chart(fig_seasons, use_container_width=True)

                # ============================================================
                # PRICE ANALYSIS (grouped expander)
                # ============================================================
                with st.expander("Price Analysis", expanded=False):
                    _pa_top20, _pa_liquid, _pa_dist, _pa_season_team, _pa_pvs, _pa_gems, _pa_tiers, _pa_roi = st.tabs([
                        "Top 20", "Most Liquid", "Distribution", "Season & Team", "Price vs Volume", "Hidden Gems", "Price Tiers", "ROI by Era"
                    ])

                    # --- Top 20 Most Valuable ---
                    with _pa_top20:
                        top20_cols = ['Season', 'CardNumber', 'PlayerName', 'Team', price_col, 'NumSales']
                        top20_cols = [c for c in top20_cols if c in analytics_df.columns]
                        top20 = analytics_df.nlargest(20, price_col)[top20_cols].copy()
                        top20['Label'] = top20['PlayerName'] + ' (' + top20['Season'] + ')'
                        fig_top20 = px.bar(
                            top20, x=price_col, y='Label', orientation='h',
                            color=price_col, color_continuous_scale='Blues',
                            hover_data={'PlayerName': True, 'Team': True, 'Label': False},
                            labels={price_col: price_label, 'Label': ''},
                        )
                        fig_top20.update_layout(
                            template="plotly_dark", height=500,
                            yaxis={'categoryorder': 'total ascending'},
                            coloraxis_showscale=False,
                        )
                        st.plotly_chart(fig_top20, use_container_width=True)

                    # --- Most Liquid ---
                    with _pa_liquid:
                        top_liquid = analytics_df.nlargest(15, 'NumSales')[['Season', 'PlayerName', 'Team', price_col, 'NumSales']].copy()
                        top_liquid['Label'] = top_liquid['PlayerName'] + ' (' + top_liquid['Season'] + ')'
                        fig_liquid = px.bar(
                            top_liquid, x='NumSales', y='Label', orientation='h',
                            color=price_col, color_continuous_scale='Greens',
                            hover_data={'PlayerName': True, price_col: True, 'Label': False},
                            labels={'NumSales': 'Sales Found', 'Label': ''},
                        )
                        fig_liquid.update_layout(
                            template="plotly_dark", height=400,
                            yaxis={'categoryorder': 'total ascending'},
                            coloraxis_showscale=False,
                        )
                        st.plotly_chart(fig_liquid, use_container_width=True)

                    # --- Distribution ---
                    with _pa_dist:
                        col_dist1, col_dist2 = st.columns(2)
                        with col_dist1:
                            fig_hist = px.histogram(
                                analytics_df, x=price_col, nbins=50,
                                labels={price_col: price_label, 'count': 'Cards'},
                                color_discrete_sequence=['#636EFA'],
                            )
                            fig_hist.update_layout(template="plotly_dark", height=350)
                            st.plotly_chart(fig_hist, use_container_width=True)

                        with col_dist2:
                            if 'Trend' in analytics_df.columns:
                                trend_counts = analytics_df['Trend'].fillna('no data').value_counts().reset_index()
                                trend_counts.columns = ['Trend', 'Count']
                                fig_trend = px.pie(
                                    trend_counts, names='Trend', values='Count',
                                    color='Trend',
                                    color_discrete_map={'up': '#00CC96', 'down': '#EF553B', 'stable': '#636EFA', 'no data': 'gray'},
                                    hole=0.4,
                                )
                                fig_trend.update_layout(template="plotly_dark", height=350)
                                st.plotly_chart(fig_trend, use_container_width=True)

                    # --- Season & Team ---
                    with _pa_season_team:
                        season_stats = analytics_df.groupby('Season').agg(
                            AvgValue=(price_col, 'mean'),
                            TotalValue=(price_col, 'sum'),
                            Cards=(price_col, 'count'),
                            MaxValue=(price_col, 'max'),
                        ).reset_index().sort_values('Season')
                        fig_season_val = px.bar(
                            season_stats, x='Season', y='AvgValue',
                            color='TotalValue', color_continuous_scale='Viridis',
                            hover_data={'TotalValue': ':.2f', 'Cards': True, 'MaxValue': ':.2f'},
                            labels={'AvgValue': f'Avg {price_mode} ($)', 'TotalValue': 'Total Value ($)'},
                            title=f"Average Card Value by Season",
                        )
                        fig_season_val.update_layout(template="plotly_dark", height=400, coloraxis_showscale=False)
                        st.plotly_chart(fig_season_val, use_container_width=True)

                        st.markdown("---")
                        team_stats = analytics_df[analytics_df['Team'] != ''].groupby('Team').agg(
                            TotalValue=(price_col, 'sum'),
                            AvgValue=(price_col, 'mean'),
                            Cards=(price_col, 'count'),
                            TopCard=(price_col, 'max'),
                        ).reset_index().nlargest(20, 'TotalValue')
                        fig_team = px.bar(
                            team_stats, x='TotalValue', y='Team', orientation='h',
                            color='AvgValue', color_continuous_scale='Oranges',
                            hover_data={'AvgValue': ':.2f', 'Cards': True, 'TopCard': ':.2f'},
                            labels={'TotalValue': f'Total {price_mode} ($)', 'AvgValue': 'Avg ($)'},
                            title=f"Total Value by Team - Top 20",
                        )
                        fig_team.update_layout(
                            template="plotly_dark", height=500,
                            yaxis={'categoryorder': 'total ascending'},
                            coloraxis_showscale=False,
                        )
                        st.plotly_chart(fig_team, use_container_width=True)

                    # --- Price vs Volume ---
                    with _pa_pvs:
                        scatter_df = analytics_df[analytics_df['NumSales'] > 0].copy()
                        if len(scatter_df) > 0:
                            scatter_df['Spread'] = scatter_df['Max'] - scatter_df['Min']
                            fig_scatter = px.scatter(
                                scatter_df, x='NumSales', y=price_col,
                                size='Spread', hover_name='PlayerName',
                                color='Season',
                                hover_data={'Team': True, 'Season': True},
                                labels={'NumSales': 'Sales Found', price_col: price_label},
                            )
                            fig_scatter.update_layout(template="plotly_dark", height=500)
                            st.plotly_chart(fig_scatter, use_container_width=True)

                    # --- Hidden Gems ---
                    with _pa_gems:
                        st.markdown(f"**Hidden Gems - High Volume, Low Price ({price_mode})**")
                        st.caption("Cards with lots of sales but below-average price — potential undervalued picks")
                        avg_price = analytics_df[price_col].mean()
                        gems = analytics_df[
                            (analytics_df['NumSales'] >= 5) & (analytics_df[price_col] < avg_price)
                        ].nlargest(15, 'NumSales')[['Season', 'PlayerName', 'Team', price_col, 'NumSales']].copy()
                        if len(gems) > 0:
                            st.dataframe(
                                gems,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    price_col: st.column_config.NumberColumn(price_label, format="$%.2f"),
                                    'NumSales': st.column_config.NumberColumn("Sales"),
                                },
                            )
                        else:
                            st.caption("No hidden gems found yet — need more price data.")

                        st.markdown("---")
                        st.markdown("**Widest Price Spreads**")
                        st.caption("Cards with the biggest gap between min and max sale — volatile or condition-sensitive")
                        spread_df = analytics_df.copy()
                        spread_df['Spread'] = spread_df['Max'] - spread_df['Min']
                        top_spread = spread_df.nlargest(15, 'Spread')[['Season', 'PlayerName', 'Team', price_col, 'Min', 'Max', 'Spread']].copy()
                        if len(top_spread) > 0:
                            st.dataframe(
                                top_spread,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    price_col: st.column_config.NumberColumn(price_label, format="$%.2f"),
                                    'Min': st.column_config.NumberColumn("Min ($)", format="$%.2f"),
                                    'Max': st.column_config.NumberColumn("Max ($)", format="$%.2f"),
                                    'Spread': st.column_config.NumberColumn("Spread ($)", format="$%.2f"),
                                },
                            )

                    # --- Price Tiers ---
                    with _pa_tiers:
                        st.caption("How many cards fall into each value bracket")
                        tier_bins = [0, 1, 5, 10, 20, 50, 100, 250, float('inf')]
                        tier_labels = ['< $1', '$1-5', '$5-10', '$10-20', '$20-50', '$50-100', '$100-250', '$250+']
                        analytics_df['Tier'] = pd.cut(analytics_df[price_col], bins=tier_bins, labels=tier_labels, right=False)
                        tier_counts = analytics_df['Tier'].value_counts().reindex(tier_labels).fillna(0).reset_index()
                        tier_counts.columns = ['Tier', 'Cards']
                        tier_counts['TotalValue'] = analytics_df.groupby('Tier', observed=False)[price_col].sum().reindex(tier_labels).fillna(0).values

                        tier_col1, tier_col2 = st.columns(2)
                        with tier_col1:
                            fig_tier_cards = px.bar(
                                tier_counts, x='Tier', y='Cards',
                                color='Cards', color_continuous_scale='Blues',
                                labels={'Tier': 'Price Range', 'Cards': 'Number of Cards'},
                                title="Cards per Tier",
                            )
                            fig_tier_cards.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                            st.plotly_chart(fig_tier_cards, use_container_width=True)

                        with tier_col2:
                            fig_tier_val = px.bar(
                                tier_counts, x='Tier', y='TotalValue',
                                color='TotalValue', color_continuous_scale='Greens',
                                labels={'Tier': 'Price Range', 'TotalValue': 'Total Value ($)'},
                                title="Value per Tier",
                            )
                            fig_tier_val.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                            st.plotly_chart(fig_tier_val, use_container_width=True)

                    # --- ROI by Era ---
                    with _pa_roi:
                        st.caption("Comparing average card value across different eras of Young Guns")

                        def get_era(season):
                            year = int(season[:4])
                            if year < 2000:
                                return '1990s'
                            elif year < 2005:
                                return '2000-04'
                            elif year < 2010:
                                return '2005-09'
                            elif year < 2015:
                                return '2010-14'
                            elif year < 2020:
                                return '2015-19'
                            else:
                                return '2020+'

                        analytics_df['Era'] = analytics_df['Season'].apply(get_era)
                        era_stats = analytics_df.groupby('Era').agg(
                            AvgValue=(price_col, 'mean'),
                            MedianValue=(price_col, 'median'),
                            TotalValue=(price_col, 'sum'),
                            Cards=(price_col, 'count'),
                            MaxCard=(price_col, 'max'),
                            AvgSales=('NumSales', 'mean'),
                        ).reset_index()
                        era_order = ['1990s', '2000-04', '2005-09', '2010-14', '2015-19', '2020+']
                        era_stats['Era'] = pd.Categorical(era_stats['Era'], categories=era_order, ordered=True)
                        era_stats = era_stats.sort_values('Era')

                        era_col1, era_col2 = st.columns(2)
                        with era_col1:
                            fig_era_avg = px.bar(
                                era_stats, x='Era', y=['AvgValue', 'MedianValue'],
                                barmode='group',
                                labels={'value': 'Value ($)', 'variable': 'Metric'},
                                title="Avg vs Median Value by Era",
                                color_discrete_map={'AvgValue': '#636EFA', 'MedianValue': '#00CC96'},
                            )
                            fig_era_avg.update_layout(template="plotly_dark", height=350)
                            st.plotly_chart(fig_era_avg, use_container_width=True)

                        with era_col2:
                            fig_era_total = px.bar(
                                era_stats, x='Era', y='TotalValue',
                                color='Cards', color_continuous_scale='Viridis',
                                hover_data={'Cards': True, 'MaxCard': ':.2f', 'AvgSales': ':.1f'},
                                labels={'TotalValue': 'Total Value ($)', 'Cards': 'Card Count'},
                                title="Total Value & Card Count by Era",
                            )
                            fig_era_total.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                            st.plotly_chart(fig_era_total, use_container_width=True)

                        # Era summary table
                        era_display = era_stats[['Era', 'Cards', 'AvgValue', 'MedianValue', 'TotalValue', 'MaxCard', 'AvgSales']].copy()
                        era_display.columns = ['Era', 'Cards', 'Avg Value', 'Median Value', 'Total Value', 'Top Card', 'Avg Sales']
                        st.dataframe(
                            era_display,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                'Avg Value': st.column_config.NumberColumn("Avg Value ($)", format="$%.2f"),
                                'Median Value': st.column_config.NumberColumn("Median ($)", format="$%.2f"),
                                'Total Value': st.column_config.NumberColumn("Total Value ($)", format="$%.2f"),
                                'Top Card': st.column_config.NumberColumn("Top Card ($)", format="$%.2f"),
                                'Avg Sales': st.column_config.NumberColumn("Avg Sales", format="%.1f"),
                            },
                        )

                # ============================================================
                # GRADED ANALYTICS (only when graded data exists)
                # ============================================================
                _has_psa10 = 'PSA10_Value' in priced_df.columns and (priced_df['PSA10_Value'] > 0).any()
                _has_bgs10 = 'BGS10_Value' in priced_df.columns and (priced_df['BGS10_Value'] > 0).any()
                if _has_psa10 or _has_bgs10:
                    _graded_mask = pd.Series(False, index=priced_df.index)
                    if _has_psa10:
                        _graded_mask = _graded_mask | (priced_df['PSA10_Value'] > 0)
                    if _has_bgs10:
                        _graded_mask = _graded_mask | (priced_df['BGS10_Value'] > 0)
                    graded_df = priced_df[_graded_mask].copy()
                else:
                    graded_df = pd.DataFrame()

                if len(graded_df) > 0:
                    with st.expander(f"Grading Analytics ({len(graded_df)} cards)", expanded=False):
                        # --- 3a. Grading ROI Table (Top 20 PSA 10 multipliers) ---
                        if 'PSA10_Value' in graded_df.columns:
                            psa10_df = graded_df[(graded_df['PSA10_Value'] > 0) & (graded_df['FairValue'] > 0)].copy()
                            if len(psa10_df) > 0:
                                psa10_df['PSA10_Mult'] = (psa10_df['PSA10_Value'] / psa10_df['FairValue']).round(1)
                                st.markdown("**Best Cards to Grade (PSA 10 ROI)**")
                                st.caption("Highest PSA 10 multiplier vs raw price — best grading ROI")
                                roi_table = psa10_df.nlargest(20, 'PSA10_Mult')[
                                    ['Season', 'PlayerName', 'Team', 'FairValue', 'PSA10_Value', 'PSA10_Mult']
                                ].copy()
                                st.dataframe(
                                    roi_table,
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        'FairValue': st.column_config.NumberColumn("Raw ($)", format="$%.2f"),
                                        'PSA10_Value': st.column_config.NumberColumn("PSA 10 ($)", format="$%.2f"),
                                        'PSA10_Mult': st.column_config.NumberColumn("Multiplier", format="%.1fx"),
                                    },
                                )

                        # --- 3b. Graded vs Raw Scatter ---
                        if 'PSA10_Value' in graded_df.columns:
                            scatter_graded = graded_df[(graded_df['PSA10_Value'] > 0) & (graded_df['FairValue'] > 0)].copy()
                            if len(scatter_graded) > 0:
                                st.markdown("---")
                                st.markdown("**Graded vs Raw Value**")
                                st.caption("Points above the diagonal = grading adds value")
                                fig_graded_scatter = px.scatter(
                                    scatter_graded, x='FairValue', y='PSA10_Value',
                                    hover_name='PlayerName',
                                    color='Season',
                                    hover_data={'Team': True, 'FairValue': ':.2f', 'PSA10_Value': ':.2f'},
                                    labels={'FairValue': 'Raw Value ($)', 'PSA10_Value': 'PSA 10 Value ($)'},
                                )
                                max_val = max(scatter_graded['FairValue'].max(), scatter_graded['PSA10_Value'].max())
                                fig_graded_scatter.add_shape(
                                    type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                                    line=dict(color="gray", dash="dash", width=1),
                                )
                                fig_graded_scatter.update_layout(template="plotly_dark", height=500)
                                st.plotly_chart(fig_graded_scatter, use_container_width=True)

                        # --- 3c. Average Grade Premium Bar Chart ---
                        st.markdown("---")
                        st.markdown("**Average Grade Premium**")
                        st.caption("Average multiplier over raw price for each grade")
                        premium_data = []
                        grade_col_pairs = [
                            ('PSA 8', 'PSA8_Value'), ('PSA 9', 'PSA9_Value'), ('PSA 10', 'PSA10_Value'),
                            ('BGS 9', 'BGS9_Value'), ('BGS 9.5', 'BGS9_5_Value'), ('BGS 10', 'BGS10_Value'),
                        ]
                        for grade_label, vcol in grade_col_pairs:
                            if vcol in graded_df.columns:
                                valid = graded_df[(graded_df[vcol] > 0) & (graded_df['FairValue'] > 0)]
                                if len(valid) > 0:
                                    avg_mult = (valid[vcol] / valid['FairValue']).mean()
                                    premium_data.append({
                                        'Grade': grade_label,
                                        'Avg Multiplier': round(avg_mult, 2),
                                        'Cards': len(valid),
                                    })
                        if premium_data:
                            premium_df = pd.DataFrame(premium_data)
                            fig_premium = px.bar(
                                premium_df, x='Grade', y='Avg Multiplier',
                                color='Avg Multiplier', color_continuous_scale='RdYlGn',
                                hover_data={'Cards': True},
                                text='Avg Multiplier',
                            )
                            fig_premium.update_traces(texttemplate='%{text:.1f}x', textposition='outside')
                            fig_premium.update_layout(
                                template="plotly_dark", height=400,
                                coloraxis_showscale=False,
                                yaxis_title="Average Multiplier (vs Raw)",
                            )
                            st.plotly_chart(fig_premium, use_container_width=True)

                        # --- 3d. Grading ROI by Season ---
                        if 'PSA10_Value' in graded_df.columns:
                            season_roi = graded_df[(graded_df['PSA10_Value'] > 0) & (graded_df['FairValue'] > 0)].copy()
                            if len(season_roi) > 0:
                                season_roi['PSA10_Mult'] = season_roi['PSA10_Value'] / season_roi['FairValue']
                                season_roi_stats = season_roi.groupby('Season').agg(
                                    AvgMult=('PSA10_Mult', 'mean'),
                                    Cards=('PSA10_Mult', 'count'),
                                ).reset_index().sort_values('Season')

                                roi_col1, roi_col2 = st.columns(2)
                                with roi_col1:
                                    st.markdown("**PSA 10 ROI by Season**")
                                    fig_season_roi = px.bar(
                                        season_roi_stats, x='Season', y='AvgMult',
                                        color='AvgMult', color_continuous_scale='RdYlGn',
                                        hover_data={'Cards': True},
                                        labels={'AvgMult': 'Avg PSA 10 Multiplier'},
                                    )
                                    fig_season_roi.update_layout(template="plotly_dark", height=400, coloraxis_showscale=False)
                                    st.plotly_chart(fig_season_roi, use_container_width=True)

                                # --- 3e. PSA vs BGS Comparison ---
                                with roi_col2:
                                    if 'BGS10_Value' in graded_df.columns:
                                        both_slabs = graded_df[
                                            (graded_df['PSA10_Value'] > 0) & (graded_df['BGS10_Value'] > 0)
                                        ].copy()
                                        if len(both_slabs) > 0:
                                            st.markdown("**PSA 10 vs BGS 10**")
                                            fig_psa_bgs = px.scatter(
                                                both_slabs, x='PSA10_Value', y='BGS10_Value',
                                                hover_name='PlayerName',
                                                color='Season',
                                                hover_data={'Team': True, 'FairValue': ':.2f'},
                                                labels={'PSA10_Value': 'PSA 10 ($)', 'BGS10_Value': 'BGS 10 ($)'},
                                            )
                                            max_slab = max(both_slabs['PSA10_Value'].max(), both_slabs['BGS10_Value'].max())
                                            fig_psa_bgs.add_shape(
                                                type="line", x0=0, y0=0, x1=max_slab, y1=max_slab,
                                                line=dict(color="gray", dash="dash", width=1),
                                            )
                                            fig_psa_bgs.update_layout(template="plotly_dark", height=400)
                                            st.plotly_chart(fig_psa_bgs, use_container_width=True)
                                        else:
                                            st.markdown("**PSA 10 vs BGS 10**")
                                            st.caption("No cards with both PSA 10 and BGS 10 data yet")

                # ============================================================
                # NHL DATA LOAD (shared by Compare Tool + Correlation Analytics)
                # ============================================================
                nhl_data = load_nhl_player_stats()
                nhl_players = nhl_data.get('players', {}) if nhl_data else {}
                nhl_standings = nhl_data.get('standings', {}) if nhl_data else {}

                # ============================================================
                # PLAYER COMPARE TOOL
                # ============================================================
                if nhl_players and len(analytics_df) > 0:
                    with st.expander("Player Compare Tool", expanded=False):
                        compare_players = sorted([
                            p for p in analytics_df['PlayerName'].unique()
                            if p in nhl_players
                        ])
                        if len(compare_players) >= 2:
                            cc1, cc2 = st.columns(2)
                            with cc1:
                                player_a = st.selectbox("Player A", compare_players, index=0, key="compare_a")
                            with cc2:
                                player_b = st.selectbox("Player B", compare_players, index=min(1, len(compare_players)-1), key="compare_b")

                            if player_a and player_b and player_a != player_b:
                                card_a = analytics_df[analytics_df['PlayerName'] == player_a].iloc[0]
                                card_b = analytics_df[analytics_df['PlayerName'] == player_b].iloc[0]
                                nhl_a = nhl_players[player_a]
                                nhl_b = nhl_players[player_b]
                                cs_a = nhl_a.get('current_season', {})
                                cs_b = nhl_b.get('current_season', {})

                                # Card price comparison
                                cmp1, cmp_mid, cmp2 = st.columns([2, 1, 2])
                                with cmp1:
                                    st.metric(player_a, f"${card_a[price_col]:.2f}")
                                    st.caption(f"{card_a.get('Season', '')} | {TEAM_ABBREV_TO_NAME.get(nhl_a.get('current_team', ''), '')}")
                                with cmp_mid:
                                    st.markdown("<div style='text-align:center;padding-top:20px;font-size:1.5rem;'>vs</div>", unsafe_allow_html=True)
                                with cmp2:
                                    st.metric(player_b, f"${card_b[price_col]:.2f}")
                                    st.caption(f"{card_b.get('Season', '')} | {TEAM_ABBREV_TO_NAME.get(nhl_b.get('current_team', ''), '')}")

                                # NHL stats comparison (skaters)
                                if nhl_a.get('type') == 'skater' and nhl_b.get('type') == 'skater':
                                    st.markdown("**NHL Stats**")
                                    stat_pairs = [('GP', 'games_played'), ('Goals', 'goals'), ('Assists', 'assists'),
                                                  ('Points', 'points'), ('+/-', 'plus_minus'), ('PPG', 'powerplay_goals')]
                                    compare_rows = []
                                    for label, key in stat_pairs:
                                        va = cs_a.get(key, 0)
                                        vb = cs_b.get(key, 0)
                                        compare_rows.append({'Stat': label, player_a: va, player_b: vb})
                                    compare_df = pd.DataFrame(compare_rows)
                                    st.dataframe(compare_df, use_container_width=True, hide_index=True)

                                elif nhl_a.get('type') == 'goalie' and nhl_b.get('type') == 'goalie':
                                    st.markdown("**Goalie Stats**")
                                    stat_pairs = [('GP', 'games_played'), ('Wins', 'wins'), ('Losses', 'losses'),
                                                  ('SV%', 'save_pct'), ('GAA', 'gaa'), ('SO', 'shutouts')]
                                    compare_rows = []
                                    for label, key in stat_pairs:
                                        va = cs_a.get(key, 0)
                                        vb = cs_b.get(key, 0)
                                        compare_rows.append({'Stat': label, player_a: va, player_b: vb})
                                    compare_df = pd.DataFrame(compare_rows)
                                    st.dataframe(compare_df, use_container_width=True, hide_index=True)

                                # Price history overlay
                                card_name_a = card_a.get('CardName', '')
                                card_name_b = card_b.get('CardName', '')
                                hist_a = load_yg_price_history(card_name_a) if card_name_a else None
                                hist_b = load_yg_price_history(card_name_b) if card_name_b else None

                                if hist_a and hist_b:
                                    st.markdown("**Price History Overlay**")
                                    fig_compare = go.Figure()
                                    df_ha = pd.DataFrame(hist_a)
                                    df_ha['date'] = pd.to_datetime(df_ha['date'])
                                    fig_compare.add_trace(go.Scatter(
                                        x=df_ha['date'], y=df_ha['fair_value'],
                                        mode='lines+markers', name=player_a,
                                        line=dict(color='#636EFA', width=2),
                                    ))
                                    df_hb = pd.DataFrame(hist_b)
                                    df_hb['date'] = pd.to_datetime(df_hb['date'])
                                    fig_compare.add_trace(go.Scatter(
                                        x=df_hb['date'], y=df_hb['fair_value'],
                                        mode='lines+markers', name=player_b,
                                        line=dict(color='#EF553B', width=2),
                                    ))
                                    fig_compare.update_layout(
                                        template="plotly_dark", height=350,
                                        yaxis_title="Fair Value ($)", xaxis_title="Date",
                                    )
                                    st.plotly_chart(fig_compare, use_container_width=True)

                                # Graded values comparison
                                graded_cols = ['PSA10_Value', 'PSA9_Value', 'PSA8_Value', 'BGS10_Value', 'BGS9_5_Value', 'BGS9_Value']
                                graded_data = []
                                for gc in graded_cols:
                                    if gc in card_a.index and gc in card_b.index:
                                        va = float(card_a.get(gc, 0) or 0)
                                        vb = float(card_b.get(gc, 0) or 0)
                                        if va > 0 or vb > 0:
                                            label = gc.replace('_Value', '').replace('PSA', 'PSA ').replace('BGS', 'BGS ').replace('9_5', '9.5')
                                            graded_data.append({
                                                'Grade': label,
                                                player_a: f"${va:.2f}" if va > 0 else "N/A",
                                                player_b: f"${vb:.2f}" if vb > 0 else "N/A",
                                            })
                                if graded_data:
                                    st.markdown("**Graded Values**")
                                    st.dataframe(pd.DataFrame(graded_data), use_container_width=True, hide_index=True)

                            elif player_a == player_b:
                                st.warning("Select two different players to compare.")
                        else:
                            st.info("Need at least 2 players with NHL data.")

                # ============================================================
                # PRICE vs PERFORMANCE CORRELATION ANALYTICS
                # ============================================================

                if nhl_players:
                    # Build a DataFrame merging card prices with NHL stats
                    nhl_rows = []
                    _seen_nhl = set()
                    for _, row in analytics_df.iterrows():
                        pname = row['PlayerName']
                        if pname in _seen_nhl:
                            continue
                        _seen_nhl.add(pname)
                        nhl = nhl_players.get(pname)
                        if nhl and nhl.get('current_season'):
                            cs = nhl['current_season']
                            nhl_row = {
                                'PlayerName': pname,
                                'Season': row['Season'],
                                'Team': row['Team'],
                                'FairValue': row[price_col],
                                'Position': nhl.get('position', ''),
                                'Type': nhl.get('type', 'skater'),
                                'TeamAbbrev': nhl.get('current_team', ''),
                                'CurrentTeam': TEAM_ABBREV_TO_NAME.get(nhl.get('current_team', ''), nhl.get('current_team', '')),
                            }
                            if nhl['type'] == 'skater':
                                nhl_row.update({
                                    'GP': cs.get('games_played', 0),
                                    'Goals': cs.get('goals', 0),
                                    'Assists': cs.get('assists', 0),
                                    'Points': cs.get('points', 0),
                                    'PlusMinus': cs.get('plus_minus', 0),
                                    'PPG': cs.get('powerplay_goals', 0),
                                    'GWG': cs.get('game_winning_goals', 0),
                                    'Shots': cs.get('shots', 0),
                                })
                            else:
                                team_abbrev = nhl.get('current_team', '')
                                team_stand = nhl_standings.get(team_abbrev, {})
                                nhl_row.update({
                                    'GP': cs.get('games_played', 0),
                                    'Wins': cs.get('wins', 0),
                                    'Losses': cs.get('losses', 0),
                                    'SavePct': cs.get('save_pct', 0),
                                    'GAA': cs.get('gaa', 0),
                                    'Shutouts': cs.get('shutouts', 0),
                                    'TeamPoints': team_stand.get('points', 0),
                                    'LeagueRank': team_stand.get('league_rank', 0),
                                })
                            nhl_rows.append(nhl_row)

                    if nhl_rows:
                        nhl_df = pd.DataFrame(nhl_rows)
                        skaters_df = nhl_df[nhl_df['Type'] == 'skater'].copy()
                        goalies_df = nhl_df[nhl_df['Type'] == 'goalie'].copy()

                        # Load correlation history
                        corr_history = load_correlation_history()
                        latest_date = max(corr_history.keys()) if corr_history else None
                        latest_snap = corr_history.get(latest_date, {}) if latest_date else {}
                        latest_corr = latest_snap.get('correlations', {})

                        # ── Impact Score Leaderboard ──
                        _team_mults = compute_team_multipliers(latest_snap) if latest_snap else {}
                        _impact = compute_impact_scores(master_df, nhl_players, _team_mults)
                        if _impact:
                            with st.expander(f"Rookie Impact Score ({len(_impact)} players)", expanded=False):
                                st.caption("Composite 0-100 score: Points Pace 40% | Team Market 20% | Draft Position 15% | +/- Rate 15% | Shooting % 10%")
                                _imp_rows = []
                                for pname, d in _impact.items():
                                    _card_row = master_df[master_df['PlayerName'] == pname]
                                    _price = float(_card_row.iloc[0].get('FairValue', 0)) if len(_card_row) > 0 else 0
                                    _imp_rows.append({
                                        'Player': pname,
                                        'Score': d['score'],
                                        'Team': TEAM_ABBREV_TO_NAME.get(d.get('team', ''), d.get('team', '')),
                                        'Pos': d.get('position', ''),
                                        'GP': d.get('gp', 0),
                                        'Pts': d.get('points', 0),
                                        'Goals': d.get('goals', 0),
                                        'Price': _price,
                                        'Pace': d['breakdown']['pace'],
                                        'Mkt': d['breakdown']['team'],
                                        'Draft': d['breakdown']['draft'],
                                        'Shot': d['breakdown']['shooting'],
                                        '+/-': d['breakdown']['plusminus'],
                                    })
                                _imp_df = pd.DataFrame(_imp_rows).sort_values('Score', ascending=False)

                                # Top metrics
                                im1, im2, im3, im4 = st.columns(4)
                                _top = _imp_df.iloc[0]
                                im1.metric("Top Scorer", f"{_top['Player']}", f"{_top['Score']:.0f}/100")
                                im2.metric("Avg Score", f"{_imp_df['Score'].mean():.1f}")
                                im3.metric("Median Score", f"{_imp_df['Score'].median():.1f}")
                                im4.metric("Players Scored", f"{len(_imp_df)}")

                                # Scatter: Impact Score vs Price
                                fig_imp = px.scatter(
                                    _imp_df, x='Score', y='Price',
                                    hover_name='Player',
                                    hover_data={'Team': True, 'GP': True, 'Pts': True, 'Goals': True},
                                    color='Score', color_continuous_scale='YlOrRd',
                                    labels={'Score': 'Impact Score (0-100)', 'Price': 'Card Price ($)'},
                                )
                                fig_imp.update_layout(template="plotly_dark", height=400)
                                fig_imp.update_traces(marker=dict(size=8))
                                st.plotly_chart(fig_imp, use_container_width=True)

                                # Top 20 leaderboard
                                st.markdown("**Top 20 Impact Scores**")
                                _show_cols = ['Player', 'Score', 'Team', 'Pos', 'GP', 'Pts', 'Goals', 'Price', 'Pace', 'Mkt', 'Draft', 'Shot', '+/-']
                                st.dataframe(
                                    _imp_df.head(20)[_show_cols],
                                    hide_index=True, use_container_width=True,
                                    column_config={
                                        'Score': st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
                                        'Price': st.column_config.NumberColumn("Price", format="$%.2f"),
                                    }
                                )

                        with st.expander(f"Price vs Performance Correlation ({len(nhl_df)} players)", expanded=False):
                            # --- Key Metrics Header ---
                            pts_corr = latest_corr.get('points_vs_price', {})
                            goals_corr = latest_corr.get('goals_vs_price', {})
                            km1, km2, km3, km4 = st.columns(4)
                            with km1:
                                st.metric("Points-Price R", f"{pts_corr.get('r', 0):.3f}" if pts_corr else "N/A")
                            with km2:
                                r_sq = pts_corr.get('r_squared', 0)
                                st.metric("R-Squared", f"{r_sq:.1%}" if pts_corr else "N/A")
                            with km3:
                                st.metric("Skaters", f"{len(skaters_df)}")
                            with km4:
                                tp = latest_snap.get('team_premiums', {})
                                ca_prices = [d['avg_price'] for t, d in tp.items() if d.get('country') == 'CA']
                                us_prices = [d['avg_price'] for t, d in tp.items() if d.get('country') == 'US']
                                if ca_prices and us_prices:
                                    ca_avg = sum(ca_prices) / len(ca_prices)
                                    us_avg = sum(us_prices) / len(us_prices)
                                    prem = ((ca_avg / max(us_avg, 0.01)) - 1) * 100
                                    st.metric("Canadian Premium", f"{prem:+.0f}%")
                                else:
                                    st.metric("Goalies", f"{len(goalies_df)}")

                            # --- 10 Tabs ---
                            tab_corr, tab_tiers, tab_teams, tab_pos, tab_value, tab_goalies, tab_nationality, tab_draft, tab_seasonal, tab_trends = st.tabs([
                                "Correlation", "Price Tiers", "Teams", "Positions", "Value Finder", "Goalies", "Nationality", "Draft", "Seasonal", "Trends"
                            ])

                            # ========== TAB 1: CORRELATION ==========
                            with tab_corr:
                                if len(skaters_df) > 0:
                                    st.markdown("**Points vs Card Value**")
                                    fig_pvp = px.scatter(
                                        skaters_df, x='Points', y='FairValue',
                                        hover_name='PlayerName',
                                        color='Position',
                                        size='GP',
                                        hover_data={'CurrentTeam': True, 'Goals': True, 'Assists': True, 'GP': True},
                                        labels={'FairValue': f'{price_mode} Value ($)', 'Points': 'NHL Points'},
                                    )
                                    # Add regression line from stored coefficients
                                    if pts_corr and pts_corr.get('slope'):
                                        x_range = [skaters_df['Points'].min(), skaters_df['Points'].max()]
                                        y_range = [pts_corr['slope'] * x + pts_corr['intercept'] for x in x_range]
                                        fig_pvp.add_trace(go.Scatter(
                                            x=x_range, y=y_range, mode='lines',
                                            name=f"R={pts_corr['r']:.3f}",
                                            line=dict(color='#FFD700', width=2, dash='dash'),
                                        ))
                                    fig_pvp.update_layout(template="plotly_dark", height=450)
                                    st.plotly_chart(fig_pvp, use_container_width=True)

                                    # Goals vs Price (smaller, side by side)
                                    gc1, gc2 = st.columns(2)
                                    with gc1:
                                        st.markdown("**Goals vs Card Value**")
                                        fig_gvp = px.scatter(
                                            skaters_df, x='Goals', y='FairValue',
                                            hover_name='PlayerName', color='Position',
                                            labels={'FairValue': f'{price_mode} ($)', 'Goals': 'Goals'},
                                        )
                                        if goals_corr and goals_corr.get('slope'):
                                            gx = [skaters_df['Goals'].min(), skaters_df['Goals'].max()]
                                            gy = [goals_corr['slope'] * x + goals_corr['intercept'] for x in gx]
                                            fig_gvp.add_trace(go.Scatter(
                                                x=gx, y=gy, mode='lines',
                                                name=f"R={goals_corr['r']:.3f}",
                                                line=dict(color='#FFD700', width=2, dash='dash'),
                                            ))
                                        fig_gvp.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_gvp, use_container_width=True)

                                    with gc2:
                                        st.markdown("**Top Performers by Points**")
                                        top_perf = skaters_df.nlargest(15, 'Points')[
                                            ['PlayerName', 'CurrentTeam', 'Position', 'GP', 'Goals', 'Assists', 'Points', 'PlusMinus', 'FairValue']
                                        ].copy()
                                        st.dataframe(
                                            top_perf, use_container_width=True, hide_index=True,
                                            column_config={
                                                'FairValue': st.column_config.NumberColumn(f"{price_mode} ($)", format="$%.2f"),
                                                'PlusMinus': st.column_config.NumberColumn("+/-"),
                                                'CurrentTeam': st.column_config.TextColumn("Team"),
                                                'Position': st.column_config.TextColumn("Pos"),
                                            },
                                        )

                            # ========== TAB 2: PRICE TIERS ==========
                            with tab_tiers:
                                tier_data = latest_snap.get('tiers', [])
                                if tier_data:
                                    st.markdown("**Average Card Price by Points Bracket**")
                                    st.caption("The exponential curve: performance only matters above ~30 points")
                                    tier_df = pd.DataFrame(tier_data)
                                    fig_tiers = px.bar(
                                        tier_df, x='label', y='avg_price',
                                        text='count',
                                        color='avg_price',
                                        color_continuous_scale='Blues',
                                        labels={'label': 'Points Bracket', 'avg_price': 'Avg Card Price ($)', 'count': 'Cards'},
                                    )
                                    fig_tiers.update_traces(texttemplate='%{text} cards', textposition='outside')
                                    fig_tiers.update_layout(
                                        template="plotly_dark", height=400,
                                        coloraxis_showscale=False,
                                        xaxis={'categoryorder': 'array', 'categoryarray': [t['label'] for t in tier_data]},
                                    )
                                    st.plotly_chart(fig_tiers, use_container_width=True)

                                    st.dataframe(
                                        tier_df[['label', 'avg_price', 'median_price', 'count']].rename(columns={
                                            'label': 'Bracket', 'avg_price': 'Avg Price', 'median_price': 'Median', 'count': 'Cards'
                                        }),
                                        use_container_width=True, hide_index=True,
                                        column_config={
                                            'Avg Price': st.column_config.NumberColumn(format="$%.2f"),
                                            'Median': st.column_config.NumberColumn(format="$%.2f"),
                                        },
                                    )
                                else:
                                    st.info("Run the NHL stats scraper to generate tier data.")

                            # ========== TAB 3: TEAMS ==========
                            with tab_teams:
                                tp = latest_snap.get('team_premiums', {})
                                if tp:
                                    # CA vs US comparison
                                    ca_data = {t: d for t, d in tp.items() if d.get('country') == 'CA'}
                                    us_data = {t: d for t, d in tp.items() if d.get('country') == 'US'}
                                    ca_avg = sum(d['avg_price'] for d in ca_data.values()) / max(len(ca_data), 1)
                                    us_avg = sum(d['avg_price'] for d in us_data.values()) / max(len(us_data), 1)

                                    tm1, tm2, tm3 = st.columns(3)
                                    with tm1:
                                        st.metric("Canadian Teams Avg", f"${ca_avg:.2f}", f"{len(ca_data)} teams")
                                    with tm2:
                                        st.metric("US Teams Avg", f"${us_avg:.2f}", f"{len(us_data)} teams")
                                    with tm3:
                                        prem_pct = ((ca_avg / max(us_avg, 0.01)) - 1) * 100
                                        st.metric("Premium", f"{prem_pct:+.0f}%")

                                    # Bar chart by team
                                    team_rows = []
                                    for t, d in tp.items():
                                        team_rows.append({
                                            'Team': TEAM_ABBREV_TO_NAME.get(t, t),
                                            'Abbrev': t,
                                            'Avg Price': d['avg_price'],
                                            'Cards': d['count'],
                                            'Market': 'Canadian' if d.get('country') == 'CA' else 'US',
                                        })
                                    team_df = pd.DataFrame(team_rows).sort_values('Avg Price', ascending=True)

                                    fig_teams = px.bar(
                                        team_df, x='Avg Price', y='Team', orientation='h',
                                        color='Market',
                                        color_discrete_map={'Canadian': '#EF553B', 'US': '#636EFA'},
                                        hover_data={'Cards': True, 'Abbrev': True},
                                        labels={'Avg Price': 'Avg Card Price ($)'},
                                    )
                                    fig_teams.update_layout(
                                        template="plotly_dark", height=max(400, len(team_df) * 18),
                                        yaxis={'categoryorder': 'total ascending'},
                                    )
                                    st.plotly_chart(fig_teams, use_container_width=True)

                                    # Team Market Multiplier
                                    st.markdown("---")
                                    st.markdown("**Team Market Multiplier**")
                                    st.caption("How much each team's market inflates/deflates card prices beyond what player performance alone predicts.")
                                    _tm = compute_team_multipliers(latest_snap)
                                    if _tm:
                                        tm_rows = []
                                        for t, d in _tm.items():
                                            tm_rows.append({
                                                'Team': TEAM_ABBREV_TO_NAME.get(t, t),
                                                'Abbrev': t,
                                                'Actual Avg': d['actual'],
                                                'Expected Avg': d['expected'],
                                                'Multiplier': d['multiplier'],
                                                'Premium': f"{d['premium_pct']:+.1f}%",
                                                'Cards': d['count'],
                                                'Market': 'Canadian' if d['country'] == 'CA' else 'US',
                                            })
                                        tm_df = pd.DataFrame(tm_rows).sort_values('Multiplier', ascending=True)

                                        fig_mult = px.bar(
                                            tm_df, x='Multiplier', y='Team', orientation='h',
                                            color='Market',
                                            color_discrete_map={'Canadian': '#EF553B', 'US': '#636EFA'},
                                            hover_data={'Actual Avg': ':.2f', 'Expected Avg': ':.2f', 'Premium': True, 'Cards': True},
                                        )
                                        fig_mult.add_vline(x=1.0, line_dash="dash", line_color="#888", annotation_text="Fair Value (1.0x)")
                                        fig_mult.update_layout(
                                            template="plotly_dark", height=max(400, len(tm_df) * 18),
                                            yaxis={'categoryorder': 'total ascending'},
                                            xaxis_title="Market Multiplier",
                                        )
                                        st.plotly_chart(fig_mult, use_container_width=True)

                                        # Top overvalued / undervalued teams
                                        ovc1, ovc2 = st.columns(2)
                                        with ovc1:
                                            st.markdown("**Highest Premium Teams**")
                                            top_prem = tm_df.sort_values('Multiplier', ascending=False).head(5)
                                            st.dataframe(top_prem[['Team', 'Multiplier', 'Premium', 'Actual Avg', 'Expected Avg', 'Cards']],
                                                         hide_index=True, use_container_width=True)
                                        with ovc2:
                                            st.markdown("**Most Discounted Teams**")
                                            low_prem = tm_df.sort_values('Multiplier', ascending=True).head(5)
                                            st.dataframe(low_prem[['Team', 'Multiplier', 'Premium', 'Actual Avg', 'Expected Avg', 'Cards']],
                                                         hide_index=True, use_container_width=True)
                                else:
                                    st.info("Run the NHL stats scraper to generate team data.")

                            # ========== TAB 4: POSITIONS ==========
                            with tab_pos:
                                pb = latest_snap.get('position_breakdown', {})
                                if pb and len(skaters_df) > 0:
                                    # Position bar chart
                                    pos_rows = []
                                    pos_labels = {'C': 'Center', 'L': 'Left Wing', 'R': 'Right Wing', 'D': 'Defense', 'G': 'Goalie'}
                                    for p, d in pb.items():
                                        pos_rows.append({
                                            'Position': pos_labels.get(p, p),
                                            'Avg Price': d.get('avg_price', 0),
                                            'Avg Points': d.get('avg_points', d.get('avg_wins', 0)),
                                            'Cards': d.get('count', 0),
                                        })
                                    pos_df = pd.DataFrame(pos_rows)

                                    pc1, pc2 = st.columns(2)
                                    with pc1:
                                        st.markdown("**Avg Card Price by Position**")
                                        fig_pos = px.bar(
                                            pos_df, x='Position', y='Avg Price',
                                            color='Avg Price', color_continuous_scale='Greens',
                                            text='Cards',
                                            labels={'Avg Price': 'Avg Card Price ($)'},
                                        )
                                        fig_pos.update_traces(texttemplate='%{text} cards', textposition='outside')
                                        fig_pos.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                                        st.plotly_chart(fig_pos, use_container_width=True)

                                    with pc2:
                                        st.markdown("**Forwards vs Defensemen**")
                                        fwd_df = skaters_df[skaters_df['Position'].isin(['C', 'L', 'R'])].copy()
                                        def_df = skaters_df[skaters_df['Position'] == 'D'].copy()
                                        fig_fvd = go.Figure()
                                        if len(fwd_df) > 0:
                                            fig_fvd.add_trace(go.Scatter(
                                                x=fwd_df['Points'], y=fwd_df['FairValue'],
                                                mode='markers', name='Forwards',
                                                text=fwd_df['PlayerName'],
                                                marker=dict(color='#00CC96', size=8, opacity=0.7),
                                            ))
                                        if len(def_df) > 0:
                                            fig_fvd.add_trace(go.Scatter(
                                                x=def_df['Points'], y=def_df['FairValue'],
                                                mode='markers', name='Defensemen',
                                                text=def_df['PlayerName'],
                                                marker=dict(color='#AB63FA', size=8, opacity=0.7),
                                            ))
                                        fig_fvd.update_layout(
                                            template="plotly_dark", height=350,
                                            xaxis_title="Points", yaxis_title=f"{price_mode} Value ($)",
                                        )
                                        st.plotly_chart(fig_fvd, use_container_width=True)
                                else:
                                    st.info("Run the NHL stats scraper to generate position data.")

                            # ========== TAB 5: VALUE FINDER ==========
                            with tab_value:
                                if len(skaters_df) > 0 and pts_corr and pts_corr.get('slope'):
                                    slope = pts_corr['slope']
                                    intercept = pts_corr['intercept']
                                    val_df = skaters_df[skaters_df['GP'] >= 10].copy()
                                    val_df['Expected'] = (val_df['Points'] * slope + intercept).round(2)
                                    val_df['Expected'] = val_df['Expected'].clip(lower=1.0)
                                    val_df['Premium%'] = (((val_df['FairValue'] / val_df['Expected']) - 1) * 100).round(1)

                                    ov1, ov2 = st.columns(2)
                                    with ov1:
                                        st.markdown("**Most Overvalued** (Price >> Expected)")
                                        st.caption("High card price relative to on-ice production")
                                        overvalued = val_df[val_df['FairValue'] > 5].nlargest(15, 'Premium%')[
                                            ['PlayerName', 'CurrentTeam', 'Points', 'GP', 'FairValue', 'Expected', 'Premium%']
                                        ]
                                        st.dataframe(
                                            overvalued, use_container_width=True, hide_index=True,
                                            column_config={
                                                'FairValue': st.column_config.NumberColumn("Actual ($)", format="$%.2f"),
                                                'Expected': st.column_config.NumberColumn("Expected ($)", format="$%.2f"),
                                                'Premium%': st.column_config.NumberColumn("Premium", format="%+.0f%%"),
                                                'CurrentTeam': st.column_config.TextColumn("Team"),
                                            },
                                        )

                                    with ov2:
                                        st.markdown("**Most Undervalued** (Price << Expected)")
                                        st.caption("Strong stats but cheap card — potential value buys")
                                        undervalued = val_df[val_df['Points'] >= 15].nsmallest(15, 'Premium%')[
                                            ['PlayerName', 'CurrentTeam', 'Points', 'GP', 'FairValue', 'Expected', 'Premium%']
                                        ]
                                        st.dataframe(
                                            undervalued, use_container_width=True, hide_index=True,
                                            column_config={
                                                'FairValue': st.column_config.NumberColumn("Actual ($)", format="$%.2f"),
                                                'Expected': st.column_config.NumberColumn("Expected ($)", format="$%.2f"),
                                                'Premium%': st.column_config.NumberColumn("Discount", format="%+.0f%%"),
                                                'CurrentTeam': st.column_config.TextColumn("Team"),
                                            },
                                        )

                                    # Residual scatter
                                    st.markdown("---")
                                    st.markdown("**Actual vs Expected Price**")
                                    st.caption("Points above the line = overvalued, below = undervalued")
                                    fig_resid = px.scatter(
                                        val_df, x='Expected', y='FairValue',
                                        hover_name='PlayerName',
                                        color='Position',
                                        hover_data={'Points': True, 'CurrentTeam': True, 'Premium%': True},
                                        labels={'Expected': 'Expected Price ($)', 'FairValue': f'Actual {price_mode} ($)'},
                                    )
                                    max_val = max(val_df['Expected'].max(), val_df['FairValue'].max())
                                    fig_resid.add_trace(go.Scatter(
                                        x=[0, max_val], y=[0, max_val], mode='lines',
                                        name='Fair Value Line',
                                        line=dict(color='gray', dash='dash', width=1),
                                    ))
                                    fig_resid.update_layout(template="plotly_dark", height=400)
                                    st.plotly_chart(fig_resid, use_container_width=True)
                                else:
                                    st.info("Run the NHL stats scraper to generate value analysis.")

                            # ========== TAB 6: GOALIES ==========
                            with tab_goalies:
                                if len(goalies_df) > 0:
                                    g1, g2 = st.columns(2)
                                    with g1:
                                        st.markdown("**Wins vs Card Value**")
                                        fig_gw = px.scatter(
                                            goalies_df, x='Wins', y='FairValue',
                                            hover_name='PlayerName', size='GP',
                                            color='SavePct', color_continuous_scale='RdYlGn',
                                            hover_data={'SavePct': ':.3f', 'GAA': ':.2f', 'TeamPoints': True},
                                            labels={'FairValue': f'{price_mode} ($)', 'Wins': 'Wins', 'SavePct': 'SV%'},
                                        )
                                        fig_gw.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_gw, use_container_width=True)

                                    with g2:
                                        st.markdown("**Save % vs Card Value**")
                                        fig_gsv = px.scatter(
                                            goalies_df, x='SavePct', y='FairValue',
                                            hover_name='PlayerName', size='GP',
                                            color='Wins', color_continuous_scale='Viridis',
                                            hover_data={'Wins': True, 'GAA': ':.2f'},
                                            labels={'FairValue': f'{price_mode} ($)', 'SavePct': 'Save %'},
                                        )
                                        fig_gsv.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_gsv, use_container_width=True)

                                    # Team placement factor
                                    if 'TeamPoints' in goalies_df.columns:
                                        st.markdown("**Team Points vs Goalie Card Value**")
                                        st.caption("Does playing for a winning team inflate goalie card prices?")
                                        fig_gtp = px.scatter(
                                            goalies_df, x='TeamPoints', y='FairValue',
                                            hover_name='PlayerName', size='Wins',
                                            hover_data={'SavePct': ':.3f', 'CurrentTeam': True},
                                            labels={'FairValue': f'{price_mode} ($)', 'TeamPoints': 'Team Points'},
                                        )
                                        fig_gtp.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_gtp, use_container_width=True)

                                    st.markdown("**Goalie Stats**")
                                    goalie_table = goalies_df.nlargest(15, 'Wins')[
                                        ['PlayerName', 'CurrentTeam', 'GP', 'Wins', 'Losses', 'SavePct', 'GAA', 'Shutouts', 'FairValue']
                                    ].copy()
                                    st.dataframe(
                                        goalie_table, use_container_width=True, hide_index=True,
                                        column_config={
                                            'FairValue': st.column_config.NumberColumn(f"{price_mode} ($)", format="$%.2f"),
                                            'SavePct': st.column_config.NumberColumn("SV%", format="%.3f"),
                                            'GAA': st.column_config.NumberColumn("GAA", format="%.2f"),
                                            'CurrentTeam': st.column_config.TextColumn("Team"),
                                        },
                                    )
                                else:
                                    st.info("No goalie data available.")

                            # ========== TAB 7: NATIONALITY ==========
                            with tab_nationality:
                                all_bios = get_all_player_bios()
                                if all_bios:
                                    nat_rows = []
                                    for _, row in nhl_df.iterrows():
                                        pname = row['PlayerName']
                                        bio = all_bios.get(pname)
                                        if bio and bio.get('birth_country'):
                                            nat_rows.append({
                                                'PlayerName': pname,
                                                'Country': bio['birth_country'],
                                                'FairValue': row['FairValue'],
                                                'Position': row.get('Position', ''),
                                                'Type': row.get('Type', 'skater'),
                                                'CurrentTeam': row.get('CurrentTeam', ''),
                                            })
                                    if nat_rows:
                                        nat_df = pd.DataFrame(nat_rows)
                                        nc1, nc2 = st.columns(2)
                                        with nc1:
                                            st.markdown("**Player Nationality Distribution**")
                                            country_counts = nat_df['Country'].value_counts().reset_index()
                                            country_counts.columns = ['Country', 'Count']
                                            fig_nat_pie = px.pie(
                                                country_counts, names='Country', values='Count',
                                                hole=0.4,
                                            )
                                            fig_nat_pie.update_layout(template="plotly_dark", height=350)
                                            st.plotly_chart(fig_nat_pie, use_container_width=True)

                                        with nc2:
                                            st.markdown("**Avg Card Price by Country** (3+ players)")
                                            country_avg = nat_df.groupby('Country').agg(
                                                AvgPrice=('FairValue', 'mean'),
                                                Count=('PlayerName', 'count')
                                            ).reset_index().sort_values('AvgPrice', ascending=False)
                                            country_sig = country_avg[country_avg['Count'] >= 3]
                                            fig_nat_bar = px.bar(
                                                country_sig, x='Country', y='AvgPrice',
                                                text='Count', color='AvgPrice',
                                                color_continuous_scale='Blues',
                                                labels={'AvgPrice': 'Avg Card Price ($)', 'Count': 'Players'},
                                            )
                                            fig_nat_bar.update_traces(texttemplate='%{text} cards', textposition='outside')
                                            fig_nat_bar.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                                            st.plotly_chart(fig_nat_bar, use_container_width=True)

                                        # Nationality scatter
                                        st.markdown("**Card Value by Country (All Players)**")
                                        fig_nat_scatter = px.strip(
                                            nat_df, x='Country', y='FairValue',
                                            hover_name='PlayerName',
                                            color='Country',
                                            labels={'FairValue': f'{price_mode} Value ($)'},
                                        )
                                        fig_nat_scatter.update_layout(template="plotly_dark", height=400, showlegend=False)
                                        st.plotly_chart(fig_nat_scatter, use_container_width=True)

                                        # Full table
                                        st.dataframe(
                                            country_avg.rename(columns={'AvgPrice': 'Avg Price', 'Count': 'Players'}),
                                            use_container_width=True, hide_index=True,
                                            column_config={
                                                'Avg Price': st.column_config.NumberColumn(format="$%.2f"),
                                            },
                                        )
                                    else:
                                        st.info("No nationality data found. Run `python scrape_nhl_stats.py --fetch-bios`")
                                else:
                                    st.info("Run `python scrape_nhl_stats.py --fetch-bios` to fetch nationality data.")

                            # ========== TAB 8: DRAFT ==========
                            with tab_draft:
                                all_bios_d = get_all_player_bios()
                                if all_bios_d:
                                    draft_rows = []
                                    undrafted_count = 0
                                    for _, row in nhl_df.iterrows():
                                        pname = row['PlayerName']
                                        bio = all_bios_d.get(pname)
                                        if not bio:
                                            continue
                                        if bio.get('draft_overall'):
                                            draft_rows.append({
                                                'PlayerName': pname,
                                                'DraftYear': bio['draft_year'],
                                                'DraftRound': bio['draft_round'],
                                                'DraftOverall': bio['draft_overall'],
                                                'DraftTeam': bio.get('draft_team', ''),
                                                'FairValue': row['FairValue'],
                                                'Position': row.get('Position', ''),
                                                'CurrentTeam': row.get('CurrentTeam', ''),
                                            })
                                        else:
                                            undrafted_count += 1
                                    if draft_rows:
                                        draft_df = pd.DataFrame(draft_rows)

                                        st.markdown("**Draft Position vs Card Value**")
                                        st.caption("Lower pick # = higher draft pick. Do top picks hold more card value?")
                                        fig_draft = px.scatter(
                                            draft_df, x='DraftOverall', y='FairValue',
                                            hover_name='PlayerName',
                                            color='DraftRound',
                                            size_max=12,
                                            hover_data={'DraftYear': True, 'CurrentTeam': True, 'DraftTeam': True},
                                            labels={'DraftOverall': 'Overall Pick #', 'FairValue': f'{price_mode} Value ($)', 'DraftRound': 'Round'},
                                        )
                                        fig_draft.update_layout(template="plotly_dark", height=450)
                                        st.plotly_chart(fig_draft, use_container_width=True)

                                        dc1, dc2 = st.columns(2)
                                        with dc1:
                                            st.markdown("**Avg Price by Draft Round**")
                                            round_avg = draft_df.groupby('DraftRound').agg(
                                                AvgPrice=('FairValue', 'mean'),
                                                Count=('PlayerName', 'count')
                                            ).reset_index().sort_values('DraftRound')
                                            fig_round = px.bar(
                                                round_avg, x='DraftRound', y='AvgPrice',
                                                text='Count', color='AvgPrice',
                                                color_continuous_scale='Greens',
                                                labels={'DraftRound': 'Round', 'AvgPrice': 'Avg Price ($)'},
                                            )
                                            fig_round.update_traces(texttemplate='%{text} cards', textposition='outside')
                                            fig_round.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                                            st.plotly_chart(fig_round, use_container_width=True)

                                        with dc2:
                                            st.markdown("**Draft Category Comparison**")
                                            draft_df['Category'] = draft_df['DraftOverall'].apply(
                                                lambda x: 'Top 5' if x <= 5 else 'Top 15' if x <= 15 else '1st Round' if x <= 32 else 'Later Rounds'
                                            )
                                            cat_order = ['Top 5', 'Top 15', '1st Round', 'Later Rounds']
                                            cat_avg = draft_df.groupby('Category').agg(
                                                AvgPrice=('FairValue', 'mean'),
                                                Count=('PlayerName', 'count')
                                            ).reindex(cat_order).reset_index()
                                            fig_cat = px.bar(
                                                cat_avg, x='Category', y='AvgPrice',
                                                text='Count', color='AvgPrice',
                                                color_continuous_scale='Blues',
                                                labels={'AvgPrice': 'Avg Price ($)'},
                                            )
                                            fig_cat.update_traces(texttemplate='%{text} cards', textposition='outside')
                                            fig_cat.update_layout(template="plotly_dark", height=350, coloraxis_showscale=False)
                                            st.plotly_chart(fig_cat, use_container_width=True)

                                        if undrafted_count > 0:
                                            st.caption(f"{undrafted_count} undrafted players not shown in chart")
                                    else:
                                        st.info("No draft data found. Run `python scrape_nhl_stats.py --fetch-bios`")
                                else:
                                    st.info("Run `python scrape_nhl_stats.py --fetch-bios` to fetch draft data.")

                            # ========== TAB 9: SEASONAL ==========
                            with tab_seasonal:
                                st.markdown("**Seasonal Price Trends**")
                                st.caption("How card prices move through the NHL season. Data accumulates over time from daily scrapes.")

                                # Load full price history and group by month
                                _seas_ph = load_yg_price_history()
                                _monthly_data = {}
                                _total_cards_tracked = 0
                                _total_data_points = 0
                                for cname, entries in _seas_ph.items():
                                    if len(entries) < 2:
                                        continue
                                    _total_cards_tracked += 1
                                    for i in range(1, len(entries)):
                                        prev_p = float(entries[i-1].get('fair_value', 0) or 0)
                                        cur_p = float(entries[i].get('fair_value', 0) or 0)
                                        if prev_p <= 0 or cur_p <= 0:
                                            continue
                                        pct = ((cur_p - prev_p) / prev_p) * 100
                                        dt = entries[i].get('date', '')
                                        if len(dt) >= 7:
                                            month_key = dt[:7]  # YYYY-MM
                                            _monthly_data.setdefault(month_key, []).append(pct)
                                            _total_data_points += 1

                                if _monthly_data:
                                    _month_rows = []
                                    for mk in sorted(_monthly_data.keys()):
                                        vals = _monthly_data[mk]
                                        _month_rows.append({
                                            'Month': mk,
                                            'Avg Change (%)': round(sum(vals) / len(vals), 2),
                                            'Median Change (%)': round(sorted(vals)[len(vals) // 2], 2),
                                            'Cards Moving': len(vals),
                                            'Gainers': len([v for v in vals if v > 0]),
                                            'Losers': len([v for v in vals if v < 0]),
                                        })
                                    _month_df = pd.DataFrame(_month_rows)

                                    sm1, sm2, sm3 = st.columns(3)
                                    sm1.metric("Months Tracked", len(_month_df))
                                    sm2.metric("Cards with History", _total_cards_tracked)
                                    sm3.metric("Data Points", _total_data_points)

                                    if len(_month_df) > 1:
                                        fig_seas = px.bar(
                                            _month_df, x='Month', y='Avg Change (%)',
                                            color='Avg Change (%)',
                                            color_continuous_scale='RdYlGn',
                                            color_continuous_midpoint=0,
                                            hover_data={'Median Change (%)': True, 'Cards Moving': True, 'Gainers': True, 'Losers': True},
                                        )
                                        fig_seas.update_layout(template="plotly_dark", height=350, xaxis_title="Month", yaxis_title="Avg Price Change (%)")
                                        st.plotly_chart(fig_seas, use_container_width=True)

                                    st.dataframe(_month_df, hide_index=True, use_container_width=True)

                                    # NHL season phase analysis
                                    _phase_map = {
                                        'Pre-Season (Sep)': ['09'],
                                        'Early Season (Oct-Nov)': ['10', '11'],
                                        'Mid Season (Dec-Jan)': ['12', '01'],
                                        'Trade Deadline (Feb)': ['02'],
                                        'Stretch Run (Mar)': ['03'],
                                        'Playoffs (Apr-Jun)': ['04', '05', '06'],
                                        'Off-Season (Jul-Aug)': ['07', '08'],
                                    }
                                    _phase_rows = []
                                    for phase, months in _phase_map.items():
                                        phase_vals = []
                                        for mk, vals in _monthly_data.items():
                                            if len(mk) >= 7 and mk[5:7] in months:
                                                phase_vals.extend(vals)
                                        if phase_vals:
                                            _phase_rows.append({
                                                'Season Phase': phase,
                                                'Avg Change (%)': round(sum(phase_vals) / len(phase_vals), 2),
                                                'Data Points': len(phase_vals),
                                            })
                                    if _phase_rows:
                                        st.markdown("**By NHL Season Phase**")
                                        _phase_df = pd.DataFrame(_phase_rows)
                                        fig_phase = px.bar(
                                            _phase_df, x='Season Phase', y='Avg Change (%)',
                                            color='Avg Change (%)',
                                            color_continuous_scale='RdYlGn',
                                            color_continuous_midpoint=0,
                                            text='Data Points',
                                        )
                                        fig_phase.update_traces(texttemplate='%{text} pts', textposition='outside')
                                        fig_phase.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_phase, use_container_width=True)
                                else:
                                    st.info("Seasonal trends will appear after multiple days of price scraping. The daily cron job is accumulating data — check back after a week of scrapes.")

                            # ========== TAB 10: TRENDS ==========
                            with tab_trends:
                                if len(corr_history) > 1:
                                    dates = sorted(corr_history.keys())
                                    trend_rows = []
                                    for d in dates:
                                        snap = corr_history[d]
                                        c = snap.get('correlations', {})
                                        trend_rows.append({
                                            'Date': d,
                                            'Points-Price R': c.get('points_vs_price', {}).get('r', 0),
                                            'Goals-Price R': c.get('goals_vs_price', {}).get('r', 0),
                                            'Skaters': snap.get('meta', {}).get('skaters_with_price', 0),
                                        })
                                    trend_df = pd.DataFrame(trend_rows)

                                    st.markdown("**Correlation Trend Over Time**")
                                    st.caption("Is the market becoming more efficient (higher R) or more hype-driven (lower R)?")
                                    fig_trend = go.Figure()
                                    fig_trend.add_trace(go.Scatter(
                                        x=trend_df['Date'], y=trend_df['Points-Price R'],
                                        mode='lines+markers', name='Points vs Price',
                                        line=dict(color='#636EFA', width=2),
                                    ))
                                    fig_trend.add_trace(go.Scatter(
                                        x=trend_df['Date'], y=trend_df['Goals-Price R'],
                                        mode='lines+markers', name='Goals vs Price',
                                        line=dict(color='#00CC96', width=2),
                                    ))
                                    fig_trend.update_layout(
                                        template="plotly_dark", height=350,
                                        yaxis_title="R-Value", xaxis_title="Date",
                                    )
                                    st.plotly_chart(fig_trend, use_container_width=True)

                                    # Tier trends
                                    tier_trend_rows = []
                                    for d in dates:
                                        snap = corr_history[d]
                                        for t in snap.get('tiers', []):
                                            tier_trend_rows.append({
                                                'Date': d,
                                                'Tier': t['label'],
                                                'Avg Price': t['avg_price'],
                                            })
                                    if tier_trend_rows:
                                        tt_df = pd.DataFrame(tier_trend_rows)
                                        st.markdown("**Price Tier Trends**")
                                        fig_tt = px.line(
                                            tt_df, x='Date', y='Avg Price', color='Tier',
                                            labels={'Avg Price': 'Avg Card Price ($)'},
                                        )
                                        fig_tt.update_layout(template="plotly_dark", height=350)
                                        st.plotly_chart(fig_tt, use_container_width=True)

                                    # Market efficiency indicator
                                    if len(trend_df) >= 2:
                                        first_r = trend_df.iloc[0]['Points-Price R']
                                        last_r = trend_df.iloc[-1]['Points-Price R']
                                        delta = last_r - first_r
                                        direction = "more efficient" if delta > 0.01 else "less efficient" if delta < -0.01 else "stable"
                                        st.info(f"Market trend: R moved from {first_r:.3f} to {last_r:.3f} ({delta:+.3f}) — market is becoming **{direction}**")
                                else:
                                    st.info("Correlation trends will appear after 2+ NHL stats scrapes on different days. Run the scraper periodically to build history.")

    # Season breakdown — moved into Market Overview expander above
