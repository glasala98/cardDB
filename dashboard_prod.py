import streamlit as st
import pandas as pd
import plotly.express as px
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "card_prices_summary.csv")

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
st.sidebar.header("Add New Card")

with st.sidebar.form("add_card_form", clear_on_submit=True):
    new_name = st.text_input("Card Name")
    new_value = st.number_input("Estimated Value ($)", min_value=0.0, value=5.0, step=0.50)
    add_submitted = st.form_submit_button("Add Card")

if add_submitted and new_name.strip():
    card_name = new_name.strip()
    new_row = pd.DataFrame([{
        'Card Name': card_name,
        'Fair Value': new_value,
        'Trend': 'no data',
        'Top 3 Prices': '',
        'Median (All)': new_value,
        'Min': new_value,
        'Max': new_value,
        'Num Sales': 0
    }])
    st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
    save_data(st.session_state.df)
    st.session_state.df = load_data()
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
