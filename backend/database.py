import sqlite3
import hashlib
import os
import secrets
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "techmatic.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def generate_api_key():
    return "tm_" + secrets.token_hex(24)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── Clients table (multi-tenant) ──────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT NOT NULL,
        client_slug TEXT UNIQUE NOT NULL,
        widget_api_key TEXT UNIQUE NOT NULL,
        domain TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")

    # ── Admin users (now with client_id + role) ───────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'client',
        client_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── AI config (per client) ────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS ai_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        api_key TEXT,
        model_name TEXT DEFAULT 'claude-4-6-sonnet-20260215',
        system_prompt TEXT,
        lead_questions_enabled INTEGER DEFAULT 1,
        qualification_questions TEXT,
        assistant_name TEXT DEFAULT 'AI Assistant',
        greeting TEXT,
        widget_color TEXT DEFAULT '#933a43',
        updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── Knowledge sources (per client) ────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS knowledge_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL DEFAULT 1,
        url TEXT NOT NULL,
        title TEXT,
        content TEXT,
        scraped_at TEXT,
        status TEXT DEFAULT 'pending',
        active INTEGER DEFAULT 1,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── Leads (per client) ────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL DEFAULT 1,
        session_id TEXT NOT NULL,
        name TEXT, email TEXT, phone TEXT,
        industry TEXT, business_type TEXT, problem TEXT, timeline TEXT,
        service_interest TEXT, conversation_summary TEXT,
        source TEXT DEFAULT 'web', status TEXT DEFAULT 'new',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── Messages (per client) ─────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL DEFAULT 1,
        session_id TEXT NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, source TEXT DEFAULT 'web',
        timestamp TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── WhatsApp config (per client — Twilio) ─────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS whatsapp_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL UNIQUE,
        enabled INTEGER DEFAULT 0,
        twilio_account_sid TEXT,
        twilio_auth_token TEXT,
        twilio_whatsapp_number TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    # ── Seed super admin ──────────────────────────────────────────────────────
    c.execute("SELECT id FROM admin_users WHERE admin_id='superadmin'")
    if not c.fetchone():
        c.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (?,?,?,?,?)",
                  ('superadmin', hash_password('Techmatic@2024'), 'superadmin', None, datetime.utcnow().isoformat()))

    # ── Seed default client (Techmatic Systems itself) ────────────────────────
    c.execute("SELECT id FROM clients WHERE client_slug='techmatic'")
    if not c.fetchone():
        now = datetime.utcnow().isoformat()
        api_key = generate_api_key()
        c.execute("""INSERT INTO clients (client_name, client_slug, widget_api_key, domain, is_active, created_at, updated_at)
                     VALUES (?,?,?,?,1,?,?)""",
                  ('Techmatic Systems', 'techmatic', api_key, 'techmaticsys.com', now, now))
        client_id = c.lastrowid

        # Seed client admin
        c.execute("SELECT id FROM admin_users WHERE admin_id='admin'")
        if not c.fetchone():
            c.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (?,?,?,?,?)",
                      ('admin', hash_password('techmatic2024'), 'client', client_id, now))

        # Seed config for default client
        c.execute("SELECT id FROM ai_config WHERE client_id=?", (client_id,))
        if not c.fetchone():
            default_questions = "\n".join([
                "What service are you interested in?",
                "What industry are you in?",
                "What type of business do you run?",
                "What problem are you trying to solve?",
                "What timeline do you have for implementing a solution?",
                "Have you used similar solutions before?",
            ])
            default_prompt = """You are an AI assistant for Techmatic Systems, an IT consulting and technology services company.

Your goals:
1. Answer questions about Techmatic's services accurately
2. Qualify potential clients through natural conversation
3. Collect contact information when interest is shown

Techmatic Systems services include:
- Digital Transformation & Cloud Services
- Data Analytics & Business Intelligence
- AI & ML Integration
- ERP Solutions (Odoo, Acumatica)
- Custom E-commerce Development
- Quality Engineering & Testing
- Data Solutions & Snowflake
- IT Consulting

Always be professional, helpful, and concise. Ask one qualification question at a time naturally. When you have collected name, email, and service interest, summarize and offer to connect them with the team."""

            c.execute("""INSERT INTO ai_config (client_id, model_name, system_prompt, lead_questions_enabled, qualification_questions,
                        assistant_name, greeting, widget_color, updated_at) VALUES (?,?,?,1,?,?,?,?,?)""",
                      (client_id, 'claude-4-6-sonnet-20260215', default_prompt, default_questions,
                       'Techmatic AI Assistant',
                       "👋 Hello! I'm the Techmatic AI Assistant. Ask me anything about our services, or let me help you find the right solution!",
                       '#933a43', now))

        # Seed knowledge sources for default client
        c.execute("SELECT id FROM knowledge_sources WHERE client_id=? LIMIT 1", (client_id,))
        if not c.fetchone():
            for url in [
                "https://www.techmaticsys.com/",
                "https://www.techmaticsys.com/services",
                "https://www.techmaticsys.com/about",
            ]:
                c.execute("INSERT INTO knowledge_sources (client_id, url, status, active) VALUES (?,?,?,1)", (client_id, url, 'pending'))

    conn.commit()
    conn.close()
    print("✅ DB ready (multi-tenant).")


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

