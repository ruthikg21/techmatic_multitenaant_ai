import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import os
import secrets
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables if .env exists
load_dotenv()

# Supabase Connection URL (Set via environment variable for security)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def get_db_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def generate_api_key():
    return "tm_" + secrets.token_hex(24)

def init_db():
    conn = get_conn()
    with conn.cursor() as c:
        # ── Clients table (multi-tenant) ──────────────────────────────────────────
        c.execute("""CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            admin_id TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'client',
            client_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )""")

        # ── AI config (per client) ────────────────────────────────────────────────
        c.execute("""CREATE TABLE IF NOT EXISTS ai_config (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL,
            api_key TEXT,
            model_name TEXT DEFAULT 'claude-3-5-sonnet-20240620',
            system_prompt TEXT,
            lead_questions_enabled INTEGER DEFAULT 1,
            qualification_questions TEXT,
            assistant_name TEXT DEFAULT 'AI Assistant',
            greeting TEXT,
            widget_color TEXT DEFAULT '#933a43',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )""")

        # ── Knowledge sources (per client) ────────────────────────────────────────
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_sources (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL DEFAULT 1,
            url TEXT NOT NULL,
            title TEXT,
            content TEXT,
            scraped_at TEXT,
            status TEXT DEFAULT 'pending',
            active INTEGER DEFAULT 1,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )""")

        # ── Leads (per client) ────────────────────────────────────────────────────
        c.execute("""CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL DEFAULT 1,
            session_id TEXT NOT NULL,
            name TEXT, email TEXT, phone TEXT,
            industry TEXT, business_type TEXT, problem TEXT, timeline TEXT,
            service_interest TEXT, conversation_summary TEXT,
            source TEXT DEFAULT 'web', status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )""")

        # ── Messages (per client) ─────────────────────────────────────────────────
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL DEFAULT 1,
            session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, source TEXT DEFAULT 'web',
            timestamp TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )""")

        # ── Seed super admin ──────────────────────────────────────────────────────
        c.execute("SELECT id FROM admin_users WHERE admin_id=%s", ('superadmin',))
        if not c.fetchone():
            c.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (%s,%s,%s,%s,%s)",
                      ('superadmin', hash_password('Techmatic@2024'), 'superadmin', None, datetime.utcnow().isoformat()))

        # ── Seed default client (Techmatic Systems itself) ────────────────────────
        c.execute("SELECT id FROM clients WHERE client_slug=%s", ('techmatic',))
        if not c.fetchone():
            now = datetime.utcnow().isoformat()
            api_key = generate_api_key()
            c.execute("""INSERT INTO clients (client_name, client_slug, widget_api_key, domain, is_active, created_at, updated_at)
                         VALUES (%s,%s,%s,%s,1,%s,%s) RETURNING id""",
                      ('Techmatic Systems', 'techmatic', api_key, 'techmaticsys.com', now, now))
            client_id = c.fetchone()[0]

            # Seed client admin
            c.execute("SELECT id FROM admin_users WHERE admin_id=%s", ('admin',))
            if not c.fetchone():
                c.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (%s,%s,%s,%s,%s)",
                          ('admin', hash_password('techmatic2024'), 'client', client_id, now))

            # Seed config for default client
            c.execute("SELECT id FROM ai_config WHERE client_id=%s", (client_id,))
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
                            assistant_name, greeting, widget_color, updated_at) VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s)""",
                          (client_id, 'claude-3-5-sonnet-20240620', default_prompt, default_questions,
                           'Techmatic AI Assistant',
                           "👋 Hello! I'm the Techmatic AI Assistant. Ask me anything about our services, or let me help you find the right solution!",
                           '#933a43', now))

            # Seed knowledge sources for default client
            c.execute("SELECT id FROM knowledge_sources WHERE client_id=%s LIMIT 1", (client_id,))
            if not c.fetchone():
                for url in [
                    "https://www.techmaticsys.com/",
                    "https://www.techmaticsys.com/services",
                    "https://www.techmaticsys.com/about",
                ]:
                    c.execute("INSERT INTO knowledge_sources (client_id, url, status, active) VALUES (%s,%s,%s,1)", (client_id, url, 'pending'))

    conn.commit()
    conn.close()
    print("✅ DB ready (multi-tenant).")


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

def verify_admin(admin_id, password):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id, role, client_id FROM admin_users WHERE admin_id=%s AND password_hash=%s",
                  (admin_id, hash_password(password)))
        row = c.fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "admin_id": admin_id, "role": row["role"], "client_id": row["client_id"]}
    return None

def update_admin_password(admin_id, new_password):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("UPDATE admin_users SET password_hash=%s WHERE admin_id=%s",
                     (hash_password(new_password), admin_id))
    conn.commit()
    conn.close()

def get_admin_info(admin_id):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id, admin_id, role, client_id FROM admin_users WHERE admin_id=%s", (admin_id,))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT MANAGEMENT (Super Admin)
# ══════════════════════════════════════════════════════════════════════════════

def create_client(client_name, client_slug, domain=None):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    api_key = generate_api_key()
    with conn.cursor() as c:
        c.execute("""INSERT INTO clients (client_name, client_slug, widget_api_key, domain, is_active, created_at, updated_at)
                     VALUES (%s,%s,%s,%s,1,%s,%s) RETURNING id""",
                  (client_name, client_slug, api_key, domain, now, now))
        client_id = c.fetchone()[0]

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
                    VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s)""",
                  (client_id, 'claude-3-5-sonnet-20240620', default_prompt, default_questions,
                   f'{client_name} AI',
                   f"👋 Hello! I'm the {client_name} AI Assistant. How can I help you today?",
                   '#933a43', now))

    conn.commit()
    conn.close()
    return {"client_id": client_id, "widget_api_key": api_key}

