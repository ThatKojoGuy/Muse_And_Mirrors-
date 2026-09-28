import os
import shutil
import sqlite3
import sys
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from PIL import Image

# Set GUI theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MakeupInventoryApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Makeup Inventory Management System")
        self.geometry("1050x720")

        # Image Storage Directory Setup
        self.app_path = self.get_app_path()
        self.img_dir = os.path.join(self.app_path, "product_images")
        os.makedirs(self.img_dir, exist_ok=True)

        self.selected_image_path = None
        self.selected_item_id = None  # Tracks item being edited

        # Initialize Local SQLite Database
        self.init_db()

        # Layout Configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar Frame (Input Form)
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=10)
        self.sidebar_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Right Frame (Table & Preview)
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        self.build_sidebar()
        self.build_main_view()
        self.load_data()

    def get_app_path(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    # ---------------- Database Initialization & Migration ----------------
    def init_db(self):
        db_path = os.path.join(self.app_path, "makeup_inventory.db")
        self.conn = sqlite3.connect(db_path)
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

        # Check and migrate existing database if image_path column is missing
        self.cursor.execute("PRAGMA table_info(inventory)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if "image_path" not in columns:
            self.cursor.execute(
                "ALTER TABLE inventory ADD COLUMN image_path TEXT"
            )

        self.conn.commit()

    # ---------------- Sidebar / Form UI ----------------
    def build_sidebar(self):
        title_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Product Details",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_label.pack(padx=10, pady=(10, 5))

        # Brand
        lbl_brand = ctk.CTkLabel(
            self.sidebar_frame,
            text="Brand",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_brand.pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_brand = ctk.CTkEntry(
            self.sidebar_frame, placeholder_text="e.g., Fenty Beauty"
        )
        self.entry_brand.pack(fill="x", padx=15, pady=(0, 4))

        # Product Name
        lbl_name = ctk.CTkLabel(
            self.sidebar_frame,
            text="Product Name",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_name.pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_name = ctk.CTkEntry(
            self.sidebar_frame, placeholder_text="e.g., Foundation"
        )
        self.entry_name.pack(fill="x", padx=15, pady=(0, 4))

        # Category / Type
        lbl_type = ctk.CTkLabel(
            self.sidebar_frame,
            text="Category",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_type.pack(anchor="w", padx=15, pady=(4, 0))
        self.combo_type = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=[
                "Uncategorized",
                "Eyes",
                "Lips",
                "Cheeks",
                "Nose",
                "Other",
            ],
        )
        self.combo_type.pack(fill="x", padx=15, pady=(0, 4))

        # Tone / Shade
        lbl_tone = ctk.CTkLabel(
            self.sidebar_frame,
            text="Tone / Shade",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_tone.pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_tone = ctk.CTkEntry(
            self.sidebar_frame, placeholder_text="e.g., Warm Nude"
        )
        self.entry_tone.pack(fill="x", padx=15, pady=(0, 4))

        # Quantity
        lbl_qty = ctk.CTkLabel(
            self.sidebar_frame,
            text="Quantity",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_qty.pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_qty = ctk.CTkEntry(
            self.sidebar_frame, placeholder_text="e.g., 5"
        )
        self.entry_qty.pack(fill="x", padx=15, pady=(0, 4))

        # Price
        lbl_price = ctk.CTkLabel(
            self.sidebar_frame,
            text="Price",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_price.pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_price = ctk.CTkEntry(
            self.sidebar_frame, placeholder_text="e.g., 24.99"
        )
        self.entry_price.pack(fill="x", padx=15, pady=(0, 4))

        # Image Picker Section
        lbl_img = ctk.CTkLabel(
            self.sidebar_frame,
            text="Product Image",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_img.pack(anchor="w", padx=15, pady=(6, 0))
        self.btn_select_img = ctk.CTkButton(
            self.sidebar_frame,
            text="📷 Select Image (Optional)",
            command=self.select_image,
            fg_color="#3B82F6",
            hover_color="#2563EB",
        )
        self.btn_select_img.pack(fill="x", padx=15, pady=(2, 2))

        self.lbl_img_path = ctk.CTkLabel(
            self.sidebar_frame,
            text="No image selected",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.lbl_img_path.pack(padx=15, pady=(0, 5))

        # Action Buttons
        btn_add = ctk.CTkButton(
            self.sidebar_frame,
            text="Add New Item",
            command=self.add_item,
            fg_color="#2EA043",
            hover_color="#238636",
        )
        btn_add.pack(fill="x", padx=15, pady=(8, 3))

        btn_update = ctk.CTkButton(
            self.sidebar_frame,
            text="Update Selected Item",
            command=self.update_item,
            fg_color="#D97706",
            hover_color="#B45309",
        )
        btn_update.pack(fill="x", padx=15, pady=3)

        btn_delete = ctk.CTkButton(
            self.sidebar_frame,
            text="Delete Selected",
            command=self.delete_item,
            fg_color="#DA3633",
            hover_color="#B62324",
        )
        btn_delete.pack(fill="x", padx=15, pady=3)

        btn_clear = ctk.CTkButton(
            self.sidebar_frame,
            text="Clear Form",
            command=self.clear_form,
            fg_color="#30363D",
            hover_color="#484F58",
        )
        btn_clear.pack(fill="x", padx=15, pady=3)

    # ---------------- Main View & Image Preview UI ----------------
    def build_main_view(self):
        search_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        search_frame.grid(
            row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew"
        )

        self.entry_search = ctk.CTkEntry(
            search_frame, placeholder_text="Search by Brand or Name..."
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_search = ctk.CTkButton(
            search_frame, text="Search", width=100, command=self.load_data
        )
        btn_search.pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#21252B",
            foreground="white",
            fieldbackground="#21252B",
            rowheight=25,
        )
        style.map("Treeview", background=[("selected", "#1F6AA5")])

        columns = ("id", "brand", "name", "type", "tone", "qty", "price")
        self.tree = ttk.Treeview(
            self.main_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        self.tree.heading("id", text="ID")
        self.tree.heading("brand", text="Brand")
        self.tree.heading("name", text="Product Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("tone", text="Tone / Shade")
        self.tree.heading("qty", text="Qty")
        self.tree.heading("price", text="Price")

        self.tree.column("id", width=35, anchor="center")
        self.tree.column("brand", width=110)
        self.tree.column("name", width=140)
        self.tree.column("type", width=90)
        self.tree.column("tone", width=110)
        self.tree.column("qty", width=50, anchor="center")
        self.tree.column("price", width=70, anchor="e")

        self.tree.grid(
            row=1, column=0, padx=(10, 5), pady=(0, 10), sticky="nsew"
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        self.preview_frame = ctk.CTkFrame(self.main_frame, width=180)
        self.preview_frame.grid(
            row=1, column=1, padx=(5, 10), pady=(0, 10), sticky="nsew"
        )

        lbl_preview_header = ctk.CTkLabel(
            self.preview_frame,
            text="Product Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_preview_header.pack(pady=10)

        self.image_display = ctk.CTkLabel(
            self.preview_frame, text="Select an item\nto view image"
        )
        self.image_display.pack(expand=True, padx=10, pady=10)

    # ---------------- Image & Selection Logic ----------------
    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Product Image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")],
        )
        if file_path:
            self.selected_image_path = file_path
            filename = os.path.basename(file_path)
            self.lbl_img_path.configure(
                text=filename[:20] + "..." if len(filename) > 20 else filename
            )

    def display_preview(self, image_rel_path):
        if image_rel_path and os.path.exists(
            os.path.join(self.app_path, image_rel_path)
        ):
            full_path = os.path.join(self.app_path, image_rel_path)
            pil_image = Image.open(full_path)
            ctk_img = ctk.CTkImage(
                light_image=pil_image, dark_image=pil_image, size=(160, 160)
            )
            self.image_display.configure(image=ctk_img, text="")
        else:
            self.image_display.configure(image="", text="No image\navailable")

    def on_item_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0])["values"]
        self.selected_item_id = values[0]

        # Populate Form Fields with Selected Item Data
        self.entry_brand.delete(0, "end")
        self.entry_brand.insert(0, values[1] if values[1] != "N/A" else "")

        self.entry_name.delete(0, "end")
        self.entry_name.insert(
            0, values[2] if values[2] != "Unnamed Item" else ""
        )

        self.combo_type.set(values[3])

        self.entry_tone.delete(0, "end")
        self.entry_tone.insert(0, values[4] if values[4] != "N/A" else "")

        self.entry_qty.delete(0, "end")
        self.entry_qty.insert(0, str(values[5]))

        self.entry_price.delete(0, "end")
        raw_price = str(values[6]).replace("$", "")
        self.entry_price.insert(0, raw_price)

        # Fetch and display image
        self.cursor.execute(
            "SELECT image_path FROM inventory WHERE id = ?",
            (self.selected_item_id,),
        )
        result = self.cursor.fetchone()
        if result:
            self.display_preview(result[0])
            if result[0]:
                filename = os.path.basename(result[0])
                self.lbl_img_path.configure(
                    text=(
                        filename[:20] + "..."
                        if len(filename) > 20
                        else filename
                    )
                )
            else:
                self.lbl_img_path.configure(text="No image attached")

    # ---------------- CRUD Operations & Parsing ----------------
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
                (f"%{query}%", f"%{query}%"),
            )
        else:
            self.cursor.execute(
                "SELECT id, brand, product_name, category, tone, quantity,"
                " price FROM inventory"
            )

        for row in self.cursor.fetchall():
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

        qty = 0
        if raw_qty:
            try:
                qty = int(raw_qty)
            except ValueError:
                messagebox.showerror(
                    "Input Error", "Quantity must be a valid whole number."
                )
                return None

        price = 0.0
        if raw_price:
            try:
                price = float(raw_price)
            except ValueError:
                messagebox.showerror(
                    "Input Error", "Price must be a valid number."
                )
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
            dest_filename = f"{clean_name}{ext}"
            dest_path = os.path.join(self.img_dir, dest_filename)

            shutil.copy(self.selected_image_path, dest_path)
            saved_img_rel_path = os.path.relpath(dest_path, self.app_path)

        self.cursor.execute(
            """
            INSERT INTO inventory (brand, product_name, category, tone, quantity, price, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (brand, name, category, tone, qty, price, saved_img_rel_path),
        )
        self.conn.commit()
        self.clear_form()
        self.load_data()

    def update_item(self):
        if not self.selected_item_id:
            messagebox.showwarning(
                "Selection Error",
                "Please click an item in the table to update.",
            )
            return

        parsed = self.parse_inputs()
        if not parsed:
            return
        brand, name, category, tone, qty, price = parsed

        self.cursor.execute(
            "SELECT image_path FROM inventory WHERE id = ?",
            (self.selected_item_id,),
        )
        current_img = self.cursor.fetchone()[0]

        saved_img_rel_path = current_img
        if self.selected_image_path:
            ext = os.path.splitext(self.selected_image_path)[1]
            clean_name = f"{brand}_{name}_{tone}".replace(" ", "_").lower()
            dest_filename = f"{clean_name}_{self.selected_item_id}{ext}"
            dest_path = os.path.join(self.img_dir, dest_filename)

            shutil.copy(self.selected_image_path, dest_path)
            saved_img_rel_path = os.path.relpath(dest_path, self.app_path)

        self.cursor.execute(
            """
            UPDATE inventory
            SET brand = ?, product_name = ?, category = ?, tone = ?, quantity = ?, price = ?, image_path = ?
            WHERE id = ?
        """,
            (
                brand,
                name,
                category,
                tone,
                qty,
                price,
                saved_img_rel_path,
                self.selected_item_id,
            ),
        )
        self.conn.commit()
        self.clear_form()
        self.load_data()

    def delete_item(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Selection Error", "Select an item from the table to delete."
            )
            return

        item_id = self.tree.item(selected[0])["values"][0]

        self.cursor.execute(
            "SELECT image_path FROM inventory WHERE id = ?", (item_id,)
        )
        row = self.cursor.fetchone()
        if row and row[0]:
            img_path = row[0]
            if os.path.exists(os.path.join(self.app_path, img_path)):
                try:
                    os.remove(os.path.join(self.app_path, img_path))
                except OSError:
                    pass

        self.cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
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