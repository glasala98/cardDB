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
        analyze_card_images, scrape_single_card, load_data, save_data,
        parse_card_name, CSV_PATH, MONEY_COLS, PARSED_COLS
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
# PASSWORD GATE
# ============================================================
def check_password():
    correct_pw = os.environ.get("DASHBOARD_PASSWORD", "")
    if not correct_pw:
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("Hockey Card Collection Dashboard")
    password = st.text_input("Enter password to access the dashboard", type="password")
    if st.button("Login", type="primary"):
        if password == correct_pw:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

check_password()

# --- Load or initialize data in session state ---
if 'df' not in st.session_state:
    st.session_state.df = load_data()
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

df = st.session_state.df

# ============================================================
# SIDEBAR - Navigation + Conditional Scan/Add Card
# ============================================================
page = st.sidebar.radio("Navigate", ["Charts", "Card Ledger"])

# Show Scan Card and Add New Card only on Card Ledger page
if page == "Card Ledger":
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
            variant = st.text_input("Variant / Parallel", value=scanned.get('variant', ''), placeholder="e.g. Red Prism, Arctic Freeze (optional)")
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
                        save_data(st.session_state.df)
                        st.session_state.df = load_data()
                        st.sidebar.success(f"Imported {len(import_df)} cards!")
                        st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Import failed: {e}")

# ============================================================
# HEADER & METRICS
# ============================================================
st.title("Hockey Card Collection Dashboard")

found_df = df[df['Num Sales'] > 0]
not_found_df = df[df['Num Sales'] == 0]
total_value = found_df['Fair Value'].sum()
total_all = df['Fair Value'].sum()

# Last Updated timestamp
csv_path = CSV_PATH
last_modified = ""
try:
    mtime = os.path.getmtime(csv_path)
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

# ============================================================
# CARD LEDGER PAGE
# ============================================================
elif page == "Card Ledger":
    st.subheader("Edit Card Values")

    # Search bar (full width)
    search_query = st.text_input("Search cards", placeholder="Search by player, set, year, card number...")

    # Filter row
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        years = sorted(df['Year'].dropna().unique().tolist(), reverse=True)
        years = [y for y in years if y]
        year_filter = st.selectbox("Year", ["All Years"] + years)
    with fcol2:
        sets = sorted(df['Set'].dropna().unique().tolist())
        sets = [s for s in sets if s]
        set_filter = st.selectbox("Set", ["All Sets"] + sets)
    with fcol3:
        trend_options = sorted(df['Trend'].unique().tolist())
        trend_filter = st.multiselect("Trend", options=trend_options, default=trend_options)
    with fcol4:
        grade_filter = st.selectbox("Grade", ["All", "Raw", "Graded"])

    # Apply filters
    mask = df['Trend'].isin(trend_filter)
    if year_filter != "All Years":
        mask &= df['Year'] == year_filter
    if set_filter != "All Sets":
        mask &= df['Set'] == set_filter
    if grade_filter == "Raw":
        mask &= df['Grade'] == ''
    elif grade_filter == "Graded":
        mask &= df['Grade'] != ''
    filtered_df = df[mask].copy()

    display_cols = ['Player', 'Year', 'Set', 'Card #', 'Grade', 'Fair Value', 'Trend', 'Num Sales', 'Min', 'Max']
    edit_df = filtered_df[display_cols].copy()

    if search_query.strip():
        terms = search_query.strip().lower().split()
        searchable = filtered_df['Card Name'].str.lower()
        mask = searchable.apply(lambda name: all(t in name for t in terms))
        edit_df = edit_df[mask].copy()

    st.caption(f"Showing {len(edit_df)} of {len(df)} cards")

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Player": st.column_config.TextColumn("Player", width="medium"),
            "Year": st.column_config.TextColumn("Year", width="small", disabled=True),
            "Set": st.column_config.TextColumn("Set", width="medium", disabled=True),
            "Card #": st.column_config.TextColumn("#", width="small", disabled=True),
            "Grade": st.column_config.TextColumn("Grade", width="small", disabled=True),
            "Fair Value": st.column_config.NumberColumn("Fair Value ($)", format="$%.2f", min_value=0),
            "Trend": st.column_config.SelectboxColumn("Trend", options=["up", "down", "stable", "no data"]),
            "Num Sales": st.column_config.NumberColumn("Sales", disabled=True),
            "Min": st.column_config.NumberColumn("Min ($)", format="$%.2f", disabled=True),
            "Max": st.column_config.NumberColumn("Max ($)", format="$%.2f", disabled=True),
        },
        key="card_editor"
    )

    bcol1, bcol2, bcol3, bcol4 = st.columns([1, 1, 1, 3])
    with bcol1:
        if st.button("Save Changes", type="primary"):
            for i, row in edited.iterrows():
                idx = edit_df.index[i] if i < len(edit_df.index) else None
                if idx is not None and idx in st.session_state.df.index:
                    st.session_state.df.at[idx, 'Fair Value'] = row['Fair Value']
                    st.session_state.df.at[idx, 'Trend'] = row['Trend']
                    # Update Player in parsed col and rebuild Card Name
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
                    new_row = {
                        'Card Name': card_name,
                        'Fair Value': r['Fair Value'],
                        'Trend': r['Trend'],
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

            save_data(st.session_state.df)
            st.success("Saved to CSV!")
            st.rerun()

    with bcol2:
        if st.button("Reload from File"):
            st.session_state.df = load_data()
            st.rerun()

    with bcol3:
        # Build rescrape options from filtered_df (which still has Card Name)
        rescrape_options = filtered_df.loc[edit_df.index, 'Card Name'].tolist() if len(edit_df) > 0 else []
        rescrape_labels = {cn: filtered_df.loc[filtered_df['Card Name'] == cn, 'Player'].iloc[0] if len(filtered_df[filtered_df['Card Name'] == cn]) > 0 else cn[:50] for cn in rescrape_options}
        rescrape_card = st.selectbox(
            "Rescrape card",
            options=[""] + rescrape_options,
            format_func=lambda x: "Select a card..." if x == "" else rescrape_labels.get(x, x[:50]),
            label_visibility="collapsed"
        )

    with bcol4:
        if st.button("Rescrape Price", disabled=rescrape_card == ""):
            if rescrape_card:
                with st.spinner(f"Scraping eBay for updated price..."):
                    stats = scrape_single_card(rescrape_card)
                if stats and stats.get('num_sales', 0) > 0:
                    idx = st.session_state.df[st.session_state.df['Card Name'] == rescrape_card].index
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
                        save_data(st.session_state.df)
                        st.success(f"Updated! Fair value: ${stats['fair_price']:.2f} ({stats['num_sales']} sales)")
                        st.rerun()
                else:
                    st.warning("No sales found for this card.")

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
        nf_display = not_found_df[['Player', 'Year', 'Set', 'Card #', 'Fair Value']].reset_index(drop=True)
        edited_nf = st.data_editor(
            nf_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Player": st.column_config.TextColumn("Player", width="medium", disabled=True),
                "Year": st.column_config.TextColumn("Year", width="small", disabled=True),
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
            save_data(st.session_state.df)
            st.success("Not Found prices saved!")
            st.rerun()
    else:
        st.info("All cards have sales data!")
