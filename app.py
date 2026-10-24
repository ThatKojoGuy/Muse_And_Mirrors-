import html
import hmac
import re
import uuid
from collections import Counter
from datetime import datetime

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
    .type-badge { background: rgba(188, 140, 255, 0.15); color: #D2A8FF; font-weight: 600; border: 1px solid rgba(188, 140, 255, 0.35); }
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
# Suggested makeup types. Admins can type any new type and it is remembered.
DEFAULT_TYPES = [
    "Foundation", "Concealer", "Primer", "Powder", "Blush", "Bronzer", "Highlighter",
    "Eyeshadow", "Eyeliner", "Mascara", "Brows", "Lipstick", "Lip Gloss", "Lip Liner",
    "Setting Spray", "Skincare", "Tools & Brushes", "Other",
]
NO_TYPE = "Uncategorized"
LOW_STOCK = 3
GRID_COLUMNS = 4  # products per row in the Visual Catalog
BUCKET = "product_images"


def esc(value) -> str:
    return html.escape(str(value))


def money(value: float) -> str:
    return f"{value:,.2f}"


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
        "product_type": (row.get("product_type") or "").strip() or NO_TYPE,
        "category": row.get("category") or "Uncategorized",
        "tone": (row.get("tone") or "").strip() or "N/A",
        "quantity": int(row.get("quantity") or 0),
        "price": float(row.get("price") or 0.0),
        "image_url": row.get("image_url"),
    }


def label_of(item: dict) -> str:
    return f"{item['brand']} — {item['product_name']} ({item['tone']})"


def matches(item: dict, query: str) -> bool:
    """Every word typed must appear somewhere in brand, name, type, shade or area."""
    hay = " ".join(
        [item["brand"], item["product_name"], item["product_type"], item["tone"], item["category"]]
    ).lower()
    return all(word in hay for word in query.split())


def status_badge(qty: int) -> str:
    """Status is always conveyed by icon + text, never by colour alone."""
    if qty > 0:
        out = "<span class='badge status-available'>✓ AVAILABLE</span>"
        if qty <= LOW_STOCK:
            out += f"<span class='badge status-low'>⚠ ONLY {qty} LEFT</span>"
        return out
    return "<span class='badge status-soldout'>✕ SOLD OUT</span>"


def type_badge(item: dict) -> str:
    if item["product_type"] == NO_TYPE:
        return ""
    return f"<span class='badge type-badge'>{esc(item['product_type'])}</span>"


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

# Optional: printed at the top of every receipt (add to Streamlit Secrets to customise)
BUSINESS_NAME = get_secret("BUSINESS_NAME") or "Muse & Mirrors Studio"
BUSINESS_ADDRESS = get_secret("BUSINESS_ADDRESS") or ""
BUSINESS_PHONE = get_secret("BUSINESS_PHONE") or ""

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
    "has_type": False,  # becomes True once the product_type column exists
}.items():
    st.session_state.setdefault(key, default)

is_admin = st.session_state["is_admin"]

# Has the database been upgraded with the product_type column? (re-checked until it has)
if not st.session_state["has_type"]:
    try:
        supabase.table("inventory").select("product_type").limit(1).execute()
        st.session_state["has_type"] = True
    except Exception:
        st.session_state["has_type"] = False
HAS_TYPE = st.session_state["has_type"]

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
existing_types = dedupe_ci(
    DEFAULT_TYPES + [i["product_type"] for i in inventory_items if i["product_type"] != NO_TYPE]
)


# =====================================================================
# RECEIPTS
# =====================================================================
def build_receipt(sale: dict) -> dict:
    """Turn a `sales` row into a printable receipt structure."""
    created = pd.to_datetime(sale.get("created_at"), errors="coerce")
    when = created.to_pydatetime() if pd.notna(created) else datetime.now()
    lines = []
    for li in sale.get("items_sold") or []:
        qty = int(li.get("quantity") or 0)
        unit = float(li.get("unit_price") or 0.0)
        name = f"{li.get('brand', 'N/A')} - {li.get('product_name', '')}".strip(" -")
        if li.get("tone") and li.get("tone") != "N/A":
            name += f" ({li['tone']})"
        lines.append({"name": name, "qty": qty, "unit": unit, "total": round(qty * unit, 2)})
    sale_id = sale.get("id")
    return {
        "number": f"{int(sale_id):05d}" if sale_id is not None else "-----",
        "date": when.strftime("%d %b %Y, %H:%M"),
        "lines": lines,
        "units": sum(line["qty"] for line in lines),
        "total": round(float(sale.get("total_amount") or 0.0), 2),
    }


