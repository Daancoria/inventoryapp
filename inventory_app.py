import tkinter as tk
import csv
import sqlite3
import os
import tempfile
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

# Add default admin user if no users exist
cursor.execute("SELECT COUNT(*) FROM users")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "admin", "admin"))
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
        """Initialize the main application window and tabs."""
        super().__init__()
        self.setup_style()
        header_height = 60
        header_canvas = tk.Canvas(self, height=header_height, width=700, highlightthickness=0)
        header_canvas.pack(fill="x")

        draw_gradient(header_canvas, 700, header_height, "#007acc", "#f2f2f2")

        # App title
        header_canvas.create_text(350, 30, text="Inventory Management System", fill="white",
                                font=("Segoe UI", 16, "bold"))
        self.username = username
        self.role = role
        self.title(f"Inventory Management - Logged in as {self.username} ({self.role})")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}")

        # Create tabs
        self.tabs = ttk.Notebook(self)
        self.inventory_tab = ttk.Frame(self.tabs)
        self.invoice_tab = ttk.Frame(self.tabs)
        self.user_tab = ttk.Frame(self.tabs)

        self.tabs.add(self.inventory_tab, text="Inventory")
        self.tabs.add(self.invoice_tab, text="Invoices")
        if self.role == "admin":
            self.tabs.add(self.user_tab, text="User Management")
        self.tabs.pack(expand=1, fill="both")

        # Initialize tab contents
        self.create_inventory_tab()
        self.create_invoice_tab()
        if self.role == "admin":
            self.create_user_tab()

        # Add logs tab for admin
        if self.role == "admin":
            self.log_tab = ttk.Frame(self.tabs)
            self.tabs.add(self.log_tab, text="Activity Logs")
            self.create_log_tab()
        
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)
        
        # Settings and recycle bin tabs
        self.settings_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.settings_tab, text="Settings")
        self.create_settings_tab()

        self.recycle_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.recycle_tab, text="Recycle Bin")
        self.create_recycle_tab()

    # === INVENTORY TAB ===
    def create_inventory_tab(self):
        """Set up the inventory management tab."""
        main_frame = ttk.Frame(self.inventory_tab)
        main_frame.pack(fill="both", expand=True)

        # Entry section for adding/updating items
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(pady=10)

        ttk.Label(entry_frame, text="Item Name").grid(row=0, column=0, padx=5)
        ttk.Label(entry_frame, text="Quantity").grid(row=0, column=1, padx=5)
        ttk.Label(entry_frame, text="Price").grid(row=0, column=2, padx=5)

        self.item_name = tk.StringVar()
        self.quantity = tk.IntVar()
        self.price = tk.DoubleVar()

        ttk.Entry(entry_frame, textvariable=self.item_name).grid(row=1, column=0, padx=5)
        ttk.Entry(entry_frame, textvariable=self.quantity).grid(row=1, column=1, padx=5)
        ttk.Entry(entry_frame, textvariable=self.price).grid(row=1, column=2, padx=5)

        # Buttons for item actions
        ttk.Button(entry_frame, text="Add Item", command=self.add_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=3, padx=5)
        ttk.Button(entry_frame, text="Update Item", command=self.update_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=4, padx=5)
        ttk.Button(entry_frame, text="Delete Item", command=self.delete_item,
                state="normal" if self.role == "admin" else "disabled").grid(row=1, column=5, padx=5)
        
        # Search section
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(pady=5)
        self.search_term = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_term, width=30).pack(side="left", padx=5)
        ttk.Button(search_frame, text="Search", command=self.search_items).pack(side="left", padx=5)
        ttk.Button(search_frame, text="Clear", command=self.load_inventory).pack(side="left", padx=5)

        # Inventory table (Treeview)
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")

        self.tree = ttk.Treeview(tree_frame, columns=("Item", "Quantity", "Price"), show='headings',
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

        # Export and print buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=5)

        ttk.Button(button_frame, text="Export Inventory to PDF", command=self.export_inventory_pdf).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Export Full Report", command=self.export_all_to_pdf).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Export Inventory to CSV", command=self.export_inventory_csv).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Refresh", command=self.load_inventory).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Print Inventory", command=self.print_inventory_preview).pack(side="left", padx=5)

        # Load inventory data
        self.load_inventory()

    def export_inventory_pdf(self):
        """Export inventory data to a PDF file."""
        default_filename = f"inventory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filename = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=default_filename,
                                                filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return  # user canceled
        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica-Bold", 16)
        c.drawString(200, height - 50, "Inventory Report")

        c.setFont("Helvetica", 10)
        c.drawString(50, height - 70, f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Table headers
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 100, "Item Name")
        c.drawString(250, height - 100, "Quantity")
        c.drawString(350, height - 100, "Price")

        # Inventory data
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        items = cursor.fetchall()

        if len(items) > 40:
            font_size = 9
            row_height = 16
        else:
            font_size = 10
            row_height = 20

        y = height - 120
        c.setFont("Helvetica", font_size)

        total_value = 0
        for item in items:
            name, qty, price = item
            total_value += qty * price
            c.drawString(50, y, str(name))
            c.drawString(250, y, str(qty))
            c.drawString(350, y, f"${price:.2f}")
            y -= row_height
            if y < 50:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", font_size)

        # After the loop
        if y < 80:
            c.showPage()
            y = height - 50
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"Total Inventory Value: ${total_value:.2f}")
        c.save()
        messagebox.showinfo("Export Complete", f"Inventory exported to {filename}")

    def export_inventory_csv(self):
        """Export inventory data to a CSV file."""
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

    def load_inventory(self):
        """Load inventory data into the treeview."""
        for row in self.tree.get_children():
            self.tree.delete(row)
        cursor.execute("SELECT item_name, quantity, price FROM inventory WHERE deleted = 0")
        for item in cursor.fetchall():
            self.tree.insert("", tk.END, values=item)
            self.autosize_columns(self.tree)

    def print_inventory_preview(self):
        """Show a print preview of the inventory and send to printer if confirmed."""
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
                os.startfile(temp_file.name, "print")  # Windows print dialog
            except Exception as e:
                messagebox.showerror("Print Error", f"Could not send to printer.\n{e}")

    # ... (Other methods for invoices, users, logs, recycle bin, settings, etc. are similarly commented above)

# === LOGIN WINDOW ===

def login_window():
    """Display the login window and authenticate users."""
    login = tk.Tk()
    login.title("Login")
    login.geometry("300x200")

    tk.Label(login, text="Username").pack(pady=5)
    username_entry = tk.Entry(login)
    username_entry.pack()

    tk.Label(login, text="Password").pack(pady=5)
    password_entry = tk.Entry(login, show="*")
    password_entry.pack()

    def attempt_login():
        username = username_entry.get()
        password = password_entry.get()
        cursor.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, password))
        result = cursor.fetchone()
        if result:
            role = result[0]
            log_action(username, "Logged in")
            login.destroy()
            app = InventoryApp(username, role)
            app.mainloop()
        else:
            messagebox.showerror("Login Failed", "Incorrect username or password.")

    tk.Button(login, text="Login", command=attempt_login).pack(pady=20)
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

