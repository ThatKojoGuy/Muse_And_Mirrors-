import html
import hmac
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

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

    /* Form sections, preview placeholder */
    .form-section {
        font-size: 12px; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase;
        color: #D2A8FF; margin: 14px 0 8px; padding-bottom: 5px;
        border-bottom: 1px solid rgba(210, 168, 255, 0.28);
    }
    .muted { color: #8B949E; font-style: italic; font-weight: 400; }
    .photo-ph {
        border: 1px dashed rgba(255, 255, 255, 0.25); border-radius: 12px;
        padding: 38px 8px; text-align: center; color: #8B949E; margin-bottom: 8px;
    }
    .st-key-card_preview:hover { transform: none; }

    /* Dialog: frosted glass panel */
    div[data-testid="stDialog"] div[role="dialog"] {
        background: rgba(16, 20, 28, 0.94);
        backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
        border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 20px;
    }
    /* Makeup-type chips wrap onto extra lines instead of scrolling sideways */
    [data-testid="stButtonGroup"] > div:last-child {
        flex-wrap: wrap !important; overflow: visible !important; row-gap: 6px;
    }
    /* Roomier inputs */
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div { min-height: 42px; }
    @media (max-width: 640px) {
        .price-tag { font-size: 16px; }
        [class*="st-key-card_"] { padding: 2px 0; }
    }

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
    "quick_nonce": 0,  # bump to reset the quick-add box
    "last_deleted": None,  # raw row, enables Undo
    "last_receipt": None,  # shown after a sale for closure
    "has_type": False,  # becomes True once the product_type column exists
    "has_void": False,  # becomes True once the sales.voided columns exist
    "rcpt_msg": None,  # result of the last void/delete action
    "has_who": False,  # becomes True once sales.customer_name / served_by exist
    "last_served_by": "",  # the cashier is remembered between sales
    "sale_nonce": 0,  # bump to clear the customer-name box after a sale
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

# Same check for the void columns on the sales table
if not st.session_state["has_void"]:
    try:
        supabase.table("sales").select("voided").limit(1).execute()
        st.session_state["has_void"] = True
    except Exception:
        st.session_state["has_void"] = False
HAS_VOID = st.session_state["has_void"]

# ...and for the optional customer name / cashier columns
if not st.session_state["has_who"]:
    try:
        supabase.table("sales").select("customer_name,served_by").limit(1).execute()
        st.session_state["has_who"] = True
    except Exception:
        st.session_state["has_who"] = False
HAS_WHO = st.session_state["has_who"]

# =====================================================================
# DATA
# =====================================================================
def fetch_all(table: str, page: int = 1000) -> list:
    """Read every row, newest first. Supabase returns at most 1000 rows per request,
    so this pages through the table instead of silently truncating."""
    rows, start = [], 0
    while True:
        batch = (
            supabase.table(table).select("*").order("id", desc=True)
            .range(start, start + page - 1).execute().data or []
        )
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


try:
    inv_rows = fetch_all("inventory")
except Exception as err:
    st.error(f"Inventory fetch error: {err}")
    inv_rows = []

raw_by_id = {r["id"]: r for r in inv_rows}
inventory_items = [clean_item(r) for r in inv_rows]
inventory_by_id = {i["id"]: i for i in inventory_items}

sales_history = []
if is_admin:  # sales/revenue are only loaded for admins
    try:
        sales_history = fetch_all("sales")
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
        "when": when,
        "voided": bool(sale.get("voided")),
        "void_reason": (sale.get("void_reason") or "").strip(),
        "customer": tidy(sale.get("customer_name")),
        "served_by": tidy(sale.get("served_by")),
    }


