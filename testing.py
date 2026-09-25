import os
import shutil
import sqlite3
import sys
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from PIL import Image, ImageTk

# Set GUI theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MakeupInventoryApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Makeup Inventory Management System")
        self.geometry("1100x750")

        # Allow flexible diagonal and horizontal scaling with a sensible minimum
        self.minsize(800, 500)
        self.resizable(True, True)

        # Application Working Directory (Portable DB & Images)
        self.app_path = self.get_app_path()
        self.img_dir = os.path.join(self.app_path, "product_images")
        os.makedirs(self.img_dir, exist_ok=True)

        self.selected_image_path = None
        self.selected_item_id = None
        self._search_timer = None

        # Fast Image Caching Memory
        self._image_cache = {}

        # Initialize Local SQLite Database
        self.init_db()

        # Responsive Grid Layout Setup
        self.grid_columnconfigure(0, weight=0, minsize=300)  # Fixed sidebar width preference
        self.grid_columnconfigure(1, weight=1)              # Main view expands freely
        self.grid_rowconfigure(0, weight=1)

        # Sidebar Frame
        self.sidebar_frame = ctk.CTkFrame(self, corner_radius=10)
        self.sidebar_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        # Main Right Frame
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        self.build_sidebar()
        self.build_main_view()
        self.load_data()

    def get_app_path(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    # ---------------- Database Management ----------------
    def init_db(self):
        db_path = os.path.join(self.app_path, "makeup_inventory.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT,
                product_name TEXT,
                category TEXT,
                tone TEXT,
                quantity INTEGER,
                price REAL,
                image_path TEXT
            )
        """)

        self.cursor.execute("PRAGMA table_info(inventory)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if "image_path" not in columns:
            self.cursor.execute("ALTER TABLE inventory ADD COLUMN image_path TEXT")

        self.conn.commit()

    # ---------------- Sidebar / Input Form ----------------
    def build_sidebar(self):
        self.scroll_sidebar = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.scroll_sidebar.pack(fill="both", expand=True, padx=2, pady=2)

        title_label = ctk.CTkLabel(
            self.scroll_sidebar,
            text="Product Details",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(padx=10, pady=(10, 10))

        fields = [
            ("Brand", "entry_brand", "e.g., Fenty Beauty"),
            ("Product Name", "entry_name", "e.g., Foundation"),
            ("Tone / Shade", "entry_tone", "e.g., Warm Nude"),
            ("Quantity", "entry_qty", "e.g., 5"),
            ("Price", "entry_price", "e.g., 24.99")
        ]

        for label_text, attr_name, placeholder in fields:
            lbl = ctk.CTkLabel(
                self.scroll_sidebar,
                text=label_text,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            lbl.pack(anchor="w", padx=10, pady=(4, 0))
            entry = ctk.CTkEntry(self.scroll_sidebar, placeholder_text=placeholder)
            entry.pack(fill="x", padx=10, pady=(0, 4))
            setattr(self, attr_name, entry)

        lbl_type = ctk.CTkLabel(
            self.scroll_sidebar,
            text="Category",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_type.pack(anchor="w", padx=10, pady=(4, 0))
        self.combo_type = ctk.CTkOptionMenu(
            self.scroll_sidebar,
            values=[
                "Uncategorized", "Foundation", "Concealer",
                "Lipstick", "Eyeshadow", "Blush", "Powder", "Other"
            ]
        )
        self.combo_type.pack(fill="x", padx=10, pady=(0, 4))

        lbl_img = ctk.CTkLabel(
            self.scroll_sidebar,
            text="Product Image",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_img.pack(anchor="w", padx=10, pady=(6, 0))
        self.btn_select_img = ctk.CTkButton(
            self.scroll_sidebar,
            text="📷 Select Image",
            command=self.select_image,
            fg_color="#3B82F6",
            hover_color="#2563EB"
        )
        self.btn_select_img.pack(fill="x", padx=10, pady=(2, 2))

        self.lbl_img_path = ctk.CTkLabel(
            self.scroll_sidebar,
            text="No image selected",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.lbl_img_path.pack(padx=10, pady=(0, 10))

        # Controls
        btn_add = ctk.CTkButton(
            self.scroll_sidebar,
            text="Add New Item",
            command=self.add_item,
            fg_color="#2EA043",
            hover_color="#238636"
        )
        btn_add.pack(fill="x", padx=10, pady=4)

        btn_update = ctk.CTkButton(
            self.scroll_sidebar,
            text="Update Selected",
            command=self.update_item,
            fg_color="#D97706",
            hover_color="#B45309"
        )
        btn_update.pack(fill="x", padx=10, pady=4)

        btn_delete = ctk.CTkButton(
            self.scroll_sidebar,
            text="Delete Selected",
            command=self.delete_item,
            fg_color="#DA3633",
            hover_color="#B62324"
        )
        btn_delete.pack(fill="x", padx=10, pady=4)

        btn_clear = ctk.CTkButton(
            self.scroll_sidebar,
            text="Clear Form",
            command=self.clear_form,
            fg_color="#30363D",
            hover_color="#484F58"
        )
        btn_clear.pack(fill="x", padx=10, pady=4)

    # ---------------- Main View & Table ----------------
    def build_main_view(self):
        search_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        search_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self.entry_search = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search by Brand or Name..."
        )
        self.entry_search.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry_search.bind("<KeyRelease>", self.on_search_key)

        btn_search = ctk.CTkButton(
            search_frame, text="Search", width=100, command=self.load_data
        )
        btn_search.grid(row=0, column=1)

        content_split = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        content_split.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        content_split.grid_columnconfigure(0, weight=4)
        content_split.grid_columnconfigure(1, weight=1, minsize=180)
        content_split.grid_rowconfigure(0, weight=1)

        # Custom Styling for Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#21252B",
            foreground="white",
            fieldbackground="#21252B",
            rowheight=28
        )
        style.map("Treeview", background=[("selected", "#1F6AA5")])

        columns = ("id", "brand", "name", "type", "tone", "qty", "price")
        self.tree = ttk.Treeview(
            content_split,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        self.tree.heading("id", text="ID")
        self.tree.heading("brand", text="Brand")
        self.tree.heading("name", text="Product Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("tone", text="Tone / Shade")
        self.tree.heading("qty", text="Qty")
        self.tree.heading("price", text="Price")

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("brand", width=110)
        self.tree.column("name", width=130)
        self.tree.column("type", width=90)
        self.tree.column("tone", width=100)
        self.tree.column("qty", width=50, anchor="center")
        self.tree.column("price", width=70, anchor="e")

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Add vertical scrollbar to table
        tree_scroll = ttk.Scrollbar(content_split, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=0, column=0, sticky="nse")

        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # Preview Panel
        self.preview_frame = ctk.CTkFrame(content_split)
        self.preview_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        lbl_preview_header = ctk.CTkLabel(
            self.preview_frame,
            text="Product Preview",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        lbl_preview_header.pack(pady=10)

        self.image_display = ctk.CTkLabel(
            self.preview_frame, text="Select an item\nto view image"
        )
        self.image_display.pack(expand=True, fill="both", padx=10, pady=10)

    # ---------------- Asynchronous Search Debouncing ----------------
    def on_search_key(self, event):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(250, self.load_data)

    # ---------------- Optimized Image Renderer ----------------
    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Product Image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")]
        )
        if file_path:
            self.selected_image_path = file_path
            filename = os.path.basename(file_path)
            self.lbl_img_path.configure(
                text=filename[:20] + "..." if len(filename) > 20 else filename
            )

    def display_preview(self, image_rel_path):
        if not image_rel_path:
            self.image_display.configure(image="", text="No image\navailable")
            return

        full_path = os.path.join(self.app_path, image_rel_path)

        if not os.path.exists(full_path):
            self.image_display.configure(image="", text="Image file\nmissing")
            return

        # Fast memory-based image retrieval
        if full_path in self._image_cache:
            self.image_display.configure(image=self._image_cache[full_path], text="")
            return

        try:
            pil_img = Image.open(full_path)
            pil_img.thumbnail((180, 180), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

            self._image_cache[full_path] = ctk_img
            self.image_display.configure(image=ctk_img, text="")
        except Exception:
            self.image_display.configure(image="", text="Error loading\nimage")

    def on_item_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0])["values"]
        self.selected_item_id = values[0]

        # Non-blocking form fill
        self.after_idle(self._fill_form_data, values)

    def _fill_form_data(self, values):
        self.entry_brand.delete(0, "end")
        self.entry_brand.insert(0, values[1] if values[1] != "N/A" else "")

        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, values[2] if values[2] != "Unnamed Item" else "")

        self.combo_type.set(values[3])

        self.entry_tone.delete(0, "end")
        self.entry_tone.insert(0, values[4] if values[4] != "N/A" else "")

        self.entry_qty.delete(0, "end")
        self.entry_qty.insert(0, str(values[5]))

        self.entry_price.delete(0, "end")
        raw_price = str(values[6]).replace("$", "")
        self.entry_price.insert(0, raw_price)

        self.cursor.execute(
            "SELECT image_path FROM inventory WHERE id = ?",
            (self.selected_item_id,)
        )
        result = self.cursor.fetchone()
        if result and result[0]:
            self.display_preview(result[0])
            filename = os.path.basename(result[0])
            self.lbl_img_path.configure(
                text=filename[:20] + "..." if len(filename) > 20 else filename
            )
        else:
            self.display_preview(None)
            self.lbl_img_path.configure(text="No image attached")

    # ---------------- Data CRUD Operations ----------------
    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        query = self.entry_search.get().strip()
        if query:
            self.cursor.execute(
                """
                SELECT id, brand, product_name, category, tone, quantity, price 
                FROM inventory WHERE brand LIKE ? OR product_name LIKE ?
            """,
                (f"%{query}%", f"%{query}%")
            )
        else:
            self.cursor.execute(
                "SELECT id, brand, product_name, category, tone, quantity, price FROM inventory"
            )

        rows = self.cursor.fetchall()
        for row in rows:
            formatted_row = list(row)
            formatted_row[6] = f"${row[6]:.2f}"
            self.tree.insert("", "end", values=formatted_row)

    def parse_inputs(self):
        brand = self.entry_brand.get().strip() or "N/A"
        name = self.entry_name.get().strip() or "Unnamed Item"
        category = self.combo_type.get()
        tone = self.entry_tone.get().strip() or "N/A"

        raw_qty = self.entry_qty.get().strip()
        raw_price = self.entry_price.get().strip()

        try:
            qty = int(raw_qty) if raw_qty else 0
        except ValueError:
            messagebox.showerror("Input Error", "Quantity must be a valid integer.")
            return None

        try:
            price = float(raw_price) if raw_price else 0.0
        except ValueError:
            messagebox.showerror("Input Error", "Price must be a valid number.")
            return None

        return brand, name, category, tone, qty, price

    def add_item(self):
        parsed = self.parse_inputs()
        if not parsed:
            return
        brand, name, category, tone, qty, price = parsed

        saved_img_rel_path = None
        if self.selected_image_path:
            ext = os.path.splitext(self.selected_image_path)[1]
            clean_name = f"{brand}_{name}_{tone}".replace(" ", "_").lower()
            dest_filename = f"{clean_name}_{os.urandom(4).hex()}{ext}"
            dest_path = os.path.join(self.img_dir, dest_filename)

            shutil.copy(self.selected_image_path, dest_path)
            saved_img_rel_path = os.path.relpath(dest_path, self.app_path)

        self.cursor.execute(
            """
            INSERT INTO inventory (brand, product_name, category, tone, quantity, price, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (brand, name, category, tone, qty, price, saved_img_rel_path)
        )
        self.conn.commit()
        self.clear_form()
        self.load_data()

    def update_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("Selection Error", "Please select an item from the table to update.")
            return

        parsed = self.parse_inputs()
        if not parsed:
            return
        brand, name, category, tone, qty, price = parsed

        self.cursor.execute("SELECT image_path FROM inventory WHERE id = ?", (self.selected_item_id,))
        current_img = self.cursor.fetchone()[0]

        saved_img_rel_path = current_img
        if self.selected_image_path:
            ext = os.path.splitext(self.selected_image_path)[1]
            clean_name = f"{brand}_{name}_{tone}".replace(" ", "_").lower()
            dest_filename = f"{clean_name}_{self.selected_item_id}{ext}"
            dest_path = os.path.join(self.img_dir, dest_filename)

            shutil.copy(self.selected_image_path, dest_path)
            saved_img_rel_path = os.path.relpath(dest_path, self.app_path)

            if saved_img_rel_path in self._image_cache:
                del self._image_cache[saved_img_rel_path]

        self.cursor.execute(
            """
            UPDATE inventory
            SET brand = ?, product_name = ?, category = ?, tone = ?, quantity = ?, price = ?, image_path = ?
            WHERE id = ?
        """,
            (brand, name, category, tone, qty, price, saved_img_rel_path, self.selected_item_id)
        )
        self.conn.commit()
        self.clear_form()
        self.load_data()

    def delete_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("Selection Error", "Select an item from the table to delete.")
            return

        self.cursor.execute("SELECT image_path FROM inventory WHERE id = ?", (self.selected_item_id,))
        row = self.cursor.fetchone()
        if row and row[0]:
            img_path = os.path.join(self.app_path, row[0])
            if img_path in self._image_cache:
                del self._image_cache[img_path]
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except OSError:
                    pass

        self.cursor.execute("DELETE FROM inventory WHERE id = ?", (self.selected_item_id,))
        self.conn.commit()
        self.display_preview(None)
        self.clear_form()
        self.load_data()

    def clear_form(self):
        self.entry_brand.delete(0, "end")
        self.entry_name.delete(0, "end")
        self.entry_tone.delete(0, "end")
        self.entry_qty.delete(0, "end")
        self.entry_price.delete(0, "end")
        self.combo_type.set("Uncategorized")
        self.selected_image_path = None
        self.selected_item_id = None
        self.lbl_img_path.configure(text="No image selected")


if __name__ == "__main__":
    app = MakeupInventoryApp()
    app.mainloop()