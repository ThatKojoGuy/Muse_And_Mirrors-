import streamlit as st
from supabase import create_client, Client
import os

# Set page layout
st.set_page_config(page_title="Makeup Inventory", layout="wide")

# --- Supabase Credentials ---
# For local testing, add these to your environment or .env file
# When deployed to Streamlit Cloud, add these under "Secrets"
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "YOUR_SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "YOUR_SUPABASE_ANON_KEY")


@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = init_supabase()

st.title("💅 Makeup Inventory Management System")

# --- Sidebar Input Form ---
st.sidebar.header("Product Details")

brand = st.sidebar.text_input("Brand", placeholder="e.g. Fenty Beauty")
name = st.sidebar.text_input("Product Name", placeholder="e.g. Foundation")
category = st.sidebar.selectbox(
    "Category",
    ["Uncategorized", "Foundation", "Concealer", "Lipstick", "Eyeshadow", "Blush", "Powder", "Other"]
)
tone = st.sidebar.text_input("Tone / Shade", placeholder="e.g. Warm Nude")
qty = st.sidebar.number_input("Quantity", min_value=0, step=1, value=1)
price = st.sidebar.number_input("Price ($)", min_value=0.0, step=0.5, format="%.2f")
uploaded_file = st.sidebar.file_uploader("Product Image", type=["png", "jpg", "jpeg", "webp"])

# --- Add Record Functionality ---
if st.sidebar.button("Add New Item", type="primary"):
    image_url = None

    # Upload image to Supabase Bucket if selected
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_name = f"{brand}_{name}_{uploaded_file.name}".replace(" ", "_").lower()

        # Upload file to 'product_images' bucket in Supabase
        upload_res = supabase.storage.from_("product_images").upload(
            file_name, file_bytes, {"content-type": uploaded_file.type}
        )
        image_url = supabase.storage.from_("product_images").get_public_url(file_name)

    # Insert row into Supabase Database
    data = {
        "brand": brand or "N/A",
        "product_name": name or "Unnamed Item",
        "category": category,
        "tone": tone or "N/A",
        "quantity": qty,
        "price": price,
        "image_url": image_url
    }

    supabase.table("inventory").insert(data).execute()
    st.sidebar.success("Item added successfully!")
    st.rerun()

# --- Main View: Search & Table ---
search_query = st.text_input("🔍 Search by Brand or Name...", "")

# Query data from cloud database
query = supabase.table("inventory").select("*")
if search_query:
    query = query.or_(f"brand.ilike.%{search_query}%,product_name.ilike.%{search_query}%")

response = query.execute()
items = response.data

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Inventory Records")
    if items:
        # Display editable data table
        st.dataframe(
            items,
            column_config={
                "image_url": st.column_config.LinkColumn("Image Link"),
                "price": st.column_config.NumberColumn("Price ($)", format="$%.2f")
            },
            use_container_width=True
        )
    else:
        st.info("No items found.")

with col2:
    st.subheader("Item Preview")
    selected_id = st.number_input("Enter ID to Preview/Delete", min_value=1, step=1)

    selected_item = next((item for item in items if item["id"] == selected_id), None)
    if selected_item:
        st.write(f"**{selected_item['brand']}** - {selected_item['product_name']}")
        st.write(f"Category: {selected_item['category']} | Shade: {selected_item['tone']}")
        st.write(f"Stock: {selected_item['quantity']} | Price: ${selected_item['price']:.2f}")

        if selected_item["image_url"]:
            st.image(selected_item["image_url"], use_column_width=True)

        if st.button("🗑️ Delete Item", type="secondary"):
            supabase.table("inventory").delete().eq("id", selected_id).execute()
            st.success("Item deleted!")
            st.rerun()