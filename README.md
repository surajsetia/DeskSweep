# DeskSweep — Full-stack monolith

A small monolithic application:
- React + Vite frontend
- FastAPI backend
- SQLite database
- Razorpay Checkout for a ₹99 one-time Pro unlock
- Browser File System Access API for local file organization

The browser handles file access locally. User files are never uploaded to the backend.

## Architecture

In production, FastAPI serves the built React app and the API from the same origin.
There is one deployable backend application (monolith), not separate microservices.

## Features

- Select a folder (Desktop, Downloads, or another folder)
- Scan top-level files
- Organize into category and subcategory folders
- Documents: PDFs, Word, Excel, PowerPoint, Text, Data
- Images, Videos, Audio, Archives, Code, Others
- Preview before moving
- Collision-safe names; existing files are not overwritten
- First 5 successful organization runs are free
- Then ₹99 one-time payment unlocks Pro
- Anonymous browser ID; no customer signup/login
- Razorpay order creation and server-side signature verification

## Requirements

- Python 3.10+
- Node.js 20+
- Latest Chrome or Edge on desktop for folder access
- Razorpay account with Payment Gateway activated for live payments

## Setup — Windows PowerShell

### 1. Extract and open the project

Open the `DeskSweep-Complete` folder in VS Code.

### 2. Configure the backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env`.

For initial development, leave Razorpay keys blank. File organization and the 5-attempt counter can be tested without payments.

To test payments, use Razorpay TEST keys:
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`

Never put the Key Secret in frontend code or commit `.env` to Git.

### 3. Install frontend dependencies

Open a second PowerShell terminal at the project root:

```powershell
cd frontend
npm install
```

### 4. Run in development

Terminal 1 (from `backend` with virtual environment active):

```powershell
uvicorn app.main:app --reload --port 8000
```

Terminal 2 (from `frontend`):

```powershell
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`.

The Vite dev server proxies `/api` requests to FastAPI at port 8000.

### 5. Build and run as one app

From `frontend`:

```powershell
npm run build
```

This creates `backend/app/static/`.

Then from `backend`:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

In production, deploy the FastAPI app with the built `backend/app/static` folder and persistent storage for SQLite. Use HTTPS and set `ALLOWED_ORIGINS` to your actual domain (or leave the same-origin default).

## Razorpay and UPI

1. Log in to Razorpay Dashboard.
2. Complete account activation/KYC and enable Payment Gateway.
3. Check that UPI is enabled under payment methods for your account.
4. Create API keys in TEST mode first.
5. Put the TEST Key ID and Key Secret in `backend/.env`.
6. Test an order and payment using Razorpay's supported test flow.
7. Only after successful tests and account activation, switch to LIVE keys.
8. UPI apps/options shown at checkout depend on Razorpay account activation, device/browser and Razorpay's current checkout availability.

The frontend uses Razorpay Standard Checkout. It does not hardcode a UPI app or collect UPI PIN. Customer completes UPI payment in Razorpay's checkout flow.

## Important notes / honest limitations

- Folder access requires the user to select a folder and grant browser permission. A website cannot silently control the whole computer.
- This MVP scans files directly inside the selected folder, not nested folders.
- File organization is local in the browser. Backend receives only anonymous usage/payment metadata, never file contents.
- No-login free limits are best-effort: clearing browser storage or switching browser/device can create a new anonymous ID. This is not strong anti-abuse protection.
- A user can potentially bypass frontend-only attempt recording by modifying browser requests. The backend enforces the 5-attempt ceiling for recorded attempts, but a fully tamper-resistant no-login quota is not possible without stronger identity/device controls.
- Use preview and explicit confirmation before moving files. Back up important data.
- SQLite is suitable for a small MVP on one persistent server. Do not deploy on ephemeral storage without a persistent volume.
- Razorpay LIVE payments require merchant account activation and payment-method availability. This project cannot activate UPI on your Razorpay account automatically.
- This code is a starter implementation; test carefully before accepting real payments.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health |
| GET | `/api/access/{client_id}` | Attempts and Pro status |
| POST | `/api/usage/complete` | Record a successful organization |
| POST | `/api/payments/create-order` | Create ₹99 order |
| POST | `/api/payments/verify` | Verify signature and payment status |
| GET | `/api/docs` | Swagger API docs |