def receipt_html(r: dict) -> str:
    """Self-contained, print-friendly receipt (open the file and press Ctrl/Cmd+P)."""
    rows = "".join(
        f"<tr><td>{esc(li['name'])}</td><td class='n'>{li['qty']}</td>"
        f"<td class='n'>{money(li['unit'])}</td><td class='n'>{money(li['total'])}</td></tr>"
        for li in r["lines"]
    )
    contact = "".join(f"<div>{esc(x)}</div>" for x in (BUSINESS_ADDRESS, BUSINESS_PHONE) if x)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Receipt {esc(r['number'])}</title>
<style>
 body{{font-family:Arial,Helvetica,sans-serif;max-width:420px;margin:24px auto;padding:0 12px;color:#111}}
 h1{{font-size:20px;margin:0;text-align:center}} .c{{text-align:center;font-size:13px;color:#444}}
 table{{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}}
 th{{text-align:left;border-bottom:2px solid #111;padding:4px 0}} td{{padding:5px 0;border-bottom:1px solid #ddd}}
 .n{{text-align:right;white-space:nowrap;padding-left:8px}} .t{{font-size:18px;font-weight:700;text-align:right;margin-top:12px}}
 @media print{{body{{margin:0}}}}
</style></head><body>
<h1>{esc(BUSINESS_NAME)}</h1><div class="c">{contact}</div>
<p class="c"><b>RECEIPT No. {esc(r['number'])}</b><br>{esc(r['date'])}</p>
<table><tr><th>Item</th><th class="n">Qty</th><th class="n">Price</th><th class="n">Total</th></tr>{rows}</table>
<div class="t">TOTAL {money(r['total'])}</div>
<p class="c">{r['units']} item(s) &middot; Thank you for shopping with us!</p>
</body></html>"""


def receipt_pdf(r: dict):
    """A5 PDF receipt. Returns bytes, or None if the PDF library isn't installed."""
    try:
        from fpdf import FPDF
    except Exception:
        return None

    _plain = str.maketrans(
        {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "×": "x", "•": "-"}
    )

    def t(s):  # the built-in PDF fonts are Latin-1 only
        return str(s).translate(_plain).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(format="A5")
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    w = pdf.epw

    def row(text, h=5, style="", size=9, align="L"):
        pdf.set_font("Helvetica", style, size)
        pdf.cell(w, h, t(text), align=align, new_x="LMARGIN", new_y="NEXT")

    def rule():
        pdf.ln(1)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + w, pdf.get_y())
        pdf.ln(2)

    row(BUSINESS_NAME, h=9, style="B", size=16, align="C")
    for extra in (BUSINESS_ADDRESS, BUSINESS_PHONE):
        if extra:
            row(extra, align="C")
    pdf.ln(3)
    row("RECEIPT", h=7, style="B", size=12, align="C")
    row(f"No. {r['number']}   |   {r['date']}", align="C")
    rule()
    for li in r["lines"]:
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(w, 5, t(li["name"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(w * 0.6, 5, t(f"{li['qty']} x {money(li['unit'])}"))
        pdf.cell(w * 0.4, 5, t(money(li["total"])), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    rule()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(w * 0.5, 8, "TOTAL")
    pdf.cell(w * 0.5, 8, t(money(r["total"])), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    row(f"{r['units']} item(s)  -  Thank you for shopping with us!", align="C")
    return bytes(pdf.output())


def render_receipt(r: dict, prefix: str):
    """On-screen receipt with download buttons."""
    with st.container(border=True, key=f"card_receipt_{prefix}"):
        st.markdown(f"#### 🧾 {esc(BUSINESS_NAME)}")
        sub = " · ".join(x for x in (BUSINESS_ADDRESS, BUSINESS_PHONE) if x)
        if sub:
            st.caption(sub)
        st.markdown(f"**Receipt No. {esc(r['number'])}** · {esc(r['date'])}")
        df = pd.DataFrame(
            {
                "Item": [li["name"] for li in r["lines"]],
                "Qty": [li["qty"] for li in r["lines"]],
                "Price": [li["unit"] for li in r["lines"]],
                "Total": [li["total"] for li in r["lines"]],
            }
        )
        st.dataframe(
            df,
            hide_index=True,
            width="stretch",
            column_config={
                "Price": st.column_config.NumberColumn(format="%.2f"),
                "Total": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.markdown(f"### Total: `{money(r['total'])}`")
        st.caption(f"{r['units']} item(s) · Thank you for shopping with us!")

        d1, d2 = st.columns(2)
        pdf_bytes = receipt_pdf(r)
        if pdf_bytes:
            d1.download_button(
                "⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"receipt-{r['number']}.pdf",
                mime="application/pdf",
                width="stretch",
                key=f"dl_pdf_{prefix}",
            )
        d2.download_button(
            "🖨️ Printable page (HTML)",
            data=receipt_html(r),
            file_name=f"receipt-{r['number']}.html",
            mime="text/html",
            width="stretch",
            key=f"dl_html_{prefix}",
            help="Open the file and press Ctrl/Cmd + P to print.",
        )


# =====================================================================
# ACTIONS
# =====================================================================
def normalize_fields(brand_raw, name_raw, tone_raw):
    """Apply case-insensitive matching + fallbacks to the three text fields."""
    brand = canon(brand_raw, existing_brands) or "N/A"
    name = canon(name_raw, existing_names) or "Unnamed Item"
    tone = canon(tone_raw, existing_tones) or "N/A"
    return brand, name, tone


def normalize_type(type_raw) -> str:
    return canon(type_raw, existing_types) or NO_TYPE


def with_type(data: dict, product_type: str) -> dict:
    """Only send product_type once the database has that column."""
    if HAS_TYPE:
        data["product_type"] = product_type
    return data


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
        .select("id,brand,product_name,tone,quantity,price")
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

    total = round(sum(fresh[iid]["price"] * qty for iid, qty in cart_lines.items()), 2)
    items_sold = [
        {
            "brand": fresh[iid]["brand"],
            "product_name": fresh[iid]["product_name"],
            "tone": fresh[iid]["tone"],
            "quantity": qty,
            "unit_price": fresh[iid]["price"],
        }
        for iid, qty in cart_lines.items()
    ]

    decremented = []  # (id, original_qty) for rollback
    sale_row = {}
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

        ins = supabase.table("sales").insert(
            {"total_amount": total, "items_sold": items_sold}
        ).execute()
        sale_row = (ins.data or [{}])[0]
    except Exception as exc:
        for iid, original in decremented:
            try:
                supabase.table("inventory").update({"quantity": original}).eq("id", iid).execute()
            except Exception:
                pass
        return False, [str(exc)]

    sale_row.setdefault("total_amount", total)
    sale_row.setdefault("items_sold", items_sold)
    return True, build_receipt(sale_row)


# =====================================================================
# FILTER HELPERS
# =====================================================================
def type_pills(key: str) -> list:
    """Clickable makeup-type chips (with counts). Nothing selected = show all."""
    if not HAS_TYPE:
        return []
    counts = Counter(i["product_type"] for i in inventory_items)
    options = sorted(counts, key=str.lower)
    if len(options) < 2:
        return []
    picked = st.pills(
        "Makeup type",
        options,
        selection_mode="multi",
        format_func=lambda t: f"{t} ({counts[t]})",
        key=key,
        help="Pick one or more types. Leave empty to show everything.",
    )
    return list(picked or [])


def reset_catalog_filters():
    st.session_state["cat_search"] = ""
    st.session_state["cat_area"] = "All"
    st.session_state["cat_status"] = "All"
    st.session_state["cat_types"] = []


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
        cart_total = sum(inventory_by_id[i]["price"] * q for i, q in cart.items())
        st.markdown(
            f"🛒 **Cart:** {cart_units} item{'s' if cart_units != 1 else ''} · {money(cart_total)}"
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
            type_in = st.selectbox(
                "Makeup Type",
                options=existing_types,
                index=None,
                accept_new_options=True,
                placeholder="e.g., Foundation, Lipstick, Mascara",
                help="Used to filter the catalog and POS. Type a new type and press Enter to create it.",
                key=f"add_type_{n}",
                disabled=not HAS_TYPE,
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
            ptype = normalize_type(type_in)
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
                    data = with_type(
                        {
                            "brand": brand,
                            "product_name": name,
                            "category": category_in,
                            "tone": tone,
                            "quantity": int(qty_in or 0),
                            "price": float(price_in or 0.0),
                            "image_url": image_url,
                        },
                        ptype,
                    )
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

if is_admin and not HAS_TYPE:
    st.warning(
        "⚙️ **One-time database update needed:** the *Makeup Type* feature needs a new column. "
        "Run the latest `setup.sql` in the Supabase SQL Editor, then refresh this page."
    )

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

            pos_search = tidy(
                st.text_input("🔍 Search brand, product, type or shade...", key="pos_search")
            ).lower()
            pos_types = type_pills("pos_types")
            pos_items = [
                i for i in inventory_items
                if matches(i, pos_search) and (not pos_types or i["product_type"] in pos_types)
            ]

            if not inventory_items:
                st.info("No products yet. Add your first one from the sidebar.")
            elif not pos_items:
                st.info("No products match. Try a shorter search or clear the type filter.")

            grid_cols = st.columns(2)
            for idx, item in enumerate(pos_items):
                with grid_cols[idx % 2]:
                    with st.container(border=True, key=f"card_pos_{item['id']}"):
                        st.markdown(f"**{esc(item['brand'])}** - {esc(item['product_name'])}")
                        st.markdown(
                            f"{type_badge(item)}"
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
                    render_receipt(receipt, "latest")
                    if st.button("🆕 Start new order", type="primary", width="stretch"):
                        st.session_state["last_receipt"] = None
                        st.rerun()
                else:
                    st.info("Cart is empty. Tap **Add to Cart** on a product, or use Quick add.")
            else:
                total = 0.0
                for item_id, qty in list(cart.items()):
                    item = inventory_by_id[item_id]
                    line_total = qty * item["price"]
                    total += line_total

                    st.markdown(f"**{esc(item['brand'])} - {esc(item['product_name'])}**")
                    st.caption(f"Shade: {item['tone']} · {money(item['price'])} each")
                    c_minus, c_qty, c_plus, c_del, c_total = st.columns([1, 1, 1, 1, 2])
                    if c_minus.button("➖", key=f"minus_{item_id}", help="Remove one"):
                        if qty > 1:
                            cart[item_id] = qty - 1
                        else:
                            del cart[item_id]
                        st.rerun()
                    c_qty.markdown(f"<div style='text-align:center;padding-top:8px'><b>{qty}</b></div>", unsafe_allow_html=True)
                    if c_plus.button("➕", key=f"plus_{item_id}", help="Add one"):
                        msg = add_to_cart(item_id)
                        if msg:
                            st.toast(msg, icon="⚠️")
                        else:
                            st.rerun()
                    if c_del.button("🗑️", key=f"remove_cart_{item_id}", help="Remove from cart"):
                        del cart[item_id]
                        st.rerun()
                    c_total.markdown(f"<div style='text-align:right;padding-top:8px'><b>{money(line_total)}</b></div>", unsafe_allow_html=True)
                    st.divider()

                st.markdown(f"### Total: `{money(total)}`")

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
        cat_search = tidy(
            st.text_input("🔍 Search brand, product, type or shade...", key="cat_search")
        ).lower()
    with f2:
        area_filter = st.selectbox("Target Area", ["All"] + CATEGORIES, key="cat_area")
    with f3:
        status_filter = st.selectbox("Stock Availability", ["All", "Available", "Sold Out"], key="cat_status")

    cat_types = type_pills("cat_types")

    filtered = [
        i for i in inventory_items
        if matches(i, cat_search) and (not cat_types or i["product_type"] in cat_types)
    ]
    if area_filter != "All":
        filtered = [i for i in filtered if i["category"] == area_filter]
    if status_filter == "Available":
        filtered = [i for i in filtered if i["quantity"] > 0]
    elif status_filter == "Sold Out":
        filtered = [i for i in filtered if i["quantity"] <= 0]

    filters_active = bool(cat_search or cat_types or area_filter != "All" or status_filter != "All")
    count_col, clear_col = st.columns([5, 1])
    count_col.caption(f"Showing {len(filtered)} of {len(inventory_items)} products")
    if filters_active:
        clear_col.button("✖ Clear filters", key="clear_filters", on_click=reset_catalog_filters, width="stretch")

    if not inventory_items:
        st.info("The catalog is empty. Products will appear here once they're added.")
    elif not filtered:
        st.info("No items match your filters. Try clearing the search or setting filters back to All.")
    else:
        for start in range(0, len(filtered), GRID_COLUMNS):
            row_cols = st.columns(GRID_COLUMNS)
            for offset, col in enumerate(row_cols):
                if start + offset >= len(filtered):
                    continue
                item = filtered[start + offset]
                with col:
                    with st.container(border=True, key=f"card_cat_{item['id']}"):
                        if item["image_url"]:
                            st.image(item["image_url"], width="stretch")
                        st.markdown(f"#### {esc(item['brand'])}")
                        st.markdown(f"**{esc(item['product_name'])}**")
                        st.markdown(
                            f"{type_badge(item)}"
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
                            if st.button("🗑️ Quick Delete", key=f"quick_del_{item['id']}", width="stretch", help="You can undo this right after"):
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
        type_opts = dedupe_ci(existing_types + [sel["product_type"]])

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
            edit_type = st.selectbox(
                "Makeup Type", type_opts, index=idx_ci(type_opts, sel["product_type"]),
                accept_new_options=True, key=f"edit_type_{ek}", disabled=not HAS_TYPE,
                help="Type a new type and press Enter to create it.",
            )
            cat_idx = CATEGORIES.index(sel["category"]) if sel["category"] in CATEGORIES else 0
            edit_category = st.selectbox("Target Area", CATEGORIES, index=cat_idx, key=f"edit_cat_{ek}")
        with e2:
            edit_tone = st.selectbox(
                "Tone / Shade", tone_opts, index=idx_ci(tone_opts, sel["tone"]),
                accept_new_options=True, key=f"edit_tone_{ek}",
            )
            edit_qty = st.number_input("Stock Quantity", min_value=0, step=1, value=sel["quantity"], key=f"edit_qty_{ek}")
            edit_price = st.number_input(
                "Retail Price", min_value=0.0, step=0.5, value=sel["price"], format="%.2f", key=f"edit_price_{ek}"
            )

        if sel["image_url"]:
            st.image(sel["image_url"], width=140, caption="Current image")
        new_image = st.file_uploader("Replace image (optional)", type=["png", "jpg", "jpeg", "webp"], key=f"edit_img_{ek}")

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
        if HAS_TYPE:
            update_data["product_type"] = normalize_type(edit_type)
        changed = new_image is not None or any(update_data[f] != sel[f] for f in update_data)
        clash = find_duplicate(brand_n, name_n, tone_n, exclude_id=k)

        if clash:
            st.warning(f"Another item already uses this brand, product and shade: **{label_of(clash)}**. Change one of them to save.")
        elif not changed:
            st.caption("No changes yet.")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 Save Changes", type="primary", width="stretch", key=f"save_btn_{k}", disabled=bool(clash) or not changed):
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
            if st.button("↩️ Reset form", width="stretch", key=f"reset_btn_{k}", disabled=not changed, help="Discard unsaved edits"):
                st.session_state[f"edit_nonce_{k}"] = en + 1
                st.rerun()
        with b3:
            if st.button("🗑️ Delete Item", type="secondary", width="stretch", key=f"full_del_btn_{k}", help="You can undo this right after"):
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
        m3.metric("Inventory Value", money(total_inventory_val))
        m4.metric("Total Revenue Realized", money(total_revenue))

        st.divider()
        st.subheader("Completed Sales History")

        if sales_history:
            def describe(items):
                if not isinstance(items, list):
                    return ""
                return "; ".join(
                    f"{i.get('brand', 'N/A')} {i.get('product_name', '')} ×{i.get('quantity', 0)} @ {float(i.get('unit_price') or 0):.2f}"
                    for i in items
                )

            df = pd.DataFrame(
                {
                    "Total Revenue": [float(s.get("total_amount") or 0.0) for s in sales_history],
                    "Timestamp": pd.to_datetime([s.get("created_at") for s in sales_history], errors="coerce"),
                    "Items Sold Details": [describe(s.get("items_sold")) for s in sales_history],
                }
            )
            st.dataframe(
                df,
                hide_index=True,  # internal IDs never shown
                width="stretch",
                column_config={
                    "Total Revenue": st.column_config.NumberColumn(format="%.2f"),
                    "Timestamp": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
                    "Items Sold Details": st.column_config.TextColumn(width="large"),
                },
            )

            st.divider()
            st.subheader("🧾 Reprint a Receipt")
            sales_by_id = {s["id"]: s for s in sales_history}

            def sale_label(sid):
                r = build_receipt(sales_by_id[sid])
                return f"No. {r['number']} · {r['date']} · {money(r['total'])}"

            picked_sale = st.selectbox(
                "Select a past sale",
                options=list(sales_by_id.keys()),
                format_func=sale_label,
                index=None,
                placeholder="Choose a sale to view or download its receipt",
                key="reprint_sale",
            )
            if picked_sale is not None:
                render_receipt(build_receipt(sales_by_id[picked_sale]), f"past_{picked_sale}")
        else:
            st.info("No sales transactions recorded yet. Completed checkouts will show up here.")