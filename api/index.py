import json
import hmac
import hashlib
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional

from api.config import settings
from api.bot.agent import djama_agent
from api.services.whatsapp import whatsapp_service
from api.services.session import session_manager
from api.services.auth import auth_service
from api.db.queries import ClientQueries, SessionQueries, MessageQueries, OrderQueries

app = FastAPI(
    title="Djama Air Logistics Bot",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# AUTH HELPERS
# ============================================

async def get_current_agent(request: Request) -> Optional[dict]:
    """Extract and verify agent from Authorization header."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    return auth_service.get_agent_from_token(token)


def require_auth(agent: Optional[dict]) -> dict:
    """Raise 401 if agent is None."""
    if not agent:
        raise HTTPException(status_code=401, detail="Non autorisé")
    return agent


# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/api/dashboard/auth/login")
async def auth_login(request: Request):
    """Authenticate agent and return JWT token."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email et mot de passe requis")

    result = auth_service.login(email, password)
    if not result:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    return result


@app.get("/api/dashboard/auth/me")
async def auth_me(request: Request):
    """Get current authenticated agent."""
    agent = await get_current_agent(request)
    agent = require_auth(agent)
    return {"agent": agent}


@app.post("/api/dashboard/auth/register")
async def auth_register(request: Request):
    """Register a new agent (admin only)."""
    current_agent = await get_current_agent(request)
    current_agent = require_auth(current_agent)

    if current_agent.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Seuls les admins peuvent créer des comptes")

    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    full_name = body.get("full_name", "")
    role = body.get("role", "AGENT")

    if not email or not password or not full_name:
        raise HTTPException(status_code=400, detail="Champs requis: email, password, full_name")

    try:
        new_agent = auth_service.create_agent(email, password, full_name, role)
        return {"agent": new_agent}
    except Exception:
        raise HTTPException(status_code=409, detail="Cet email existe déjà")


@app.post("/api/dashboard/auth/change-password")
async def auth_change_password(request: Request):
    """Change the current agent's password."""
    agent = await get_current_agent(request)
    agent = require_auth(agent)

    body = await request.json()
    new_password = body.get("new_password", "")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")

    from api.db.connection import execute_query
    new_hash = auth_service.hash_password(new_password)
    execute_query(
        "UPDATE agents SET password_hash = %s WHERE id = %s",
        (new_hash, agent["id"])
    )

    return {"status": "password_changed"}


# ============================================
# WEBHOOK ENDPOINTS
# ============================================

@app.get("/api/webhook")
async def webhook_verify(request: Request):
    """WhatsApp webhook verification (GET request from Meta/Vendrix)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.VENDRIX_WEBHOOK_SECRET:
        return PlainTextResponse(content=challenge, status_code=200)

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/api/webhook")
async def webhook_receive(request: Request):
    """
    Main webhook endpoint receiving messages from WhatsApp via Vendrix.
    Process flow:
    1. Parse incoming payload
    2. Extract message data
    3. Route to AI agent
    4. Send response back via WhatsApp
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Parse WhatsApp Cloud API payload structure
    entry = body.get("entry", [])
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])

            for message in messages:
                await _process_message(message, value)

    return JSONResponse(content={"status": "ok"}, status_code=200)


async def _process_message(message: dict, value: dict) -> None:
    """Process a single incoming WhatsApp message."""
    phone_number = message.get("from", "")
    message_type = message.get("type", "")
    message_id = message.get("id", "")

    # Extract text content
    text = ""
    media_data = None
    media_type = None

    if message_type == "text":
        text = message.get("text", {}).get("body", "")
    elif message_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            text = interactive.get("list_reply", {}).get("title", "")
    elif message_type in ["image", "document"]:
        # Handle media
        media_info = message.get(message_type, {})
        media_id = media_info.get("id")
        caption = media_info.get("caption", "")
        text = caption

        if media_id:
            try:
                media_data = await whatsapp_service.download_media(media_id)
                media_type = media_info.get("mime_type", "image/jpeg")
            except Exception:
                media_data = None

    # Skip empty messages
    if not text and not media_data:
        return

    # Check global bot status
    if not session_manager.is_bot_enabled():
        return  # Bot globally disabled, messages go to dashboard only

    # Route to AI agent
    try:
        response = await djama_agent.handle_message(
            phone_number=phone_number,
            message_text=text,
            media_data=media_data,
            media_type=media_type
        )

        # Send response if bot generated one
        if response:
            await whatsapp_service.send_text_message(phone_number, response)
    except Exception as e:
        # Log error, don't crash webhook
        # In production: log to error tracking service
        print(f"Error processing message from {phone_number}: {str(e)}")

        # Notify about the error
        error_msg = (
            "Désolé, je rencontre un problème technique. "
            "Un conseiller va vous répondre rapidement. 🙏"
        )
        try:
            await whatsapp_service.send_text_message(phone_number, error_msg)
        except Exception:
            pass


