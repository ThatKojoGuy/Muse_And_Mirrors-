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
    self.geometry("1050x700")

    # Image Storage Directory Setup
    self.app_path = self.get_app_path()
    self.img_dir = os.path.join(self.app_path, "product_images")
    os.makedirs(self.img_dir, exist_ok=True)

    self.selected_image_path = None

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

  # ---------------- Database Initialization ----------------
  def init_db(self):
    db_path = os.path.join(self.app_path, "makeup_inventory.db")
    self.conn = sqlite3.connect(db_path)
    self.cursor = self.conn.cursor()

    # Create Table with image_path Column
    self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                tone TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                image_path TEXT
            )
        """)
    self.conn.commit()

  # ---------------- Sidebar / Form UI ----------------
  def build_sidebar(self):
    title_label = ctk.CTkLabel(
        self.sidebar_frame,
        text="Product Details",
        font=ctk.CTkFont(size=18, weight="bold"),
    )
    title_label.pack(padx=10, pady=(10, 5))

    self.entry_brand = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Brand")
    self.entry_brand.pack(fill="x", padx=15, pady=4)

    self.entry_name = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Product Name"
    )
    self.entry_name.pack(fill="x", padx=15, pady=4)

    self.combo_type = ctk.CTkOptionMenu(
        self.sidebar_frame,
        values=[
            "Foundation",
            "Concealer",
            "Lipstick",
            "Eyeshadow",
            "Blush",
            "Powder",
            "Eye Liner",
            "Other",
        ],
    )
    self.combo_type.pack(fill="x", padx=15, pady=4)

    self.entry_tone = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Tone / Shade"
    )
    self.entry_tone.pack(fill="x", padx=15, pady=4)

    self.entry_qty = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Quantity"
    )
    self.entry_qty.pack(fill="x", padx=15, pady=4)

    self.entry_price = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Price"
    )
    self.entry_price.pack(fill="x", padx=15, pady=4)

    # Image Picker Section
    self.btn_select_img = ctk.CTkButton(
        self.sidebar_frame,
        text="📷 Select Product Image",
        command=self.select_image,
        fg_color="#3B82F6",
        hover_color="#2563EB",
    )
    self.btn_select_img.pack(fill="x", padx=15, pady=(8, 2))

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
        text="Add Item",
        command=self.add_item,
        fg_color="#2EA043",
        hover_color="#238636",
    )
    btn_add.pack(fill="x", padx=15, pady=(10, 4))

    btn_delete = ctk.CTkButton(
        self.sidebar_frame,
        text="Delete Selected",
        command=self.delete_item,
        fg_color="#DA3633",
        hover_color="#B62324",
    )
    btn_delete.pack(fill="x", padx=15, pady=4)

    btn_clear = ctk.CTkButton(
        self.sidebar_frame,
        text="Clear Form",
        command=self.clear_form,
        fg_color="#30363D",
        hover_color="#484F58",
    )
    btn_clear.pack(fill="x", padx=15, pady=4)

  # ---------------- Main View & Image Preview UI ----------------
  def build_main_view(self):
    # Top Search Bar
    search_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
    search_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

    self.entry_search = ctk.CTkEntry(
        search_frame, placeholder_text="Search by Brand or Name..."
    )
    self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))

    btn_search = ctk.CTkButton(
        search_frame, text="Search", width=100, command=self.load_data
    )
    btn_search.pack(side="right")

    # Treeview Table
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
        self.main_frame, columns=columns, show="headings", selectmode="browse"
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

    # Image Preview Panel (Right Side)
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

  # ---------------- Image Handling Logic ----------------
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

    item_id = self.tree.item(selected[0])["values"][0]
    self.cursor.execute(
        "SELECT image_path FROM inventory WHERE id = ?", (item_id,)
    )
    result = self.cursor.fetchone()
    if result:
      self.display_preview(result[0])

  # ---------------- Logic & CRUD Operations ----------------
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
          "SELECT id, brand, product_name, category, tone, quantity, price FROM"
          " inventory"
      )

    for row in self.cursor.fetchall():
      formatted_row = list(row)
      formatted_row[6] = f"${row[6]:.2f}"
      self.tree.insert("", "end", values=formatted_row)

  def add_item(self):
    brand = self.entry_brand.get().strip()
    name = self.entry_name.get().strip()
    category = self.combo_type.get()
    tone = self.entry_tone.get().strip()
    qty = self.entry_qty.get().strip()
    price = self.entry_price.get().strip()

    if not (brand and name and tone and qty and price):
      messagebox.showwarning("Input Error", "Please fill in all text fields.")
      return

    try:
      qty = int(qty)
      price = float(price)
    except ValueError:
      messagebox.showerror(
          "Input Error", "Quantity must be an integer and Price a number."
      )
      return

    # Handle Image File Copying
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

  def delete_item(self):
    selected = self.tree.selection()
    if not selected:
      messagebox.showwarning(
          "Selection Error", "Select an item from the table to delete."
      )
      return

    item_id = self.tree.item(selected[0])["values"][0]

    # Clean up associated image file if present
    self.cursor.execute(
        "SELECT image_path FROM inventory WHERE id = ?", (item_id,)
    )
    img_path = self.cursor.fetchone()[0]
    if img_path and os.path.exists(os.path.join(self.app_path, img_path)):
      try:
        os.remove(os.path.join(self.app_path, img_path))
      except OSError:
        pass

    self.cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    self.conn.commit()
    self.display_preview(None)
    self.load_data()

  def clear_form(self):
    self.entry_brand.delete(0, "end")
    self.entry_name.delete(0, "end")
    self.entry_tone.delete(0, "end")
    self.entry_qty.delete(0, "end")
    self.entry_price.delete(0, "end")
    self.selected_image_path = None
    self.lbl_img_path.configure(text="No image selected")


if __name__ == "__main__":
  app = MakeupInventoryApp()
  app.mainloop()