def create_client_admin(admin_id, password, client_id):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    with conn.cursor() as c:
        c.execute("INSERT INTO admin_users (admin_id, password_hash, role, client_id, created_at) VALUES (%s,%s,%s,%s,%s)",
                     (admin_id, hash_password(password), 'client', client_id, now))
    conn.commit()
    conn.close()

def get_all_clients():
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM leads WHERE client_id=c.id) as lead_count,
                   (SELECT COUNT(*) FROM messages WHERE client_id=c.id) as message_count,
                   (SELECT COUNT(DISTINCT session_id) FROM messages WHERE client_id=c.id) as session_count
            FROM clients c ORDER BY c.created_at DESC
        """)
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_client_by_id(client_id):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM clients WHERE id=%s", (client_id,))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_client_by_api_key(api_key):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM clients WHERE widget_api_key=%s AND is_active=1", (api_key,))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_client_admins(client_id):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id, admin_id, role, created_at FROM admin_users WHERE client_id=%s", (client_id,))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_client(client_id, **kwargs):
    conn = get_conn()
    kwargs['updated_at'] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=%s" for k in kwargs)
    with conn.cursor() as c:
        c.execute(f"UPDATE clients SET {cols} WHERE id=%s", list(kwargs.values()) + [client_id])
    conn.commit()
    conn.close()

def toggle_client_active(client_id, is_active):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("UPDATE clients SET is_active=%s, updated_at=%s WHERE id=%s",
                     (1 if is_active else 0, datetime.utcnow().isoformat(), client_id))
    conn.commit()
    conn.close()

def regenerate_client_api_key(client_id):
    conn = get_conn()
    new_key = generate_api_key()
    with conn.cursor() as c:
        c.execute("UPDATE clients SET widget_api_key=%s, updated_at=%s WHERE id=%s",
                     (new_key, datetime.utcnow().isoformat(), client_id))
    conn.commit()
    conn.close()
    return new_key


# ══════════════════════════════════════════════════════════════════════════════
# AI CONFIG (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_config(client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM ai_config WHERE client_id=%s ORDER BY id DESC LIMIT 1", (client_id,))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_config(client_id=1, **kwargs):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id FROM ai_config WHERE client_id=%s", (client_id,))
        existing = c.fetchone()
        if existing:
            cols = ", ".join(f"{k}=%s" for k in kwargs)
            c.execute(f"UPDATE ai_config SET {cols}, updated_at=%s WHERE client_id=%s",
                         list(kwargs.values()) + [now, client_id])
        else:
            kwargs['client_id'] = client_id
            kwargs['updated_at'] = now
            cols = ", ".join(kwargs.keys()); ph = ", ".join("%s" for _ in kwargs)
            c.execute(f"INSERT INTO ai_config ({cols}) VALUES ({ph})", list(kwargs.values()))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGES (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def save_message(session_id, role, content, source='web', client_id=1):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("INSERT INTO messages (client_id, session_id, role, content, source, timestamp) VALUES (%s,%s,%s,%s,%s,%s)",
                     (client_id, session_id, role, content, source, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def get_session_messages(session_id, limit=40, client_id=None):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        if client_id:
            c.execute("SELECT * FROM messages WHERE session_id=%s AND client_id=%s ORDER BY id ASC LIMIT %s",
                                (session_id, client_id, limit))
        else:
            c.execute("SELECT * FROM messages WHERE session_id=%s ORDER BY id ASC LIMIT %s",
                                (session_id, limit))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_messages(limit=300, client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM messages WHERE client_id=%s ORDER BY id DESC LIMIT %s", (client_id, limit))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_sessions(client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("""
            SELECT session_id, COUNT(*) as msg_count,
                   MIN(timestamp) as first_msg, MAX(timestamp) as last_msg,
                   MAX(CASE WHEN role='user' THEN content END) as last_user_msg
            FROM messages WHERE client_id=%s GROUP BY session_id ORDER BY last_msg DESC
        """, (client_id,))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# LEADS (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def upsert_lead(session_id, client_id=1, **kwargs):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id FROM leads WHERE session_id=%s AND client_id=%s", (session_id, client_id))
        existing = c.fetchone()
        if existing:
            cols = ", ".join(f"{k}=%s" for k in kwargs)
            c.execute(f"UPDATE leads SET {cols}, updated_at=%s WHERE session_id=%s AND client_id=%s",
                         list(kwargs.values()) + [now, session_id, client_id])
        else:
            kwargs['session_id'] = session_id
            kwargs['client_id'] = client_id
            kwargs['created_at'] = now; kwargs['updated_at'] = now
            cols = ", ".join(kwargs.keys()); ph = ", ".join("%s" for _ in kwargs)
            c.execute(f"INSERT INTO leads ({cols}) VALUES ({ph})", list(kwargs.values()))
    conn.commit(); conn.close()

def get_all_leads(limit=200, client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM leads WHERE client_id=%s ORDER BY created_at DESC LIMIT %s", (client_id, limit))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_lead_status(lead_id, status, client_id=1):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("UPDATE leads SET status=%s, updated_at=%s WHERE id=%s AND client_id=%s",
                     (status, datetime.utcnow().isoformat(), lead_id, client_id))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_knowledge(client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT * FROM knowledge_sources WHERE client_id=%s AND active=1 ORDER BY id ASC", (client_id,))
        rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_knowledge_content(source_id, title, content, client_id=1):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("UPDATE knowledge_sources SET title=%s, content=%s, scraped_at=%s, status='scraped' WHERE id=%s AND client_id=%s",
                     (title, content, datetime.utcnow().isoformat(), source_id, client_id))
    conn.commit(); conn.close()

def add_knowledge_url(url, client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        c.execute("SELECT id FROM knowledge_sources WHERE url=%s AND client_id=%s", (url, client_id))
        existing = c.fetchone()
        if not existing:
            c.execute("INSERT INTO knowledge_sources (client_id, url, status, active) VALUES (%s,%s,'pending',1)", (client_id, url))
    conn.commit()
    conn.close()

def delete_knowledge(source_id, client_id=1):
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("UPDATE knowledge_sources SET active=0 WHERE id=%s AND client_id=%s", (source_id, client_id))
    conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# STATS (scoped by client_id)
# ══════════════════════════════════════════════════════════════════════════════

def get_stats(client_id=1):
    conn = get_conn()
    with get_db_cursor(conn) as c:
        def scalar(sql, params=()):
            c.execute(sql, params)
            r = c.fetchone()
            return list(r.values())[0] if r else 0
        s = {
            "total_leads": scalar("SELECT COUNT(*) FROM leads WHERE client_id=%s", (client_id,)),
            "new_leads": scalar("SELECT COUNT(*) FROM leads WHERE client_id=%s AND status='new'", (client_id,)),
            "total_messages": scalar("SELECT COUNT(*) FROM messages WHERE client_id=%s", (client_id,)),
            "messages_today": scalar("SELECT COUNT(*) FROM messages WHERE client_id=%s AND timestamp::date = CURRENT_DATE", (client_id,)),
            "sessions": scalar("SELECT COUNT(DISTINCT session_id) FROM messages WHERE client_id=%s", (client_id,)),
            "kb_sources": scalar("SELECT COUNT(*) FROM knowledge_sources WHERE client_id=%s AND active=1", (client_id,)),
            "kb_scraped": scalar("SELECT COUNT(*) FROM knowledge_sources WHERE client_id=%s AND active=1 AND status='scraped'", (client_id,)),
        }
    conn.close()
    return s

def get_global_stats():
    """Stats across all clients — for super admin dashboard."""
    conn = get_conn()
    with get_db_cursor(conn) as c:
        def scalar(sql):
            c.execute(sql)
            r = c.fetchone()
            return list(r.values())[0] if r else 0
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