# ============================================
# DASHBOARD API ENDPOINTS
# ============================================

@app.get("/api/dashboard/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "bot_enabled": session_manager.is_bot_enabled()}


@app.get("/api/dashboard/sessions")
async def get_sessions(status: Optional[str] = None):
    """Get sessions for dashboard inbox."""
    from api.db.connection import execute_query

    if status:
        sessions = execute_query(
            """SELECT s.*, c.phone_number, c.first_name, c.last_name, c.client_type
            FROM sessions s JOIN clients c ON s.client_id = c.id
            WHERE s.status = %s ORDER BY s.updated_at DESC LIMIT 50""",
            (status,),
            fetch_all=True
        )
    else:
        sessions = execute_query(
            """SELECT s.*, c.phone_number, c.first_name, c.last_name, c.client_type
            FROM sessions s JOIN clients c ON s.client_id = c.id
            WHERE s.status != 'CLOSED'
            ORDER BY CASE s.status
                WHEN 'HUMAN_HANDOFF' THEN 1
                WHEN 'HUMAN_ACTIVE' THEN 2
                WHEN 'BOT_ACTIVE' THEN 3
                ELSE 4 END,
            s.updated_at DESC LIMIT 50""",
            fetch_all=True
        )

    return {"sessions": sessions or []}


@app.get("/api/dashboard/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages for a session."""
    messages = MessageQueries.get_session_messages(session_id, limit=100)
    return {"messages": messages or []}


@app.post("/api/dashboard/sessions/{session_id}/takeover")
async def takeover_session(session_id: str, request: Request):
    """Agent takes over a session (silent takeover)."""
    body = await request.json()
    agent_id = body.get("agent_id")

    from api.db.connection import execute_query
    session = execute_query(
        "SELECT * FROM sessions WHERE id = %s", (session_id,), fetch_one=True
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get client phone for Redis
    client = execute_query(
        "SELECT phone_number FROM clients WHERE id = %s",
        (session["client_id"],), fetch_one=True
    )

    # Update session
    SessionQueries.update_status(session_id, "HUMAN_ACTIVE", agent_id=agent_id)

    # Disable bot in Redis
    if client:
        session_manager.disable_bot_for_session(client["phone_number"])

    return {"status": "ok", "session_status": "HUMAN_ACTIVE"}


@app.post("/api/dashboard/sessions/{session_id}/reply")
async def agent_reply(session_id: str, request: Request):
    """Agent sends a reply to a client."""
    body = await request.json()
    message_text = body.get("message", "")
    agent_id = body.get("agent_id")

    from api.db.connection import execute_query
    session = execute_query(
        "SELECT * FROM sessions WHERE id = %s", (session_id,), fetch_one=True
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    client = execute_query(
        "SELECT * FROM clients WHERE id = %s",
        (session["client_id"],), fetch_one=True
    )

    # Store message
    MessageQueries.create(
        session_id=session_id,
        client_id=session["client_id"],
        sender="agent",
        content=message_text
    )

    # Send via WhatsApp
    await whatsapp_service.send_text_message(client["phone_number"], message_text)

    return {"status": "sent"}


@app.post("/api/dashboard/sessions/{session_id}/resolve")
async def resolve_session(session_id: str):
    """Mark a session as resolved."""
    SessionQueries.update_status(session_id, "RESOLVED")
    return {"status": "resolved"}


@app.post("/api/dashboard/bot/toggle")
async def toggle_bot(request: Request):
    """Global kill-switch: enable/disable bot."""
    body = await request.json()
    enabled = body.get("enabled", True)
    session_manager.set_bot_enabled(enabled)
    return {"bot_enabled": enabled}


@app.get("/api/dashboard/orders")
async def get_orders(order_type: Optional[str] = None, status: Optional[str] = None):
    """Get orders for the order management board."""
    from api.db.connection import execute_query

    conditions = ["1=1"]
    params = []

    if order_type:
        conditions.append("o.order_type = %s")
        params.append(order_type)
    if status:
        conditions.append("o.status = %s")
        params.append(status)

    orders = execute_query(
        f"""SELECT o.*, c.phone_number, c.first_name, c.last_name
        FROM orders o JOIN clients c ON o.client_id = c.id
        WHERE {' AND '.join(conditions)}
        ORDER BY o.created_at DESC LIMIT 50""",
        tuple(params) if params else None,
        fetch_all=True
    )

    return {"orders": orders or []}


@app.get("/api/dashboard/notifications")
async def get_notifications(unread_only: bool = True):
    """Get pending notifications for the dashboard."""
    from api.db.connection import execute_query

    if unread_only:
        notifs = execute_query(
            """SELECT * FROM notifications
            WHERE channel = 'dashboard' AND sent = true
            ORDER BY created_at DESC LIMIT 20""",
            fetch_all=True
        )
    else:
        notifs = execute_query(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50",
            fetch_all=True
        )

    return {"notifications": notifs or []}


@app.get("/api/dashboard/stats")
async def get_stats():
    """Get analytics data for the dashboard."""
    from api.db.connection import execute_query

    # Today's stats
    stats = execute_query(
        """SELECT
            COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as sessions_today,
            COUNT(*) FILTER (WHERE status = 'HUMAN_HANDOFF') as pending_handoffs,
            COUNT(*) FILTER (WHERE status = 'RESOLVED' AND updated_at::date = CURRENT_DATE) as resolved_today
        FROM sessions""",
        fetch_one=True
    )

    orders_stats = execute_query(
        """SELECT
            COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as orders_today,
            COALESCE(SUM(estimated_price) FILTER (WHERE created_at::date = CURRENT_DATE), 0) as estimated_revenue_today
        FROM orders""",
        fetch_one=True
    )

    return {
        "sessions_today": stats.get("sessions_today", 0) if stats else 0,
        "pending_handoffs": stats.get("pending_handoffs", 0) if stats else 0,
        "resolved_today": stats.get("resolved_today", 0) if stats else 0,
        "orders_today": orders_stats.get("orders_today", 0) if orders_stats else 0,
        "estimated_revenue_today": orders_stats.get("estimated_revenue_today", 0) if orders_stats else 0,
    }


# ============================================
# PRICING GRID MANAGEMENT
# ============================================

@app.get("/api/dashboard/pricing")
async def get_pricing_grids():
    """Get all active pricing grids."""
    from api.db.connection import execute_query
    grids = execute_query(
        "SELECT * FROM pricing_grids WHERE valid_until IS NULL OR valid_until > NOW() ORDER BY mode, origin",
        fetch_all=True
    )
    return {"grids": grids or []}


@app.post("/api/dashboard/pricing")
async def update_pricing_grid(request: Request):
    """Create or update a pricing grid."""
    from api.db.connection import execute_query
    body = await request.json()

    mode = body.get("mode")
    origin = body.get("origin", "")
    rules = body.get("rules")
    updated_by = body.get("updated_by", "")

    if not mode or not rules:
        raise HTTPException(status_code=400, detail="mode and rules are required")

    # Expire old grid
    execute_query(
        "UPDATE pricing_grids SET valid_until = NOW() WHERE mode = %s AND origin = %s AND valid_until IS NULL",
        (mode, origin)
    )

    # Create new grid
    import json as json_module
    new_grid = execute_query(
        """INSERT INTO pricing_grids (id, mode, origin, rules, valid_from, updated_by, created_at, updated_at)
        VALUES (gen_random_uuid(), %s, %s, %s::jsonb, NOW(), %s, NOW(), NOW())
        RETURNING *""",
        (mode, origin, json_module.dumps(rules), updated_by),
        fetch_one=True
    )

    return {"grid": new_grid}


# ============================================
# SETTINGS MANAGEMENT
# ============================================

@app.get("/api/dashboard/settings")
async def get_settings():
    """Get all app settings."""
    from api.db.connection import execute_query
    all_settings = execute_query("SELECT * FROM settings", fetch_all=True)
    return {"settings": {s["key"]: s["value"] for s in all_settings} if all_settings else {}}


@app.post("/api/dashboard/settings")
async def update_settings(request: Request):
    """Update app settings."""
    from api.db.connection import execute_query
    body = await request.json()

    for key, value in body.items():
        execute_query(
            """INSERT INTO settings (id, key, value)
            VALUES (gen_random_uuid(), %s, %s)
            ON CONFLICT (key) DO UPDATE SET value = %s""",
            (key, str(value), str(value))
        )

    return {"status": "updated"}