def receipt_html(r: dict) -> str:
    """Self-contained, print-friendly receipt (open the file and press Ctrl/Cmd+P)."""
    rows = "".join(
        f"<tr><td>{esc(li['name'])}</td><td class='n'>{li['qty']}</td>"
        f"<td class='n'>{money(li['unit'])}</td><td class='n'>{money(li['total'])}</td></tr>"
        for li in r["lines"]
    )
    contact = "".join(f"<div>{esc(x)}</div>" for x in (BUSINESS_ADDRESS, BUSINESS_PHONE) if x)
    who_html = "".join(
        f"<br>{label}: {esc(r[k])}"
        for k, label in (("customer", "Customer"), ("served_by", "Served by"))
        if r.get(k)
    )
    void_block = ""
    if r.get("voided"):
        why = f"<br><span style='font-size:13px;font-weight:400'>{esc(r['void_reason'])}</span>" if r.get("void_reason") else ""
        void_block = (
            "<p style='text-align:center;color:#b00020;font-weight:700;font-size:22px;"
            f"border:3px solid #b00020;padding:6px;margin:10px 0'>VOID{why}</p>"
        )
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
<p class="c"><b>RECEIPT No. {esc(r['number'])}</b><br>{esc(r['date'])}{who_html}</p>{void_block}
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
    if r.get("customer"):
        row(f"Customer: {r['customer']}", align="C")
    if r.get("served_by"):
        row(f"Served by: {r['served_by']}", align="C")
    if r.get("voided"):
        pdf.set_text_color(176, 0, 32)
        row("*** VOID ***", h=8, style="B", size=14, align="C")
        if r.get("void_reason"):
            row(r["void_reason"], align="C")
        pdf.set_text_color(0, 0, 0)
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
        who = " · ".join(
            f"{label}: **{esc(r[k])}**"
            for k, label in (("customer", "Customer"), ("served_by", "Served by"))
            if r.get(k)
        )
        if who:
            st.markdown(who)
        if r.get("voided"):
            st.error("🚫 **VOID**" + (f" — {r['void_reason']}" if r.get("void_reason") else ""))
        # Stacked lines (not a wide table) so every amount fits the narrow cart column
        for li in r["lines"]:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;gap:12px;"
                f"padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.1)'>"
                f"<div><b>{esc(li['name'])}</b><br>"
                f"<span style='color:#8B949E;font-size:13px'>{li['qty']} × {money(li['unit'])}</span></div>"
                f"<div style='white-space:nowrap'><b>{money(li['total'])}</b></div></div>",
                unsafe_allow_html=True,
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
            "🖨️ Print version",
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


def find_duplicate(brand, name, tone, exclude_id=None, items=None):
    key = (brand.lower(), name.lower(), tone.lower())
    for i in (inventory_items if items is None else items):
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


def complete_sale(cart_lines: dict, customer: str = "", served_by: str = ""):
    """Returns (ok, receipt_dict_or_list_of_problems). Stock is re-checked live,
    decremented with a guard against concurrent sales, and rolled back if
    logging the sale fails. `customer` and `served_by` are optional."""
    customer, served_by = tidy(customer)[:80], tidy(served_by)[:80]
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
            "item_id": iid,
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

        payload = {"total_amount": total, "items_sold": items_sold}
        if HAS_WHO:  # older databases simply don't store these two optional fields
            if customer:
                payload["customer_name"] = customer
            if served_by:
                payload["served_by"] = served_by
        ins = supabase.table("sales").insert(payload).execute()
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


def restore_stock(items_sold) -> tuple:
    """Put sold units back into inventory. Returns (restored_labels, skipped_labels).
    Lines are matched by item_id when the sale recorded one, else by brand/name/shade."""
    restored, skipped = [], []
    for li in items_sold or []:
        qty = int(li.get("quantity") or 0)
        label = f"{li.get('brand', 'N/A')} - {li.get('product_name', '')} x{qty}"
        if qty <= 0:
            continue
        target = inventory_by_id.get(li.get("item_id"))
        if target is None:
            b = (li.get("brand") or "").lower()
            n = (li.get("product_name") or "").lower()
            t = (li.get("tone") or "").lower() if "tone" in li else None
            target = next(
                (i for i in inventory_items
                 if i["brand"].lower() == b and i["product_name"].lower() == n
                 and (t is None or i["tone"].lower() == t)),
                None,
            )
        if target is None:
            skipped.append(f"{label} (product no longer exists)")
            continue
        done = False
        for _ in range(3):  # retry if someone changes the stock at the same moment
            cur = supabase.table("inventory").select("quantity").eq("id", target["id"]).execute().data
            if not cur:
                break
            current = int(cur[0]["quantity"] or 0)
            res = (
                supabase.table("inventory").update({"quantity": current + qty})
                .eq("id", target["id"]).eq("quantity", current).execute()
            )
            if res.data:
                done = True
                break
        (restored if done else skipped).append(label if done else f"{label} (stock update failed)")
    return restored, skipped


