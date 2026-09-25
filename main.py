import sqlite3
from tkinter import ttk, messagebox
import customtkinter as ctk

# Set GUI theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MakeupInventoryApp(ctk.CTk):

  def __init__(self):
    super().__init__()

    self.title("Makeup Inventory Management System")
    self.geometry("950x650")

    # Initialize Local SQLite Database
    self.init_db()

    # Layout Configuration
    self.grid_columnconfigure(1, weight=1)
    self.grid_rowconfigure(0, weight=1)

    # Sidebar Frame (Input Form)
    self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=10)
    self.sidebar_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

    # Right Frame (Table & Search)
    self.main_frame = ctk.CTkFrame(self, corner_radius=10)
    self.main_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
    self.main_frame.grid_columnconfigure(0, weight=1)
    self.main_frame.grid_rowconfigure(1, weight=1)

    self.build_sidebar()
    self.build_main_view()
    self.load_data()

  # ---------------- Database Initialization ----------------
  def init_db(self):
    self.conn = sqlite3.connect("makeup_inventory.db")
    self.cursor = self.conn.cursor()
    self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                tone TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL
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
    title_label.pack(padx=10, pady=(15, 10))

    self.entry_brand = ctk.CTkEntry(self.sidebar_frame, placeholder_text="Brand")
    self.entry_brand.pack(fill="x", padx=15, pady=5)

    self.entry_name = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Product Name"
    )
    self.entry_name.pack(fill="x", padx=15, pady=5)

    self.combo_type = ctk.CTkOptionMenu(
        self.sidebar_frame,
        values=[
            "Foundation",
            "Concealer",
            "Lipstick",
            "Eyeshadow",
            "Blush",
            "Powder",
            "Other",
        ],
    )
    self.combo_type.pack(fill="x", padx=15, pady=5)

    self.entry_tone = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Tone / Shade"
    )
    self.entry_tone.pack(fill="x", padx=15, pady=5)

    self.entry_qty = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Quantity"
    )
    self.entry_qty.pack(fill="x", padx=15, pady=5)

    self.entry_price = ctk.CTkEntry(
        self.sidebar_frame, placeholder_text="Price ($)"
    )
    self.entry_price.pack(fill="x", padx=15, pady=5)

    # Action Buttons
    btn_add = ctk.CTkButton(
        self.sidebar_frame,
        text="Add Item",
        command=self.add_item,
        fg_color="#2EA043",
        hover_color="#238636",
    )
    btn_add.pack(fill="x", padx=15, pady=(15, 5))

    btn_delete = ctk.CTkButton(
        self.sidebar_frame,
        text="Delete Selected",
        command=self.delete_item,
        fg_color="#DA3633",
        hover_color="#B62324",
    )
    btn_delete.pack(fill="x", padx=15, pady=5)

    btn_clear = ctk.CTkButton(
        self.sidebar_frame,
        text="Clear Form",
        command=self.clear_form,
        fg_color="#30363D",
        hover_color="#484F58",
    )
    btn_clear.pack(fill="x", padx=15, pady=5)

  # ---------------- Main Data Table UI ----------------
  def build_main_view(self):
    # Search Bar Section
    search_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
    search_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

    self.entry_search = ctk.CTkEntry(
        search_frame, placeholder_text="Search by Brand or Name..."
    )
    self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))

    btn_search = ctk.CTkButton(
        search_frame, text="Search", width=100, command=self.load_data
    )
    btn_search.pack(side="right")

    # Treeview (Data Grid Table)
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
    self.tree.heading("qty", text="Quantity")
    self.tree.heading("price", text="Price")

    self.tree.column("id", width=40, anchor="center")
    self.tree.column("brand", width=120)
    self.tree.column("name", width=160)
    self.tree.column("type", width=100)
    self.tree.column("tone", width=120)
    self.tree.column("qty", width=70, anchor="center")
    self.tree.column("price", width=80, anchor="e")

    self.tree.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

  # ---------------- Logic & CRUD Operations ----------------
  def load_data(self):
    for item in self.tree.get_children():
      self.tree.delete(item)

    query = self.entry_search.get().strip()
    if query:
      self.cursor.execute(
          "SELECT * FROM inventory WHERE brand LIKE ? OR product_name LIKE ?",
          (f"%{query}%", f"%{query}%"),
      )
    else:
      self.cursor.execute("SELECT * FROM inventory")

    for row in self.cursor.fetchall():
      formatted_row = list(row)
      formatted_row[6] = f"${row[6]:.2f}"  # Format price
      self.tree.insert("", "end", values=formatted_row)

  def add_item(self):
    brand = self.entry_brand.get().strip()
    name = self.entry_name.get().strip()
    category = self.combo_type.get()
    tone = self.entry_tone.get().strip()
    qty = self.entry_qty.get().strip()
    price = self.entry_price.get().strip()

    if not (brand and name and tone and qty and price):
      messagebox.showwarning("Input Error", "Please fill in all fields.")
      return

    try:
      qty = int(qty)
      price = float(price)
    except ValueError:
      messagebox.showerror(
          "Input Error", "Quantity must be an integer and Price a number."
      )
      return

    self.cursor.execute(
        """
            INSERT INTO inventory (brand, product_name, category, tone, quantity, price)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        (brand, name, category, tone, qty, price),
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
    self.cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    self.conn.commit()
    self.load_data()

  def clear_form(self):
    self.entry_brand.delete(0, "end")
    self.entry_name.delete(0, "end")
    self.entry_tone.delete(0, "end")
    self.entry_qty.delete(0, "end")
    self.entry_price.delete(0, "end")


if __name__ == "__main__":
  app = MakeupInventoryApp()
  app.mainloop()