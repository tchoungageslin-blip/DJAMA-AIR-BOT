import json
import hmac
import hashlib
import traceback
import asyncio
import time
from collections import OrderedDict
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


# Message deduplication cache (WhatsApp retries messages)
_processed_messages: OrderedDict = OrderedDict()
_DEDUP_MAX_SIZE = 200
_DEDUP_TTL_SECONDS = 120


def _is_duplicate_message(message_id: str) -> bool:
    """Check and track message IDs to prevent duplicate processing."""
    now = time.time()
    # Evict old entries
    while _processed_messages:
        oldest_id, oldest_time = next(iter(_processed_messages.items()))
        if now - oldest_time > _DEDUP_TTL_SECONDS:
            _processed_messages.pop(oldest_id)
        else:
            break
    # Cap size
    while len(_processed_messages) >= _DEDUP_MAX_SIZE:
        _processed_messages.popitem(last=False)
    if message_id in _processed_messages:
        return True
    _processed_messages[message_id] = now
    return False

app = FastAPI(
    title="Djama Air Logistics Bot",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# CORS for dashboard - SECURED
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL] if settings.APP_ENV == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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

    # CRYPTO-01: Constant time comparison to prevent timing attacks
    if mode == "subscribe" and hmac.compare_digest(token.encode(), settings.WHATSAPP_VERIFY_TOKEN.encode()):
        return PlainTextResponse(content=challenge, status_code=200)

    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/api/webhook")