PERMISSION_HINT = "The database refused the change. Run the latest setup.sql in the Supabase SQL Editor, then try again."


def _stock_note(restored, skipped) -> str:
    note = f" {len(restored)} item line(s) returned to stock." if restored else ""
    if skipped:
        note += " Not returned: " + "; ".join(skipped) + "."
    return note


def void_sale(sale: dict, reason: str, return_stock: bool) -> tuple:
    """Mark a sale as void (the record is kept, revenue excludes it). Returns (ok, message)."""
    if not HAS_VOID:
        return False, "Voiding needs a one-time database update. Run the latest setup.sql, then refresh."
    num = build_receipt(sale)["number"]
    try:
        res = (
            supabase.table("sales")
            .update({"voided": True, "void_reason": tidy(reason) or None,
                     "voided_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", sale["id"]).eq("voided", False).execute()
        )
    except Exception as err:
        return False, f"Could not void receipt {num}: {err}"
    if not res.data:
        return False, f"Receipt {num} was not changed (already voided?). {PERMISSION_HINT}"
    note = ""
    if return_stock:
        note = _stock_note(*restore_stock(sale.get("items_sold")))
    return True, f"Receipt {num} voided.{note}"


def delete_sale(sale: dict, return_stock: bool) -> tuple:
    """Permanently erase a sale record. Returns (ok, message)."""
    num = build_receipt(sale)["number"]
    try:
        res = supabase.table("sales").delete().eq("id", sale["id"]).execute()
    except Exception as err:
        return False, f"Could not delete receipt {num}: {err}"
    if not res.data:
        return False, f"Receipt {num} was not deleted. {PERMISSION_HINT}"
    note = ""
    if return_stock and not sale.get("voided"):  # a voided sale was already dealt with
        note = _stock_note(*restore_stock(sale.get("items_sold")))
    return True, f"Receipt {num} permanently deleted.{note}"


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
# ADD-PRODUCT DIALOG
# =====================================================================
# Makeup types that clearly belong to one face area (used to pre-fill "Target area")
TYPE_AREA = {
    "mascara": "Eyes", "eyeshadow": "Eyes", "eyeliner": "Eyes", "brows": "Eyes",
    "lipstick": "Lips", "lip gloss": "Lips", "lip liner": "Lips",
    "blush": "Cheeks", "bronzer": "Cheeks", "highlighter": "Cheeks",
}
ADD_DEFAULTS = {
    "add_brand": None, "add_name": None, "add_type": None, "add_tone": None,
    "add_area": "Uncategorized", "add_qty": 1, "add_price": 0.0,
}


def fetch_inventory() -> list:
    return [clean_item(r) for r in fetch_all("inventory")]


def options_from(items: list):
    brands = dedupe_ci(i["brand"] for i in items if i["brand"] != "N/A")
    names = dedupe_ci(i["product_name"] for i in items if i["product_name"] != "Unnamed Item")
    tones = dedupe_ci(i["tone"] for i in items if i["tone"] != "N/A")
    types = dedupe_ci(DEFAULT_TYPES + [i["product_type"] for i in items if i["product_type"] != NO_TYPE])
    return brands, names, tones, types


def last_price_for(brand: str, items: list):
    for i in items:  # newest first
        if i["brand"].lower() == brand.lower() and i["price"] > 0:
            return i["price"]
    return None


def _on_brand_change():
    ss = st.session_state
    brand = tidy(ss.get("add_brand"))
    if not brand or ss.get("add_price"):
        return
    try:
        price = last_price_for(brand, fetch_inventory())
    except Exception:
        return
    if price:
        ss["add_price"] = float(price)


def _on_type_change():
    ss = st.session_state
    area = TYPE_AREA.get(tidy(ss.get("add_type")).lower())
    if area and ss.get("add_area", "Uncategorized") == "Uncategorized":
        ss["add_area"] = area


def _reset_add_fields(keep_brand_type: bool, price: float = 0.0):
    ss = st.session_state
    ss["add_name"] = None
    ss["add_tone"] = None
    ss["add_qty"] = 1
    ss["add_img_nonce"] = ss.get("add_img_nonce", 0) + 1  # clears the file uploader
    if keep_brand_type:
        ss["add_price"] = float(price or 0.0)  # same brand is usually the same price
    else:
        for key in ("add_brand", "add_type"):
            ss[key] = None
        ss["add_area"] = "Uncategorized"
        ss["add_price"] = 0.0


def _save_new(close: bool):
    """Button callback: validate against fresh data, save, then reset for the next item."""
    ss = st.session_state
    try:
        items = fetch_inventory()
        brands, names, tones, types = options_from(items)
        brand = canon(ss.get("add_brand"), brands) or "N/A"
        name = canon(ss.get("add_name"), names) or "Unnamed Item"
        tone = canon(ss.get("add_tone"), tones) or "N/A"
        ptype = canon(ss.get("add_type"), types) or NO_TYPE
        if find_duplicate(brand, name, tone, items=items):
            ss["add_msg"] = ("error", f"{brand} — {name} ({tone}) already exists. Use “Add to stock” instead.")
            return
        image_url, warn = None, ""
        upload = ss.get(f"add_img_{ss.get('add_img_nonce', 0)}")
        if upload is not None:
            try:
                image_url = upload_image(upload, brand, name)
            except Exception as img_err:
                warn = f" (photo not saved: {img_err})"
        qty = int(ss.get("add_qty") or 0)
        price = float(ss.get("add_price") or 0.0)
        data = with_type(
            {
                "brand": brand, "product_name": name, "category": ss.get("add_area") or "Uncategorized",
                "tone": tone, "quantity": qty, "price": price, "image_url": image_url,
            },
            ptype,
        )
        supabase.table("inventory").insert(data).execute()
    except Exception as err:
        ss["add_msg"] = ("error", f"Could not save the product: {err}")
        return
    note = " Price is 0.00, remember to set it." if not price else ""
    ss["add_msg"] = ("success", f"Saved {brand} — {name}.{note}{warn}")
    _reset_add_fields(keep_brand_type=not close, price=price)
    if close:
        ss["add_close"] = True


def _add_to_existing(dup_id):
    ss = st.session_state
    try:
        row = supabase.table("inventory").select("id,quantity,brand,product_name").eq("id", dup_id).execute().data[0]
        add = int(ss.get("add_qty") or 0)
        supabase.table("inventory").update({"quantity": int(row["quantity"] or 0) + add}).eq("id", dup_id).execute()
    except Exception as err:
        ss["add_msg"] = ("error", f"Could not update stock: {err}")
        return
    ss["add_msg"] = ("success", f"Added {add} to {row['brand']} — {row['product_name']}.")
    _reset_add_fields(keep_brand_type=True, price=float(ss.get("add_price") or 0.0))


def _cancel_add():
    st.session_state.pop("add_msg", None)
    _reset_add_fields(keep_brand_type=False)
    st.session_state["add_close"] = True


def section(title: str):
    st.markdown(f"<div class='form-section'>{esc(title)}</div>", unsafe_allow_html=True)


def add_product_form():
    ss = st.session_state
    for key, default in ADD_DEFAULTS.items():
        ss.setdefault(key, default)
    ss.setdefault("add_img_nonce", 0)

    msg = ss.pop("add_msg", None)
    if ss.pop("add_close", False):  # a full rerun closes the dialog and refreshes the page behind it
        if msg:
            st.toast(msg[1], icon="✅" if msg[0] == "success" else "⚠️")
        st.rerun()

    items = fetch_inventory()  # always fresh, so duplicates and suggestions are never stale
    brands, names, tones, types = options_from(items)

    if msg:
        (st.success if msg[0] == "success" else st.error)(msg[1])

    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Product")
        c1, c2 = st.columns(2)
        c1.selectbox(
            "Brand *", brands, index=None, accept_new_options=True,
            placeholder="Pick or type a brand", key="add_brand", on_change=_on_brand_change,
            help="Not in the list? Type it and press Enter. Capitalisation is matched automatically.",
        )
        c2.selectbox(
            "Product name *", names, index=None, accept_new_options=True,
            placeholder="Pick or type a name", key="add_name",
        )
        c3, c4 = st.columns(2)
        c3.selectbox(
            "Makeup type", types, index=None, accept_new_options=True,
            placeholder="e.g., Foundation", key="add_type", on_change=_on_type_change,
            disabled=not HAS_TYPE, help="Used to filter the catalog and POS. Type a new type and press Enter to create it.",
        )
        c4.selectbox(
            "Tone / shade", tones, index=None, accept_new_options=True,
            placeholder="e.g., Warm Nude", key="add_tone",
        )

        section("Stock & price")
        c5, c6, c7 = st.columns(3)
        c5.selectbox("Target area", CATEGORIES, key="add_area")
        c6.number_input("Quantity", min_value=0, step=1, key="add_qty")
        c7.number_input("Retail price", min_value=0.0, step=0.5, format="%.2f", key="add_price")

        brand_typed = tidy(ss.get("add_brand"))
        lp = last_price_for(brand_typed, items) if brand_typed else None
        if lp:
            st.caption(f"💡 Last price used for {canon(brand_typed, brands)}: **{money(lp)}**")

        section("Photo")
        upload = st.file_uploader(
            "Product image (optional)", type=["png", "jpg", "jpeg", "webp"],
            key=f"add_img_{ss['add_img_nonce']}", label_visibility="collapsed",
        )
        st.caption("\\* Recommended. Anything left blank is saved as “N/A” / “Unnamed Item”.")

    brand = canon(ss.get("add_brand"), brands)
    name = canon(ss.get("add_name"), names)
    tone = canon(ss.get("add_tone"), tones)
    ptype = canon(ss.get("add_type"), types) or NO_TYPE
    qty = int(ss.get("add_qty") or 0)
    price = float(ss.get("add_price") or 0.0)
    dup = find_duplicate(brand or "N/A", name or "Unnamed Item", tone or "N/A", items=items)

    with right:
        section("Live preview")
        preview = {"product_type": ptype}
        with st.container(border=True, key="card_preview"):
            if upload is not None:
                st.image(upload.getvalue(), width="stretch")
            else:
                st.markdown("<div class='photo-ph'>📷 No photo yet</div>", unsafe_allow_html=True)
            st.markdown(
                f"#### {esc(brand) if brand else '<span class=muted>Brand name</span>'}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**{esc(name)}**" if name else "<span class='muted'>Product name</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"{type_badge(preview)}"
                f"<span class='badge category-badge'>{esc(ss.get('add_area') or 'Uncategorized')}</span>"
                f"<span class='badge shade-badge'>Shade: {esc(tone or 'N/A')}</span>"
                f"{status_badge(qty)}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<span class='price-tag'>{money(price)}</span> &nbsp;|&nbsp; Stock: {qty}",
                unsafe_allow_html=True,
            )
        if dup:
            st.warning(f"**{label_of(dup)}** already exists ({dup['quantity']} in stock).")
            st.button(
                f"➕ Add {qty} to its stock", key="add_to_existing", width="stretch",
                on_click=_add_to_existing, args=(dup["id"],), disabled=qty <= 0,
            )
        elif not price:
            st.caption("⚠️ Price is 0.00. You can still save and set it later.")

    a1, a2, a3 = st.columns([1, 2, 2])
    a1.button("Cancel", key="add_cancel", width="stretch", on_click=_cancel_add)
    a2.button(
        "💾 Save & add another", key="add_save_more", width="stretch",
        on_click=_save_new, args=(False,), disabled=bool(dup),
        help="Keeps brand, type and area filled in for the next item.",
    )
    a3.button(
        "✅ Save & close", key="add_save_close", type="primary", width="stretch",
        on_click=_save_new, args=(True,), disabled=bool(dup),
    )


def _dialog():
    try:  # on_dismiss needs a recent Streamlit; fall back gracefully
        return st.dialog("➕ Add New Product", width="large", on_dismiss="rerun")
    except TypeError:
        return st.dialog("➕ Add New Product", width="large")


@_dialog()
def add_product_dialog():
    add_product_form()


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

        if st.button("➕ Add Product", type="primary", width="stretch", key="open_add_sidebar"):
            add_product_dialog()
        st.caption("Opens a form with a live preview.")
    else:
        st.info("💡 **Viewer Mode**: Log in as Admin above to add, edit, or delete inventory.")

# =====================================================================
# HEADER
# =====================================================================
head_l, head_r = st.columns([5, 1.2], vertical_alignment="center")
head_l.title("✨ Muse & Mirrors Studio POS")
if is_admin and head_r.button("➕ Add Product", type="primary", width="stretch", key="open_add_main"):
    add_product_dialog()

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

                # Optional details that appear on the receipt
                staff = dedupe_ci(
                    s["served_by"] for s in sales_history if tidy(s.get("served_by"))
                )
                last = st.session_state["last_served_by"]
                if last and idx_ci(staff, last) is None:
                    staff.append(last)
                customer_in = st.text_input(
                    "Customer name (optional)", max_chars=80, disabled=not HAS_WHO,
                    key=f"sale_customer_{st.session_state['sale_nonce']}",
                    placeholder="e.g., Ama Mensah",
                )
                served_in = st.selectbox(
                    "Served by (optional)", staff, index=idx_ci(staff, last),
                    accept_new_options=True, disabled=not HAS_WHO, key="sale_served_by",
                    placeholder="Who made this sale? Pick or type a name",
                    help="Remembered for the next sale. Type a new name to add it.",
                )
                served_in = canon(served_in, staff) if served_in else ""
                st.session_state["last_served_by"] = served_in
                if not HAS_WHO:
                    st.caption("Run the latest `setup.sql` once to enable these two fields.")

                b_clear, b_pay = st.columns([1, 2])
                if b_clear.button("🧹 Clear", key="clear_cart", width="stretch", help="Empty the cart"):
                    cart.clear()
                    st.rerun()
                if b_pay.button("💳 Complete Transaction", type="primary", width="stretch"):
                    with st.spinner("Recording sale…"):
                        ok, result = complete_sale(cart, customer_in, served_in)
                    if ok:
                        st.session_state["sale_nonce"] += 1  # clears the customer box
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

        # Quick restock: the most common stock change, one click
        with st.container(border=True, key="card_restock"):
            r1, r2 = st.columns([2, 1], vertical_alignment="bottom")
            units = r1.number_input(
                "📦 Quick restock: units received", min_value=1, step=1, value=1, key=f"restock_units_{k}"
            )
            if r2.button("➕ Add to stock", key=f"restock_btn_{k}", width="stretch", type="primary"):
                try:
                    supabase.table("inventory").update(
                        {"quantity": sel["quantity"] + int(units)}
                    ).eq("id", k).execute()
                    st.toast(f"Stock is now {sel['quantity'] + int(units)}", icon="📦")
                    st.rerun()
                except Exception as err:
                    st.error(f"Could not update stock: {err}")

        section("Product")
        e1, e2 = st.columns(2)
        edit_brand = e1.selectbox(
            "Brand *", brand_opts, index=idx_ci(brand_opts, sel["brand"]),
            accept_new_options=True, key=f"edit_brand_{ek}",
            help="Type to search, or type a new brand and press Enter.",
        )
        edit_name = e2.selectbox(
            "Product name *", name_opts, index=idx_ci(name_opts, sel["product_name"]),
            accept_new_options=True, key=f"edit_name_{ek}",
        )
        e3, e4 = st.columns(2)
        edit_type = e3.selectbox(
            "Makeup type", type_opts, index=idx_ci(type_opts, sel["product_type"]),
            accept_new_options=True, key=f"edit_type_{ek}", disabled=not HAS_TYPE,
            help="Type a new type and press Enter to create it.",
        )
        edit_tone = e4.selectbox(
            "Tone / shade", tone_opts, index=idx_ci(tone_opts, sel["tone"]),
            accept_new_options=True, key=f"edit_tone_{ek}",
        )

        section("Stock & price")
        e5, e6, e7 = st.columns(3)
        cat_idx = CATEGORIES.index(sel["category"]) if sel["category"] in CATEGORIES else 0
        edit_category = e5.selectbox("Target area", CATEGORIES, index=cat_idx, key=f"edit_cat_{ek}")
        edit_qty = e6.number_input("Quantity", min_value=0, step=1, value=sel["quantity"], key=f"edit_qty_{ek}")
        edit_price = e7.number_input(
            "Retail price", min_value=0.0, step=0.5, value=sel["price"], format="%.2f", key=f"edit_price_{ek}"
        )

        section("Photo")
        if sel["image_url"]:
            st.image(sel["image_url"], width=140, caption="Current image")
        new_image = st.file_uploader(
            "Replace image (optional)", type=["png", "jpg", "jpeg", "webp"], key=f"edit_img_{ek}"
        )

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
# TAB 4: SALES, RECEIPTS & REVENUE (ADMIN ONLY)
# =====================================================================
def describe_sale(items) -> str:
    if not isinstance(items, list):
        return ""
    return "; ".join(
        f"{i.get('brand', 'N/A')} {i.get('product_name', '')} ×{i.get('quantity', 0)} @ {float(i.get('unit_price') or 0):.2f}"
        for i in items
    )


with tab_analytics:
    if not is_admin:
        st.warning("🔒 Log in as Admin via the sidebar to view sales and revenue.")
    else:
        completed = [s for s in sales_history if not s.get("voided")]
        voided = [s for s in sales_history if s.get("voided")]

        total_products = len(inventory_items)
        total_stock = sum(i["quantity"] for i in inventory_items)
        total_inventory_val = sum(i["quantity"] * i["price"] for i in inventory_items)
        total_revenue = sum(float(s.get("total_amount") or 0.0) for s in completed)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Unique Items", total_products)
        m2.metric("In-Stock Units", total_stock)
        m3.metric("Inventory Value", money(total_inventory_val))
        m4.metric("Total Revenue Realized", money(total_revenue))
        if voided:
            st.caption(f"{len(voided)} voided sale(s) are not counted in revenue.")

        st.divider()
        st.subheader("🧾 Receipts & Sales History")

        banner = st.session_state.pop("rcpt_msg", None)
        if banner:
            (st.success if banner[0] == "success" else st.error)(banner[1])

        if not sales_history:
            st.info("No sales transactions recorded yet. Completed checkouts will show up here.")
        else:
            f1, f2, f3 = st.columns([3, 2, 2])
            q = tidy(f1.text_input("🔍 Search receipt no., customer, staff or items", key="rcpt_search")).lower()
            date_pick = f2.date_input("Date range", value=(), key="rcpt_dates")
            status_pick = f3.selectbox("Status", ["All", "Completed", "Voided"], key="rcpt_status")

            days = list(date_pick) if isinstance(date_pick, (list, tuple)) else [date_pick]
            lo = days[0] if days else None
            hi = days[-1] if days else None

            pairs = []
            for sale in sales_history:
                r = build_receipt(sale)
                hay = (f"{r['number']} {r['customer']} {r['served_by']} "
                       f"{describe_sale(sale.get('items_sold'))}").lower()
                if q and not all(w in hay for w in q.split()):
                    continue
                if lo and not (lo <= r["when"].date() <= hi):
                    continue
                if status_pick == "Completed" and r["voided"]:
                    continue
                if status_pick == "Voided" and not r["voided"]:
                    continue
                pairs.append((sale, r))

            st.caption(f"Showing {len(pairs)} of {len(sales_history)} receipts")
            if not pairs:
                st.info("No receipts match your filters. Try clearing the search or the date range.")
            else:
                df = pd.DataFrame(
                    {
                        "Receipt No.": [r["number"] for _, r in pairs],
                        "Timestamp": [r["when"] for _, r in pairs],
                        "Customer": [r["customer"] or "-" for _, r in pairs],
                        "Served by": [r["served_by"] or "-" for _, r in pairs],
                        "Items Sold Details": [describe_sale(s.get("items_sold")) for s, _ in pairs],
                        "Total": [r["total"] for _, r in pairs],
                        "Status": ["🚫 VOID" if r["voided"] else "✓ Completed" for _, r in pairs],
                    }
                )
                st.dataframe(
                    df,
                    hide_index=True,  # internal IDs never shown
                    width="stretch",
                    column_config={
                        "Total": st.column_config.NumberColumn(format="%.2f"),
                        "Timestamp": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
                        "Items Sold Details": st.column_config.TextColumn(width="large"),
                    },
                )

                st.markdown("##### Open a receipt")
                by_id = {s["id"]: (s, r) for s, r in pairs}
                picked = st.selectbox(
                    "Select a receipt to view, reprint, void or delete",
                    options=list(by_id.keys()),
                    format_func=lambda sid: (
                        f"No. {by_id[sid][1]['number']} · {by_id[sid][1]['date']} · "
                        f"{money(by_id[sid][1]['total'])}" + ("  [VOID]" if by_id[sid][1]["voided"] else "")
                    ),
                    index=None,
                    placeholder="Choose a receipt",
                    key="reprint_sale",
                )
                if picked is not None:
                    sale, r = by_id[picked]
                    view_col, act_col = st.columns([1, 1], gap="large")
                    with view_col:
                        render_receipt(r, f"past_{picked}")
                    with act_col:
                        st.markdown("##### Manage this receipt")
                        if r["voided"]:
                            st.info(
                                "This sale is **void**: the record is kept for your books, "
                                "but it no longer counts toward revenue."
                            )
                        else:
                            with st.expander("🚫 Void this sale (recommended)", expanded=True):
                                st.caption("Keeps the record, marks it VOID and removes it from revenue.")
                                if not HAS_VOID:
                                    st.warning("Voiding needs a one-time database update: run the latest `setup.sql`, then refresh.")
                                reason = st.text_input(
                                    "Reason (optional)", placeholder="e.g., wrong item, customer returned it",
                                    key=f"void_reason_{picked}",
                                )
                                back = st.checkbox("Return the items to stock", value=True, key=f"void_stock_{picked}")
                                sure = st.checkbox("I understand this can't be undone", key=f"void_sure_{picked}")
                                if st.button(
                                    "🚫 Void receipt", type="primary", width="stretch",
                                    disabled=not (sure and HAS_VOID), key=f"void_btn_{picked}",
                                ):
                                    ok, msg = void_sale(sale, reason, back)
                                    st.session_state["rcpt_msg"] = ("success" if ok else "error", msg)
                                    st.rerun()

                        with st.expander("🗑️ Delete permanently"):
                            st.warning(
                                "This erases the sale completely, as if it never happened, "
                                "and revenue will drop. Use **Void** instead unless you are sure."
                            )
                            back_del = False
                            if not r["voided"]:
                                back_del = st.checkbox("Also return the items to stock", value=False, key=f"del_stock_{picked}")
                            typed = st.text_input(f"Type the receipt number ({r['number']}) to confirm", key=f"del_confirm_{picked}")
                            if st.button(
                                "🗑️ Delete receipt permanently", width="stretch",
                                disabled=tidy(typed) != r["number"], key=f"del_btn_{picked}",
                            ):
                                ok, msg = delete_sale(sale, back_del)
                                st.session_state["rcpt_msg"] = ("success" if ok else "error", msg)
                                st.rerun()