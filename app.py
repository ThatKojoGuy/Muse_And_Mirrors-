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

st.set_page_config(page_title="Muse And Mirrors Inventory System", layout="wide")

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
    price_input = st.sidebar.number_input("Price", min_value=0.0, step=0.5, value=0.0, format="%.2f")
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
                "price": st.column_config.NumberColumn("Price", format="%.2f")
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
        st.write(f"Stock: {selected_item['quantity']} | Price: {selected_item['price']:.2f}")

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

import streamlit as st
from supabase import create_client, Client
import pandas as pd

# --- Page Configuration ---
st.set_page_config(
    page_title="Muse & Mirrors | Studio POS & Inventory",
    page_icon="💅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main { background-color: #0E1117; }
    .product-card {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .price-tag { font-size: 18px; font-weight: bold; color: #3FB950; }
    .category-badge {
        background-color: #21262D; color: #58A6FF;
        font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 12px;
    }
    .shade-badge {
        background-color: #21262D; color: #8B949E;
        font-size: 11px; padding: 3px 8px; border-radius: 12px;
    }
    .status-available {
        background-color: #1F3A2B; color: #3FB950;
        font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; border: 1px solid #238636;
    }
    .status-soldout {
        background-color: #3D1E24; color: #F8514C;
        font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; border: 1px solid #DA3633;
    }
</style>
""", unsafe_allow_html=True)

# --- Credentials & Initialization ---
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

# --- Initialize Session States ---
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "cart" not in st.session_state:
    st.session_state["cart"] = {}

CATEGORIES = ["Uncategorized", "Eyes", "Ears", "Nose", "Lips", "Cheeks", "Other"]

# --- Fetch Data ---
try:
    inv_response = supabase.table("inventory").select("*").order("created_at", desc=True).execute()
    inventory_items = inv_response.data or []

    sales_response = supabase.table("sales").select("*").order("created_at", desc=True).execute()
    sales_history = sales_response.data or []
except Exception as err:
    st.error(f"Data fetch error: {err}")
    inventory_items, sales_history = [], []

# Dynamic auto-complete dropdown values from existing items
existing_brands = sorted(list(set(item["brand"] for item in inventory_items if item.get("brand"))))
existing_names = sorted(list(set(item["product_name"] for item in inventory_items if item.get("product_name"))))

# --- Sidebar Controls ---
with st.sidebar:
    st.title("💅 Studio Controls")

    # Access Control Widget
    with st.expander("🔐 Access Control", expanded=not st.session_state["is_admin"]):
        if st.session_state["is_admin"]:
            st.success("Authenticated as Admin")
            if st.button("Log Out", type="secondary", use_container_width=True):
                st.session_state["is_admin"] = False
                st.rerun()
        else:
            user = st.text_input("Username", key="login_user")
            pwd = st.text_input("Password", type="password", key="login_pass")
            if st.button("Log In", type="primary", use_container_width=True):
                if user == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
                    st.session_state["is_admin"] = True
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

    st.divider()

    # Product Add Management (Admin Only)
    if st.session_state["is_admin"]:
        st.subheader("➕ Add New Product")

        # Excel-style Brand selection/creation dropdown
        brand_choice = st.selectbox(
            "Brand Name",
            options=["➕ Add New Brand"] + existing_brands,
            key="add_brand_select"
        )
        if brand_choice == "➕ Add New Brand":
            brand = st.text_input("Enter New Brand", placeholder="e.g., Fenty Beauty", key="add_brand_custom").strip()
        else:
            brand = brand_choice

        # Excel-style Product Name selection/creation dropdown
        name_choice = st.selectbox(
            "Product Name",
            options=["➕ Add New Product Name"] + existing_names,
            key="add_name_select"
        )
        if name_choice == "➕ Add New Product Name":
            name = st.text_input("Enter New Product Name", placeholder="e.g., Foundation", key="add_name_custom").strip()
        else:
            name = name_choice

        category = st.selectbox("Target Area", CATEGORIES, key="add_cat")
        tone = st.text_input("Tone / Shade", placeholder="e.g., Warm Nude", key="add_tone").strip()
        qty = st.number_input("Stock Quantity", min_value=0, step=1, value=1, key="add_qty")
        price = st.number_input("Retail Price ($)", min_value=0.0, step=0.5, value=0.0, format="%.2f", key="add_price")
        uploaded_file = st.file_uploader("Product Image", type=["png", "jpg", "jpeg", "webp"], key="add_img")

        if st.button("Save New Product", type="primary", use_container_width=True):
            image_url = None
            if uploaded_file is not None:
                try:
                    file_bytes = uploaded_file.read()
                    clean_filename = f"{brand}_{name}_{uploaded_file.name}".replace(" ", "_").lower()
                    supabase.storage.from_("product_images").upload(clean_filename, file_bytes, {"content-type": uploaded_file.type})
                    image_url = supabase.storage.from_("product_images").get_public_url(clean_filename)
                except Exception as img_err:
                    st.warning(f"Image notice: {img_err}")

            data = {
                "brand": brand or "N/A",
                "product_name": name or "Unnamed Item",
                "category": category,
                "tone": tone or "N/A",
                "quantity": int(qty),
                "price": float(price),
                "image_url": image_url
            }

            try:
                supabase.table("inventory").insert(data).execute()
                st.success("Saved to database!")
                st.rerun()
            except Exception as db_err:
                st.error(f"Database Error: {db_err}")
    else:
        st.info("💡 **Viewer Mode**: Log in as Admin above to add, edit, or delete inventory.")

# Metrics Calculations
total_products = len(inventory_items)
total_stock = sum(item.get("quantity", 0) for item in inventory_items)
total_inventory_val = sum(item.get("quantity", 0) * item.get("price", 0.0) for item in inventory_items)
total_revenue = sum(sale.get("total_amount", 0.0) for sale in sales_history)

# --- Header & Analytics ---
st.title("✨ Muse & Mirrors Studio POS")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Unique Items", total_products)
m2.metric("In-Stock Units", total_stock)
m3.metric("Inventory Value", f"${total_inventory_val:,.2f}")
m4.metric("Total Revenue Realized", f"${total_revenue:,.2f}")

st.divider()

# --- Tabs ---
tab_pos, tab_catalog, tab_manage, tab_analytics = st.tabs([
    "🛒 Checkout POS",
    "🖼️ Visual Catalog",
    "⚙️ Edit & Delete (Admin)",
    "📈 Sales & Revenue"
])

# ==========================================
# TAB 1: POS CHECKOUT
# ==========================================
with tab_pos:
    pos_col1, pos_col2 = st.columns([2, 1])

    with pos_col1:
        st.subheader("Select Products")
        pos_search = st.text_input("🔍 Search product or brand name...", key="pos_search").strip().lower()

        pos_items = [
            item for item in inventory_items
            if pos_search in item.get("brand", "").lower() or pos_search in item.get("product_name", "").lower()
        ]

        grid_cols = st.columns(2)
        for idx, item in enumerate(pos_items):
            with grid_cols[idx % 2]:
                st.markdown('<div class="product-card">', unsafe_allow_html=True)
                st.markdown(f"**{item['brand']}** - {item['product_name']}")

                # Status Tag
                status_html = "<span class='status-available'>AVAILABLE</span>" if item['quantity'] > 0 else "<span class='status-soldout'>SOLD OUT</span>"
                st.markdown(f"{status_html} &nbsp; • &nbsp; <span class='price-tag'>${item['price']:.2f}</span> | Stock: {item['quantity']}", unsafe_allow_html=True)
                st.write("")

                if item["quantity"] > 0:
                    if st.button("➕ Add to Cart", key=f"add_cart_{item['id']}", use_container_width=True):
                        current_cart_qty = st.session_state["cart"].get(item["id"], {}).get("qty", 0)
                        if current_cart_qty < item["quantity"]:
                            st.session_state["cart"][item["id"]] = {
                                "item": item,
                                "qty": current_cart_qty + 1
                            }
                            st.rerun()
                        else:
                            st.warning("Stock limit reached!")
                else:
                    st.error("Item Sold Out")
                st.markdown('</div>', unsafe_allow_html=True)

    with pos_col2:
        st.subheader("Active Order")
        if not st.session_state["cart"]:
            st.info("Cart is empty.")
        else:
            subtotal = 0.0
            for item_id, cart_data in list(st.session_state["cart"].items()):
                item = cart_data["item"]
                qty = cart_data["qty"]
                item_total = qty * item["price"]
                subtotal += item_total

                st.write(f"**{item['brand']} - {item['product_name']}**")
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"${item['price']:.2f} x {qty}")
                c2.write(f"**${item_total:.2f}**")
                if c3.button("❌", key=f"remove_cart_{item_id}"):
                    del st.session_state["cart"][item_id]
                    st.rerun()
                st.divider()

            tax = subtotal * 0.05
            grand_total = subtotal + tax

            st.write(f"**Subtotal:** ${subtotal:,.2f}")
            st.write(f"**Tax (5%):** ${tax:,.2f}")
            st.markdown(f"### Grand Total: `${grand_total:,.2f}`")

            if st.button("💳 Complete Transaction", type="primary", use_container_width=True):
                try:
                    sale_payload = {
                        "total_amount": grand_total,
                        "items_sold": [
                            {
                                "brand": data["item"]["brand"],
                                "product_name": data["item"]["product_name"],
                                "quantity": data["qty"],
                                "unit_price": data["item"]["price"]
                            }
                            for data in st.session_state["cart"].values()
                        ]
                    }
                    supabase.table("sales").insert(sale_payload).execute()

                    for data in st.session_state["cart"].values():
                        new_stock = data["item"]["quantity"] - data["qty"]
                        supabase.table("inventory").update({"quantity": new_stock}).eq("id", data["item"]["id"]).execute()

                    st.session_state["cart"] = {}
                    st.balloons()
                    st.success("Transaction recorded!")
                    st.rerun()

                except Exception as checkout_err:
                    st.error(f"Checkout error: {checkout_err}")

# ==========================================
# TAB 2: VISUAL CATALOG
# ==========================================
with tab_catalog:
    col_cat_search, col_status_filter = st.columns([3, 1])
    with col_cat_search:
        cat_search = st.text_input("🔍 Search catalog by brand or product name...", key="cat_search").strip().lower()
    with col_status_filter:
        status_filter = st.selectbox("Stock Availability", ["All", "Available", "Sold Out"])

    filtered_catalog = [
        item for item in inventory_items
        if cat_search in item.get("brand", "").lower() or cat_search in item.get("product_name", "").lower()
    ]
    if status_filter == "Available":
        filtered_catalog = [item for item in filtered_catalog if item.get("quantity", 0) > 0]
    elif status_filter == "Sold Out":
        filtered_catalog = [item for item in filtered_catalog if item.get("quantity", 0) <= 0]

    if not filtered_catalog:
        st.info("No items match your query.")
    else:
        cols_per_row = 3
        for i in range(0, len(filtered_catalog), cols_per_row):
            row_cols = st.columns(cols_per_row)
            for j, col in enumerate(row_cols):
                if i + j < len(filtered_catalog):
                    item = filtered_catalog[i + j]
                    with col:
                        st.markdown('<div class="product-card">', unsafe_allow_html=True)
                        if item.get("image_url"):
                            st.image(item["image_url"], use_container_width=True)
                        st.markdown(f"### {item['brand']}")
                        st.markdown(f"**{item['product_name']}**")

                        status_html = "<span class='status-available'>AVAILABLE</span>" if item['quantity'] > 0 else "<span class='status-soldout'>SOLD OUT</span>"
                        st.markdown(
                            f"<span class='category-badge'>{item['category']}</span> "
                            f"<span class='shade-badge'>Shade: {item['tone']}</span> "
                            f"{status_html}",
                            unsafe_allow_html=True
                        )
                        st.write("")
                        st.markdown(f"<span class='price-tag'>${item['price']:.2f}</span> | Stock: {item['quantity']}", unsafe_allow_html=True)

                        if st.session_state["is_admin"]:
                            if st.button("🗑️ Quick Delete", key=f"quick_del_{item['id']}", use_container_width=True):
                                try:
                                    supabase.table("inventory").delete().eq("id", item["id"]).execute()
                                    st.success("Deleted!")
                                    st.rerun()
                                except Exception as del_err:
                                    st.error(f"Failed to delete: {del_err}")

                        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# TAB 3: EDIT & DELETE MANAGEMENT (ADMIN ONLY)
# ==========================================
with tab_manage:
    if not st.session_state["is_admin"]:
        st.warning("🔒 You must log in as Admin via the sidebar to access edit and delete tools.")
    else:
        st.subheader("📝 Edit or Delete Existing Inventory Items")

        if not inventory_items:
            st.info("No inventory items found to edit.")
        else:
            # Map items without displaying raw internal IDs
            item_options = {f"{item['brand']} — {item['product_name']} ({item['tone']})": item for item in inventory_items}
            selected_option = st.selectbox("Select Product Name to Modify", list(item_options.keys()))

            selected_item = item_options[selected_option]

            st.markdown("---")
            st.write(f"Editing: **{selected_item['brand']} - {selected_item['product_name']}**")

            col_edit1, col_edit2 = st.columns(2)

            with col_edit1:
                edit_brand = st.text_input("Brand", value=selected_item.get("brand", ""), key=f"edit_brand_{selected_item['id']}")
                edit_name = st.text_input("Product Name", value=selected_item.get("product_name", ""), key=f"edit_name_{selected_item['id']}")

                cat_idx = CATEGORIES.index(selected_item["category"]) if selected_item.get("category") in CATEGORIES else 0
                edit_category = st.selectbox("Target Area", CATEGORIES, index=cat_idx, key=f"edit_cat_{selected_item['id']}")

            with col_edit2:
                edit_tone = st.text_input("Tone / Shade", value=selected_item.get("tone", ""), key=f"edit_tone_{selected_item['id']}")
                edit_qty = st.number_input("Stock Quantity", min_value=0, step=1, value=int(selected_item.get("quantity", 0)), key=f"edit_qty_{selected_item['id']}")
                edit_price = st.number_input("Price ($)", min_value=0.0, step=0.5, value=float(selected_item.get("price", 0.0)), format="%.2f", key=f"edit_price_{selected_item['id']}")

            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                if st.button("💾 Save Changes", type="primary", use_container_width=True, key=f"save_btn_{selected_item['id']}"):
                    update_data = {
                        "brand": edit_brand or "N/A",
                        "product_name": edit_name or "Unnamed Item",
                        "category": edit_category,
                        "tone": edit_tone or "N/A",
                        "quantity": int(edit_qty),
                        "price": float(edit_price)
                    }
                    try:
                        supabase.table("inventory").update(update_data).eq("id", selected_item["id"]).execute()
                        st.success("Product updated successfully!")
                        st.rerun()
                    except Exception as update_err:
                        st.error(f"Failed to update item: {update_err}")

            with btn_col2:
                if st.button("🗑️ Permanently Delete Item", type="secondary", use_container_width=True, key=f"full_del_btn_{selected_item['id']}"):
                    try:
                        supabase.table("inventory").delete().eq("id", selected_item["id"]).execute()
                        st.success("Product permanently deleted!")
                        st.rerun()
                    except Exception as del_err:
                        st.error(f"Failed to delete item: {del_err}")

# ==========================================
# TAB 4: SALES ANALYTICS
# ==========================================
with tab_analytics:
    st.subheader("Completed Sales History")
    if sales_history:
        df_sales = pd.DataFrame(sales_history)

        # Display data table without ID column
        st.dataframe(
            df_sales[["total_amount", "created_at", "items_sold"]],
            column_config={
                "total_amount": st.column_config.NumberColumn("Total Revenue ($)", format="$%.2f"),
                "created_at": st.column_config.DatetimeColumn("Timestamp", format="D MMM YYYY, HH:mm"),
                "items_sold": st.column_config.ListColumn("Items Sold Details")
            },
            use_container_width=True
        )
    else:
        st.info("No sales transactions recorded yet.")

