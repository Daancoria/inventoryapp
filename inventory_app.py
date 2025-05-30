import tkinter as tk
import csv
import sqlite3
import os
import tempfile
import hashlib
from tkinter import ttk, messagebox
from tkinter import filedialog
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# === DATABASE SETUP ===

# Connect to SQLite database
conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

# Create inventory table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL
)''')

# Create invoices table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    date TEXT NOT NULL
)''')
conn.commit()

# Create users table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'viewer'))
)''')

# Create logs table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
)''')

# Add 'deleted' column to inventory if missing (for soft delete)
cursor.execute("PRAGMA table_info(inventory)")
if 'deleted' not in [col[1] for col in cursor.fetchall()]:
    cursor.execute("ALTER TABLE inventory ADD COLUMN deleted INTEGER DEFAULT 0")

# Add 'deleted' column to invoices if missing (for soft delete)
cursor.execute("PRAGMA table_info(invoices)")
if 'deleted' not in [col[1] for col in cursor.fetchall()]:
    cursor.execute("ALTER TABLE invoices ADD COLUMN deleted INTEGER DEFAULT 0")
conn.commit()

# Add 'deleted_at' column to inventory if missing (timestamp for deletion)
cursor.execute("PRAGMA table_info(inventory)")
if 'deleted_at' not in [col[1] for col in cursor.fetchall()]:
    cursor.execute("ALTER TABLE inventory ADD COLUMN deleted_at TEXT")

# Add 'deleted_at' column to invoices if missing (timestamp for deletion)
cursor.execute("PRAGMA table_info(invoices)")
if 'deleted_at' not in [col[1] for col in cursor.fetchall()]:
    cursor.execute("ALTER TABLE invoices ADD COLUMN deleted_at TEXT")

conn.commit()

# === ADMIN USER SETUP ===

# Create default admin user with hashed password if no users exist
cursor.execute("SELECT COUNT(*) FROM users")
if cursor.fetchone()[0] == 0:
    hashed_admin_pw = hashlib.sha256("admin".encode()).hexdigest()
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        ("admin", hashed_admin_pw, "admin")
    )
    conn.commit()

# Fix legacy plain-text password for admin
cursor.execute("SELECT password FROM users WHERE username = 'admin'")
row = cursor.fetchone()
if row and row[0] == "admin":  # still plain text
    hashed = hashlib.sha256("admin".encode()).hexdigest()
    cursor.execute("UPDATE users SET password = ? WHERE username = 'admin'", (hashed,))
    conn.commit()

# === LOGGING FUNCTION ===

