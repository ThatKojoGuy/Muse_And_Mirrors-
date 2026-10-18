import html
import hmac
import re
import uuid
from collections import Counter

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
        display: inline-block; font-size: 12px; padding: 3px 9px;
        border-radius: 12px; margin: 0 4px 4px 0;
        backdrop-filter: blur(6px);
    }
    .category-badge { background: rgba(88, 166, 255, 0.15); color: #79B8FF; font-weight: 600; border: 1px solid rgba(88, 166, 255, 0.35); }
    .shade-badge { background: rgba(139, 148, 158, 0.15); color: #C9D1D9; border: 1px solid rgba(139, 148, 158, 0.3); }
    .status-available { background: rgba(35, 134, 54, 0.2); color: #56D364; font-weight: 700; border: 1px solid #238636; }
    .status-low { background: rgba(210, 153, 34, 0.2); color: #E3B341; font-weight: 700; border: 1px solid #9E6A03; }
    .status-soldout { background: rgba(218, 54, 51, 0.2); color: #FF7B72; font-weight: 700; border: 1px solid #DA3633; }

    /* Accessibility: visible keyboard focus + comfortable touch targets */
    button:focus-visible, input:focus-visible, [role="combobox"]:focus-visible {
        outline: 2px solid #79B8FF !important; outline-offset: 2px;
    }
    .stButton > button, .stFormSubmitButton > button { min-height: 40px; }
    @media (prefers-reduced-motion: reduce) {
        [class*="st-key-card_"] { transition: none; }
        [class*="st-key-card_"]:hover { transform: none; }
    }
</style>
""",
    unsafe_allow_html=True,
)

# =====================================================================
# CONSTANTS & HELPERS
# =====================================================================
CATEGORIES = ["Uncategorized", "Eyes", "Ears", "Nose", "Lips", "Cheeks", "Other"]
TAX_RATE = 0.05
LOW_STOCK = 3
BUCKET = "product_images"


def esc(value) -> str:
    return html.escape(str(value))


def money(value: float) -> str:
    return f"${value:,.2f}"


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


def label_of(item: dict) -> str:
    return f"{item['brand']} — {item['product_name']} ({item['tone']})"


def matches(item: dict, query: str) -> bool:
    return query in item["brand"].lower() or query in item["product_name"].lower()


def status_badge(qty: int) -> str:
    """Status is always conveyed by icon + text, never by colour alone."""
    if qty > 0:
        out = "<span class='badge status-available'>✓ AVAILABLE</span>"
        if qty <= LOW_STOCK:
            out += f"<span class='badge status-low'>⚠ ONLY {qty} LEFT</span>"
        return out
    return "<span class='badge status-soldout'>✕ SOLD OUT</span>"


# ---- case-insensitive name handling ---------------------------------
def tidy(value) -> str:
    """Trim and collapse repeated whitespace."""
    return " ".join(str(value or "").split())


def dedupe_ci(values) -> list:
    """Case-insensitive unique list; keeps the most common spelling of each."""
    groups = {}
    for v in values:
        groups.setdefault(v.lower(), Counter())[v] += 1

    def best(counter):
        # most common spelling; on a tie prefer one with capital letters
        return max(counter, key=lambda v: (counter[v], v != v.lower(), v == v.title()))

    return sorted((best(c) for c in groups.values()), key=str.lower)


def canon(value, options) -> str:
    """Map typed text onto an existing spelling ('fenty beauty' -> 'Fenty Beauty')."""
    value = tidy(value)
    return {o.lower(): o for o in options}.get(value.lower(), value)


def idx_ci(options, value):
    for i, o in enumerate(options):
        if o.lower() == str(value).lower():
            return i
    return None


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
for key, default in {
    "is_admin": False,
    "cart": {},  # {item_id: qty}
    "form_nonce": 0,  # bump to reset the add-product form
    "quick_nonce": 0,  # bump to reset the quick-add box
    "last_deleted": None,  # raw row, enables Undo
    "last_receipt": None,  # shown after a sale for closure
    "dup_pending": None,  # duplicate found while adding a product
}.items():
    st.session_state.setdefault(key, default)

is_admin = st.session_state["is_admin"]

# =====================================================================
# DATA
# =====================================================================
try:
    inv_rows = (
            supabase.table("inventory").select("*").order("id", desc=True).execute().data or []
    )
except Exception as err:
    st.error(f"Inventory fetch error: {err}")
    inv_rows = []

raw_by_id = {r["id"]: r for r in inv_rows}
inventory_items = [clean_item(r) for r in inv_rows]
inventory_by_id = {i["id"]: i for i in inventory_items}

sales_history = []
if is_admin:  # sales/revenue are only loaded for admins
    try:
        sales_history = (
                supabase.table("sales").select("*").order("id", desc=True).execute().data or []
        )
    except Exception as err:
        st.error(f"Sales fetch error: {err}")

# Drop cart lines for items that were deleted elsewhere
st.session_state["cart"] = {
    k: v for k, v in st.session_state["cart"].items() if k in inventory_by_id
}
cart = st.session_state["cart"]

# Dropdown suggestions (case-insensitive unique)
existing_brands = dedupe_ci(i["brand"] for i in inventory_items if i["brand"] != "N/A")
existing_names = dedupe_ci(
    i["product_name"] for i in inventory_items if i["product_name"] != "Unnamed Item"
)
existing_tones = dedupe_ci(i["tone"] for i in inventory_items if i["tone"] != "N/A")


# =====================================================================
# ACTIONS
# =====================================================================
def normalize_fields(brand_raw, name_raw, tone_raw):
    """Apply case-insensitive matching + fallbacks to the three text fields."""
    brand = canon(brand_raw, existing_brands) or "N/A"
    name = canon(name_raw, existing_names) or "Unnamed Item"
    tone = canon(tone_raw, existing_tones) or "N/A"
    return brand, name, tone


def find_duplicate(brand, name, tone, exclude_id=None):
    key = (brand.lower(), name.lower(), tone.lower())
    for i in inventory_items:
        if i["id"] != exclude_id and (
                i["brand"].lower(),
                i["product_name"].lower(),
                i["tone"].lower(),
        ) == key:
            return i
    return None


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
    """Deletes the row but keeps its image so the delete can be undone."""
    supabase.table("inventory").delete().eq("id", item["id"]).execute()
    st.session_state["last_deleted"] = raw_by_id.get(item["id"]) or item
    cart.pop(item["id"], None)


def undo_delete():
    row = st.session_state["last_deleted"]
    supabase.table("inventory").insert(row).execute()
    st.session_state["last_deleted"] = None


def add_to_cart(item_id):
    """Returns None on success, or a message explaining why nothing was added."""
    item = inventory_by_id[item_id]
    current = cart.get(item_id, 0)
    if item["quantity"] <= 0:
        return f"{item['product_name']} is sold out."
    if current >= item["quantity"]:
        return f"Only {item['quantity']} of {item['product_name']} in stock."
    cart[item_id] = current + 1
    st.session_state["last_receipt"] = None
    return None


def complete_sale(cart_lines: dict):
    """Returns (ok, receipt_dict_or_list_of_problems). Stock is re-checked live,
    decremented with a guard against concurrent sales, and rolled back if
    logging the sale fails."""
    ids = list(cart_lines.keys())
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
    for iid, qty in cart_lines.items():
        row = fresh.get(iid)
        label = inventory_by_id.get(iid, {}).get("product_name", f"Item {iid}")
        if row is None:
            problems.append(f"{label} no longer exists.")
        elif row["quantity"] < qty:
            problems.append(f"{row['brand']} - {row['product_name']}: only {row['quantity']} left.")
    if problems:
        return False, problems

    subtotal = round(sum(fresh[iid]["price"] * qty for iid, qty in cart_lines.items()), 2)
    grand_total = round(subtotal * (1 + TAX_RATE), 2)
    items_sold = [
        {
            "brand": fresh[iid]["brand"],
            "product_name": fresh[iid]["product_name"],
            "quantity": qty,
            "unit_price": fresh[iid]["price"],
        }
        for iid, qty in cart_lines.items()
    ]

    decremented = []  # (id, original_qty) for rollback
    try:
        for iid, qty in cart_lines.items():
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

    return True, {
        "items": items_sold,
        "subtotal": subtotal,
        "tax": round(grand_total - subtotal, 2),
        "total": grand_total,
    }


# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.title("💅 Studio Controls")

    with st.expander("🔐 Access Control", expanded=not is_admin):
        if is_admin:
            st.success("Signed in as Admin")
            if st.button("🚪 Log Out", type="secondary", width="stretch"):
                st.session_state["is_admin"] = False
                st.rerun()
        else:
            # A form lets Enter submit the login
            with st.form("login_form", border=False):
                user = st.text_input("Username", key="login_user")
                pwd = st.text_input("Password", type="password", key="login_pass")
                login_clicked = st.form_submit_button("🔑 Log In", type="primary", width="stretch")
            if login_clicked:
                ok_user = hmac.compare_digest(user.encode(), str(ADMIN_USERNAME).encode())
                ok_pass = hmac.compare_digest(pwd.encode(), str(ADMIN_PASSWORD).encode())
                if ok_user and ok_pass:
                    st.session_state["is_admin"] = True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    st.divider()

    if is_admin:
        # Always-visible cart summary so the cashier never has to remember it
        cart_units = sum(cart.values())
        cart_sub = sum(inventory_by_id[i]["price"] * q for i, q in cart.items())
        st.markdown(
            f"🛒 **Cart:** {cart_units} item{'s' if cart_units != 1 else ''} · "
            f"{money(cart_sub * (1 + TAX_RATE))} incl. tax"
        )
        st.divider()

        st.subheader("➕ Add New Product")
        n = st.session_state["form_nonce"]

        # Type to search existing entries, or type a new one and press Enter.
        # Matching is case-insensitive, so "fenty beauty" reuses "Fenty Beauty".
        with st.form(f"add_form_{n}", border=False):
            brand_in = st.selectbox(
                "Brand Name",
                options=existing_brands,
                index=None,
                accept_new_options=True,
                placeholder="Select a brand or type a new one",
                help="Not in the list? Type it and press Enter. Capitalisation is matched automatically.",
                key=f"add_brand_{n}",
            )
            name_in = st.selectbox(
                "Product Name",
                options=existing_names,
                index=None,
                accept_new_options=True,
                placeholder="Select a product or type a new one",
                key=f"add_name_{n}",
            )
            category_in = st.selectbox("Target Area", CATEGORIES, key=f"add_cat_{n}")
            tone_in = st.selectbox(
                "Tone / Shade",
                options=existing_tones,
                index=None,
                accept_new_options=True,
                placeholder="Select a shade or type a new one",
                key=f"add_tone_{n}",
            )
            qty_in = st.number_input("Stock Quantity", min_value=0, step=1, value=1, key=f"add_qty_{n}")
            price_in = st.number_input(
                "Retail Price", min_value=0.0, step=0.5, value=0.0, format="%.2f", key=f"add_price_{n}"
            )
            file_in = st.file_uploader(
                "Product Image (optional)", type=["png", "jpg", "jpeg", "webp"], key=f"add_img_{n}"
            )
            add_clicked = st.form_submit_button("💾 Save New Product", type="primary", width="stretch")

        if add_clicked:
            brand, name, tone = normalize_fields(brand_in, name_in, tone_in)
            dup = find_duplicate(brand, name, tone)
            if dup:
                # Error prevention: don't create a second identical row
                st.session_state["dup_pending"] = {"id": dup["id"], "qty": int(qty_in or 0)}
            else:
                st.session_state["dup_pending"] = None
                with st.spinner("Saving…"):
                    image_url = None
                    if file_in is not None:
                        try:
                            image_url = upload_image(file_in, brand, name)
                        except Exception as img_err:
                            st.warning(f"Image upload failed, saving without image: {img_err}")
                    data = {
                        "brand": brand,
                        "product_name": name,
                        "category": category_in,
                        "tone": tone,
                        "quantity": int(qty_in or 0),
                        "price": float(price_in or 0.0),
                        "image_url": image_url,
                    }
                    try:
                        supabase.table("inventory").insert(data).execute()
                        note = " — price is 0.00, remember to set it" if not price_in else ""
                        st.session_state["form_nonce"] += 1  # clears the form
                        st.toast(f"Saved {brand} — {name}{note}", icon="✅" if price_in else "⚠️")
                        st.rerun()
                    except Exception as db_err:
                        st.error(f"Could not save the product: {db_err}")

        pend = st.session_state["dup_pending"]
        if pend:
            existing = inventory_by_id.get(pend["id"])
            if existing is None:
                st.session_state["dup_pending"] = None
            else:
                st.warning(
                    f"**{label_of(existing)}** already exists ({existing['quantity']} in stock). "
                    "Add to its stock instead?"
                )
                d1, d2 = st.columns(2)
                if d1.button(
                        f"➕ Add {pend['qty']} to stock",
                        key="dup_add",
                        type="primary",
                        width="stretch",
                        disabled=pend["qty"] <= 0,
                ):
                    try:
                        supabase.table("inventory").update(
                            {"quantity": existing["quantity"] + pend["qty"]}
                        ).eq("id", existing["id"]).execute()
                        st.session_state["dup_pending"] = None
                        st.session_state["form_nonce"] += 1
                        st.toast(f"Added {pend['qty']} to {existing['product_name']}", icon="✅")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Could not update stock: {err}")
                if d2.button("✖ Dismiss", key="dup_dismiss", width="stretch"):
                    st.session_state["dup_pending"] = None
                    st.rerun()
    else:
        st.info("💡 **Viewer Mode**: Log in as Admin above to add, edit, or delete inventory.")

# =====================================================================
# HEADER
# =====================================================================
st.title("✨ Muse & Mirrors Studio POS")

# Undo banner (keeps users in control and makes deletes reversible)
if is_admin and st.session_state["last_deleted"]:
    gone = clean_item(st.session_state["last_deleted"])
    u1, u2, u3 = st.columns([6, 1.3, 1.3])
    u1.info(f"🗑️ Deleted **{gone['brand']} — {gone['product_name']}**. Changed your mind?")
    if u2.button("↩️ Undo", key="undo_delete", type="primary", width="stretch"):
        try:
            undo_delete()
            st.toast("Item restored", icon="↩️")
            st.rerun()
        except Exception as err:
            st.error(f"Could not restore the item: {err}")
    if u3.button("✖ Dismiss", key="undo_dismiss", width="stretch"):
        st.session_state["last_deleted"] = None
        st.rerun()

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

            # Expert shortcut: type a name, pick it, it's in the cart
            in_stock = [i for i in inventory_items if i["quantity"] > 0]
            quick = st.selectbox(
                "⚡ Quick add",
                options=[i["id"] for i in in_stock],
                index=None,
                format_func=lambda iid: label_of(inventory_by_id[iid]),
                placeholder="Type a name and press Enter to add instantly",
                key=f"quick_add_{st.session_state['quick_nonce']}",
            )
            if quick is not None:
                msg = add_to_cart(quick)
                st.session_state["quick_nonce"] += 1
                if msg:
                    st.toast(msg, icon="⚠️")
                st.rerun()

            pos_search = tidy(st.text_input("🔍 Search product or brand name...", key="pos_search")).lower()
            pos_items = [i for i in inventory_items if matches(i, pos_search)]

            if not inventory_items:
                st.info("No products yet. Add your first one from the sidebar.")
            elif not pos_items:
                st.info("No products match your search. Try a shorter name or clear the box.")

            grid_cols = st.columns(2)
            for idx, item in enumerate(pos_items):
                with grid_cols[idx % 2]:
                    with st.container(border=True, key=f"card_pos_{item['id']}"):
                        st.markdown(f"**{esc(item['brand'])}** - {esc(item['product_name'])}")
                        st.markdown(
                            f"<span class='badge category-badge'>{esc(item['category'])}</span>"
                            f"<span class='badge shade-badge'>Shade: {esc(item['tone'])}</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"{status_badge(item['quantity'])}<br>"
                            f"<span class='price-tag'>{money(item['price'])}</span> &nbsp;|&nbsp; Stock: {item['quantity']}",
                            unsafe_allow_html=True,
                        )
                        if cart.get(item["id"]):
                            st.caption(f"🛒 {cart[item['id']]} in cart")
                        if item["quantity"] > 0:
                            if st.button("➕ Add to Cart", key=f"add_cart_{item['id']}", width="stretch"):
                                msg = add_to_cart(item["id"])
                                if msg:
                                    st.toast(msg, icon="⚠️")
                                else:
                                    st.rerun()
                        else:
                            st.button("✕ Sold Out", key=f"soldout_{item['id']}", disabled=True, width="stretch")

        with pos_col2:
            st.subheader("Active Order")
            if not cart:
                receipt = st.session_state["last_receipt"]
                if receipt:
                    st.success(f"✅ Sale complete — {money(receipt['total'])}")
                    for line in receipt["items"]:
                        st.write(
                            f"{line['brand']} {line['product_name']} × {line['quantity']} "
                            f"— {money(line['unit_price'] * line['quantity'])}"
                        )
                    st.caption(
                        f"Subtotal {money(receipt['subtotal'])} · Tax {money(receipt['tax'])} · "
                        f"Total {money(receipt['total'])}"
                    )
                    if st.button("🆕 Start new order", type="primary", width="stretch"):
                        st.session_state["last_receipt"] = None
                        st.rerun()
                else:
                    st.info("Cart is empty. Tap **Add to Cart** on a product, or use Quick add.")
            else:
                subtotal = 0.0
                for item_id, qty in list(cart.items()):
                    item = inventory_by_id[item_id]
                    line_total = qty * item["price"]
                    subtotal += line_total

                    st.markdown(f"**{esc(item['brand'])} - {esc(item['product_name'])}**")
                    st.caption(f"Shade: {item['tone']} · {money(item['price'])} each")
                    c_minus, c_qty, c_plus, c_del, c_total = st.columns([1, 1, 1, 1, 2])
                    if c_minus.button("➖", key=f"minus_{item_id}", help="Remove one"):
                        if qty > 1:
                            cart[item_id] = qty - 1
                        else:
                            del cart[item_id]
                        st.rerun()
                    c_qty.markdown(f"<div style='text-align:center;padding-top:8px'><b>{qty}</b></div>",
                                   unsafe_allow_html=True)
                    if c_plus.button("➕", key=f"plus_{item_id}", help="Add one"):
                        msg = add_to_cart(item_id)
                        if msg:
                            st.toast(msg, icon="⚠️")
                        else:
                            st.rerun()
                    if c_del.button("🗑️", key=f"remove_cart_{item_id}", help="Remove from cart"):
                        del cart[item_id]
                        st.rerun()
                    c_total.markdown(f"<div style='text-align:right;padding-top:8px'><b>{money(line_total)}</b></div>",
                                     unsafe_allow_html=True)
                    st.divider()

                tax = subtotal * TAX_RATE
                grand_total = subtotal + tax
                st.write(f"**Subtotal:** {money(subtotal)}")
                st.write(f"**Tax ({TAX_RATE:.0%}):** {money(tax)}")
                st.markdown(f"### Grand Total: `{money(grand_total)}`")

                b_clear, b_pay = st.columns([1, 2])
                if b_clear.button("🧹 Clear", key="clear_cart", width="stretch", help="Empty the cart"):
                    cart.clear()
                    st.rerun()
                if b_pay.button("💳 Complete Transaction", type="primary", width="stretch"):
                    with st.spinner("Recording sale…"):
                        ok, result = complete_sale(cart)
                    if ok:
                        st.session_state["cart"] = {}
                        st.session_state["last_receipt"] = result
                        st.balloons()
                        st.rerun()
                    else:
                        for msg in result:
                            st.error(msg)
                        st.caption("Nothing was charged. Adjust the cart and try again.")

# =====================================================================
# TAB 2: VISUAL CATALOG
# =====================================================================
with tab_catalog:
    f1, f2, f3 = st.columns([3, 1, 1])
    with f1:
        cat_search = tidy(st.text_input("🔍 Search catalog by brand or product name...", key="cat_search")).lower()
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

    st.caption(f"Showing {len(filtered)} of {len(inventory_items)} products")

    if not inventory_items:
        st.info("The catalog is empty. Products will appear here once they're added.")
    elif not filtered:
        st.info("No items match your filters. Try clearing the search or setting filters back to All.")
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
                            f"<span class='price-tag'>{money(item['price'])}</span> &nbsp;|&nbsp; Stock: {item['quantity']}",
                            unsafe_allow_html=True,
                        )
                        if is_admin:
                            if st.button("🗑️ Quick Delete", key=f"quick_del_{item['id']}", width="stretch",
                                         help="You can undo this right after"):
                                try:
                                    delete_item(item)
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
        st.info("No inventory items found to edit. Add one from the sidebar.")
    else:
        st.subheader("📝 Edit or Delete Existing Inventory Items")

        # Select by ID internally; the label never shows the ID, and duplicate labels can't collide.
        selected_id = st.selectbox(
            "Select Product to Modify",
            options=[i["id"] for i in inventory_items],
            format_func=lambda iid: label_of(inventory_by_id[iid]),
            key="manage_select",
        )
        sel = inventory_by_id[selected_id]
        k = sel["id"]
        en = st.session_state.get(f"edit_nonce_{k}", 0)  # bump to reset the form to saved values
        ek = f"{k}_{en}"

        st.markdown("---")
        st.write(
            f"Editing: **{sel['brand']} - {sel['product_name']}** · "
            f"{sel['quantity']} in stock · {money(sel['price'])}"
        )

        brand_opts = dedupe_ci(existing_brands + [sel["brand"]])
        name_opts = dedupe_ci(existing_names + [sel["product_name"]])
        tone_opts = dedupe_ci(existing_tones + [sel["tone"]])

        e1, e2 = st.columns(2)
        with e1:
            edit_brand = st.selectbox(
                "Brand", brand_opts, index=idx_ci(brand_opts, sel["brand"]),
                accept_new_options=True, key=f"edit_brand_{ek}",
                help="Type to search, or type a new brand and press Enter.",
            )
            edit_name = st.selectbox(
                "Product Name", name_opts, index=idx_ci(name_opts, sel["product_name"]),
                accept_new_options=True, key=f"edit_name_{ek}",
            )
            cat_idx = CATEGORIES.index(sel["category"]) if sel["category"] in CATEGORIES else 0
            edit_category = st.selectbox("Target Area", CATEGORIES, index=cat_idx, key=f"edit_cat_{ek}")
        with e2:
            edit_tone = st.selectbox(
                "Tone / Shade", tone_opts, index=idx_ci(tone_opts, sel["tone"]),
                accept_new_options=True, key=f"edit_tone_{ek}",
            )
            edit_qty = st.number_input("Stock Quantity", min_value=0, step=1, value=sel["quantity"],
                                       key=f"edit_qty_{ek}")
            edit_price = st.number_input(
                "Retail Price", min_value=0.0, step=0.5, value=sel["price"], format="%.2f", key=f"edit_price_{ek}"
            )

        if sel["image_url"]:
            st.image(sel["image_url"], width=140, caption="Current image")
        new_image = st.file_uploader("Replace image (optional)", type=["png", "jpg", "jpeg", "webp"],
                                     key=f"edit_img_{ek}")

        # Live validation: tell the user before they press Save
        brand_n, name_n, tone_n = normalize_fields(edit_brand, edit_name, edit_tone)
        update_data = {
            "brand": brand_n,
            "product_name": name_n,
            "category": edit_category,
            "tone": tone_n,
            "quantity": int(edit_qty or 0),
            "price": float(edit_price or 0.0),
        }
        changed = new_image is not None or any(update_data[f] != sel[f] for f in update_data)
        clash = find_duplicate(brand_n, name_n, tone_n, exclude_id=k)

        if clash:
            st.warning(
                f"Another item already uses this brand, product and shade: **{label_of(clash)}**. Change one of them to save.")
        elif not changed:
            st.caption("No changes yet.")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 Save Changes", type="primary", width="stretch", key=f"save_btn_{k}",
                         disabled=bool(clash) or not changed):
                try:
                    with st.spinner("Saving…"):
                        if new_image is not None:
                            update_data["image_url"] = upload_image(new_image, brand_n, name_n)
                        supabase.table("inventory").update(update_data).eq("id", k).execute()
                        if new_image is not None:
                            delete_image(sel["image_url"])
                    st.toast(f"Updated {brand_n} — {name_n}", icon="✅")
                    st.rerun()
                except Exception as update_err:
                    st.error(f"Failed to update item: {update_err}")
        with b2:
            if st.button("↩️ Reset form", width="stretch", key=f"reset_btn_{k}", disabled=not changed,
                         help="Discard unsaved edits"):
                st.session_state[f"edit_nonce_{k}"] = en + 1
                st.rerun()
        with b3:
            if st.button("🗑️ Delete Item", type="secondary", width="stretch", key=f"full_del_btn_{k}",
                         help="You can undo this right after"):
                try:
                    delete_item(sel)
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
        m3.metric("Inventory Value ($)", money(total_inventory_val))
        m4.metric("Total Revenue Realized ($)", money(total_revenue))

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
            st.info("No sales transactions recorded yet. Completed checkouts will show up here.")