def verify_admin(admin_id, password):
    conn = get_conn()
    row = conn.execute("SELECT id, role, client_id FROM admin_users WHERE admin_id=? AND password_hash=?",
                       (admin_id, hash_password(password))).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "admin_id": admin_id, "role": row["role"], "client_id": row["client_id"]}
    return None

def update_admin_password(admin_id, new_password):
    conn = get_conn()
    conn.execute("UPDATE admin_users SET password_hash=? WHERE admin_id=?",
                 (hash_password(new_password), admin_id))
    conn.commit()
    conn.close()

def get_admin_info(admin_id):
    conn = get_conn()
    row = conn.execute("SELECT id, admin_id, role, client_id FROM admin_users WHERE admin_id=?", (admin_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT MANAGEMENT (Super Admin)
# ══════════════════════════════════════════════════════════════════════════════

def create_client(client_name, client_slug, domain=None):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    api_key = generate_api_key()
    c = conn.cursor()
    c.execute("""INSERT INTO clients (client_name, client_slug, widget_api_key, domain, is_active, created_at, updated_at)
                 VALUES (?,?,?,?,1,?,?)""",
              (client_name, client_slug, api_key, domain, now, now))
    client_id = c.lastrowid

    # Create default config for client
    default_prompt = f"""You are an AI assistant for {client_name}. Be professional, helpful, and concise.
Your goals:
1. Answer questions about the company accurately
2. Qualify potential clients through natural conversation
3. Collect contact information when interest is shown"""

    default_questions = "\n".join([
        "What service are you interested in?",
        "What industry are you in?",
        "What problem are you trying to solve?",
    ])

    c.execute("""INSERT INTO ai_config (client_id, model_name, system_prompt, lead_questions_enabled,
                qualification_questions, assistant_name, greeting, widget_color, updated_at)
                VALUES (?,?,?,1,?,?,?,?,?)""",
              (client_id, 'claude-4-6-sonnet-20260215', default_prompt, default_questions,
               f'{client_name} AI',
               f"👋 Hello! I'm the {client_name} AI Assistant. How can I help you today?",
               '#933a43', now))

    conn.commit()
    conn.close()
    return {"client_id": client_id, "widget_api_key": api_key}

def create_client_admin(admin_id, password, client_id):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (?,?,?,?,?)",
                 (admin_id, hash_password(password), 'client', client_id, now))
    conn.commit()
    conn.close()

def get_all_clients():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM leads WHERE client_id=c.id) as lead_count,
               (SELECT COUNT(*) FROM messages WHERE client_id=c.id) as message_count,
               (SELECT COUNT(DISTINCT session_id) FROM messages WHERE client_id=c.id) as session_count
        FROM clients c ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_client_by_id(client_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_client_by_api_key(api_key):
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE widget_api_key=? AND is_active=1", (api_key,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_client_admins(client_id):
    conn = get_conn()
    rows = conn.execute("SELECT id, admin_id, role, created_at FROM admin_users WHERE client_id=?", (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_client(client_id, **kwargs):
    conn = get_conn()
    kwargs['updated_at'] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE clients SET {cols} WHERE id=?", list(kwargs.values()) + [client_id])
    conn.commit()
    conn.close()

def toggle_client_active(client_id, is_active):
    conn = get_conn()
    conn.execute("UPDATE clients SET is_active=?, updated_at=? WHERE id=?",
                 (1 if is_active else 0, datetime.utcnow().isoformat(), client_id))
    conn.commit()
    conn.close()

def regenerate_client_api_key(client_id):
    conn = get_conn()
    new_key = generate_api_key()
    conn.execute("UPDATE clients SET widget_api_key=?, updated_at=? WHERE id=?",
                 (new_key, datetime.utcnow().isoformat(), client_id))
    conn.commit()
    conn.close()
    return new_key


# ══════════════════════════════════════════════════════════════════════════════
# AI CONFIG (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_config(client_id=1):
    conn = get_conn()
    row = conn.execute("SELECT * FROM ai_config WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_config(client_id=1, **kwargs):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM ai_config WHERE client_id=?", (client_id,)).fetchone()
    if existing:
        cols = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE ai_config SET {cols}, updated_at=? WHERE client_id=?",
                     list(kwargs.values()) + [now, client_id])
    else:
        kwargs['client_id'] = client_id
        kwargs['updated_at'] = now
        cols = ", ".join(kwargs.keys()); ph = ", ".join("?" * len(kwargs))
        conn.execute(f"INSERT INTO ai_config ({cols}) VALUES ({ph})", list(kwargs.values()))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGES (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def save_message(session_id, role, content, source='web', client_id=1):
    conn = get_conn()
    conn.execute("INSERT INTO messages (client_id, session_id, role, content, source, timestamp) VALUES (?,?,?,?,?,?)",
                 (client_id, session_id, role, content, source, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def get_session_messages(session_id, limit=40, client_id=None):
    conn = get_conn()
    if client_id:
        rows = conn.execute("SELECT * FROM messages WHERE session_id=? AND client_id=? ORDER BY id ASC LIMIT ?",
                            (session_id, client_id, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
                            (session_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_messages(limit=300, client_id=1):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM messages WHERE client_id=? ORDER BY id DESC LIMIT ?", (client_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_sessions(client_id=1):
    conn = get_conn()
    rows = conn.execute("""
        SELECT session_id, COUNT(*) as msg_count,
               MIN(timestamp) as first_msg, MAX(timestamp) as last_msg,
               MAX(CASE WHEN role='user' THEN content END) as last_user_msg
        FROM messages WHERE client_id=? GROUP BY session_id ORDER BY last_msg DESC
    """, (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# LEADS (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def upsert_lead(session_id, client_id=1, **kwargs):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM leads WHERE session_id=? AND client_id=?", (session_id, client_id)).fetchone()
    if existing:
        cols = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE leads SET {cols}, updated_at=? WHERE session_id=? AND client_id=?",
                     list(kwargs.values()) + [now, session_id, client_id])
    else:
        kwargs['session_id'] = session_id
        kwargs['client_id'] = client_id
        kwargs['created_at'] = now; kwargs['updated_at'] = now
        cols = ", ".join(kwargs.keys()); ph = ", ".join("?" * len(kwargs))
        conn.execute(f"INSERT INTO leads ({cols}) VALUES ({ph})", list(kwargs.values()))
    conn.commit(); conn.close()

def get_all_leads(limit=200, client_id=1):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM leads WHERE client_id=? ORDER BY created_at DESC LIMIT ?", (client_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_lead_status(lead_id, status, client_id=1):
    conn = get_conn()
    conn.execute("UPDATE leads SET status=?, updated_at=? WHERE id=? AND client_id=?",
                 (status, datetime.utcnow().isoformat(), lead_id, client_id))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_knowledge(client_id=1):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM knowledge_sources WHERE client_id=? AND active=1 ORDER BY id ASC", (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_knowledge_content(source_id, title, content, client_id=1):
    conn = get_conn()
    conn.execute("UPDATE knowledge_sources SET title=?, content=?, scraped_at=?, status='scraped' WHERE id=? AND client_id=?",
                 (title, content, datetime.utcnow().isoformat(), source_id, client_id))
    conn.commit(); conn.close()

def add_knowledge_url(url, client_id=1):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM knowledge_sources WHERE url=? AND client_id=?", (url, client_id)).fetchone()
    if not existing:
        conn.execute("INSERT INTO knowledge_sources (client_id, url, status, active) VALUES (?,?,'pending',1)", (client_id, url))
        conn.commit()
    conn.close()

def delete_knowledge(source_id, client_id=1):
    conn = get_conn()
    conn.execute("UPDATE knowledge_sources SET active=0 WHERE id=? AND client_id=?", (source_id, client_id))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# STATS (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_stats(client_id=1):
    conn = get_conn()
    def scalar(sql, params=()): r = conn.execute(sql, params).fetchone(); return list(r)[0] if r else 0
    s = {
        "total_leads": scalar("SELECT COUNT(*) FROM leads WHERE client_id=?", (client_id,)),
        "new_leads": scalar("SELECT COUNT(*) FROM leads WHERE client_id=? AND status='new'", (client_id,)),
        "total_messages": scalar("SELECT COUNT(*) FROM messages WHERE client_id=?", (client_id,)),
        "messages_today": scalar("SELECT COUNT(*) FROM messages WHERE client_id=? AND DATE(timestamp)=DATE('now')", (client_id,)),
        "sessions": scalar("SELECT COUNT(DISTINCT session_id) FROM messages WHERE client_id=?", (client_id,)),
        "kb_sources": scalar("SELECT COUNT(*) FROM knowledge_sources WHERE client_id=? AND active=1", (client_id,)),
        "kb_scraped": scalar("SELECT COUNT(*) FROM knowledge_sources WHERE client_id=? AND active=1 AND status='scraped'", (client_id,)),
    }
    conn.close()
    return s

def get_global_stats():
    """Stats across all clients — for super admin dashboard."""
    conn = get_conn()
    def scalar(sql): r = conn.execute(sql).fetchone(); return list(r)[0] if r else 0
    s = {
        "total_clients": scalar("SELECT COUNT(*) FROM clients"),
        "active_clients": scalar("SELECT COUNT(*) FROM clients WHERE is_active=1"),
        "total_leads": scalar("SELECT COUNT(*) FROM leads"),
        "total_messages": scalar("SELECT COUNT(*) FROM messages"),
        "total_sessions": scalar("SELECT COUNT(DISTINCT session_id) FROM messages"),
        "total_admins": scalar("SELECT COUNT(*) FROM admin_users WHERE role='client'"),
    }
    conn.close()
    return s


# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP CONFIG (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_whatsapp_config(client_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM whatsapp_config WHERE client_id=?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_whatsapp_config(client_id, **kwargs):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM whatsapp_config WHERE client_id=?", (client_id,)).fetchone()
    if existing:
        cols = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE whatsapp_config SET {cols}, updated_at=? WHERE client_id=?",
                     list(kwargs.values()) + [now, client_id])
    else:
        kwargs['client_id'] = client_id
        kwargs['created_at'] = now
        kwargs['updated_at'] = now
        cols = ", ".join(kwargs.keys())
        ph = ", ".join("?" * len(kwargs))
        conn.execute(f"INSERT INTO whatsapp_config ({cols}) VALUES ({ph})", list(kwargs.values()))
    conn.commit()
    conn.close()

def get_whatsapp_config_by_number(whatsapp_number):
    """Look up WhatsApp config by Twilio WhatsApp number (for incoming webhook)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT wc.*, c.is_active as client_active FROM whatsapp_config wc JOIN clients c ON c.id=wc.client_id WHERE wc.twilio_whatsapp_number=? AND wc.enabled=1",
        (whatsapp_number,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_whatsapp_sessions(client_id):
    """Get all WhatsApp sessions for a client."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT session_id, COUNT(*) as msg_count,
               MIN(timestamp) as first_msg, MAX(timestamp) as last_msg,
               MAX(CASE WHEN role='user' THEN content END) as last_user_msg
        FROM messages WHERE client_id=? AND source='whatsapp'
        GROUP BY session_id ORDER BY last_msg DESC
    """, (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
