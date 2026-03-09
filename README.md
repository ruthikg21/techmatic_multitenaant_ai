# Techmatic AI Chatbot — Multi-Tenant Platform

## Overview

This is the multi-tenant version of the Techmatic AI Chatbot platform. It allows Techmatic to create client accounts and provide each client with an embeddable chatbot widget for their website.

## Architecture

```
backend/
  ├── main.py          ← FastAPI server (multi-tenant APIs)
  ├── database.py      ← SQLite database with client_id scoping
  ├── ai_engine.py     ← Claude AI engine (unchanged logic)
  ├── scraper.py       ← Web scraper (unchanged)
  └── requirements.txt

admin/                 ← Client Admin Panel (unchanged design)
  ├── login.html       ← Updated to route superadmin/client
  ├── dashboard.html   ← Same as before (scoped to client)
  ├── leads.html
  ├── conversations.html
  ├── settings.html
  ├── knowledge.html
  ├── account.html
  ├── admin.css
  └── admin.js

superadmin/            ← NEW: Techmatic Super Admin
  ├── dashboard.html   ← Platform-wide stats
  └── clients.html     ← Create/manage client accounts + embed codes

widget/
  └── tm-chatbot.js    ← Embeddable widget (single file, self-contained)
```

## Setup & Deployment

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Start the backend server

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Serve static files

The backend should serve the widget JS as a static file. Add this to your deployment:

Option A — Using FastAPI static files (add to main.py):
```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="../"), name="static")
```

Option B — Use Nginx/Apache to serve the static files and proxy API calls.

### 4. File structure on server

```
/var/www/techmatic-ai/
  ├── backend/           ← FastAPI app
  ├── admin/             ← Client admin panel
  ├── superadmin/        ← Super admin panel  
  └── widget/            ← Embeddable widget files
```

## Default Credentials

### Super Admin (Techmatic)
- **Admin ID:** `superadmin`
- **Password:** `Techmatic@2024`
- **Access:** `/superadmin/dashboard.html`

### Default Client Admin (Techmatic Systems)
- **Admin ID:** `admin`
- **Password:** `techmatic2024`
- **Access:** `/admin/login.html`

## How It Works

### For Techmatic (Super Admin)

1. Log in at `/admin/login.html` with superadmin credentials
2. You'll be redirected to `/superadmin/dashboard.html`
3. Go to **Clients** → **Create Client**
4. Fill in client name, slug, domain, and set admin credentials
5. The system generates a **Widget API Key** and **Embed Code**
6. Share the admin credentials with the client
7. Share the embed code for the client's website

### For Clients

1. Log in at `/admin/login.html` with credentials provided by Techmatic
2. Access the admin panel (same interface — Dashboard, Leads, Conversations, Settings, Knowledge Base)
3. All data is scoped to their own client account — they only see their own chatbot data
4. Configure AI settings, knowledge base, and manage leads

### Embedding the Chatbot on a Client Website

The client (or Techmatic) pastes this code before `</body>` on the client's website:

```html
<script>
  window.TM_WIDGET_CONFIG = {
    apiKey: "tm_xxxxxxxxxxxx",
    serverUrl: "https://your-server.com"
  };
</script>
<script src="https://your-server.com/static/widget/tm-chatbot.js" defer></script>
```

The chatbot widget will automatically appear in the bottom-right corner. No other setup required.

## API Endpoints

### Public Widget APIs (authenticated by API key)
- `POST /widget/chat` — Chat with the AI
- `GET /widget/config?api_key=...` — Get widget config
- `GET /widget/messages?api_key=...&session_id=...` — Get message history

### Legacy APIs (backward compatible with your existing website)
- `POST /chat` — Chat (uses client_id parameter)
- `GET /messages` — Get messages
- `GET /widget-config` — Get widget config

### Client Admin APIs (authenticated by X-Admin-Token)
- `POST /admin/login` / `POST /admin/logout`
- `GET /admin/stats` / `GET /admin/leads` / `GET /admin/conversations`
- `GET /admin/settings` / `POST /admin/settings`
- `GET /admin/knowledge` / `POST /admin/knowledge`
- All scoped to the logged-in client's data

### Super Admin APIs (requires superadmin role)
- `GET /superadmin/stats` — Platform-wide stats
- `GET /superadmin/clients` — List all clients
- `POST /superadmin/clients` — Create a new client
- `GET /superadmin/clients/{id}` — Client details
- `PATCH /superadmin/clients/{id}` — Update client
- `GET /superadmin/clients/{id}/embed-code` — Get embed snippet
- `POST /superadmin/clients/{id}/regenerate-key` — Regenerate API key

## What Changed vs. Original

| Component | Change |
|-----------|--------|
| Chatbot UI | **Zero changes** — identical widget |
| Chatbot logic | **Zero changes** — same AI engine |
| Admin panel | **Zero changes** to design/UX — added client_id scoping in backend |
| Backend APIs | Added client_id parameter to all queries |
| Database | Added `clients` table, `client_id` columns |
| New: Widget embed | `tm-chatbot.js` — self-contained, auth via API key |
| New: Super admin | Dashboard + Client management pages |
| New: Login routing | Routes superadmin → super admin panel, client → client panel |
