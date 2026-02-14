import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
from datetime import datetime

# Import utils
try:
    from dashboard_utils import (
        analyze_card_images, scrape_single_card, load_data, save_data, backup_data,
        parse_card_name, load_sales_history, append_price_history, load_price_history,
        append_portfolio_snapshot, load_portfolio_history, scrape_graded_comparison,
        archive_card, load_archive, restore_card,
        get_user_paths, load_users, verify_password, init_user_data,
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

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; padding: 15px; border-radius: 5px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
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
# LOGIN GATE
# ============================================================
if not public_view:
    users_config = load_users()

    # If no users.yaml exists or is empty, fall back to env var password (backward compat)
    if not users_config:
        correct_pw = os.environ.get("DASHBOARD_PASSWORD", "")
        if correct_pw and not st.session_state.get("authenticated"):
            st.title("Hockey Card Collection Dashboard")
            password = st.text_input("Enter password to access the dashboard", type="password")
            if st.button("Login", type="primary"):
                if password == correct_pw:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
            st.stop()
    else:
        # Multi-user login
        if not st.session_state.get("authenticated"):
            st.title("Hockey Card Collection Dashboard")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Login", type="primary"):
                if verify_password(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.display_name = users_config[username].get('display_name', username)
                    # Clear any stale data from previous user
                    st.session_state.pop('df', None)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            st.stop()

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
if public_view:
    nav_pages = ["Charts", "Card Inspect"]
else:
    nav_pages = ["Charts", "Card Ledger", "Card Inspect"]
if 'nav_page' in st.session_state and st.session_state.nav_page in nav_pages:
    st.session_state['_nav_radio'] = st.session_state.nav_page
    del st.session_state.nav_page

page = st.sidebar.radio("Navigate", nav_pages, key="_nav_radio")

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
                        'Num Sales': stats['num_sales']
                    }])
                    append_price_history(card_name, stats['fair_price'], stats['num_sales'], history_path=_history_path)
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

st.caption(f"Data last updated: {last_modified}")
st.divider()

# ============================================================
# CHARTS PAGE
# ============================================================
if page == "Charts":
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
    st.subheader("Portfolio Value Over Time")
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

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Current Value", f"${latest['total_value']:,.2f}",
                    delta=f"${value_change:+,.2f}")
        pc2.metric("Total Cards", int(latest['total_cards']))
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
    st.subheader("Edit Card Values")

    # Collection summary metrics
    total_cards = len(df)
    total_value = df['Fair Value'].sum()
    avg_value = df['Fair Value'].mean() if total_cards > 0 else 0
    top_card_idx = df['Fair Value'].idxmax() if total_cards > 0 else None
    top_card_name = parse_card_name(df.at[top_card_idx, 'Card Name'])['Player'] if top_card_idx is not None else "N/A"
    top_card_val = df.at[top_card_idx, 'Fair Value'] if top_card_idx is not None else 0

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Total Cards", total_cards)
    mcol2.metric("Collection Value", f"${total_value:,.2f}")
    mcol3.metric("Avg Card Value", f"${avg_value:,.2f}")
    mcol4.metric("Most Valuable", f"{top_card_name}", delta=f"${top_card_val:,.2f}")

    st.markdown("---")

    # Search bar (full width)
    search_query = st.text_input("Search cards", placeholder="Search by player, set, year, card number...")

    # Filter row
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        sets = sorted(df['Set'].dropna().unique().tolist())
        sets = [s for s in sets if s]
        set_filter = st.selectbox("Set", ["All Sets"] + sets)
    with fcol2:
        trend_options = sorted(df['Trend'].unique().tolist())
        trend_filter = st.multiselect("Trend", options=trend_options, default=trend_options)
    with fcol3:
        grade_filter = st.selectbox("Grade", ["All", "Raw", "Graded"])

    # Apply filters
    mask = df['Trend'].isin(trend_filter)
    if set_filter != "All Sets":
        mask &= df['Set'] == set_filter
    if grade_filter == "Raw":
        mask &= df['Grade'] == ''
    elif grade_filter == "Graded":
        mask &= df['Grade'] != ''
    filtered_df = df[mask].copy()

    display_cols = ['Player', 'Set', 'Subset', 'Card #', 'Serial', 'Grade', 'Fair Value', 'Trend', 'Num Sales', 'Min', 'Max', 'Top 3 Prices', 'Last Scraped']
    edit_df = filtered_df[display_cols].copy()
    edit_df['Top 3 Prices'] = edit_df['Top 3 Prices'].fillna('')
    edit_df['Last Scraped'] = edit_df['Last Scraped'].fillna('')

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
                 'Num Sales', 'Fair Value', 'Min', 'Max', 'Trend',
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

    bcol1, bcol2 = st.columns([1, 1])
    with bcol1:
        if st.button("Save Changes", type="primary"):
            for i, row in edited.iterrows():
                idx = edit_df.index[i] if i < len(edit_df.index) else None
                if idx is not None and idx in st.session_state.df.index:
                    st.session_state.df.at[idx, 'Fair Value'] = row['Fair Value']
                    # Strip emoji prefix from trend before saving
                    raw_trend = row['Trend'].split(' ', 1)[-1] if isinstance(row['Trend'], str) else row['Trend']
                    st.session_state.df.at[idx, 'Trend'] = raw_trend
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
                        'Num Sales': 0
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
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            st.metric("Player", card_row['Player'])
        with dc2:
            st.metric("Set", card_row['Set'] if card_row['Set'] else "N/A")
        with dc3:
            st.metric("Subset", card_row['Subset'] if card_row['Subset'] else "Base")

        dc4, dc5, dc6, dc7 = st.columns(4)
        with dc4:
            st.metric("Card #", card_row['Card #'] if card_row['Card #'] else "N/A")
        with dc5:
            st.metric("Serial", card_row['Serial'] if card_row['Serial'] else "N/A")
        with dc6:
            st.metric("Grade", card_row['Grade'] if card_row['Grade'] else "Raw")

        vc1, vc2, vc3, vc4, vc5 = st.columns(5)
        with vc1:
            st.metric("Fair Value", f"${card_row['Fair Value']:.2f}")
        with vc2:
            st.metric("Trend", card_row['Trend'])
        with vc3:
            st.metric("Sales Found", int(card_row['Num Sales']))
        with vc4:
            st.metric("Min", f"${card_row['Min']:.2f}")
        with vc5:
            st.metric("Max", f"${card_row['Max']:.2f}")

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
        st.subheader("Fair Value Tracking")
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
            st.subheader("Grading ROI Calculator")
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
        st.subheader("eBay Sales History")
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