async def webhook_receive(request: Request):
    """
    Main webhook endpoint receiving messages from WhatsApp.
    Processes messages within the request lifecycle to avoid Vercel event loop closure.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    tasks = []
    entry = body.get("entry", [])
    for e in entry:
        for change in e.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                msg_id = message.get("id", "")
                # Skip duplicate messages (WhatsApp retries)
                if msg_id and _is_duplicate_message(msg_id):
                    print(f"[WEBHOOK DEDUP] Skipping duplicate message: {msg_id}")
                    continue
                tasks.append(_process_message(message, value))

    if tasks:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=25.0
            )
            # Log any exceptions that were returned (not raised)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"[WEBHOOK GATHER ERROR] Task {i}: {type(result).__name__}: {result}")
        except asyncio.TimeoutError:
            print("[WEBHOOK] Processing timeout after 25s")

    return JSONResponse(content={"status": "ok"}, status_code=200)


async def _process_message(message: dict, value: dict) -> None:
    """Process a single incoming WhatsApp message."""
    phone_number = message.get("from", "")
    message_type = message.get("type", "")
    message_id = message.get("id", "")
    print(f"[WEBHOOK PROCESS] Phone: {phone_number}, Type: {message_type}, ID: {message_id}")
    print(f"[WEBHOOK RAW] Message: {json.dumps(message, ensure_ascii=False)}")

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
        # Log error with full traceback for debugging
        error_detail = traceback.format_exc()
        print(f"[WEBHOOK ERROR] Phone: {phone_number}, Error: {str(e)}")
        print(f"[WEBHOOK TRACEBACK] {error_detail}")

        # Notify about the error
        error_msg = (
            "Désolé, je rencontre un problème technique. "
            "Un conseiller va vous répondre rapidement."
        )
        try:
            await whatsapp_service.send_text_message(phone_number, error_msg)
        except Exception as send_err:
            print(f"[WEBHOOK SEND ERROR] Failed to send error message: {send_err}")


@app.get("/api/cron/timeout-sessions")
async def cron_timeout_sessions():
    """
    Cron endpoint (e.g. called every hour by Vercel Cron or external service)
    Checks for sessions that are BOT_ACTIVE but haven't been updated in 5 hours.
    It moves them to HUMAN_HANDOFF and sends a follow-up message to the client.
    """
    try:
        from api.db.connection import execute_query
        from api.db.queries import SessionQueries
        
        # Find sessions older than 5 hours that are still BOT_ACTIVE
        query = """
            SELECT s.id, s.client_id, c.phone_number 
            FROM sessions s
            JOIN clients c ON s.client_id = c.id
            WHERE s.status = 'BOT_ACTIVE' 
            AND s.updated_at < NOW() - INTERVAL '5 hours'
        """
        stale_sessions = execute_query(query, fetch_all=True) or []
        
        results = []
        for session in stale_sessions:
            phone = session["phone_number"]
            sid = session["id"]
            
            # Update status
            SessionQueries.update_status(sid, "HUMAN_HANDOFF", ai_summary="Timeout de 5h: Le client n'a pas terminé le processus.")
            SessionQueries.add_tag(sid, "TIMEOUT_5H")
            
            # Disable bot
            session_manager.disable_bot_for_session(phone)
            
            # Notify agent
            await notification_service.notify_handoff(
                client_phone=phone,
                session_id=sid,
                summary="Le client a été inactif pendant 5h. Handoff automatique.",
                tags=["TIMEOUT_5H"]
            )
            
            # Send message to client
            timeout_msg = (
                "Bonjour Mr/Mme,\n\n"
                "Je remarque que notre processus est resté inachevé. "
                "J'ai transmis votre dossier à un conseiller qui prendra le relais "
                "pour répondre à vos questions et finaliser votre demande.\n"
                "À très vite !"
            )
            try:
                await whatsapp_service.send_text_message(phone, timeout_msg)
            except Exception as e:
                print(f"[CRON] Failed to send timeout msg to {phone}: {e}")
                
            results.append({"session_id": sid, "phone": phone, "status": "handed_off"})
            
        return {"status": "ok", "processed": len(results), "details": results}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {"status": "error", "error": str(e), "traceback": error_detail}


# ============================================
# DASHBOARD API ENDPOINTS
# ============================================

@app.get("/api/dashboard/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "bot_enabled": session_manager.is_bot_enabled()}


@app.post("/api/debug/test-message")
async def debug_test_message(request: Request):
    """Debug endpoint to test bot message processing directly."""
    body = await request.json()
    phone = body.get("phone", "23799999999")
    text = body.get("text", "Bonjour")

    try:
        response = await djama_agent.handle_message(
            phone_number=phone,
            message_text=text
        )
        return {"status": "ok", "response": response}
    except Exception as e:
        error_detail = traceback.format_exc()
        return {
            "status": "error",
            "error": str(e),
            "type": type(e).__name__,
            "traceback": error_detail
        }


@app.post("/api/debug/reset-bot")
async def debug_reset_bot(request: Request):
    """Debug endpoint to reset a session status to BOT_ACTIVE."""
    body = await request.json()
    phone = body.get("phone")
    if not phone:
        return {"status": "error", "error": "Phone required"}
        
    try:
        from api.db.connection import execute_query
        from api.db.queries import SessionQueries
        
        # 1. Update session status
        execute_query(
            "UPDATE sessions SET status = 'BOT_ACTIVE' WHERE id IN (SELECT s.id FROM sessions s JOIN clients c ON s.client_id = c.id WHERE c.phone_number = %s)",
            (phone,), fetch_one=False
        )
        
        # 2. Re-enable bot in session context
        context = session_manager.get_context(phone)
        if context:
            context["bot_disabled"] = False
            session_manager.set_context(phone, context)
            
        # We can also clear the whole context to force a completely fresh start (which might be safer after a handoff)
        session_manager.clear_context(phone)
        
        return {"status": "ok", "message": f"Bot re-enabled for {phone}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/debug/system-check")
async def debug_system_check():
    """Comprehensive system diagnostic - tests every component."""
    results = {}

    # 1. Database connectivity
    try:
        from api.db.connection import execute_query
        db_result = execute_query("SELECT NOW() as ts, current_database() as db", fetch_one=True)
        results["database"] = {"status": "ok", "timestamp": str(db_result["ts"]), "db": db_result["db"]}
    except Exception as e:
        results["database"] = {"status": "error", "error": str(e), "type": type(e).__name__}

    # 2. Tables existence
    try:
        tables = ["clients", "sessions", "messages", "orders", "agents", "notifications"]
        missing = []
        for t in tables:
            r = execute_query(f"SELECT COUNT(*) as cnt FROM {t}", fetch_one=True)
            if r is None:
                missing.append(t)
        results["tables"] = {"status": "ok" if not missing else "error", "missing": missing}
    except Exception as e:
        results["tables"] = {"status": "error", "error": str(e), "type": type(e).__name__}

    # 3. Redis / Session manager
    try:
        sm_status = {
            "use_fallback": session_manager._use_fallback,
            "bot_enabled": session_manager.is_bot_enabled(),
        }
        if not session_manager._use_fallback:
            session_manager.redis_client.ping()
            sm_status["redis_ping"] = "ok"
        results["session_manager"] = {"status": "ok", **sm_status}
    except Exception as e:
        results["session_manager"] = {"status": "error", "error": str(e), "use_fallback": session_manager._use_fallback}

    # 4. OpenAI/OpenRouter connectivity
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            max_retries=1,
            timeout=15.0,
        )
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": "Réponds juste 'OK'"}],
            max_tokens=5,
        )
        ai_response = response.choices[0].message.content.strip()
        await client.close()
        results["openai"] = {"status": "ok", "response": ai_response, "model": settings.LLM_MODEL}
    except Exception as e:
        results["openai"] = {"status": "error", "error": str(e), "type": type(e).__name__,
                             "base_url": settings.OPENROUTER_BASE_URL,
                             "key_set": bool(settings.OPENROUTER_API_KEY)}

    # 5. WhatsApp service config
    try:
        wa = whatsapp_service
        wa_status = {
            "api_url": wa.api_url,
            "phone_number_id": wa.phone_number_id,
            "token_set": bool(wa.access_token),
            "token_length": len(wa.access_token) if wa.access_token else 0,
        }
        results["whatsapp"] = {"status": "ok" if wa.access_token and wa.phone_number_id else "warning", **wa_status}
    except Exception as e:
        results["whatsapp"] = {"status": "error", "error": str(e)}

    # 6. Config summary
    results["config"] = {
        "app_env": settings.APP_ENV,
        "llm_model": settings.LLM_MODEL,
        "database_url_set": bool(settings.DATABASE_URL),
        "redis_url_set": bool(settings.REDIS_URL),
        "openrouter_key_set": bool(settings.OPENROUTER_API_KEY),
        "whatsapp_phone_id_set": bool(settings.WHATSAPP_PHONE_NUMBER_ID),
        "whatsapp_token_set": bool(settings.WHATSAPP_TOKEN),
    }

    # Overall
    all_ok = all(r.get("status") == "ok" for r in results.values() if isinstance(r, dict) and "status" in r)
    return {"overall": "ok" if all_ok else "issues_found", "components": results}


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
    if agent_id == "current":
        agent_id = None

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
    try:
        from api.db.queries import SessionQueries
        SessionQueries.update_status(session_id, "HUMAN_ACTIVE", agent_id=agent_id)
    except Exception as e:
        print(f"Error in takeover: {e}")

    # Disable bot in Redis
    if client:
        session_manager.disable_bot_for_session(client["phone_number"])

    return {"status": "ok", "session_status": "HUMAN_ACTIVE"}


@app.post("/api/dashboard/sessions/{session_id}/release")
async def release_session(session_id: str):
    """Release a session back to the bot."""
    from api.db.connection import execute_query
    session = execute_query(
        "SELECT * FROM sessions WHERE id = %s", (session_id,), fetch_one=True
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    client = execute_query(
        "SELECT phone_number FROM clients WHERE id = %s",
        (session["client_id"],), fetch_one=True
    )

    try:
        from api.db.queries import SessionQueries
        SessionQueries.update_status(session_id, "BOT_ACTIVE", agent_id=None)
    except Exception as e:
        print(f"Error in release: {e}")

    if client:
        phone = client["phone_number"]
        context = session_manager.get_context(phone)
        if context:
            context["bot_disabled"] = False
            session_manager.set_context(phone, context)
        session_manager.clear_context(phone)

    return {"status": "ok", "session_status": "BOT_ACTIVE"}


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
            COUNT(*) FILTER (WHERE status = 'RESOLVED' AND updated_at::date = CURRENT_DATE) as resolved_today,
            COUNT(*) FILTER (WHERE status IN ('BOT_ACTIVE', 'HUMAN_HANDOFF', 'HUMAN_ACTIVE')) as active_sessions,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') as sessions_30d,
            COUNT(*) FILTER (WHERE status = 'HUMAN_HANDOFF' AND created_at >= NOW() - INTERVAL '30 days') as handoffs_30d,
            COUNT(*) FILTER (WHERE status = 'RESOLVED' AND updated_at >= NOW() - INTERVAL '30 days') as resolved_30d
        FROM sessions""",
        fetch_one=True
    )

    orders_stats = execute_query(
        """SELECT
            COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE)::int as orders_today,
            COALESCE(SUM(estimated_price) FILTER (WHERE created_at::date = CURRENT_DATE), 0)::bigint as estimated_revenue_today
        FROM orders""",
        fetch_one=True
    )

    messages_stats = execute_query(
        """SELECT
            COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as messages_today,
            COUNT(*) FILTER (WHERE sender = 'client' AND created_at::date = CURRENT_DATE) as client_messages_today,
            COUNT(*) FILTER (WHERE sender = 'bot' AND created_at::date = CURRENT_DATE) as bot_messages_today,
            COUNT(*) FILTER (WHERE sender = 'agent' AND created_at::date = CURRENT_DATE) as agent_messages_today
        FROM messages""",
        fetch_one=True
    )

    clients_stats = execute_query(
        "SELECT COUNT(*) as total_clients FROM clients",
        fetch_one=True
    )

    daily_metrics = execute_query(
        """WITH days AS (
            SELECT generate_series(CURRENT_DATE - INTERVAL '13 days', CURRENT_DATE, INTERVAL '1 day')::date AS day
        ),
        session_counts AS (
            SELECT created_at::date AS day,
                COUNT(*) AS sessions,
                COUNT(*) FILTER (WHERE status = 'HUMAN_HANDOFF') AS handoffs
            FROM sessions
            WHERE created_at >= CURRENT_DATE - INTERVAL '13 days'
            GROUP BY created_at::date
        ),
        message_counts AS (
            SELECT created_at::date AS day,
                COUNT(*) AS messages
            FROM messages
            WHERE created_at >= CURRENT_DATE - INTERVAL '13 days'
            GROUP BY created_at::date
        ),
        order_counts AS (
            SELECT created_at::date AS day,
                COUNT(*) AS orders,
                COALESCE(SUM(estimated_price), 0) AS revenue
            FROM orders
            WHERE created_at >= CURRENT_DATE - INTERVAL '13 days'
            GROUP BY created_at::date
        )
        SELECT
            d.day::text AS day,
            TO_CHAR(d.day, 'DD/MM') AS label,
            COALESCE(sc.sessions, 0)::int AS sessions,
            COALESCE(sc.handoffs, 0)::int AS handoffs,
            COALESCE(mc.messages, 0)::int AS messages,
            COALESCE(oc.orders, 0)::int AS orders,
            COALESCE(oc.revenue, 0)::bigint AS revenue
        FROM days d
        LEFT JOIN session_counts sc ON sc.day = d.day
        LEFT JOIN message_counts mc ON mc.day = d.day
        LEFT JOIN order_counts oc ON oc.day = d.day
        ORDER BY d.day""",
        fetch_all=True
    )

    session_status = execute_query(
        """SELECT status::text AS status, COUNT(*)::int AS sessions
        FROM sessions
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY status
        ORDER BY sessions DESC""",
        fetch_all=True
    )

    message_sources = execute_query(
        """SELECT sender, COUNT(*)::int AS messages
        FROM messages
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY sender
        ORDER BY messages DESC""",
        fetch_all=True
    )

    order_types = execute_query(
        """SELECT order_type::text AS order_type, COUNT(*)::int AS orders
        FROM orders
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY order_type
        ORDER BY orders DESC""",
        fetch_all=True
    )

    sessions_30d = int(stats.get("sessions_30d", 0)) if stats else 0
    handoffs_30d = int(stats.get("handoffs_30d", 0)) if stats else 0
    resolved_30d = int(stats.get("resolved_30d", 0)) if stats else 0
    messages_today = int(messages_stats.get("messages_today", 0)) if messages_stats else 0
    bot_messages_today = int(messages_stats.get("bot_messages_today", 0)) if messages_stats else 0
    agent_messages_today = int(messages_stats.get("agent_messages_today", 0)) if messages_stats else 0
    handled_today = bot_messages_today + agent_messages_today

    return {
        "sessions_today": stats.get("sessions_today", 0) if stats else 0,
        "pending_handoffs": stats.get("pending_handoffs", 0) if stats else 0,
        "resolved_today": stats.get("resolved_today", 0) if stats else 0,
        "active_sessions": stats.get("active_sessions", 0) if stats else 0,
        "orders_today": orders_stats.get("orders_today", 0) if orders_stats else 0,
        "estimated_revenue_today": orders_stats.get("estimated_revenue_today", 0) if orders_stats else 0,
        "messages_today": messages_today,
        "client_messages_today": messages_stats.get("client_messages_today", 0) if messages_stats else 0,
        "bot_messages_today": bot_messages_today,
        "agent_messages_today": agent_messages_today,
        "total_clients": clients_stats.get("total_clients", 0) if clients_stats else 0,
        "handoff_rate": round((handoffs_30d / sessions_30d) * 100, 1) if sessions_30d else 0,
        "resolution_rate": round((resolved_30d / sessions_30d) * 100, 1) if sessions_30d else 0,
        "automation_rate": round((bot_messages_today / handled_today) * 100, 1) if handled_today else 0,
        "daily_metrics": daily_metrics or [],
        "session_status": session_status or [],
        "message_sources": message_sources or [],
        "order_types": order_types or [],
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