def log_action(username, action):
    """Log user actions to the logs table."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO logs (username, action, timestamp) VALUES (?, ?, ?)",
                    (username, action, timestamp))
    conn.commit()

# === MAIN APPLICATION CLASS ===

class InventoryApp(tk.Tk):
    def __init__(self, username, role):
        super().__init__()
        self.username = username
        self.role = role
        self.title(f"Inventory Management - Logged in as {self.username} ({self.role})")
        self.geometry("1000x700")
        self.setup_style()

        header_canvas = tk.Canvas(self, height=60)
        header_canvas.pack(fill="x")
        draw_gradient(header_canvas, 1000, 60, "#007acc", "#f2f2f2")
        header_canvas.create_text(500, 30, text="Inventory Management System", fill="white", font=("Segoe UI", 16, "bold"))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(expand=True, fill="both")

        self.inventory_tab = ttk.Frame(self.tabs)
        self.invoice_tab = ttk.Frame(self.tabs)
        self.user_tab = ttk.Frame(self.tabs)
        self.log_tab = ttk.Frame(self.tabs)
        self.settings_tab = ttk.Frame(self.tabs)
        self.recycle_tab = ttk.Frame(self.tabs)

        self.tabs.add(self.inventory_tab, text="Inventory")
        self.tabs.add(self.invoice_tab, text="Invoices")
        if self.role == "admin":
            self.tabs.add(self.user_tab, text="User Management")
            self.tabs.add(self.log_tab, text="Activity Logs")
        self.tabs.add(self.settings_tab, text="Settings")
        self.tabs.add(self.recycle_tab, text="Recycle Bin")

        self.create_inventory_tab()
        self.create_invoice_tab()
        if self.role == "admin":
            self.create_user_tab()
            self.create_log_tab()
        self.create_settings_tab()
        self.create_recycle_tab()

        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Global Font
        default_font = ("Segoe UI Variable", 10)
        style.configure(".", font=default_font)

        # Buttons
        style.configure("TButton",
            font=default_font,
            padding=(10, 6),
            background="#F3F3F3",
            relief="flat",
            borderwidth=0
        )
        style.map("TButton",
            background=[("active", "#E1E1E1"), ("pressed", "#D0D0D0")],
            foreground=[("disabled", "#888")])

        # Notebook Tabs
        style.configure("TNotebook.Tab",
            font=("Segoe UI Variable", 10, "bold"),
            padding=[12, 8],
            background="#E8E8E8")
        style.map("TNotebook.Tab",
            background=[("selected", "#FFFFFF"), ("active", "#F2F2F2")])

        # Treeview
        style.configure("Treeview",
            font=default_font,
            rowheight=28,
            borderwidth=0,
            relief="flat",
            background="#FFFFFF",
            fieldbackground="#FFFFFF"
        )
        style.configure("TButton",
            font=("Segoe UI Variable", 10),
            padding=(10, 6),
            relief="solid",        # solid border
            borderwidth=1,         # visible border
            background="#F3F3F3",
            foreground="#000000"
        )
        style.map("TButton",
            background=[("active", "#E1E1E1"), ("pressed", "#D0D0D0")],
            bordercolor=[("active", "#A0A0A0")],
            relief=[("pressed", "sunken")]
        )

        # Labels
        style.configure("TLabel", font=default_font)

        # Combobox
        style.configure("TCombobox", padding=5, relief="flat")

    def on_app_close(self):
        if messagebox.askokcancel("Exit", "Do you want to close the application?"):
            log_action(self.username, "Closed application")
            self.destroy()

    def export_all_to_pdf(self):
        filename = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="full_report.pdf",
                                                filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return

        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        y = height - 50

        c.setFont("Helvetica-Bold", 16)
        c.drawString(180, y, "Full Inventory and Invoice Report")
        y -= 40

        # Inventory Section
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Inventory Items")
        y -= 20
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        for item in cursor.fetchall():
            c.setFont("Helvetica", 10)
            c.drawString(60, y, f"{item[0]} | Qty: {item[1]} | Price: ${item[2]:.2f}")
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50

        # Invoices Section
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Invoices")
        y -= 20
        cursor.execute("SELECT supplier_name, invoice_number, date FROM invoices WHERE deleted = 0")
        for inv in cursor.fetchall():
            c.setFont("Helvetica", 10)
            c.drawString(60, y, f"{inv[0]} | Invoice: {inv[1]} | Date: {inv[2]}")
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50

        c.save()
        messagebox.showinfo("Export Complete", f"Full report saved to:\n{filename}")

    def create_inventory_tab(self):
        self.minsize(1000, 720)  # Ensure minimum height

        main_frame = ttk.Frame(self.inventory_tab)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Grid layout configuration
        main_frame.grid_rowconfigure(2, weight=1)  # Let treeview grow
        main_frame.grid_columnconfigure(0, weight=1)

        # Entry Form
        entry_frame = ttk.Frame(main_frame)
        entry_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(entry_frame, text="Item Name").grid(row=0, column=0, padx=5)
        ttk.Label(entry_frame, text="Quantity").grid(row=0, column=1, padx=5)
        ttk.Label(entry_frame, text="Price").grid(row=0, column=2, padx=5)

        self.item_name = tk.StringVar()
        self.quantity = tk.IntVar()
        self.price = tk.DoubleVar()

        ttk.Entry(entry_frame, textvariable=self.item_name).grid(row=1, column=0, padx=5)
        ttk.Entry(entry_frame, textvariable=self.quantity).grid(row=1, column=1, padx=5)
        ttk.Entry(entry_frame, textvariable=self.price).grid(row=1, column=2, padx=5)

        ttk.Button(entry_frame, text="➕ Add Item", command=self.add_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=3, padx=5)
        ttk.Button(entry_frame, text="✏️ Update Item", command=self.update_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=4, padx=5)
        ttk.Button(entry_frame, text="🗑️ Delete Item", command=self.delete_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=5, padx=5)

        # Search Form
        search_frame = ttk.Frame(main_frame)
        search_frame.grid(row=1, column=0, sticky="ew")
        self.search_term = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_term, width=30).pack(side="left", padx=5)
        ttk.Button(search_frame, text="🔍 Search", command=self.search_items).pack(side="left", padx=5)
        ttk.Button(search_frame, text="❌ Clear", command=self.load_inventory).pack(side="left", padx=5)

        # Treeview Area
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 5))

        scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")

        self.tree = ttk.Treeview(tree_frame, columns=("Item", "Quantity", "Price"), show="headings",
                                yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.heading("Item", text="Item Name")
        self.tree.heading("Quantity", text="Quantity")
        self.tree.heading("Price", text="Price")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_item)

        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Summary
        self.summary_label = ttk.Label(main_frame, text="", font=("Segoe UI", 10, "bold"))
        self.summary_label.grid(row=3, column=0, sticky="w", padx=5)

        # Low Stock
        self.low_stock_frame = ttk.LabelFrame(main_frame, text="🚨 Low Stock Alerts (Qty < 5)")
        self.low_stock_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=(5, 10))
        self.low_stock_list = tk.Listbox(self.low_stock_frame, height=4)
        self.low_stock_list.pack(fill="x", padx=5, pady=5)

        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, sticky="ew", pady=10)

        ttk.Button(button_frame, text="📤 Export PDF", command=self.export_inventory_pdf).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📑 Export CSV", command=self.export_inventory_csv).pack(side="left", padx=5)
        ttk.Button(button_frame, text="🧾 Full Report", command=self.export_all_to_pdf).pack(side="left", padx=5)
        ttk.Button(button_frame, text="🔄 Refresh", command=self.load_inventory).pack(side="left", padx=5)
        ttk.Button(button_frame, text="🖨️ Print", command=self.print_inventory_preview).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📥 Import CSV", command=self.import_inventory_csv).pack(side="left", padx=5)

        self.load_inventory()

    def export_all_to_pdf(self):
        filename = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="full_report.pdf",
                                                filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return

        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        y = height - 50

        c.setFont("Helvetica-Bold", 16)
        c.drawString(180, y, "Full Inventory and Invoice Report")
        y -= 40

        # Inventory Section
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Inventory Items")
        y -= 20
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        for item in cursor.fetchall():
            c.setFont("Helvetica", 10)
            c.drawString(60, y, f"{item[0]} | Qty: {item[1]} | Price: ${item[2]:.2f}")
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50

        # Invoices Section
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Invoices")
        y -= 20
        cursor.execute("SELECT supplier_name, invoice_number, date FROM invoices WHERE deleted = 0")
        for inv in cursor.fetchall():
            c.setFont("Helvetica", 10)
            c.drawString(60, y, f"{inv[0]} | Invoice: {inv[1]} | Date: {inv[2]}")
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50

        c.save()
        messagebox.showinfo("Export Complete", f"Full report saved to:\n{filename}")

    def add_item(self):
        name = self.item_name.get().strip()
        qty = self.quantity.get()
        price = self.price.get()

        if not name:
            messagebox.showwarning("Input Error", "Item name is required.")
            return

        cursor.execute("INSERT INTO inventory (item_name, quantity, price) VALUES (?, ?, ?)", (name, qty, price))
        conn.commit()
        log_action(self.username, f"Added item: {name}")
        self.load_inventory()

    def update_item(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select an item to update.")
            return

        values = self.tree.item(selected, "values")
        name = self.item_name.get().strip()
        qty = self.quantity.get()
        price = self.price.get()

        cursor.execute("UPDATE inventory SET quantity = ?, price = ? WHERE item_name = ?", (qty, price, values[0]))
        conn.commit()
        log_action(self.username, f"Updated item: {name}")
        self.load_inventory()

    def delete_item(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select an item to delete.")
            return

        values = self.tree.item(selected, "values")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE inventory SET deleted = 1, deleted_at = ? WHERE item_name = ?", (timestamp, values[0]))
        conn.commit()
        log_action(self.username, f"Soft deleted item: {values[0]}")
        self.load_inventory()

    def load_selected_item(self, event):
        selected = self.tree.focus()
        if selected:
            values = self.tree.item(selected, "values")
            self.item_name.set(values[0])
            self.quantity.set(values[1])
            self.price.set(values[2])

    def load_inventory(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
            self.low_stock_list.delete(0, tk.END)

        total_quantity = 0
        total_value = 0
        item_count = 0

        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        for item_name, quantity, price in cursor.fetchall():
            tag = "low" if quantity < 5 else ""
            self.tree.insert("", tk.END, values=(item_name, quantity, price), tags=(tag,))
            item_count += 1
            total_quantity += quantity
            total_value += quantity * price
            
            if quantity < 5:
                self.low_stock_list.insert(tk.END, f"{item_name} - Qty: {quantity}")

        self.tree.tag_configure("low", foreground="red")

        self.summary_label.config(
            text=f"Total Items: {item_count} | Total Quantity: {total_quantity} | Total Value: ${total_value:.2f}"
        )

    def search_items(self):
        term = self.search_term.get().lower()
        for row in self.tree.get_children():
            self.tree.delete(row)
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0 AND lower(item_name) LIKE ?", (f"%{term}%",))
        for item in cursor.fetchall():
            self.tree.insert("", tk.END, values=item)
        selected = self.user_tree.focus()
        if not selected:
            return
        username = self.user_tree.item(selected, "values")[0]
        if username == "admin":
            messagebox.showwarning("Protected User", "The default admin user cannot be deleted.")
            return
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete user '{username}'?"):
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            log_action(self.username, f"Deleted user: {username}")
            self.load_users()

    def export_inventory_pdf(self):
        filename = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return

        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        y = height - 50

        c.setFont("Helvetica-Bold", 16)
        c.drawString(200, y, "Inventory Report")
        y -= 30

        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        y -= 30

        # Headers
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Item Name")
        c.drawString(250, y, "Quantity")
        c.drawString(350, y, "Price")
        y -= 20

        # Data
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        for name, qty, price in cursor.fetchall():
            c.setFont("Helvetica", 10)
            c.drawString(50, y, str(name))
            c.drawString(250, y, str(qty))
            c.drawString(350, y, f"${price:.2f}")
            y -= 15

            if y < 50:
                c.showPage()
                y = height - 50

        c.save()
        messagebox.showinfo("Export Complete", f"Inventory exported to {filename}")

    def import_inventory_csv(self):
        file_path = filedialog.askopenfilename(
            title="Select Inventory CSV",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not file_path:
            return

        imported_count = 0
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name = row.get("Item Name", "").strip()
                try:
                    quantity = int(row.get("Quantity", 0))
                    price = float(row.get("Price", 0.0))
                except ValueError:
                    continue  # skip rows with invalid numbers

                if name:
                    cursor.execute("INSERT INTO inventory (item_name, quantity, price) VALUES (?, ?, ?)",
                                (name, quantity, price))
                    imported_count += 1

        conn.commit()
        log_action(self.username, f"Imported {imported_count} items from CSV")
        self.load_inventory()
        messagebox.showinfo("Import Complete", f"{imported_count} items imported.")
    
    def export_inventory_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return

        with open(file_path, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Item Name", "Quantity", "Price"])
            cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
            for row in cursor.fetchall():
                writer.writerow(row)

        messagebox.showinfo("Export Complete", f"Inventory exported to:\n{file_path}")

    def print_inventory_preview(self):
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        items = cursor.fetchall()

        if not items:
            messagebox.showinfo("No Data", "No inventory data to print.")
            return

        preview_text = "Inventory Report\n\n"
        preview_text += f"{'Item Name':<30}{'Quantity':<15}{'Price':<10}\n"
        preview_text += "-" * 60 + "\n"
        for item in items:
            name, qty, price = item
            preview_text += f"{name:<30}{qty:<15}{price:<10.2f}\n"

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        temp_file.write(preview_text)
        temp_file.close()

        should_print = messagebox.askyesno("Print Preview", "Preview saved. Open print dialog?")
        if should_print:
            try:
                os.startfile(temp_file.name, "print")
            except Exception as e:
                messagebox.showerror("Print Error", f"Could not send to printer.\n{e}")

    def create_invoice_tab(self):
        frame = ttk.Frame(self.invoice_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Input Form
        top_frame = ttk.Frame(frame)
        top_frame.pack(pady=(0, 10), fill="x")

        ttk.Label(top_frame, text="Supplier Name").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(top_frame, text="Invoice Number").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(top_frame, text="Date").grid(row=0, column=2, padx=5, pady=5, sticky="w")

        self.supplier_name = tk.StringVar()
        self.invoice_number = tk.StringVar()
        self.invoice_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))

        ttk.Entry(top_frame, textvariable=self.supplier_name).grid(row=1, column=0, padx=5)
        ttk.Entry(top_frame, textvariable=self.invoice_number).grid(row=1, column=1, padx=5)
        ttk.Entry(top_frame, textvariable=self.invoice_date).grid(row=1, column=2, padx=5)
        ttk.Button(top_frame, text="Add Invoice", command=self.add_invoice).grid(row=1, column=3, padx=5)
        ttk.Button(top_frame, text="Import CSV", command=self.import_invoice_csv).grid(row=1, column=4, padx=5)

        # Table
        self.invoice_tree = ttk.Treeview(frame, columns=("Supplier", "Invoice Number", "Date"), show="headings")
        for col in ("Supplier", "Invoice Number", "Date"):
            self.invoice_tree.heading(col, text=col)
        self.invoice_tree.pack(fill="both", expand=True)

        self.load_invoices()

    def import_invoice_csv(self):
        file_path = filedialog.askopenfilename(
            title="Select Invoice CSV File",
            filetypes=[("CSV files", "*.csv")]
        )
        if not file_path:
            return

        imported_count = 0
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name = row.get("Supplier Name", "").strip()
                number = row.get("Invoice Number", "").strip()
                date = row.get("Date", "").strip()

                if name and number and date:
                    cursor.execute(
                        "INSERT INTO invoices (supplier_name, invoice_number, date) VALUES (?, ?, ?)",
                        (name, number, date)
                    )
                    imported_count += 1

        conn.commit()
        log_action(self.username, f"Imported {imported_count} invoices from CSV")
        self.load_invoices()
        messagebox.showinfo("Import Complete", f"{imported_count} invoices imported successfully.")

    def add_invoice(self):
        name = self.supplier_name.get().strip()
        number = self.invoice_number.get().strip()
        date = self.invoice_date.get().strip()

        if not (name and number and date):
            messagebox.showwarning("Input Error", "All invoice fields are required.")
            return

        cursor.execute(
            "INSERT INTO invoices (supplier_name, invoice_number, date) VALUES (?, ?, ?)",
            (name, number, date)
        )
        conn.commit()
        log_action(self.username, f"Added invoice: {number}")
        self.load_invoices()

    def load_invoices(self):
        for row in self.invoice_tree.get_children():
            self.invoice_tree.delete(row)
        cursor.execute("SELECT supplier_name, invoice_number, date FROM invoices WHERE deleted = 0")
        for row in cursor.fetchall():
            self.invoice_tree.insert("", tk.END, values=row)

    def create_user_tab(self):
        frame = ttk.Frame(self.user_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        form_frame = ttk.Frame(frame)
        form_frame.pack(pady=(0, 10), fill="x")

        ttk.Label(form_frame, text="Username").grid(row=0, column=0, padx=5)
        ttk.Label(form_frame, text="Password").grid(row=0, column=1, padx=5)
        ttk.Label(form_frame, text="Role").grid(row=0, column=2, padx=5)

        self.new_username = tk.StringVar()
        self.new_password = tk.StringVar()
        self.new_role = tk.StringVar()

        ttk.Entry(form_frame, textvariable=self.new_username).grid(row=1, column=0, padx=5)
        ttk.Entry(form_frame, textvariable=self.new_password).grid(row=1, column=1, padx=5)
        ttk.Combobox(form_frame, textvariable=self.new_role, values=["admin", "viewer"], state="readonly").grid(row=1, column=2, padx=5)

        ttk.Button(form_frame, text="Add User", command=self.add_user).grid(row=1, column=3, padx=5)
        ttk.Button(form_frame, text="Delete User", command=self.delete_user).grid(row=2, column=3, padx=5)

        self.user_tree = ttk.Treeview(frame, columns=("Username", "Role"), show="headings")
        self.user_tree.heading("Username", text="Username")
        self.user_tree.heading("Role", text="Role")
        self.user_tree.pack(fill="both", expand=True)

        self.load_users()

    def add_user(self):
        username = self.new_username.get().strip()
        password = self.new_password.get().strip()
        role = self.new_role.get().strip()

        if not (username and password and role):
            messagebox.showwarning("Input Error", "All user fields are required.")
            return

        try:
            hashed_pw = hashlib.sha256(password.encode()).hexdigest()
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, role))
            conn.commit()
            log_action(self.username, f"Added user: {username}")
            self.load_users()
            self.new_username.set("")
            self.new_password.set("")
            self.new_role.set("")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists.")

    def delete_user(self):
        selected = self.user_tree.focus()
        if not selected:
            return

        username = self.user_tree.item(selected, "values")[0]
        if username == "admin":
            messagebox.showwarning("Protected User", "The default admin user cannot be deleted.")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete user '{username}'?"):
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            log_action(self.username, f"Deleted user: {username}")
            self.load_users()

    def load_users(self):
        for row in self.user_tree.get_children():
            self.user_tree.delete(row)
        cursor.execute("SELECT username, role FROM users")
        for row in cursor.fetchall():
            self.user_tree.insert("", tk.END, values=row)

    def logout_user(self):
        if messagebox.askyesno("Log Out", "Are you sure you want to log out?"):
            log_action(self.username, "Logged out")
            self.destroy()
            login_window()  # Re-launch login

    def create_log_tab(self):
        frame = ttk.Frame(self.log_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_tree = ttk.Treeview(frame, columns=("Username", "Action", "Timestamp"), show="headings")
        self.log_tree.heading("Username", text="Username")
        self.log_tree.heading("Action", text="Action")
        self.log_tree.heading("Timestamp", text="Timestamp")

        self.log_tree.pack(fill="both", expand=True)
        ttk.Button(frame, text="Clear All Logs", command=self.clear_logs).pack(anchor="e", pady=(10, 0))

        self.load_logs()

    def clear_logs(self):
        if messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete all activity logs?"):
            cursor.execute("DELETE FROM logs")
            conn.commit()
            log_action(self.username, "Cleared all activity logs")
            self.load_logs()
            messagebox.showinfo("Logs Cleared", "All logs have been successfully deleted.")

    def load_logs(self):
        for row in self.log_tree.get_children():
            self.log_tree.delete(row)
        cursor.execute("SELECT username, action, timestamp FROM logs ORDER BY timestamp DESC")
        for row in cursor.fetchall():
            self.log_tree.insert("", tk.END, values=row)

    def create_settings_tab(self):
        frame = ttk.Frame(self.settings_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Application Settings", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="Select Theme:").pack(anchor="w")

        self.theme_choice = tk.StringVar(value="clam")
        theme_menu = ttk.Combobox(frame, textvariable=self.theme_choice, values=["clam", "default", "alt"], state="readonly")
        theme_menu.pack(pady=5)

        ttk.Button(frame, text="Apply Theme", command=self.apply_theme).pack(pady=(10, 0), anchor="e")

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=10)
        ttk.Button(frame, text="Log Out", command=self.logout_user).pack(pady=5, anchor="e")

    def apply_theme(self):
        try:
            style = ttk.Style(self)
            style.theme_use(self.theme_choice.get())
            messagebox.showinfo("Theme Applied", f"Theme '{self.theme_choice.get()}' applied successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not apply theme: {e}")

    def create_recycle_tab(self):
        frame = ttk.Frame(self.recycle_tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Deleted Inventory Items", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

        self.recycle_tree = ttk.Treeview(frame, columns=("Item", "Quantity", "Price", "Deleted At"), show="headings")
        for col in ("Item", "Quantity", "Price", "Deleted At"):
            self.recycle_tree.heading(col, text=col)
        self.recycle_tree.pack(fill="both", expand=True, pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="Restore Selected", command=self.restore_deleted_item).pack(side="left")
        ttk.Button(btn_frame, text="Permanently Delete", command=self.permanently_delete_item).pack(side="right")

        self.load_recycle_bin()

    def load_recycle_bin(self):
        for row in self.recycle_tree.get_children():
            self.recycle_tree.delete(row)
        cursor.execute("SELECT item_name, quantity, price, deleted_at FROM inventory WHERE deleted = 1")
        for row in cursor.fetchall():
            self.recycle_tree.insert("", tk.END, values=row)

    def restore_deleted_item(self):
        selected = self.recycle_tree.focus()
        if not selected:
            return

        item_name = self.recycle_tree.item(selected, "values")[0]
        cursor.execute("UPDATE inventory SET deleted = 0, deleted_at = NULL WHERE item_name = ?", (item_name,))
        conn.commit()
        log_action(self.username, f"Restored item: {item_name}")
        self.load_recycle_bin()
        self.load_inventory()

    def permanently_delete_item(self):
        selected = self.recycle_tree.focus()
        if not selected:
            return

        item_name = self.recycle_tree.item(selected, "values")[0]
        if messagebox.askyesno("Confirm Delete", f"Permanently delete '{item_name}'?"):
            cursor.execute("DELETE FROM inventory WHERE item_name = ?", (item_name,))
            conn.commit()
            log_action(self.username, f"Permanently deleted item: {item_name}")
            self.load_recycle_bin()

# === LOGIN WINDOW ===

def login_window():
    login = tk.Tk()
    login.title("Login")
    login.geometry("320x240")
    login.configure(bg="#F5F7FA")

    font = ("Segoe UI Variable", 10)

    tk.Label(login, text="Username", font=font, bg="#F5F7FA").pack(pady=(15, 5))
    username_entry = tk.Entry(login, font=font)
    username_entry.pack(pady=(0, 10))

    tk.Label(login, text="Password", font=font, bg="#F5F7FA").pack(pady=(10, 5))
    password_entry = tk.Entry(login, show="*", font=font)
    password_entry.pack(pady=(0, 20))

    def attempt_login():
        username = username_entry.get()
        password = password_entry.get()
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, hashed_pw))
        result = cursor.fetchone()
        if result:
            role = result[0]
            log_action(username, "Logged in")
            login.destroy()
            app = InventoryApp(username, role)
            app.mainloop()
        else:
            messagebox.showerror("Login Failed", "Incorrect username or password.")

    ttk.Button(login, text="Login", command=attempt_login).pack(pady=5)

    login.mainloop()

# === GRADIENT DRAWING FUNCTION ===

def draw_gradient(canvas, width, height, start_color, end_color):
    """Draw a vertical gradient on a canvas."""
    r1, g1, b1 = canvas.winfo_rgb(start_color)
    r2, g2, b2 = canvas.winfo_rgb(end_color)

    r_ratio = (r2 - r1) / height
    g_ratio = (g2 - g1) / height
    b_ratio = (b2 - b1) / height

    for i in range(height):
        nr = int(r1 + (r_ratio * i)) >> 8
        ng = int(g1 + (g_ratio * i)) >> 8
        nb = int(b1 + (b_ratio * i)) >> 8
        color = f'#{nr:02x}{ng:02x}{nb:02x}'
        canvas.create_line(0, i, width, i, fill=color)

# === MAIN ENTRY POINT ===

if __name__ == "__main__":
    login_window()
