# NexaBank — Banking Management System

A desktop banking management application built with Python and **tkinter**.  
Features account registration, deposit/withdraw/transfer operations, transaction history, and PIN-based authentication — all backed by JSON file storage.

## Features

- **Multi-step Account Registration** — Personal info, address (with Cambodian province/district/commune/village lookup via Pumi API), account details, PIN setup
- **Secure Login** — PIN hashed with SHA-256
- **Dashboard** — Real-time balance, quick actions, recent transactions table, account info
- **Deposit / Withdraw / Transfer** — Dialog-based operations with validation
- **Transaction History** — Per-account statement viewer with reference IDs
- **Admin View** — List all accounts in a sortable table
- **Error Handling** — Custom exception hierarchy for banking-specific errors

## Tech Stack

- **Language:** Python 3.14+
- **GUI:** tkinter / ttk
- **Data Storage:** JSON files (`bank_data/accounts.json`, `bank_data/transactions.json`)
- **External API:** [Pumi API](https://pumi.onrender.com/pumi) (Cambodia administrative divisions)

## Project Structure

```
BMS/
├── main.py                        # Application entry point (~1270 lines)
├── bank_data/
│   ├── accounts.json              # Account data store
│   └── transactions.json          # Transaction data store
├── .venv/                         # Virtual environment (Python 3.14)
├── .gitignore
└── README.md
```

## Classes (all in `main.py`)

| Class | Purpose |
|---|---|
| `Address` | Value object for residential address |
| `BankAccount` | Account entity with deposit/withdraw methods |
| `Transaction` | Transaction record with type, amount, timestamp |
| `AccountRepository` | JSON file read/write for accounts and transactions |
| `BankingService` | Business logic: register, authenticate, deposit, withdraw, transfer |
| `BankingApp` | tkinter GUI application |

## Custom Exceptions

- `BankingError` — base exception
- `AccountNotFoundError`
- `DuplicateAccountError`
- `InsufficientFundsError`
- `InvalidAmountError`
- `ValidationError`

## Getting Started

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd BMS
   ```

2. **Run the application**
   ```bash
   python main.py
   ```

## Requirements

- Python 3.14+
- `requests` (for Pumi API address lookup)

Install dependencies with:

```bash
pip install requests
```

Or using the requirements file:

```bash
pip install -r requirements.txt
```

## Usage

- **Open Account** — Click "Open New Account" and follow the 4-step registration wizard
- **Login** — Use your generated Account ID + PIN to access the dashboard
- **Dashboard** — View balance, perform transactions, see recent activity
- **All Accounts** — Browse all registered accounts (admin-style view)

## License

MIT
