"""
Banking Management System
Uses: Classes/Objects, File Storage (JSON), Exception Handling, tkinter GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox, font
import json
import os
import re
import uuid
import hashlib
import threading
import requests
from datetime import datetime, date
from pathlib import Path


# ─────────────────────────────────────────────
#  DATA LAYER — Files & Custom Exceptions
# ─────────────────────────────────────────────

DATA_DIR = Path("bank_data")
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"


class BankingError(Exception):
    """Base exception for all banking errors."""


class AccountNotFoundError(BankingError):
    pass


class DuplicateAccountError(BankingError):
    pass


class InsufficientFundsError(BankingError):
    pass


class InvalidAmountError(BankingError):
    pass


class ValidationError(BankingError):
    pass


# ─────────────────────────────────────────────
#  DOMAIN CLASSES
# ─────────────────────────────────────────────

class Address:
    def __init__(self, street, city, state, postal_code, country):
        self.street = street
        self.city = city
        self.state = state
        self.postal_code = postal_code
        self.country = country

    def to_dict(self):
        return vars(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class BankAccount:
    def __init__(self, account_id, full_name, dob, gender, national_id,
                 phone, email, address: Address,
                 account_type, balance, currency, branch,
                 created_at=None, pin_hash=None):
        self.account_id = account_id
        self.full_name = full_name
        self.dob = dob
        self.gender = gender
        self.national_id = national_id
        self.phone = phone
        self.email = email
        self.address = address
        self.account_type = account_type
        self.balance = balance
        self.currency = currency
        self.branch = branch
        self.created_at = created_at or datetime.now().isoformat()
        self.pin_hash = pin_hash

    def deposit(self, amount):
        if amount <= 0:
            raise InvalidAmountError("Deposit amount must be positive.")
        self.balance += amount

    def withdraw(self, amount):
        if amount <= 0:
            raise InvalidAmountError("Withdrawal amount must be positive.")
        if amount > self.balance:
            raise InsufficientFundsError(
                f"Insufficient funds. Balance: {self.currency} {self.balance:,.2f}"
            )
        self.balance -= amount

    def to_dict(self):
        d = vars(self).copy()
        d["address"] = self.address.to_dict()
        return d

    @classmethod
    def from_dict(cls, d):
        d = d.copy()
        d["address"] = Address.from_dict(d["address"])
        return cls(**d)


class Transaction:
    def __init__(self, account_id, tx_type, amount, currency, note="", tx_id=None, timestamp=None):
        self.tx_id = tx_id or str(uuid.uuid4())[:8].upper()
        self.account_id = account_id
        self.tx_type = tx_type          # "DEPOSIT" | "WITHDRAWAL" | "TRANSFER_IN" | "TRANSFER_OUT"
        self.amount = amount
        self.currency = currency
        self.note = note
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self):
        return vars(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# ─────────────────────────────────────────────
#  REPOSITORY — Reads / writes JSON files
# ─────────────────────────────────────────────

class AccountRepository:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        if not ACCOUNTS_FILE.exists():
            ACCOUNTS_FILE.write_text("[]")
        if not TRANSACTIONS_FILE.exists():
            TRANSACTIONS_FILE.write_text("[]")

    def _load_accounts(self):
        with open(ACCOUNTS_FILE, "r") as f:
            return [BankAccount.from_dict(d) for d in json.load(f)]

    def _save_accounts(self, accounts):
        with open(ACCOUNTS_FILE, "w") as f:
            json.dump([a.to_dict() for a in accounts], f, indent=2)

    def _load_transactions(self):
        with open(TRANSACTIONS_FILE, "r") as f:
            return [Transaction.from_dict(d) for d in json.load(f)]

    def _save_transactions(self, txs):
        with open(TRANSACTIONS_FILE, "w") as f:
            json.dump([t.to_dict() for t in txs], f, indent=2)

    def all_accounts(self):
        return self._load_accounts()

    def find_by_id(self, account_id):
        for acc in self._load_accounts():
            if acc.account_id == account_id:
                return acc
        raise AccountNotFoundError(f"Account '{account_id}' not found.")

    def find_by_email(self, email):
        for acc in self._load_accounts():
            if acc.email.lower() == email.lower():
                return acc
        return None

    def save_account(self, account: BankAccount):
        accounts = self._load_accounts()
        for i, a in enumerate(accounts):
            if a.account_id == account.account_id:
                accounts[i] = account
                self._save_accounts(accounts)
                return
        if self.find_by_email(account.email):
            raise DuplicateAccountError(f"An account with email '{account.email}' already exists.")
        accounts.append(account)
        self._save_accounts(accounts)

    def delete_account(self, account_id):
        accounts = self._load_accounts()
        new_list = [a for a in accounts if a.account_id != account_id]
        if len(new_list) == len(accounts):
            raise AccountNotFoundError(f"Account '{account_id}' not found.")
        self._save_accounts(new_list)

    def add_transaction(self, tx: Transaction):
        txs = self._load_transactions()
        txs.append(tx)
        self._save_transactions(txs)

    def get_transactions(self, account_id):
        return [t for t in self._load_transactions() if t.account_id == account_id]


# ─────────────────────────────────────────────
#  SERVICE LAYER
# ─────────────────────────────────────────────

class BankingService:
    def __init__(self):
        self.repo = AccountRepository()

    @staticmethod
    def _hash_pin(pin):
        return hashlib.sha256(pin.encode()).hexdigest()

    @staticmethod
    def _validate_email(email):
        if not re.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$", email):
            raise ValidationError("Invalid email address format.")

    @staticmethod
    def _validate_phone(phone):
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 7 or len(digits) > 15:
            raise ValidationError("Phone number must be 7–15 digits.")

    @staticmethod
    def _validate_deposit(amount):
        if amount < 0:
            raise InvalidAmountError("Initial deposit cannot be negative.")

    def register(self, *, full_name, dob, gender, national_id, phone, email,
                 street, city, state, postal_code, country,
                 account_type, initial_deposit, currency, branch, pin):
        if not full_name.strip():
            raise ValidationError("Full name is required.")
        self._validate_email(email)
        self._validate_phone(phone)
        self._validate_deposit(initial_deposit)
        if not pin or len(pin) < 4:
            raise ValidationError("PIN must be at least 4 digits.")

        address = Address(street, city, state, postal_code, country)
        account_id = "ACC" + str(uuid.uuid4())[:6].upper()
        account = BankAccount(
            account_id=account_id,
            full_name=full_name.strip(),
            dob=dob, gender=gender,
            national_id=national_id, phone=phone, email=email,
            address=address,
            account_type=account_type,
            balance=initial_deposit,
            currency=currency, branch=branch,
            pin_hash=self._hash_pin(pin)
        )
        self.repo.save_account(account)
        if initial_deposit > 0:
            tx = Transaction(account_id, "DEPOSIT", initial_deposit, currency, "Initial deposit")
            self.repo.add_transaction(tx)
        return account

    def authenticate(self, account_id, pin):
        acc = self.repo.find_by_id(account_id)
        if acc.pin_hash != self._hash_pin(pin):
            raise ValidationError("Incorrect PIN.")
        return acc

    def deposit(self, account_id, amount, note=""):
        acc = self.repo.find_by_id(account_id)
        acc.deposit(amount)
        self.repo.save_account(acc)
        tx = Transaction(account_id, "DEPOSIT", amount, acc.currency, note)
        self.repo.add_transaction(tx)
        return acc

    def withdraw(self, account_id, amount, note=""):
        acc = self.repo.find_by_id(account_id)
        acc.withdraw(amount)
        self.repo.save_account(acc)
        tx = Transaction(account_id, "WITHDRAWAL", amount, acc.currency, note)
        self.repo.add_transaction(tx)
        return acc

    def transfer(self, from_id, to_id, amount, note=""):
        if from_id == to_id:
            raise BankingError("Cannot transfer to the same account.")
        src = self.repo.find_by_id(from_id)
        dst = self.repo.find_by_id(to_id)
        src.withdraw(amount)
        dst.deposit(amount)
        self.repo.save_account(src)
        self.repo.save_account(dst)
        self.repo.add_transaction(Transaction(from_id, "TRANSFER_OUT", amount, src.currency, f"To {to_id}: {note}"))
        self.repo.add_transaction(Transaction(to_id, "TRANSFER_IN", amount, dst.currency, f"From {from_id}: {note}"))
        return src, dst

    def get_statement(self, account_id):
        return self.repo.get_transactions(account_id)

    def all_accounts(self):
        return self.repo.all_accounts()

    def delete_account(self, account_id):
        self.repo.delete_account(account_id)


# ─────────────────────────────────────────────
#  GUI — tkinter with multi-step registration
# ─────────────────────────────────────────────

GOLD   = "#C9A84C"
DARK   = "#0D1117"
PANEL  = "#161B22"
CARD   = "#1C2330"
BORDER = "#2D3748"
TEXT   = "#E6EDF3"
MUTED  = "#8B949E"
GREEN  = "#3FB950"
RED    = "#F85149"
BLUE   = "#58A6FF"

PUMI_API = "https://pumi.onrender.com/pumi"

BRANCHES = ["Main Branch", "North Branch", "South Branch", "East Branch",
            "West Branch", "Airport Branch", "Online Only"]

CURRENCIES = ["USD", "KHR", "EUR", "GBP", "AUD", "SGD", "THB", "JPY"]

ACCOUNT_TYPES = ["Savings", "Checking", "Fixed Deposit", "Joint", "Business", "Student"]

COUNTRY_CODES = ["+855 KH", "+1 US", "+44 UK", "+61 AU", "+65 SG", "+66 TH", "+84 VN"]


class BankingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.service = BankingService()
        self.title("NexaBank — Banking Management System")
        self.geometry("1100x750")
        self.minsize(900, 650)
        self.configure(bg=DARK)
        self._setup_styles()
        self.current_account = None
        self._show_home()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=DARK, foreground=TEXT, font=("Georgia", 10))
        style.configure("TFrame", background=DARK)
        style.configure("TLabel", background=DARK, foreground=TEXT)
        style.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                         insertcolor=TEXT, bordercolor=BORDER, relief="flat", padding=6)
        style.configure("TCombobox", fieldbackground=CARD, foreground=TEXT,
                         background=CARD, selectbackground=CARD, selectforeground=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)],
                  selectbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
        style.configure("TRadiobutton", background=DARK, foreground=TEXT)
        style.configure("Treeview", background=CARD, foreground=TEXT,
                         fieldbackground=CARD, rowheight=28)
        style.configure("Treeview.Heading", background=PANEL, foreground=GOLD,
                         font=("Georgia", 9, "bold"))
        style.map("Treeview", background=[("selected", BORDER)])

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _btn(self, parent, text, cmd, bg=GOLD, fg=DARK, width=18, pady=10):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg=fg, font=("Georgia", 10, "bold"),
                      relief="flat", cursor="hand2",
                      padx=14, pady=pady, width=width,
                      activebackground=GOLD, activeforeground=DARK)
        return b

    def _label(self, parent, text, size=10, bold=False, color=TEXT):
        weight = "bold" if bold else "normal"
        return tk.Label(parent, text=text,
                        font=("Georgia", size, weight),
                        bg=DARK, fg=color)

    def _entry(self, parent, show=None):
        e = ttk.Entry(parent, show=show)
        e.configure(style="TEntry")
        return e

    def _combo(self, parent, values, width=22):
        v = tk.StringVar()
        c = ttk.Combobox(parent, textvariable=v, values=values,
                          state="readonly", width=width)
        return c, v

    def _field_row(self, parent, label, widget, row, col=0, span=1):
        tk.Label(parent, text=label, bg=DARK, fg=MUTED,
                 font=("Georgia", 9)).grid(row=row*2, column=col, columnspan=span,
                                           sticky="w", padx=(0, 8), pady=(8, 0))
        widget.grid(row=row*2+1, column=col, columnspan=span,
                    sticky="ew", pady=(0, 4))

    # ── HOME SCREEN ──────────────────────────────

    def _show_home(self):
        self._clear()
        self.current_account = None

        bar = tk.Frame(self, bg=PANEL, height=70)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 20, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=30, pady=18)
        tk.Label(bar, text="Modern Banking • Secure • Reliable",
                 font=("Georgia", 10, "italic"),
                 bg=PANEL, fg=MUTED).pack(side="left", padx=6, pady=24)

        center = tk.Frame(self, bg=DARK)
        center.pack(expand=True)

        tk.Label(center, text="Welcome to NexaBank",
                 font=("Georgia", 28, "bold"),
                 bg=DARK, fg=TEXT).pack(pady=(40, 6))
        tk.Label(center, text="Your trusted partner for modern banking",
                 font=("Georgia", 12, "italic"),
                 bg=DARK, fg=MUTED).pack(pady=(0, 40))

        btn_frame = tk.Frame(center, bg=DARK)
        btn_frame.pack()

        self._btn(btn_frame, "🏦  Open New Account", self._show_register,
                  width=22, pady=14).grid(row=0, column=0, padx=12, pady=8)
        self._btn(btn_frame, "🔑  Login to Account", self._show_login,
                  bg=CARD, fg=GOLD, width=22, pady=14).grid(row=0, column=1, padx=12, pady=8)
        self._btn(btn_frame, "📋  All Accounts", self._show_all_accounts,
                  bg=CARD, fg=TEXT, width=22, pady=14).grid(row=0, column=2, padx=12, pady=8)

        tk.Label(center, text=f"© {date.today().year} NexaBank. All rights reserved.",
                 font=("Georgia", 9), bg=DARK, fg=BORDER).pack(pady=60)

    # ── REGISTRATION — multi-step ─────────────────

    def _show_register(self):
        self._clear()
        self.reg_data = {}
        self._reg_step = 1
        self._build_reg_step1()

    def _reg_header(self, step):
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 16, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=24, pady=14)
        tk.Button(bar, text="← Home", command=self._show_home,
                  bg=PANEL, fg=MUTED, relief="flat",
                  font=("Georgia", 9), cursor="hand2").pack(side="right", padx=24)

        steps_frame = tk.Frame(self, bg=DARK)
        steps_frame.pack(pady=14)
        labels = ["1  Personal Info", "2  Address", "3  Account Details", "4  Security"]
        for i, lbl in enumerate(labels, 1):
            col = GOLD if i == step else (TEXT if i < step else MUTED)
            sep_col = GOLD if i < step else BORDER
            if i > 1:
                tk.Label(steps_frame, text="────", bg=DARK, fg=sep_col,
                         font=("Georgia", 9)).pack(side="left")
            tk.Label(steps_frame, text=lbl, bg=DARK, fg=col,
                     font=("Georgia", 9, "bold" if i == step else "normal")).pack(side="left", padx=6)

    def _scrollable_body(self):
        outer = tk.Frame(self, bg=DARK)
        outer.pack(fill="both", expand=True, padx=40, pady=10)

        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=DARK)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(window, width=canvas.winfo_width())

        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        return inner

    def _section(self, parent, title):
        f = tk.LabelFrame(parent, text=f"  {title}  ", bg=DARK, fg=GOLD,
                          font=("Georgia", 10, "bold"),
                          bd=1, relief="groove",
                          labelanchor="nw", padx=16, pady=12)
        f.pack(fill="x", pady=8)
        return f

    # ── STEP 1: Personal Info ──

    def _build_reg_step1(self):
        self._reg_header(1)
        body = self._scrollable_body()

        tk.Label(body, text="Step 1: Personal Information",
                 font=("Georgia", 16, "bold"), bg=DARK, fg=TEXT).pack(anchor="w", pady=(0, 8))

        sec = self._section(body, "Personal Details")
        sec.columnconfigure((0, 1), weight=1, uniform="col")

        tk.Label(sec, text="Full Name *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._e_fullname = ttk.Entry(sec, width=30)
        self._e_fullname.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))

        tk.Label(sec, text="Date of Birth *  (YYYY-MM-DD)", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=1, sticky="w", pady=(4, 0))
        self._e_dob = ttk.Entry(sec, width=30)
        self._e_dob.insert(0, "1990-01-01")
        self._e_dob.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        tk.Label(sec, text="Gender *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self._gender_var = tk.StringVar(value="Male")
        gf = tk.Frame(sec, bg=DARK)
        gf.grid(row=3, column=0, sticky="w", pady=(0, 8))
        for g in ["Male", "Female", "Other", "Prefer not to say"]:
            ttk.Radiobutton(gf, text=g, variable=self._gender_var, value=g).pack(side="left", padx=6)

        tk.Label(sec, text="National ID / SSN *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=1, sticky="w", pady=(4, 0))
        self._e_nid = ttk.Entry(sec, show="*", width=30)
        self._e_nid.grid(row=3, column=1, sticky="ew", pady=(0, 8))

        tk.Label(sec, text="Phone Number *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=4, column=0, sticky="w", pady=(4, 0))
        pf = tk.Frame(sec, bg=DARK)
        pf.grid(row=5, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        pf.columnconfigure(1, weight=1)
        self._cc_var = tk.StringVar(value=COUNTRY_CODES[0])
        ttk.Combobox(pf, textvariable=self._cc_var, values=COUNTRY_CODES,
                     state="readonly", width=10).grid(row=0, column=0, padx=(0, 4))
        self._e_phone = ttk.Entry(pf)
        self._e_phone.grid(row=0, column=1, sticky="ew")

        tk.Label(sec, text="Email Address *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=4, column=1, sticky="w", pady=(4, 0))
        self._e_email = ttk.Entry(sec, width=30)
        self._e_email.grid(row=5, column=1, sticky="ew", pady=(0, 8))

        nav = tk.Frame(body, bg=DARK)
        nav.pack(fill="x", pady=16)
        self._btn(nav, "← Back", self._show_home, bg=CARD, fg=TEXT).pack(side="left")
        self._btn(nav, "Next: Address →", self._reg_step1_next).pack(side="right")

    def _reg_step1_next(self):
        try:
            full_name = self._e_fullname.get().strip()
            if not full_name:
                raise ValidationError("Full name is required.")
            dob = self._e_dob.get().strip()
            datetime.strptime(dob, "%Y-%m-%d")
            phone = self._cc_var.get().split()[0] + self._e_phone.get().strip()
            BankingService._validate_phone(self._e_phone.get().strip())
            email = self._e_email.get().strip()
            BankingService._validate_email(email)
            nid = self._e_nid.get().strip()
            if not nid:
                raise ValidationError("National ID is required.")

            self.reg_data.update(dict(
                full_name=full_name, dob=dob,
                gender=self._gender_var.get(),
                national_id=nid, phone=phone, email=email
            ))
            self._clear()
            self._build_reg_step2()
        except (ValidationError, ValueError) as e:
            messagebox.showerror("Validation Error", str(e))

    # ── STEP 2: Address — Pumi API (Cambodia) ──

    # ── API helpers ────────────────────────────────

    def _fetch_provinces(self):
        try:
            r = requests.get(f"{PUMI_API}/provinces", timeout=10)
            r.raise_for_status()
            return [(p["id"], p["name_en"]) for p in r.json()]
        except Exception:
            return []

    def _fetch_districts(self, province_id):
        try:
            r = requests.get(f"{PUMI_API}/districts", params={"province_id": province_id}, timeout=10)
            r.raise_for_status()
            return [(d["id"], d["name_en"]) for d in r.json()]
        except Exception:
            return []

    def _fetch_communes(self, district_id):
        try:
            r = requests.get(f"{PUMI_API}/communes", params={"district_id": district_id}, timeout=10)
            r.raise_for_status()
            return [(c["id"], c["name_en"]) for c in r.json()]
        except Exception:
            return []

    def _fetch_villages(self, commune_id):
        try:
            r = requests.get(f"{PUMI_API}/villages", params={"commune_id": commune_id}, timeout=10)
            r.raise_for_status()
            return [(v["id"], v["name_en"]) for v in r.json()]
        except Exception:
            return []

    def _populate_combo(self, combo_var, combo_widget, items):
        values = [name for _, name in items]
        combo_widget.configure(values=values)
        if values:
            combo_var.set(values[0])
        else:
            combo_var.set("")
        combo_widget._items = items

    def _load_provinces_async(self):
        def task():
            items = self._fetch_provinces()
            self.after(0, lambda: self._populate_combo(
                self._province_var, self._province_cb, items))
            self.after(0, lambda: self._province_cb.bind(
                "<<ComboboxSelected>>", self._on_province_selected, add="+"))
        threading.Thread(target=task, daemon=True).start()

    def _on_province_selected(self, event=None):
        selected = self._province_var.get()
        items = getattr(self._province_cb, "_items", [])
        pid = None
        for iid, name in items:
            if name == selected:
                pid = iid
                break
        if not pid:
            return
        self._district_cb.configure(values=[])
        self._commune_cb.configure(values=[])
        self._village_cb.configure(values=[])
        self._district_var.set("")
        self._commune_var.set("")
        self._village_var.set("")
        def task():
            districts = self._fetch_districts(pid)
            self.after(0, lambda: self._populate_combo(
                self._district_var, self._district_cb, districts))
            self.after(0, lambda: self._district_cb.bind(
                "<<ComboboxSelected>>", self._on_district_selected, add="+"))
        threading.Thread(target=task, daemon=True).start()

    def _on_district_selected(self, event=None):
        selected = self._district_var.get()
        items = getattr(self._district_cb, "_items", [])
        did = None
        for iid, name in items:
            if name == selected:
                did = iid
                break
        if not did:
            return
        self._commune_cb.configure(values=[])
        self._village_cb.configure(values=[])
        self._commune_var.set("")
        self._village_var.set("")
        def task():
            communes = self._fetch_communes(did)
            self.after(0, lambda: self._populate_combo(
                self._commune_var, self._commune_cb, communes))
            self.after(0, lambda: self._commune_cb.bind(
                "<<ComboboxSelected>>", self._on_commune_selected, add="+"))
        threading.Thread(target=task, daemon=True).start()

    def _on_commune_selected(self, event=None):
        selected = self._commune_var.get()
        items = getattr(self._commune_cb, "_items", [])
        cid = None
        for iid, name in items:
            if name == selected:
                cid = iid
                break
        if not cid:
            return
        self._village_cb.configure(values=[])
        self._village_var.set("")
        def task():
            villages = self._fetch_villages(cid)
            self.after(0, lambda: self._populate_combo(
                self._village_var, self._village_cb, villages))
        threading.Thread(target=task, daemon=True).start()

    # ── Build step 2 ───────────────────────────────

    def _build_reg_step2(self):
        self._reg_header(2)
        body = self._scrollable_body()

        tk.Label(body, text="Step 2: Address Information (Cambodia)",
                 font=("Georgia", 16, "bold"), bg=DARK, fg=TEXT).pack(anchor="w", pady=(0, 8))

        sec = self._section(body, "Residential Address")
        sec.columnconfigure((0, 1), weight=1, uniform="col")

        tk.Label(sec, text="Street / House No. *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        self._e_street = tk.Text(sec, height=3, bg=CARD, fg=TEXT,
                                  insertbackground=TEXT, relief="flat",
                                  font=("Georgia", 10), padx=6, pady=6)
        self._e_street.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        tk.Label(sec, text="Country", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        tk.Label(sec, text="Cambodia", bg=CARD, fg=GOLD,
                 font=("Georgia", 10, "bold"), padx=8, pady=4).grid(
            row=3, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))

        tk.Label(sec, text="Province *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=1, sticky="w", pady=(4, 0))
        self._province_var = tk.StringVar()
        self._province_cb = ttk.Combobox(sec, textvariable=self._province_var,
                                          state="readonly", width=28)
        self._province_cb.grid(row=3, column=1, sticky="ew", pady=(0, 8))
        self._province_cb._items = []

        tk.Label(sec, text="District *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=4, column=0, sticky="w", pady=(4, 0))
        self._district_var = tk.StringVar()
        self._district_cb = ttk.Combobox(sec, textvariable=self._district_var,
                                          state="readonly", width=28)
        self._district_cb.grid(row=5, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        self._district_cb._items = []

        tk.Label(sec, text="Commune *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=4, column=1, sticky="w", pady=(4, 0))
        self._commune_var = tk.StringVar()
        self._commune_cb = ttk.Combobox(sec, textvariable=self._commune_var,
                                         state="readonly", width=28)
        self._commune_cb.grid(row=5, column=1, sticky="ew", pady=(0, 8))
        self._commune_cb._items = []

        tk.Label(sec, text="Village", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=6, column=0, sticky="w", pady=(4, 0))
        self._village_var = tk.StringVar()
        self._village_cb = ttk.Combobox(sec, textvariable=self._village_var,
                                         state="readonly", width=28)
        self._village_cb.grid(row=7, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        self._village_cb._items = []

        nav = tk.Frame(body, bg=DARK)
        nav.pack(fill="x", pady=16)
        self._btn(nav, "← Back", lambda: [self._clear(), self._build_reg_step1()],
                  bg=CARD, fg=TEXT).pack(side="left")
        self._btn(nav, "Next: Account Details →", self._reg_step2_next).pack(side="right")

        self._load_provinces_async()

    def _reg_step2_next(self):
        try:
            street = self._e_street.get("1.0", "end").strip()
            province = self._province_var.get()
            district = self._district_var.get()
            commune = self._commune_var.get()
            if not all([street, province, district, commune]):
                raise ValidationError("Street, province, district, and commune are required.")
            self.reg_data.update(dict(
                street=street, city=commune,
                state=district,
                postal_code="",
                country="Cambodia"
            ))
            self._clear()
            self._build_reg_step3()
        except ValidationError as e:
            messagebox.showerror("Validation Error", str(e))

    # ── STEP 3: Account Details ──

    def _build_reg_step3(self):
        self._reg_header(3)
        body = self._scrollable_body()

        tk.Label(body, text="Step 3: Account Details",
                 font=("Georgia", 16, "bold"), bg=DARK, fg=TEXT).pack(anchor="w", pady=(0, 8))

        sec = self._section(body, "Account Configuration")
        sec.columnconfigure((0, 1), weight=1, uniform="col")

        tk.Label(sec, text="Account Type *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._atype_var = tk.StringVar(value=ACCOUNT_TYPES[0])
        ttk.Combobox(sec, textvariable=self._atype_var, values=ACCOUNT_TYPES,
                     state="readonly", width=28).grid(row=1, column=0, sticky="ew",
                                                      padx=(0, 10), pady=(0, 8))

        tk.Label(sec, text="Currency *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=1, sticky="w", pady=(4, 0))
        self._curr_var = tk.StringVar(value=CURRENCIES[0])
        ttk.Combobox(sec, textvariable=self._curr_var, values=CURRENCIES,
                     state="readonly", width=28).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        tk.Label(sec, text="Initial Deposit Amount *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self._e_deposit = ttk.Entry(sec, width=30)
        self._e_deposit.insert(0, "0")
        self._e_deposit.grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))

        tk.Label(sec, text="Preferred Branch (Optional)", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=1, sticky="w", pady=(4, 0))
        self._branch_var = tk.StringVar(value=BRANCHES[0])
        ttk.Combobox(sec, textvariable=self._branch_var, values=BRANCHES,
                     state="readonly", width=28).grid(row=3, column=1, sticky="ew", pady=(0, 8))

        nav = tk.Frame(body, bg=DARK)
        nav.pack(fill="x", pady=16)
        self._btn(nav, "← Back", lambda: [self._clear(), self._build_reg_step2()],
                  bg=CARD, fg=TEXT).pack(side="left")
        self._btn(nav, "Next: Security →", self._reg_step3_next).pack(side="right")

    def _reg_step3_next(self):
        try:
            deposit_str = self._e_deposit.get().strip()
            try:
                deposit = float(deposit_str)
            except ValueError:
                raise ValidationError("Initial deposit must be a number.")
            if deposit < 0:
                raise InvalidAmountError("Deposit cannot be negative.")
            self.reg_data.update(dict(
                account_type=self._atype_var.get(),
                initial_deposit=deposit,
                currency=self._curr_var.get(),
                branch=self._branch_var.get()
            ))
            self._clear()
            self._build_reg_step4()
        except (ValidationError, InvalidAmountError) as e:
            messagebox.showerror("Validation Error", str(e))

    # ── STEP 4: Security (PIN) ──

    def _build_reg_step4(self):
        self._reg_header(4)
        body = self._scrollable_body()

        tk.Label(body, text="Step 4: Security Setup",
                 font=("Georgia", 16, "bold"), bg=DARK, fg=TEXT).pack(anchor="w", pady=(0, 8))

        sec = self._section(body, "Set Your PIN")
        sec.columnconfigure(0, weight=1)

        tk.Label(sec, text="Choose a 4–6 digit PIN *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._e_pin = ttk.Entry(sec, show="●", width=30)
        self._e_pin.grid(row=1, column=0, sticky="w", pady=(0, 8))

        tk.Label(sec, text="Confirm PIN *", bg=DARK, fg=MUTED, font=("Georgia", 9)).grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self._e_pin2 = ttk.Entry(sec, show="●", width=30)
        self._e_pin2.grid(row=3, column=0, sticky="w", pady=(0, 8))

        tk.Label(sec, text="⚠  Keep your PIN secret. NexaBank will never ask for it.",
                 bg=DARK, fg=GOLD, font=("Georgia", 9, "italic")).grid(
            row=4, column=0, sticky="w", pady=(8, 4))

        sum_sec = self._section(body, "Registration Summary")
        d = self.reg_data
        summary = (
            f"Name: {d.get('full_name')}     |     Email: {d.get('email')}\n"
            f"Account Type: {d.get('account_type')}     |     Currency: {d.get('currency')}\n"
            f"Initial Deposit: {d.get('currency')} {d.get('initial_deposit', 0):,.2f}     "
            f"|     Branch: {d.get('branch')}"
        )
        tk.Label(sum_sec, text=summary, bg=DARK, fg=TEXT,
                 font=("Courier", 9), justify="left").pack(anchor="w")

        nav = tk.Frame(body, bg=DARK)
        nav.pack(fill="x", pady=16)
        self._btn(nav, "← Back", lambda: [self._clear(), self._build_reg_step3()],
                  bg=CARD, fg=TEXT).pack(side="left")
        self._btn(nav, "✓  Create Account", self._submit_registration,
                  bg=GREEN, fg=DARK).pack(side="right")

    def _submit_registration(self):
        try:
            pin = self._e_pin.get()
            pin2 = self._e_pin2.get()
            if len(pin) < 4:
                raise ValidationError("PIN must be at least 4 digits.")
            if not pin.isdigit():
                raise ValidationError("PIN must contain digits only.")
            if pin != pin2:
                raise ValidationError("PINs do not match.")

            d = self.reg_data
            account = self.service.register(
                full_name=d["full_name"], dob=d["dob"],
                gender=d["gender"], national_id=d["national_id"],
                phone=d["phone"], email=d["email"],
                street=d["street"], city=d["city"],
                state=d["state"], postal_code=d["postal_code"],
                country=d["country"],
                account_type=d["account_type"],
                initial_deposit=d["initial_deposit"],
                currency=d["currency"], branch=d["branch"],
                pin=pin
            )
            self._show_success(account)
        except (ValidationError, DuplicateAccountError, BankingError) as e:
            messagebox.showerror("Registration Error", str(e))

    def _show_success(self, account):
        self._clear()
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 16, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=24, pady=14)

        center = tk.Frame(self, bg=DARK)
        center.pack(expand=True)

        tk.Label(center, text="✅", font=("Segoe UI Emoji", 48), bg=DARK).pack(pady=10)
        tk.Label(center, text="Account Created Successfully!",
                 font=("Georgia", 22, "bold"), bg=DARK, fg=GREEN).pack()
        tk.Label(center, text=f"Welcome, {account.full_name}",
                 font=("Georgia", 14), bg=DARK, fg=TEXT).pack(pady=4)

        card = tk.Frame(center, bg=CARD, padx=30, pady=20)
        card.pack(pady=20)
        rows = [
            ("Account ID", account.account_id),
            ("Account Type", account.account_type),
            ("Balance", f"{account.currency} {account.balance:,.2f}"),
            ("Branch", account.branch),
        ]
        for i, (k, v) in enumerate(rows):
            tk.Label(card, text=k + ":", bg=CARD, fg=MUTED,
                     font=("Georgia", 10)).grid(row=i, column=0, sticky="w", padx=(0, 20), pady=4)
            tk.Label(card, text=v, bg=CARD, fg=GOLD,
                     font=("Georgia", 10, "bold")).grid(row=i, column=1, sticky="w")

        tk.Label(center,
                 text="📌  Save your Account ID — you'll need it to log in.",
                 bg=DARK, fg=MUTED, font=("Georgia", 9, "italic")).pack(pady=4)

        btn_f = tk.Frame(center, bg=DARK)
        btn_f.pack(pady=14)
        self._btn(btn_f, "Login Now", lambda: self._show_login(account.account_id)).pack(side="left", padx=8)
        self._btn(btn_f, "Home", self._show_home, bg=CARD, fg=TEXT).pack(side="left", padx=8)

    # ── LOGIN ──────────────────────────────────────

    def _show_login(self, prefill_id=""):
        self._clear()
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 16, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=24, pady=14)
        tk.Button(bar, text="← Home", command=self._show_home,
                  bg=PANEL, fg=MUTED, relief="flat",
                  font=("Georgia", 9), cursor="hand2").pack(side="right", padx=24)

        center = tk.Frame(self, bg=DARK)
        center.pack(expand=True)

        card = tk.Frame(center, bg=CARD, padx=40, pady=32, relief="flat")
        card.pack(pady=20)

        tk.Label(card, text="🔑  Account Login", font=("Georgia", 18, "bold"),
                 bg=CARD, fg=TEXT).pack(pady=(0, 20))

        tk.Label(card, text="Account ID", bg=CARD, fg=MUTED,
                 font=("Georgia", 9)).pack(anchor="w")
        e_id = ttk.Entry(card, width=32)
        e_id.insert(0, prefill_id)
        e_id.pack(pady=(2, 12), ipady=4)

        tk.Label(card, text="PIN", bg=CARD, fg=MUTED,
                 font=("Georgia", 9)).pack(anchor="w")
        e_pin = ttk.Entry(card, show="●", width=32)
        e_pin.pack(pady=(2, 20), ipady=4)

        def do_login():
            try:
                acc = self.service.authenticate(e_id.get().strip(), e_pin.get())
                self.current_account = acc
                self._show_dashboard()
            except (AccountNotFoundError, ValidationError) as err:
                messagebox.showerror("Login Failed", str(err))

        self._btn(card, "Login →", do_login, width=28, pady=12).pack()

    # ── DASHBOARD ──────────────────────────────────

    def _show_dashboard(self):
        self._clear()
        acc = self.current_account

        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 14, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=20, pady=12)
        tk.Label(bar, text=f"👤  {acc.full_name}  |  {acc.account_id}",
                 bg=PANEL, fg=TEXT, font=("Georgia", 9)).pack(side="left", padx=16)
        tk.Button(bar, text="Logout", command=self._show_home,
                  bg=RED, fg="white", relief="flat",
                  font=("Georgia", 9, "bold"), cursor="hand2",
                  padx=12, pady=4).pack(side="right", padx=20, pady=10)

        main = tk.Frame(self, bg=DARK)
        main.pack(fill="both", expand=True, padx=20, pady=14)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)

        left = tk.Frame(main, bg=DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        right = tk.Frame(main, bg=DARK)
        right.grid(row=0, column=1, sticky="nsew")

        bal_card = tk.Frame(left, bg=CARD, padx=20, pady=20)
        bal_card.pack(fill="x", pady=(0, 10))
        tk.Label(bal_card, text="Current Balance", bg=CARD, fg=MUTED,
                 font=("Georgia", 9)).pack(anchor="w")
        tk.Label(bal_card,
                 text=f"{acc.currency} {acc.balance:,.2f}",
                 bg=CARD, fg=GOLD, font=("Georgia", 22, "bold")).pack(anchor="w")
        tk.Label(bal_card,
                 text=f"{acc.account_type} Account  •  {acc.branch}",
                 bg=CARD, fg=MUTED, font=("Georgia", 9)).pack(anchor="w", pady=(4, 0))

        actions_card = tk.Frame(left, bg=CARD, padx=20, pady=16)
        actions_card.pack(fill="x", pady=(0, 10))
        tk.Label(actions_card, text="Quick Actions", bg=CARD, fg=TEXT,
                 font=("Georgia", 11, "bold")).pack(anchor="w", pady=(0, 10))

        btns = [
            ("💰  Deposit", self._do_deposit, GOLD, DARK),
            ("💸  Withdraw", self._do_withdraw, RED, "white"),
            ("↔  Transfer", self._do_transfer, BLUE, DARK),
            ("📄  Statement", self._do_statement, CARD, TEXT),
        ]
        for text, cmd, bg_, fg_ in btns:
            b = tk.Button(actions_card, text=text, command=cmd,
                          bg=bg_, fg=fg_, relief="flat",
                          font=("Georgia", 10, "bold"),
                          cursor="hand2", padx=10, pady=8,
                          activebackground=bg_, activeforeground=fg_)
            b.pack(fill="x", pady=3)

        info_card = tk.Frame(left, bg=CARD, padx=20, pady=16)
        info_card.pack(fill="x", pady=(0, 10))
        tk.Label(info_card, text="Account Info", bg=CARD, fg=TEXT,
                 font=("Georgia", 11, "bold")).pack(anchor="w", pady=(0, 8))
        details = [
            ("Email", acc.email),
            ("Phone", acc.phone),
            ("DOB", acc.dob),
            ("Country", acc.address.country),
            ("Opened", acc.created_at[:10]),
        ]
        for k, v in details:
            row = tk.Frame(info_card, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=k + ":", bg=CARD, fg=MUTED,
                     font=("Georgia", 9), width=8, anchor="w").pack(side="left")
            tk.Label(row, text=v, bg=CARD, fg=TEXT,
                     font=("Georgia", 9)).pack(side="left")

        tk.Label(right, text="Recent Transactions", bg=DARK, fg=TEXT,
                 font=("Georgia", 14, "bold")).pack(anchor="w", pady=(0, 8))

        cols = ("Date", "Type", "Amount", "Note")
        tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120 if c != "Note" else 180)
        tree.pack(fill="both", expand=True)

        txs = self.service.get_statement(acc.account_id)
        for tx in reversed(txs[-50:]):
            sign = "+" if tx.tx_type in ("DEPOSIT", "TRANSFER_IN") else "-"
            tree.insert("", "end", values=(
                tx.timestamp[:10],
                tx.tx_type.replace("_", " "),
                f"{sign}{acc.currency} {tx.amount:,.2f}",
                tx.note
            ))

        self._btn(right, "↻  Refresh", self._refresh_dashboard,
                  bg=CARD, fg=TEXT, width=14, pady=6).pack(anchor="e", pady=6)

    def _refresh_dashboard(self):
        try:
            self.current_account = self.service.repo.find_by_id(self.current_account.account_id)
        except BankingError:
            pass
        self._show_dashboard()

    # ── OPERATIONS ────────────────────────────────

    def _operation_dialog(self, title, fields, callback):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=DARK)
        win.geometry("380x320")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text=title, font=("Georgia", 14, "bold"),
                 bg=DARK, fg=TEXT).pack(pady=(20, 14))

        entries = {}
        for label, key, show in fields:
            tk.Label(win, text=label, bg=DARK, fg=MUTED,
                     font=("Georgia", 9)).pack(anchor="w", padx=30)
            e = ttk.Entry(win, show=show or "")
            e.pack(fill="x", padx=30, pady=(2, 10), ipady=4)
            entries[key] = e

        msg_var = tk.StringVar()
        tk.Label(win, textvariable=msg_var, bg=DARK, fg=RED,
                 font=("Georgia", 9)).pack()

        def submit():
            try:
                vals = {k: v.get().strip() for k, v in entries.items()}
                callback(vals, win)
            except (BankingError, ValueError) as e:
                msg_var.set(str(e))

        self._btn(win, "Confirm", submit, width=20, pady=10).pack(pady=10)

    def _do_deposit(self):
        def callback(vals, win):
            amount = float(vals["amount"])
            self.current_account = self.service.deposit(
                self.current_account.account_id, amount, vals.get("note", ""))
            win.destroy()
            self._show_dashboard()
            messagebox.showinfo("Deposit Successful",
                                f"Deposited {self.current_account.currency} {amount:,.2f}")

        self._operation_dialog("💰 Deposit Funds", [
            ("Amount", "amount", None),
            ("Note (optional)", "note", None),
        ], callback)

    def _do_withdraw(self):
        def callback(vals, win):
            amount = float(vals["amount"])
            self.current_account = self.service.withdraw(
                self.current_account.account_id, amount, vals.get("note", ""))
            win.destroy()
            self._show_dashboard()
            messagebox.showinfo("Withdrawal Successful",
                                f"Withdrawn {self.current_account.currency} {amount:,.2f}")

        self._operation_dialog("💸 Withdraw Funds", [
            ("Amount", "amount", None),
            ("Note (optional)", "note", None),
        ], callback)

    def _do_transfer(self):
        def callback(vals, win):
            amount = float(vals["amount"])
            src, _ = self.service.transfer(
                self.current_account.account_id,
                vals["to_id"], amount, vals.get("note", ""))
            self.current_account = src
            win.destroy()
            self._show_dashboard()
            messagebox.showinfo("Transfer Successful",
                                f"Transferred {src.currency} {amount:,.2f} to {vals['to_id']}")

        self._operation_dialog("↔ Transfer Funds", [
            ("Recipient Account ID", "to_id", None),
            ("Amount", "amount", None),
            ("Note (optional)", "note", None),
        ], callback)

    def _do_statement(self):
        win = tk.Toplevel(self)
        win.title("Account Statement")
        win.configure(bg=DARK)
        win.geometry("680x480")
        win.grab_set()

        acc = self.current_account
        tk.Label(win, text=f"Statement — {acc.full_name}  ({acc.account_id})",
                 font=("Georgia", 13, "bold"), bg=DARK, fg=TEXT).pack(pady=14)
        tk.Label(win, text=f"Balance: {acc.currency} {acc.balance:,.2f}",
                 font=("Georgia", 11), bg=DARK, fg=GOLD).pack(pady=(0, 10))

        cols = ("Ref", "Date", "Type", "Amount", "Note")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=90 if c != "Note" else 200)
        tree.pack(fill="both", expand=True, padx=16, pady=8)

        txs = self.service.get_statement(acc.account_id)
        for tx in reversed(txs):
            sign = "+" if tx.tx_type in ("DEPOSIT", "TRANSFER_IN") else "-"
            tree.insert("", "end", values=(
                tx.tx_id, tx.timestamp[:10],
                tx.tx_type.replace("_", " "),
                f"{sign}{acc.currency} {tx.amount:,.2f}",
                tx.note
            ))

        self._btn(win, "Close", win.destroy, bg=CARD, fg=TEXT, width=14).pack(pady=10)

    # ── ALL ACCOUNTS (admin view) ──────────────────

    def _show_all_accounts(self):
        self._clear()
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        tk.Label(bar, text="✦ NexaBank", font=("Georgia", 14, "bold"),
                 bg=PANEL, fg=GOLD).pack(side="left", padx=20, pady=12)
        tk.Button(bar, text="← Home", command=self._show_home,
                  bg=PANEL, fg=MUTED, relief="flat",
                  font=("Georgia", 9), cursor="hand2").pack(side="right", padx=20)

        main = tk.Frame(self, bg=DARK)
        main.pack(fill="both", expand=True, padx=20, pady=14)

        tk.Label(main, text="All Accounts", font=("Georgia", 16, "bold"),
                 bg=DARK, fg=TEXT).pack(anchor="w", pady=(0, 10))

        cols = ("Account ID", "Name", "Type", "Balance", "Currency", "Branch", "Opened")
        tree = ttk.Treeview(main, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            w = 130 if c in ("Name", "Branch") else 90
            tree.column(c, width=w)
        tree.pack(fill="both", expand=True)

        accounts = self.service.all_accounts()
        for acc in accounts:
            tree.insert("", "end", values=(
                acc.account_id, acc.full_name,
                acc.account_type,
                f"{acc.balance:,.2f}",
                acc.currency, acc.branch,
                acc.created_at[:10]
            ))

        tk.Label(main, text=f"Total accounts: {len(accounts)}",
                 bg=DARK, fg=MUTED, font=("Georgia", 9)).pack(anchor="e", pady=4)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = BankingApp()
    app.mainloop()
