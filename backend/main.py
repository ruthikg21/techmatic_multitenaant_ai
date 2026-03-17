from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import secrets
import uuid
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

from database import (
    init_db, verify_admin, update_admin_password, get_admin_info,
    get_config, save_config, get_knowledge, save_knowledge_content,
    add_knowledge_url, delete_knowledge, get_all_leads, update_lead_status,
    get_all_messages, get_session_messages, get_all_sessions, get_stats,
    upsert_lead, get_global_stats,
    # Client management
    create_client, create_client_admin, get_all_clients, get_client_by_id,
    get_client_by_api_key, get_client_admins, update_client,
    toggle_client_active, regenerate_client_api_key,
    # WhatsApp
    get_whatsapp_config, save_whatsapp_config, get_whatsapp_config_by_phone_number_id,
    get_whatsapp_sessions, get_all_whatsapp_configs_enabled
)
from ai_engine import handle_incoming_message
from scraper import scrape_url

from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Techmatic AI Platform", version="2.0.0")

# Mount static files from the root directory
app.mount("/static", StaticFiles(directory="../"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()


# ══════════════════════════════════════════════════════════════════════════════
# SESSION / AUTH
# ══════════════════════════════════════════════════════════════════════════════

# In-memory session store: token → {admin_id, role, client_id}
_sessions = {}

def create_token(admin_info):
    token = secrets.token_hex(32)
    _sessions[token] = admin_info  # {admin_id, role, client_id}
    return token

def get_admin(request: Request):
    """Returns admin session dict: {admin_id, role, client_id}"""
    token = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _sessions[token]

def require_superadmin(request: Request):
    admin = get_admin(request)
    if admin.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return admin

def get_client_id_for_admin(admin):
    """Get client_id from admin session. Super admins must pass client_id explicitly."""
    return admin.get("client_id")


# ══════════════════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════════════════

class ChatReq(BaseModel):
    message: str
    session_id: Optional[str] = None
    source: Optional[str] = "web"
    client_id: Optional[int] = 1

class WidgetChatReq(BaseModel):
    message: str
    session_id: Optional[str] = None
    source: Optional[str] = "web"
    api_key: str

class LoginReq(BaseModel):
    admin_id: str
    password: str

class ConfigReq(BaseModel):
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    system_prompt: Optional[str] = None
    lead_questions_enabled: Optional[bool] = None
    qualification_questions: Optional[str] = None
    assistant_name: Optional[str] = None
    greeting: Optional[str] = None

class KnowledgeReq(BaseModel):
    url: str

class LeadStatusReq(BaseModel):
    status: str

class ChangePasswordReq(BaseModel):
    current_password: str
    new_password: str

class CreateClientReq(BaseModel):
    client_name: str
    client_slug: str
    domain: Optional[str] = None
    admin_id: str
    admin_password: str

class UpdateClientReq(BaseModel):
    client_name: Optional[str] = None
    domain: Optional[str] = None
    is_active: Optional[bool] = None

class WhatsAppConfigReq(BaseModel):
    enabled: Optional[bool] = None
    meta_phone_number_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    meta_waba_id: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/login")
async def login(req: LoginReq):
    admin_info = verify_admin(req.admin_id, req.password)
    if not admin_info:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(admin_info)
    return {
        "token": token,
        "admin_id": admin_info["admin_id"],
        "role": admin_info["role"],
        "client_id": admin_info["client_id"]
    }

@app.post("/admin/logout")
async def logout(request: Request):
    token = request.headers.get("X-Admin-Token") or ""
    _sessions.pop(token, None)
    return {"status": "ok"}

@app.post("/admin/change-password")
async def change_password(req: ChangePasswordReq, request: Request):
    admin = get_admin(request)
    admin_id = admin["admin_id"]
    result = verify_admin(admin_id, req.current_password)
    if not result:
        raise HTTPException(status_code=401, detail="Current password incorrect")
    update_admin_password(admin_id, req.new_password)
    return {"status": "ok"}

@app.get("/admin/me")
async def me(request: Request):
    admin = get_admin(request)
    return {"admin_id": admin["admin_id"], "role": admin["role"], "client_id": admin["client_id"]}


# ══════════════════════════════════════════════════════════════════════════════
# WIDGET PUBLIC ROUTES (authenticated by widget API key)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/widget/chat")
async def widget_chat(req: WidgetChatReq):
    """Chat endpoint for embedded widgets — authenticated by widget API key."""
    client = get_client_by_api_key(req.api_key)
    if not client:
        raise HTTPException(status_code=403, detail="Invalid widget API key")
    session_id = req.session_id or str(uuid.uuid4())
    reply = await handle_incoming_message(req.source, req.message, session_id, client["id"])
    return {"reply": reply, "session_id": session_id}

@app.get("/widget/config")
async def widget_config(api_key: str):
    """Get widget config (greeting, colors, name) — public route for embedded widgets."""
    client = get_client_by_api_key(api_key)
    if not client:
        raise HTTPException(status_code=403, detail="Invalid widget API key")
    config = get_config(client["id"]) or {}
    return {
        "greeting": config.get("greeting", "Hello! How can I help you?"),
        "assistant_name": config.get("assistant_name", "AI Assistant"),
        "widget_color": config.get("widget_color", "#933a43"),
        "client_name": client["client_name"],
    }

@app.get("/widget/messages")
async def widget_messages(api_key: str, session_id: str):
    """Get message history for a widget session."""
    client = get_client_by_api_key(api_key)
    if not client:
        raise HTTPException(status_code=403, detail="Invalid widget API key")
    return {"messages": get_session_messages(session_id, 50, client["id"])}


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY CHAT ROUTES (backwards compatible — for your local Techmatic website)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
async def chat(req: ChatReq):
    session_id = req.session_id or str(uuid.uuid4())
    reply = await handle_incoming_message(req.source, req.message, session_id, req.client_id or 1)
    return {"reply": reply, "session_id": session_id}

@app.get("/messages")
async def get_messages_route(session_id: Optional[str] = None, client_id: int = 1, limit: int = 50):
    if session_id:
        return {"messages": get_session_messages(session_id, limit, client_id)}
    return {"messages": get_all_messages(limit, client_id)}

@app.get("/widget-config")
async def legacy_widget_config(client_id: int = 1):
    config = get_config(client_id) or {}
    return {
        "greeting": config.get("greeting", "Hello! How can I help you?"),
        "assistant_name": config.get("assistant_name", "AI Assistant"),
        "widget_color": config.get("widget_color", "#933a43"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — STATS (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/stats")
async def stats(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context. Use super admin routes.")
    return get_stats(cid)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — LEADS (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/leads")
async def leads(request: Request, limit: int = 200):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"leads": get_all_leads(limit, cid)}

@app.patch("/admin/leads/{lead_id}")
async def patch_lead(lead_id: int, body: LeadStatusReq, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    update_lead_status(lead_id, body.status, cid)
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — CONVERSATIONS (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/conversations")
async def conversations(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"sessions": get_all_sessions(cid)}

@app.get("/admin/conversations/{session_id}")
async def conversation(session_id: str, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"messages": get_session_messages(session_id, 100, cid)}


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — SETTINGS (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/settings")
async def get_settings(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    config = get_config(cid) or {}
    if config.get('api_key'):
        k = config['api_key']
        config['api_key_masked'] = k[:8] + '••••••••' + k[-4:] if len(k) > 12 else '••••••••'
        config['has_key'] = True
    else:
        config['api_key_masked'] = ''
        config['has_key'] = False
    config.pop('api_key', None)
    return config

@app.post("/admin/settings")
async def post_settings(req: ConfigReq, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    updates = {}
    # Restricted for clients: model_name and api_key are now superadmin only
    # if req.api_key and req.api_key.strip():
    #     updates['api_key'] = req.api_key.strip()
    # if req.model_name: updates['model_name'] = req.model_name
    
    if req.system_prompt is not None: updates['system_prompt'] = req.system_prompt
    if req.lead_questions_enabled is not None:
        updates['lead_questions_enabled'] = 1 if req.lead_questions_enabled else 0
    if req.qualification_questions is not None: updates['qualification_questions'] = req.qualification_questions
    if req.assistant_name: updates['assistant_name'] = req.assistant_name
    if req.greeting is not None: updates['greeting'] = req.greeting
    if updates:
        save_config(cid, **updates)
    return {"status": "ok"}

@app.post("/admin/test-ai")
async def test_ai(request: Request):
    # Testing also restricted to super admin context or handled via superadmin panel
    raise HTTPException(status_code=403, detail="AI connectivity testing is now restricted to super administrators.")
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    config = get_config(cid)
    if not config or not config.get('api_key'):
        raise HTTPException(status_code=400, detail="No API key configured.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config['api_key'])
        resp = client.messages.create(
            model='claude-3-haiku-20240307',
            max_tokens=50,
            messages=[{"role": "user", "content": "Reply with exactly: AI Connected!"}]
        )
        return {"status": "success", "message": resp.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — KNOWLEDGE BASE (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/knowledge")
async def knowledge(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"sources": get_knowledge(cid)}

@app.post("/admin/knowledge")
async def add_knowledge(req: KnowledgeReq, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    add_knowledge_url(req.url, cid)
    return {"status": "ok", "message": "URL added. Click Scrape to fetch content."}

@app.delete("/admin/knowledge/{source_id}")
async def del_knowledge(source_id: int, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    delete_knowledge(source_id, cid)
    return {"status": "ok"}

@app.post("/admin/knowledge/{source_id}/scrape")
async def scrape_one(source_id: int, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    sources = get_knowledge(cid)
    src = next((s for s in sources if s['id'] == source_id), None)
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")
    result = await scrape_url(src['url'])
    if result['success']:
        save_knowledge_content(source_id, result['title'], result['content'], cid)
        return {"status": "ok", "title": result['title'], "chars": len(result['content'])}
    else:
        raise HTTPException(status_code=500, detail=result.get('error', 'Scrape failed'))

@app.post("/admin/knowledge/scrape-all")
async def scrape_all(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    sources = get_knowledge(cid)
    results = []
    for s in sources:
        res = await scrape_url(s['url'])
        if res['success']:
            save_knowledge_content(s['id'], res['title'], res['content'], cid)
            results.append({"id": s['id'], "url": s['url'], "status": "ok", "chars": len(res['content'])})
        else:
            results.append({"id": s['id'], "url": s['url'], "status": "error", "error": res.get('error')})
    return {"results": results}


# ══════════════════════════════════════════════════════════════════════════════
# SUPER ADMIN — CLIENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/superadmin/stats")
async def superadmin_stats(request: Request):
    require_superadmin(request)
    return get_global_stats()

@app.get("/superadmin/clients")
async def list_clients(request: Request):
    require_superadmin(request)
    return {"clients": get_all_clients()}

@app.get("/superadmin/clients/{client_id}")
async def get_client(client_id: int, request: Request):
    require_superadmin(request)
    client = get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    admins = get_client_admins(client_id)
    config = get_config(client_id) or {}
    # Mask key for safety
    if config.get('api_key'):
        k = config['api_key']
        config['api_key_masked'] = k[:8] + '••••••••' + k[-4:] if len(k) > 12 else '••••••••'
    return {"client": client, "admins": admins, "config": config}

@app.post("/superadmin/clients/{client_id}/ai-config")
async def update_client_ai_config(client_id: int, req: ConfigReq, request: Request):
    require_superadmin(request)
    client = get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    updates = {}
    if req.api_key and req.api_key.strip():
        updates['api_key'] = req.api_key.strip()
    # Model selection removed as per request
    # if req.model_name: updates['model_name'] = req.model_name
    if req.system_prompt is not None: updates['system_prompt'] = req.system_prompt
    if req.assistant_name: updates['assistant_name'] = req.assistant_name
    if req.greeting is not None: updates['greeting'] = req.greeting
    
    if updates:
        save_config(client_id, **updates)
    return {"status": "ok"}

@app.post("/superadmin/clients/{client_id}/test-ai")
async def test_client_ai(client_id: int, request: Request):
    require_superadmin(request)
    config = get_config(client_id)
    if not config or not config.get('api_key'):
        raise HTTPException(status_code=400, detail="No API key configured for this client.")
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config['api_key'])
        # Hardcoded to valid model, bypassing DB config
        model = 'claude-3-haiku-20240307'
        resp = client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": "Reply with exactly: Techmatic AI Connected!"}]
        )
        return {"status": "success", "message": resp.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/superadmin/clients")
async def new_client(req: CreateClientReq, request: Request):
    require_superadmin(request)
    try:
        result = create_client(req.client_name, req.client_slug, req.domain)
        create_client_admin(req.admin_id, req.admin_password, result["client_id"])
        return {
            "status": "ok",
            "client_id": result["client_id"],
            "widget_api_key": result["widget_api_key"],
            "admin_id": req.admin_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.patch("/superadmin/clients/{client_id}")
async def patch_client(client_id: int, req: UpdateClientReq, request: Request):
    require_superadmin(request)
    updates = {}
    if req.client_name: updates["client_name"] = req.client_name
    if req.domain is not None: updates["domain"] = req.domain
    if req.is_active is not None:
        toggle_client_active(client_id, req.is_active)
    if updates:
        update_client(client_id, **updates)
    return {"status": "ok"}

@app.post("/superadmin/clients/{client_id}/regenerate-key")
async def regen_key(client_id: int, request: Request):
    require_superadmin(request)
    new_key = regenerate_client_api_key(client_id)
    return {"status": "ok", "widget_api_key": new_key}

@app.get("/superadmin/clients/{client_id}/embed-code")
async def get_embed_code(client_id: int, request: Request):
    """Return the HTML embed snippet the client should paste into their website."""
    require_superadmin(request)
    client = get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "https" in str(request.url) else "http"
    base_url = f"{scheme}://{host}"

    embed = f"""<!-- Techmatic AI Chatbot Widget -->
<script>
  window.TM_WIDGET_CONFIG = {{
    apiKey: "{client['widget_api_key']}",
    serverUrl: "{base_url}"
  }};
</script>
<script src="{base_url}/static/widget/tm-chatbot.js" defer></script>"""

    return {"embed_code": embed, "api_key": client["widget_api_key"]}


# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP — META CLOUD API WEBHOOK (public — receives incoming WhatsApp messages)
# ══════════════════════════════════════════════════════════════════════════════

from fastapi.responses import PlainTextResponse
import httpx

@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    Meta sends a GET request to verify the webhook URL.
    We must return the hub.challenge value if the verify token matches.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token and challenge:
        # Check if any client has this verify token
        all_configs = get_all_whatsapp_configs_enabled()
        for cfg in all_configs:
            if cfg.get("meta_verify_token") == token:
                print(f"[WhatsApp Webhook] Verification successful for client_id={cfg['client_id']}")
                return PlainTextResponse(content=challenge, status_code=200)
        print(f"[WhatsApp Webhook] Verification failed — token mismatch")
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    raise HTTPException(status_code=400, detail="Missing verification parameters")


import asyncio
import json as json_module

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Meta Cloud API sends incoming WhatsApp messages here.
    We parse the message, run the AI in the background, and reply via the Graph API.
    Must return 200 immediately — Meta times out after ~15s.
    """
    try:
        raw_body = await request.body()
        body = json_module.loads(raw_body)
        print(f"[WhatsApp Webhook] Received: {raw_body[:500]}")
    except Exception as ex:
        print(f"[WhatsApp Webhook] Failed to parse body: {ex}")
        return {"status": "ok"}

    # Meta webhook payload structure
    entry = body.get("entry", [])
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")

            # Skip status updates (delivered, read, etc.)
            if "statuses" in value and "messages" not in value:
                print(f"[WhatsApp] Status update, skipping")
                continue

            messages = value.get("messages", [])
            if not messages or not phone_number_id:
                print(f"[WhatsApp] No messages or no phone_number_id in payload")
                continue

            # Look up client config by phone number ID
            wa_config = get_whatsapp_config_by_phone_number_id(str(phone_number_id).strip())
            if not wa_config:
                # Try matching against all enabled configs
                print(f"[WhatsApp] No exact match for phone_number_id={phone_number_id}, trying all configs...")
                all_cfgs = get_all_whatsapp_configs_enabled()
                wa_config = None
                for cfg in all_cfgs:
                    stored = str(cfg.get("meta_phone_number_id", "")).strip()
                    if stored == str(phone_number_id).strip():
                        wa_config = cfg
                        break
                if not wa_config:
                    print(f"[WhatsApp] No config found for phone_number_id={phone_number_id}. Stored configs: {[c.get('meta_phone_number_id') for c in all_cfgs]}")
                    continue

            if not wa_config.get("client_active"):
                print(f"[WhatsApp] Client not active for phone_number_id={phone_number_id}")
                continue

            client_id = wa_config["client_id"]
            access_token = wa_config.get("meta_access_token")

            for msg in messages:
                msg_type = msg.get("type")
                from_number = msg.get("from", "")  # e.g. 919876543210

                # Only handle text messages for now
                if msg_type != "text":
                    print(f"[WhatsApp] Non-text message type: {msg_type}, skipping")
                    continue

                text = msg.get("text", {}).get("body", "").strip()
                if not text:
                    continue

                print(f"[WhatsApp] Incoming from={from_number} text={text[:80]}")

                session_id = f"wa_{from_number}"

                # Process in background so we return 200 immediately
                asyncio.ensure_future(
                    _process_wa_message(text, session_id, client_id, from_number, phone_number_id, access_token)
                )

    return {"status": "ok"}


async def _process_wa_message(text, session_id, client_id, from_number, phone_number_id, access_token):
    """Background task: run AI and send reply via Meta Graph API."""
    try:
        reply = await handle_incoming_message("whatsapp", text, session_id, client_id)
        print(f"[WhatsApp] AI reply for {from_number}: {reply[:80]}")
    except Exception as ex:
        print(f"[WhatsApp] AI error: {ex}")
        reply = "Sorry, something went wrong. Please try again."

    # Send reply via Meta Graph API
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.post(
                f"https://graph.facebook.com/v21.0/{phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": from_number,
                    "type": "text",
                    "text": {"body": reply},
                },
                timeout=30,
            )
            print(f"[WhatsApp] Send reply status={resp.status_code} body={resp.text[:200]}")
    except Exception as ex:
        print(f"[WhatsApp] Failed to send reply to {from_number}: {ex}")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — WHATSAPP CONFIG (scoped to client)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/whatsapp")
async def get_wa_settings(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    raw = get_whatsapp_config(cid)
    config = {
        "enabled": 0,
        "meta_phone_number_id": "",
        "meta_waba_id": "",
        "meta_verify_token": "",
        "has_token": False,
        "meta_access_token_masked": "",
    }
    if raw:
        config["enabled"] = raw.get("enabled", 0)
        config["meta_phone_number_id"] = raw.get("meta_phone_number_id") or ""
        config["meta_waba_id"] = raw.get("meta_waba_id") or ""
        config["meta_verify_token"] = raw.get("meta_verify_token") or ""
        if raw.get("meta_access_token"):
            t = raw["meta_access_token"]
            config["meta_access_token_masked"] = t[:8] + "••••••••" + t[-4:] if len(t) > 12 else "••••••••"
            config["has_token"] = True

    # Build webhook URL for display
    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if "https" in str(request.url) else "http"
    config["webhook_url"] = f"{scheme}://{host}/webhook/whatsapp"

    return config

@app.post("/admin/whatsapp")
async def post_wa_settings(req: WhatsAppConfigReq, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    updates = {}
    if req.enabled is not None:
        updates["enabled"] = 1 if req.enabled else 0
    if req.meta_phone_number_id is not None:
        updates["meta_phone_number_id"] = req.meta_phone_number_id.strip()
    if req.meta_access_token is not None and req.meta_access_token.strip():
        updates["meta_access_token"] = req.meta_access_token.strip()
    if req.meta_waba_id is not None:
        updates["meta_waba_id"] = req.meta_waba_id.strip()

    # Auto-generate verify token if none exists yet
    existing = get_whatsapp_config(cid)
    if not existing or not existing.get("meta_verify_token"):
        updates["meta_verify_token"] = f"tm_verify_{secrets.token_hex(16)}"

    if updates:
        save_whatsapp_config(cid, **updates)
    return {"status": "ok"}

@app.post("/admin/whatsapp/regenerate-verify-token")
async def regenerate_verify_token(request: Request):
    """Regenerate the webhook verify token."""
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    new_token = f"tm_verify_{secrets.token_hex(16)}"
    save_whatsapp_config(cid, meta_verify_token=new_token)
    return {"status": "ok", "meta_verify_token": new_token}

@app.post("/admin/whatsapp/test")
async def test_wa_connection(request: Request):
    """Test Meta WhatsApp credentials by calling the Graph API."""
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    config = get_whatsapp_config(cid)
    if not config or not config.get("meta_access_token") or not config.get("meta_phone_number_id"):
        raise HTTPException(status_code=400, detail="Meta WhatsApp credentials not configured")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v21.0/{config['meta_phone_number_id']}",
                headers={"Authorization": f"Bearer {config['meta_access_token']}"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                display_name = data.get("verified_name") or data.get("display_phone_number") or "WhatsApp Business"
                return {"status": "success", "message": f"Connected! Phone: {display_name}"}
            else:
                err = resp.json().get("error", {}).get("message", resp.text)
                raise HTTPException(status_code=500, detail=f"Meta API error: {err}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

@app.get("/admin/whatsapp/conversations")
async def wa_conversations(request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"sessions": get_whatsapp_sessions(cid)}

@app.get("/admin/whatsapp/conversations/{session_id}")
async def wa_conversation(session_id: str, request: Request):
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    return {"messages": get_session_messages(session_id, 100, cid)}


class WhatsAppSendReq(BaseModel):
    phone: str
    message: str

@app.post("/admin/whatsapp/send")
async def wa_send_message(req: WhatsAppSendReq, request: Request):
    """Send a manual WhatsApp message via Meta Cloud API."""
    admin = get_admin(request)
    cid = admin["client_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="No client context")
    config = get_whatsapp_config(cid)
    if not config or not config.get("meta_access_token") or not config.get("meta_phone_number_id"):
        raise HTTPException(status_code=400, detail="Meta WhatsApp credentials not configured")

    phone = req.phone.strip().replace("+", "").replace(" ", "").replace("-", "")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://graph.facebook.com/v21.0/{config['meta_phone_number_id']}/messages",
                headers={
                    "Authorization": f"Bearer {config['meta_access_token']}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {"body": req.message},
                },
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                err = resp.json().get("error", {}).get("message", resp.text)
                raise HTTPException(status_code=500, detail=f"Meta API error: {err}")

        # Save the outgoing message to the conversation
        from database import save_message
        session_id = f"wa_{phone}"
        save_message(session_id, 'bot', req.message, 'whatsapp', cid)
        return {"status": "ok", "message": "Message sent!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")


@app.get("/")
def root():
    return {"status": "Techmatic AI Platform v2.0 (multi-tenant) running."}
