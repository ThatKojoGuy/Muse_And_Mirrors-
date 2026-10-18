import html
import hmac
import re
import uuid

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# =====================================================================
# PAGE CONFIG
# =====================================================================
st.set_page_config(
    page_title="Muse & Mirrors | Studio POS & Inventory",
    page_icon="💅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# GLASSMORPHISM THEME
# =====================================================================
st.markdown(
    """
<style>
    .stApp {
        background:
            radial-gradient(900px circle at 10% 0%, rgba(168, 85, 247, 0.18), transparent 55%),
            radial-gradient(900px circle at 90% 10%, rgba(236, 72, 153, 0.14), transparent 55%),
            radial-gradient(900px circle at 50% 100%, rgba(59, 130, 246, 0.12), transparent 55%),
            #0B0E14;
    }
    section[data-testid="stSidebar"] {
        background: rgba(14, 17, 23, 0.55);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    /* Glass cards (keyed containers: card_*) */
    [class*="st-key-card_"] {
        background: rgba(255, 255, 255, 0.06);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
        padding: 6px 4px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    [class*="st-key-card_"]:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.25) !important;
    }
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.06);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
        padding: 14px 18px;
    }
    .price-tag { font-size: 18px; font-weight: 700; color: #3FB950; }
    .badge {
        display: inline-block; font-size: 11px; padding: 3px 9px;
        border-radius: 12px; margin: 0 4px 4px 0;
        backdrop-filter: blur(6px);
    }
    .category-badge { background: rgba(88, 166, 255, 0.15); color: #58A6FF; font-weight: 600; border: 1px solid rgba(88, 166, 255, 0.35); }
    .shade-badge { background: rgba(139, 148, 158, 0.15); color: #B1BAC4; border: 1px solid rgba(139, 148, 158, 0.3); }
    .status-available { background: rgba(35, 134, 54, 0.2); color: #3FB950; font-weight: 700; border: 1px solid #238636; }
    .status-soldout { background: rgba(218, 54, 51, 0.2); color: #F8514C; font-weight: 700; border: 1px solid #DA3633; }
</style>
""",
    unsafe_allow_html=True,
)

# =====================================================================
# CONSTANTS & HELPERS
# =====================================================================
CATEGORIES = ["Uncategorized", "Eyes", "Ears", "Nose", "Lips", "Cheeks", "Other"]
TAX_RATE = 0.05
BUCKET = "product_images"
NEW_BRAND = "➕ Add New Brand"
NEW_NAME = "➕ Add New Product Name"


def esc(value) -> str:
    return html.escape(str(value))


def get_secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


def clean_item(row: dict) -> dict:
    """Normalise a DB row so NULLs never crash the UI."""
    return {
        "id": row.get("id"),
        "brand": (row.get("brand") or "").strip() or "N/A",
        "product_name": (row.get("product_name") or "").strip() or "Unnamed Item",
        "category": row.get("category") or "Uncategorized",
        "tone": (row.get("tone") or "").strip() or "N/A",
        "quantity": int(row.get("quantity") or 0),
        "price": float(row.get("price") or 0.0),
        "image_url": row.get("image_url"),
    }


def matches(item: dict, query: str) -> bool:
    return query in item["brand"].lower() or query in item["product_name"].lower()


def status_badge(qty: int) -> str:
    if qty > 0:
        return "<span class='badge status-available'>AVAILABLE</span>"
    return "<span class='badge status-soldout'>SOLD OUT</span>"


# =====================================================================
# CREDENTIALS & SUPABASE
# =====================================================================
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")
ADMIN_USERNAME = get_secret("ADMIN_USERNAME")
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")

missing = [
    n
    for n, v in {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "ADMIN_USERNAME": ADMIN_USERNAME,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
    }.items()
    if not v
]
if missing:
    st.error(f"⚠️ Missing Streamlit Secrets: {', '.join(missing)}")
    st.stop()


@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Failed to connect to Supabase: {e}")
    st.stop()

# =====================================================================
# SESSION STATE
# =====================================================================
st.session_state.setdefault("is_admin", False)
st.session_state.setdefault("cart", {})  # {item_id: qty}
st.session_state.setdefault("form_nonce", 0)  # bump to reset the add-product form

is_admin = st.session_state["is_admin"]

# =====================================================================
# DATA
# =====================================================================
try:
    inv_rows = (
            supabase.table("inventory").select("*").order("created_at", desc=True).execute().data or []
    )
except Exception as err:
    st.error(f"Inventory fetch error: {err}")
    inv_rows = []

inventory_items = [clean_item(r) for r in inv_rows]
inventory_by_id = {i["id"]: i for i in inventory_items}

sales_history = []
if is_admin:  # sales/revenue are only loaded for admins
    try:
        sales_history = (
                supabase.table("sales").select("*").order("created_at", desc=True).execute().data or []
        )
    except Exception as err:
        st.error(f"Sales fetch error: {err}")

# Drop cart lines for items that were deleted elsewhere
st.session_state["cart"] = {
    k: v for k, v in st.session_state["cart"].items() if k in inventory_by_id
}

existing_brands = sorted({i["brand"] for i in inventory_items if i["brand"] != "N/A"})
existing_names = sorted(
    {i["product_name"] for i in inventory_items if i["product_name"] != "Unnamed Item"}
)


# =====================================================================
# STORAGE HELPERS
# =====================================================================
def upload_image(uploaded, brand: str, name: str):
    ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "jpg"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{brand}-{name}".lower()).strip("-") or "item"
    path = f"{slug}-{uuid.uuid4().hex[:8]}.{ext}"  # unique -> no duplicate-name failures
    supabase.storage.from_(BUCKET).upload(
        path, uploaded.getvalue(), {"content-type": uploaded.type or "image/jpeg"}
    )
    return supabase.storage.from_(BUCKET).get_public_url(path)


def delete_image(url):
    if not url or f"/{BUCKET}/" not in url:
        return
    try:
        path = url.split(f"/{BUCKET}/")[-1].split("?")[0]
        supabase.storage.from_(BUCKET).remove([path])
    except Exception:
        pass  # orphaned image is harmless


def delete_item(item: dict):
    supabase.table("inventory").delete().eq("id", item["id"]).execute()
    delete_image(item.get("image_url"))
    st.session_state["cart"].pop(item["id"], None)


# =====================================================================
# CHECKOUT (re-validates stock against the database)
# =====================================================================
def complete_sale(cart: dict):
    """Returns (ok, message_or_list). Stock is re-checked live, decremented
    with a guard against concurrent sales, and rolled back if logging fails."""
    ids = list(cart.keys())
    fresh_rows = (
            supabase.table("inventory")
            .select("id,brand,product_name,quantity,price")
            .in_("id", ids)
            .execute()
            .data
            or []
    )
    fresh = {r["id"]: clean_item(r) for r in fresh_rows}

    problems = []
    for iid, qty in cart.items():
        row = fresh.get(iid)
        label = inventory_by_id.get(iid, {}).get("product_name", f"Item {iid}")
        if row is None:
            problems.append(f"{label} no longer exists.")
        elif row["quantity"] < qty:
            problems.append(f"{row['brand']} - {row['product_name']}: only {row['quantity']} left.")
    if problems:
        return False, problems

    subtotal = sum(fresh[iid]["price"] * qty for iid, qty in cart.items())
    grand_total = round(subtotal * (1 + TAX_RATE), 2)
    items_sold = [
        {
            "brand": fresh[iid]["brand"],
            "product_name": fresh[iid]["product_name"],
            "quantity": qty,
            "unit_price": fresh[iid]["price"],
        }
        for iid, qty in cart.items()
    ]

    decremented = []  # (id, original_qty) for rollback
    try:
        for iid, qty in cart.items():
            current = fresh[iid]["quantity"]
            res = (
                supabase.table("inventory")
                .update({"quantity": current - qty})
                .eq("id", iid)
                .eq("quantity", current)  # fails if someone else sold it meanwhile
                .execute()
            )
            if not res.data:
                raise RuntimeError(
                    f"{fresh[iid]['product_name']} changed while checking out. Please try again."
                )
            decremented.append((iid, current))

        supabase.table("sales").insert(
            {"total_amount": grand_total, "items_sold": items_sold}
        ).execute()
    except Exception as exc:
        for iid, original in decremented:
            try:
                supabase.table("inventory").update({"quantity": original}).eq("id", iid).execute()
            except Exception:
                pass
        return False, [str(exc)]

    return True, grand_total


# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.title("💅 Studio Controls")

    with st.expander("🔐 Access Control", expanded=not is_admin):
        if is_admin:
            st.success("Authenticated as Admin")
            if st.button("Log Out", type="secondary", width="stretch"):
                st.session_state["is_admin"] = False
                st.rerun()
        else:
            user = st.text_input("Username", key="login_user")
            pwd = st.text_input("Password", type="password", key="login_pass")
            if st.button("Log In", type="primary", width="stretch"):
                ok_user = hmac.compare_digest(user.encode(), str(ADMIN_USERNAME).encode())
                ok_pass = hmac.compare_digest(pwd.encode(), str(ADMIN_PASSWORD).encode())
                if ok_user and ok_pass:
                    st.session_state["is_admin"] = True
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

    st.divider()

    if is_admin:
        st.subheader("➕ Add New Product")
        n = st.session_state["form_nonce"]

        brand_choice = st.selectbox("Brand Name", [NEW_BRAND] + existing_brands, key=f"add_brand_select_{n}")
        if brand_choice == NEW_BRAND:
            brand = st.text_input("Enter New Brand", placeholder="e.g., Fenty Beauty",
                                  key=f"add_brand_custom_{n}").strip()
        else:
            brand = brand_choice

        name_choice = st.selectbox("Product Name", [NEW_NAME] + existing_names, key=f"add_name_select_{n}")
        if name_choice == NEW_NAME:
            name = st.text_input("Enter New Product Name", placeholder="e.g., Foundation",
                                 key=f"add_name_custom_{n}").strip()
        else:
            name = name_choice

        category = st.selectbox("Target Area", CATEGORIES, key=f"add_cat_{n}")
        tone = st.text_input("Tone / Shade", placeholder="e.g., Warm Nude", key=f"add_tone_{n}").strip()
        qty = st.number_input("Stock Quantity", min_value=0, step=1, value=1, key=f"add_qty_{n}")
        price = st.number_input("Retail Price ($)", min_value=0.0, step=0.5, value=0.0, format="%.2f",
                                key=f"add_price_{n}")
        uploaded_file = st.file_uploader("Product Image (optional)", type=["png", "jpg", "jpeg", "webp"],
                                         key=f"add_img_{n}")

        if st.button("Save New Product", type="primary", width="stretch"):
            image_url = None
            if uploaded_file is not None:
                try:
                    image_url = upload_image(uploaded_file, brand or "item", name or "product")
                except Exception as img_err:
                    st.warning(f"Image upload failed, saving without image: {img_err}")

            data = {
                "brand": brand or "N/A",
                "product_name": name or "Unnamed Item",
                "category": category,
                "tone": tone or "N/A",
                "quantity": int(qty or 0),
                "price": float(price or 0.0),
                "image_url": image_url,
            }
            try:
                supabase.table("inventory").insert(data).execute()
                st.session_state["form_nonce"] += 1  # clears the form
                st.toast("Saved to database!", icon="✅")
                st.rerun()
            except Exception as db_err:
                st.error(f"Database Error: {db_err}")
    else:
        st.info("💡 **Viewer Mode**: Log in as Admin above to add, edit, or delete inventory.")

# =====================================================================
# HEADER
# =====================================================================
st.title("✨ Muse & Mirrors Studio POS")

tab_pos, tab_catalog, tab_manage, tab_analytics = st.tabs(
    ["🛒 Checkout POS", "🖼️ Visual Catalog", "⚙️ Edit & Delete (Admin)", "📈 Sales & Revenue"]
)

# =====================================================================
# TAB 1: POS CHECKOUT
# =====================================================================
with tab_pos:
    if not is_admin:
        st.warning("🔒 Log in as Admin via the sidebar to use the checkout. Browse products in the Visual Catalog.")
    else:
        pos_col1, pos_col2 = st.columns([2, 1])

        with pos_col1:
            st.subheader("Select Products")
            pos_search = st.text_input("🔍 Search product or brand name...", key="pos_search").strip().lower()
            pos_items = [i for i in inventory_items if matches(i, pos_search)]

            if not pos_items:
                st.info("No products match your search.")

            grid_cols = st.columns(2)
            for idx, item in enumerate(pos_items):
                with grid_cols[idx % 2]:
                    with st.container(border=True, key=f"card_pos_{item['id']}"):
                        st.markdown(f"**{esc(item['brand'])}** - {esc(item['product_name'])}")
                        st.markdown(
                            f"{status_badge(item['quantity'])} "
                            f"<span class='price-tag'>${item['price']:.2f}</span> &nbsp;|&nbsp; Stock: {item['quantity']}",
                            unsafe_allow_html=True,
                        )
                        if item["quantity"] > 0:
                            if st.button("➕ Add to Cart", key=f"add_cart_{item['id']}", width="stretch"):
                                in_cart = st.session_state["cart"].get(item["id"], 0)
                                if in_cart < item["quantity"]:
                                    st.session_state["cart"][item["id"]] = in_cart + 1
                                    st.rerun()
                                else:
                                    st.warning("Stock limit reached!")
                        else:
                            st.button("Sold Out", key=f"soldout_{item['id']}", disabled=True, width="stretch")

        with pos_col2:
            st.subheader("Active Order")
            cart = st.session_state["cart"]
            if not cart:
                st.info("Cart is empty.")
            else:
                subtotal = 0.0
                for item_id, qty in list(cart.items()):
                    item = inventory_by_id[item_id]
                    line_total = qty * item["price"]
                    subtotal += line_total

                    st.write(f"**{item['brand']} - {item['product_name']}**")
                    c1, c2, c3 = st.columns([2, 2, 1])
                    c1.write(f"${item['price']:.2f} x {qty}")
                    c2.write(f"**${line_total:.2f}**")
                    if c3.button("❌", key=f"remove_cart_{item_id}"):
                        del st.session_state["cart"][item_id]
                        st.rerun()
                    st.divider()

                tax = subtotal * TAX_RATE
                grand_total = subtotal + tax
                st.write(f"**Subtotal:** ${subtotal:,.2f}")
                st.write(f"**Tax ({TAX_RATE:.0%}):** ${tax:,.2f}")
                st.markdown(f"### Grand Total: `${grand_total:,.2f}`")

                if st.button("💳 Complete Transaction", type="primary", width="stretch"):
                    ok, result = complete_sale(st.session_state["cart"])
                    if ok:
                        st.session_state["cart"] = {}
                        st.balloons()
                        st.toast(f"Transaction recorded: ${result:,.2f}", icon="✅")
                        st.rerun()
                    else:
                        for msg in result:
                            st.error(msg)

# =====================================================================
# TAB 2: VISUAL CATALOG
# =====================================================================
with tab_catalog:
    f1, f2, f3 = st.columns([3, 1, 1])
    with f1:
        cat_search = st.text_input("🔍 Search catalog by brand or product name...", key="cat_search").strip().lower()
    with f2:
        area_filter = st.selectbox("Target Area", ["All"] + CATEGORIES, key="cat_area")
    with f3:
        status_filter = st.selectbox("Stock Availability", ["All", "Available", "Sold Out"], key="cat_status")

    filtered = [i for i in inventory_items if matches(i, cat_search)]
    if area_filter != "All":
        filtered = [i for i in filtered if i["category"] == area_filter]
    if status_filter == "Available":
        filtered = [i for i in filtered if i["quantity"] > 0]
    elif status_filter == "Sold Out":
        filtered = [i for i in filtered if i["quantity"] <= 0]

    if not filtered:
        st.info("No items match your query.")
    else:
        per_row = 3
        for start in range(0, len(filtered), per_row):
            row_cols = st.columns(per_row)
            for offset, col in enumerate(row_cols):
                if start + offset >= len(filtered):
                    continue
                item = filtered[start + offset]
                with col:
                    with st.container(border=True, key=f"card_cat_{item['id']}"):
                        if item["image_url"]:
                            st.image(item["image_url"], width="stretch")
                        st.markdown(f"### {esc(item['brand'])}")
                        st.markdown(f"**{esc(item['product_name'])}**")
                        st.markdown(
                            f"<span class='badge category-badge'>{esc(item['category'])}</span>"
                            f"<span class='badge shade-badge'>Shade: {esc(item['tone'])}</span>"
                            f"{status_badge(item['quantity'])}",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"<span class='price-tag'>${item['price']:.2f}</span> &nbsp;|&nbsp; Stock: {item['quantity']}",
                            unsafe_allow_html=True,
                        )
                        if is_admin:
                            if st.button("🗑️ Quick Delete", key=f"quick_del_{item['id']}", width="stretch"):
                                try:
                                    delete_item(item)
                                    st.toast("Deleted!", icon="🗑️")
                                    st.rerun()
                                except Exception as del_err:
                                    st.error(f"Failed to delete: {del_err}")

# =====================================================================
# TAB 3: EDIT & DELETE (ADMIN ONLY)
# =====================================================================
with tab_manage:
    if not is_admin:
        st.warning("🔒 You must log in as Admin via the sidebar to access edit and delete tools.")
    elif not inventory_items:
        st.info("No inventory items found to edit.")
    else:
        st.subheader("📝 Edit or Delete Existing Inventory Items")

        # Select by ID internally; the label never shows the ID, and duplicate labels can't collide.
        selected_id = st.selectbox(
            "Select Product to Modify",
            options=[i["id"] for i in inventory_items],
            format_func=lambda iid: (
                f"{inventory_by_id[iid]['brand']} — {inventory_by_id[iid]['product_name']} "
                f"({inventory_by_id[iid]['tone']})"
            ),
            key="manage_select",
        )
        sel = inventory_by_id[selected_id]
        k = sel["id"]

        st.markdown("---")
        st.write(f"Editing: **{sel['brand']} - {sel['product_name']}**")

        e1, e2 = st.columns(2)
        with e1:
            edit_brand = st.text_input("Brand", value=sel["brand"], key=f"edit_brand_{k}")
            edit_name = st.text_input("Product Name", value=sel["product_name"], key=f"edit_name_{k}")
            cat_idx = CATEGORIES.index(sel["category"]) if sel["category"] in CATEGORIES else 0
            edit_category = st.selectbox("Target Area", CATEGORIES, index=cat_idx, key=f"edit_cat_{k}")
        with e2:
            edit_tone = st.text_input("Tone / Shade", value=sel["tone"], key=f"edit_tone_{k}")
            edit_qty = st.number_input("Stock Quantity", min_value=0, step=1, value=sel["quantity"],
                                       key=f"edit_qty_{k}")
            edit_price = st.number_input("Price ($)", min_value=0.0, step=0.5, value=sel["price"], format="%.2f",
                                         key=f"edit_price_{k}")

        if sel["image_url"]:
            st.image(sel["image_url"], width=140, caption="Current image")
        new_image = st.file_uploader("Replace image (optional)", type=["png", "jpg", "jpeg", "webp"],
                                     key=f"edit_img_{k}")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("💾 Save Changes", type="primary", width="stretch", key=f"save_btn_{k}"):
                update_data = {
                    "brand": edit_brand.strip() or "N/A",
                    "product_name": edit_name.strip() or "Unnamed Item",
                    "category": edit_category,
                    "tone": edit_tone.strip() or "N/A",
                    "quantity": int(edit_qty or 0),
                    "price": float(edit_price or 0.0),
                }
                try:
                    if new_image is not None:
                        update_data["image_url"] = upload_image(new_image, update_data["brand"],
                                                                update_data["product_name"])
                    supabase.table("inventory").update(update_data).eq("id", k).execute()
                    if new_image is not None:
                        delete_image(sel["image_url"])
                    st.toast("Product updated!", icon="✅")
                    st.rerun()
                except Exception as update_err:
                    st.error(f"Failed to update item: {update_err}")
        with b2:
            confirm = st.checkbox("Confirm permanent delete", key=f"confirm_del_{k}")
            if st.button("🗑️ Permanently Delete Item", type="secondary", width="stretch", key=f"full_del_btn_{k}",
                         disabled=not confirm):
                try:
                    delete_item(sel)
                    st.toast("Product permanently deleted!", icon="🗑️")
                    st.rerun()
                except Exception as del_err:
                    st.error(f"Failed to delete item: {del_err}")

# =====================================================================
# TAB 4: SALES & REVENUE ANALYTICS (ADMIN ONLY)
# =====================================================================
with tab_analytics:
    if not is_admin:
        st.warning("🔒 Log in as Admin via the sidebar to view sales and revenue.")
    else:
        total_products = len(inventory_items)
        total_stock = sum(i["quantity"] for i in inventory_items)
        total_inventory_val = sum(i["quantity"] * i["price"] for i in inventory_items)
        total_revenue = sum(float(s.get("total_amount") or 0.0) for s in sales_history)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Unique Items", total_products)
        m2.metric("In-Stock Units", total_stock)
        m3.metric("Inventory Value ($)", f"${total_inventory_val:,.2f}")
        m4.metric("Total Revenue Realized ($)", f"${total_revenue:,.2f}")

        st.divider()
        st.subheader("Completed Sales History")

        if sales_history:
            def describe(items):
                if not isinstance(items, list):
                    return ""
                return "; ".join(
                    f"{i.get('brand', 'N/A')} {i.get('product_name', '')} ×{i.get('quantity', 0)} @ ${float(i.get('unit_price') or 0):.2f}"
                    for i in items
                )


            df = pd.DataFrame(
                {
                    "Total Revenue ($)": [float(s.get("total_amount") or 0.0) for s in sales_history],
                    "Timestamp": pd.to_datetime([s.get("created_at") for s in sales_history], errors="coerce"),
                    "Items Sold Details": [describe(s.get("items_sold")) for s in sales_history],
                }
            )
            st.dataframe(
                df,
                hide_index=True,  # internal IDs never shown
                width="stretch",
                column_config={
                    "Total Revenue ($)": st.column_config.NumberColumn(format="$%.2f"),
                    "Timestamp": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
                    "Items Sold Details": st.column_config.TextColumn(width="large"),
                },
            )
        else:
            st.info("No sales transactions recorded yet.")
