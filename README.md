# Inventory App for Business

A professional inventory and invoice management application built using Python and Tkinter. This app is designed to help small businesses efficiently manage their product inventory, supplier data, and invoice generation, with a user-friendly GUI and advanced export/print features.

## 🔧 Features

- 📦 Add, update, and delete inventory items with name, quantity, and price
- 🧾 Supplier invoice generation and history tracking
- 📂 Export inventory and logs to CSV and Excel
- 🖨️ Print Preview and System Print support for invoices
- 📊 Dashboard with real-time statistics and visual charts
- 🎨 Dark mode toggle
- 🌍 Multi-language interface support (EN/ES/FR/IT)
- ⚙️ Settings page for saving default invoice template and user preferences
- 🔔 Notification popups for user actions
- 🧪 Unit tested core features like invoice creation and label formatting
- 💼 Packaged for standalone use as a Windows .exe with PyInstaller

## 📁 Project Structure

```
inventory_app/
├── assets/               # App assets and templates
├── invoices/             # Saved invoice files
├── src/                  # Core app logic and GUI components
├── tests/                # Unit test files
└── inventory_app.py      # Main application file
```

## ▶️ How to Run

```bash
python inventory_app.py
```

To package as a Windows executable:
```bash
pyinstaller --onefile --windowed inventory_app.py
```

## 🧪 Running Tests

```bash
python -m unittest discover tests
```

## 📄 License

This project is licensed under the MIT License.

---

Developed by Daniel Coria | 📧 daancoria@gmail.com
