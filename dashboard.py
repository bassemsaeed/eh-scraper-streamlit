import streamlit as st
import pandas as pd
import json
import os

# Set page config
st.set_page_config(layout="wide", page_title="Electric House Scraper Dashboard")

# Title
st.title("Electric House Data Viewer")

# Load Data
@st.cache_data
def load_data():
    file_path = "output.json"
    if not os.path.exists(file_path):
        return pd.DataFrame()
    
    with open(file_path, "r") as f:
        try:
            data = json.load(f)
            # Ensure it's a list (scrapy output might be a list of dicts)
            if isinstance(data, list):
                return pd.DataFrame(data)
            else:
                return pd.DataFrame()
        except json.JSONDecodeError:
            return pd.DataFrame()

df = load_data()

if df.empty:
    st.warning("No data found in `output.json`. Please run the scraper first.")
else:
    # Sidebar Filters
    st.sidebar.header("Filters")
    
    # Filter by Stock Status
    all_statuses = df["stock_status"].unique().tolist()
    selected_statuses = st.sidebar.multiselect("Stock Status", all_statuses, default=all_statuses)
    
    # Filter by Price Range
    min_price = float(df["final_price"].min())
    max_price = float(df["final_price"].max())
    price_range = st.sidebar.slider("Price Range (SAR)", min_price, max_price, (min_price, max_price))
    
    # Apply filters
    filtered_df = df[
        (df["stock_status"].isin(selected_statuses)) &
        (df["final_price"] >= price_range[0]) &
        (df["final_price"] <= price_range[1])
    ]

    # Metrics
    st.header("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Products", len(filtered_df))
    
    with col2:
        in_stock_count = len(filtered_df[filtered_df["stock_status"] == "IN_STOCK"])
        st.metric("In Stock", in_stock_count)
    
    with col3:
        out_stock_count = len(filtered_df[filtered_df["stock_status"] == "OUT_OF_STOCK"])
        st.metric("Out of Stock", out_stock_count)
        
    with col4:
        avg_price = filtered_df["final_price"].mean()
        st.metric("Avg Final Price", f"{avg_price:.2f} SAR")

    # Data Display
    st.header("Product Data")
    
    # Show dataframe with images
    # We can't render images directly in standard st.dataframe easily without column config
    # configuring the image column
    
    st.dataframe(
        filtered_df[["image_url", "name", "sku", "final_price", "regular_price", "stock_status", "url_key"]],
        column_config={
            "image_url": st.column_config.ImageColumn(
                "Preview", help="Product Image"
            ),
            "final_price": st.column_config.NumberColumn(
                "Final Price", format="%.2f SAR"
            ),
             "regular_price": st.column_config.NumberColumn(
                "Reg. Price", format="%.2f SAR"
            )
        },
        use_container_width=True,
        hide_index=True,
        height=600
    )
    
    # Charts
    st.header("Visualizations")
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Price Distribution")
        st.bar_chart(filtered_df["final_price"])
        
    with col_chart2:
        st.subheader("Stock Status Distribution")
        stock_counts = filtered_df["stock_status"].value_counts()
        st.bar_chart(stock_counts)

    # Raw Json view for selected item (optional, maybe simple search)
    st.header("Inspector")
    search_term = st.text_input("Search by SKU or Name")
    if search_term:
        results = filtered_df[
            filtered_df["name"].str.contains(search_term, case=False) | 
            filtered_df["sku"].str.contains(search_term, case=False)
        ]
        if not results.empty:
            st.json(results.iloc[0].to_dict())
        else:
            st.info("No matching products found.")
