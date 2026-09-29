"""
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

"""
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Makeup Inventory Management System", layout="wide")

# --- Credentials Retrieval ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
ADMIN_USERNAME = st.secrets.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "admin123")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ Supabase credentials missing from Streamlit Secrets.")
    st.stop()


@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Failed to connect to Supabase: {e}")
    st.stop()

# --- Session State for Auth ---
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

# --- Sidebar Auth Controls ---
st.sidebar.title("🔐 Access Control")

if st.session_state["is_admin"]:
    st.sidebar.success("Logged in as Admin")
    if st.sidebar.button("Logout"):
        st.session_state["is_admin"] = False
        st.rerun()
else:
    with st.sidebar.expander("Admin Login"):
        username_input = st.text_input("Username", key="login_user")
        password_input = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In"):
            if username_input == ADMIN_USERNAME and password_input == ADMIN_PASSWORD:
                st.session_state["is_admin"] = True
                st.sidebar.success("Authenticated!")
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials.")

st.sidebar.divider()

# --- Product Management Form (Admin Only) ---
if st.session_state["is_admin"]:
    st.sidebar.header("Product Management")

    # Inputs allow empty strings or defaults
    brand_input = st.sidebar.text_input("Brand", placeholder="e.g., Fenty Beauty").strip()
    name_input = st.sidebar.text_input("Product Name", placeholder="e.g., Foundation").strip()

    # Updated Categories: Areas of the face
    category = st.sidebar.selectbox(
        "Category / Area",
        ["Uncategorized", "Eyes", "Ears", "Nose", "Lips", "Cheeks", "Other"]
    )

    tone_input = st.sidebar.text_input("Tone / Shade", placeholder="e.g., Warm Nude").strip()
    qty_input = st.sidebar.number_input("Quantity", min_value=0, step=1, value=0)
    price_input = st.sidebar.number_input("Price ($)", min_value=0.0, step=0.5, value=0.0, format="%.2f")
    uploaded_file = st.sidebar.file_uploader("Product Image (Optional)", type=["png", "jpg", "jpeg", "webp"])

    if st.sidebar.button("Add New Item", type="primary"):
        # Handle empty string or null inputs with sensible defaults
        brand = brand_input if brand_input else "N/A"
        product_name = name_input if name_input else "Unnamed Item"
        tone = tone_input if tone_input else "N/A"
        qty = int(qty_input) if qty_input is not None else 0
        price = float(price_input) if price_input is not None else 0.0

        # Upload image if provided
        image_url = None
        if uploaded_file is not None:
            try:
                file_bytes = uploaded_file.read()
                clean_filename = f"{brand}_{product_name}_{uploaded_file.name}".replace(" ", "_").lower()
                supabase.storage.from_("product_images").upload(
                    clean_filename, file_bytes, {"content-type": uploaded_file.type}
                )
                image_url = supabase.storage.from_("product_images").get_public_url(clean_filename)
            except Exception as img_err:
                st.sidebar.warning(f"Could not upload image: {img_err}")

        # Construct database record
        data = {
            "brand": brand,
            "product_name": product_name,
            "category": category,
            "tone": tone,
            "quantity": qty,
            "price": price,
            "image_url": image_url
        }

        try:
            supabase.table("inventory").insert(data).execute()
            st.sidebar.success("Item added successfully!")
            st.rerun()
        except Exception as db_err:
            st.sidebar.error(f"Database Error: {db_err}")

else:
    st.sidebar.info("👀 Viewing in Read-Only Mode. Log in as Admin to edit records or add new items.")

# --- Main Section: Public Search & Data Display ---
st.title("💅 Makeup Inventory System")

search_query = st.text_input("🔍 Search by Brand or Name...", "").strip()

try:
    query = supabase.table("inventory").select("*")
    if search_query:
        query = query.or_(f"brand.ilike.%{search_query}%,product_name.ilike.%{search_query}%")

    response = query.execute()
    items = response.data or []
except Exception as fetch_err:
    st.error(f"Error fetching data: {fetch_err}")
    items = []

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Inventory Records")
    if items:
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
    selected_id = st.number_input("Enter ID to Inspect", min_value=1, step=1)

    selected_item = next((item for item in items if item["id"] == selected_id), None)
    if selected_item:
        st.write(f"**{selected_item['brand']}** - {selected_item['product_name']}")
        st.write(f"Category: {selected_item['category']} | Shade: {selected_item['tone']}")
        st.write(f"Stock: {selected_item['quantity']} | Price: ${selected_item['price']:.2f}")

        if selected_item.get("image_url"):
            st.image(selected_item["image_url"], use_column_width=True)

        if st.session_state["is_admin"]:
            if st.button("🗑️ Delete Item", type="secondary"):
                try:
                    supabase.table("inventory").delete().eq("id", selected_id).execute()
                    st.success(f"Item #{selected_id} deleted!")
                    st.rerun()
                except Exception as del_err:
                    st.error(f"Failed to delete item: {del_err}")