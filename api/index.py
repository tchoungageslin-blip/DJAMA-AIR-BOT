import json
import hmac
import hashlib
import logging
import traceback
import asyncio
import time
from collections import OrderedDict
from fastapi import FastAPI, Request, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional
from pydantic import BaseModel

from api.config import settings
from api.bot.agent import djama_agent
from api.services.whatsapp import whatsapp_service
from api.services.session import session_manager
from api.services.auth import auth_service
from api.services.notifications import notification_service
from api.db.queries import ClientQueries, SessionQueries, MessageQueries, OrderQueries

# Configure root logger for all djama.* loggers
logging.basicConfig(
    level=logging.DEBUG if settings.APP_ENV != "production" else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("djama.webhook")

# In-memory dedup fallback (used only when Redis is unavailable)
_dedup_fallback: OrderedDict = OrderedDict()
_DEDUP_MAX_SIZE = 200
_DEDUP_TTL_SECONDS = 120


def _is_duplicate_message(message_id: str) -> bool:
    """Check and track message IDs to prevent duplicate processing.
    Uses Redis when available (works across multiple Vercel instances),
    falls back to in-memory OrderedDict for single-instance setups.
    """
    redis = session_manager.redis_client
    if redis:
        try:
            key = f"dedup:{message_id}"
            # SET NX EX: only set if not exists, expire after TTL
            added = redis.set(key, "1", nx=True, ex=_DEDUP_TTL_SECONDS)
            return added is None  # None = key already existed → duplicate
        except Exception:
            pass  # Fall through to in-memory fallback

    # In-memory fallback
    now = time.time()
    while _dedup_fallback:
        oldest_id, oldest_time = next(iter(_dedup_fallback.items()))
        if now - oldest_time > _DEDUP_TTL_SECONDS:
            _dedup_fallback.pop(oldest_id)
        else:
            break
    while len(_dedup_fallback) >= _DEDUP_MAX_SIZE:
        _dedup_fallback.popitem(last=False)
    if message_id in _dedup_fallback:
        return True
    _dedup_fallback[message_id] = now
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


def require_dev_env() -> None:
    """Block debug endpoints in production."""
    if settings.APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found")


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
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
    """
    Main webhook endpoint receiving messages from WhatsApp.
    Returns 200 immediately to Vendrix, processes message in background.
    This eliminates the ~25s wait before Vendrix retries and cuts perceived latency.
    """
    try:
        raw = await request.body()
        raw_text = raw.decode("utf-8", errors="ignore")
        body = json.loads(raw_text)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Optional Vendrix signature verification if headers are present
    vendrix_sig = request.headers.get("x-vendrix-signature") or request.headers.get("X-Vendrix-Signature")
    vendrix_ts = request.headers.get("x-vendrix-timestamp") or request.headers.get("X-Vendrix-Timestamp")
    if vendrix_sig and vendrix_ts and settings.VENDRIX_WEBHOOK_SECRET:
        try:
            message_str = f"{vendrix_ts}.{raw_text}"
            expected = hmac.new(settings.VENDRIX_WEBHOOK_SECRET.encode("utf-8"), message_str.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, vendrix_sig):
                raise HTTPException(status_code=403, detail="Invalid Vendrix signature")
        except HTTPException:
            raise
        except Exception:
            pass

    tasks = []

    # Vendrix Gateway payload support
    if isinstance(body, dict) and body.get("event_type") and body.get("data"):
        etype = body.get("event_type")
        data = body.get("data", {})
        phone = (data.get("from", "") or data.get("wa_id", "")).replace(" ", "").lstrip("+")
        now_id = f"vendrix.{int(time.time()*1000)}"
        if etype == "message":
            text_body = data.get("text") or data.get("body") or ""
            message = {"from": phone, "id": now_id, "type": "text", "text": {"body": text_body}}
            value = {"messages": [message]}
            if text_body and not _is_duplicate_message(now_id):
                tasks.append((message, value))
        elif etype == "media_message":
            mtype = (data.get("media_type") or "document").lower()
            if mtype not in ["image", "document", "audio"]:
                mtype = "document"
            media_id = data.get("id") or data.get("media_id")
            caption = data.get("caption", "")
            mime = data.get("mime_type") or data.get("content_type")
            message = {"from": phone, "id": now_id, "type": mtype, mtype: {"id": media_id, "caption": caption, "mime_type": mime}}
            value = {"messages": [message]}
            if media_id and not _is_duplicate_message(now_id):
                tasks.append((message, value))
        elif etype in ["interactive_reply", "button_click"]:
            title = data.get("title") or data.get("text") or ""
            message = {"from": phone, "id": now_id, "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"title": title}}}
            value = {"messages": [message]}
            if title and not _is_duplicate_message(now_id):
                tasks.append((message, value))
    else:
        # Meta/Graph payload support
        entry = body.get("entry", [])
        for e in entry:
            for change in e.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    msg_id = message.get("id", "")
                    if msg_id and _is_duplicate_message(msg_id):
                        logger.debug("Dedup: skipping duplicate message %s", msg_id)
                        continue
                    tasks.append((message, value))

    # Return 200 to Vendrix immediately, then process in background
    # This prevents Vendrix from timing out and retrying
    if tasks:
        background_tasks.add_task(_process_messages_background, tasks)

    return JSONResponse(content={"status": "ok"}, status_code=200)


async def _process_messages_background(tasks: list) -> None:
    """Process all incoming messages asynchronously after 200 is returned."""
    coros = [_process_message(msg, val) for msg, val in tasks]
    try:
        results = await asyncio.gather(*coros, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Background task %d failed: %s: %s", i, type(result).__name__, result)
    except Exception as e:
        logger.error("Background processing error: %s", e)


async def _process_message(message: dict, value: dict) -> None:
    """Process a single incoming WhatsApp message."""
    phone_number = message.get("from", "")
    message_type = message.get("type", "")
    message_id = message.get("id", "")
    logger.info("Incoming message phone=%s type=%s id=%s", phone_number, message_type, message_id)
    logger.debug("Raw message: %s", json.dumps(message, ensure_ascii=False))

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
    elif message_type in ["image", "document", "audio"]:
        # Handle media (images, documents, voice notes)
        media_info = message.get(message_type, {})
        media_id = media_info.get("id")
        caption = media_info.get("caption", "")
        if message_type != "audio":
            text = caption

        if media_id:
            try:
                media_data = await whatsapp_service.download_media(media_id)
                media_type = media_info.get("mime_type", "image/jpeg" if message_type == "image" else "audio/ogg")
                
                # If it's an audio message, transcribe it immediately
                if message_type == "audio" and media_data:
                    from api.bot.audio import audio_processor
                    transcription = await audio_processor.transcribe_audio(media_data, media_type)
                    if transcription:
                        logger.info("Audio transcribed: %s", transcription[:100])
                        text = transcription
                        # We don't need to pass the raw audio data to the AI agent anymore, just the text
                        media_data = None
                        media_type = None
            except Exception as e:
                logger.error("Failed to download or process media: %s", e)
                media_data = None

    # Skip empty messages
    if not text and not media_data:
        return

    # Check global bot status — store message regardless, then skip response
    if not session_manager.is_bot_enabled():
        # Still need to persist the message so it appears in the inbox
        try:
            client = ClientQueries.find_by_phone(phone_number)
            if not client:
                client = ClientQueries.create(phone_number)
            session = SessionQueries.get_active_session(client["id"])
            if not session:
                session = SessionQueries.create(client["id"])
            MessageQueries.create(
                session_id=session["id"],
                client_id=client["id"],
                sender="client",
                content=text or "[media]",
            )
            logger.info("Bot disabled: stored message from %s without responding", phone_number)
        except Exception as e:
            logger.error("Failed to store message while bot disabled: %s", e)
        return

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
        logger.error("Webhook error phone=%s: %s\n%s", phone_number, e, error_detail)

        # Notify about the error
        error_msg = (
            "Désolé, je rencontre un problème technique. "
            "Un conseiller va vous répondre rapidement."
        )
        try:
            await whatsapp_service.send_text_message(phone_number, error_msg)
        except Exception as send_err:
            logger.error("Failed to send error message to %s: %s", phone_number, send_err)


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
                logger.error("Cron: failed to send timeout msg to %s: %s", phone, e)
                
            results.append({"session_id": sid, "phone": phone, "status": "handed_off"})
            
        return {"status": "ok", "processed": len(results), "details": results}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {"status": "error", "error": str(e), "traceback": error_detail}


# ============================================
# DASHBOARD API ENDPOINTS
# ============================================

@app.api_route("/api/dashboard/health", methods=["GET", "HEAD"])
async def health_check():
    """Health check endpoint — accepts GET and HEAD for UptimeRobot keep-alive."""
    return {"status": "ok", "bot_enabled": session_manager.is_bot_enabled()}


@app.post("/api/debug/test-message")
async def debug_test_message(request: Request):
    """Debug endpoint to test bot message processing directly."""
    require_dev_env()
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
    require_dev_env()
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
    require_dev_env()
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


@app.get("/api/dashboard/clients")
async def get_clients(search: Optional[str] = None):
    """CRM: list all clients with aggregated data."""
    from api.db.connection import execute_query

    conditions = ["1=1"]
    params: list = []

    if search:
        conditions.append("(c.phone_number ILIKE %s OR c.first_name ILIKE %s OR c.last_name ILIKE %s)")
        term = f"%{search}%"
        params.extend([term, term, term])

    where = " AND ".join(conditions)

    clients = execute_query(
        f"""SELECT
            c.id,
            c.phone_number,
            c.first_name,
            c.last_name,
            c.client_type,
            c.created_at AS first_contact,
            COUNT(DISTINCT s.id) AS session_count,
            COUNT(DISTINCT o.id) AS order_count,
            MAX(s.updated_at) AS last_activity,
            (SELECT ai_summary FROM sessions WHERE client_id = c.id
             AND ai_summary IS NOT NULL ORDER BY updated_at DESC LIMIT 1) AS last_summary,
            (SELECT order_type FROM orders WHERE client_id = c.id
             ORDER BY created_at DESC LIMIT 1) AS last_order_type,
            (SELECT status FROM orders WHERE client_id = c.id
             ORDER BY created_at DESC LIMIT 1) AS last_order_status,
            COALESCE(SUM(o.estimated_price), 0)::bigint AS total_revenue
        FROM clients c
        LEFT JOIN sessions s ON s.client_id = c.id
        LEFT JOIN orders o ON o.client_id = c.id
        WHERE {where}
        GROUP BY c.id
        HAVING COUNT(DISTINCT o.id) > 0
        ORDER BY MAX(s.updated_at) DESC NULLS LAST
        LIMIT 200""",
        tuple(params) if params else None,
        fetch_all=True
    )
    return {"clients": clients or []}


@app.get("/api/dashboard/clients/{client_id}/orders")
async def get_client_orders(client_id: str):
    """CRM: get all orders for a specific client."""
    from api.db.connection import execute_query
    orders = execute_query(
        """SELECT * FROM orders WHERE client_id = %s ORDER BY created_at DESC""",
        (client_id,), fetch_all=True
    )
    return {"orders": orders or []}


@app.get("/api/dashboard/sessions")
async def get_sessions(status: Optional[str] = None, hide_test: bool = False, search: Optional[str] = None):
    """Get sessions for dashboard inbox, sorted by most recent activity."""
    from api.db.connection import execute_query

    # Build WHERE clauses
    conditions = ["s.status != 'CLOSED'"]
    params: list = []

    if status:
        conditions = [f"s.status = %s"]
        params.append(status)

    # Exclude test/seed phone numbers when hide_test=True
    if hide_test:
        conditions.append(
            "c.phone_number NOT SIMILAR TO '%(test|seed|0000|1111|2222|3333|4444|5555|6666|7777|8888|9999)%'"
        )
        conditions.append("c.phone_number NOT LIKE '+1555%'")

    # Search by phone number or first name
    if search:
        conditions.append("(c.phone_number ILIKE %s OR c.first_name ILIKE %s OR c.last_name ILIKE %s)")
        term = f"%{search}%"
        params.extend([term, term, term])

    where = " AND ".join(conditions)

    sessions = execute_query(
        f"""SELECT s.*, c.phone_number, c.first_name, c.last_name, c.client_type
        FROM sessions s JOIN clients c ON s.client_id = c.id
        WHERE {where}
        ORDER BY s.updated_at DESC LIMIT 100""",
        tuple(params) if params else None,
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
        logger.error("Takeover error: %s", e)

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
        logger.error("Release error: %s", e)

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
    """Global kill-switch: enable/disable bot. Requires agent auth."""
    agent = await get_current_agent(request)
    require_auth(agent)
    body = await request.json()
    enabled = body.get("enabled", True)
    session_manager.set_bot_enabled(enabled)
    return {"bot_enabled": enabled}


@app.post("/api/debug/test-billetterie")
async def test_billetterie_flow():
    """End-to-end test: simulate a billetterie conversation and verify order creation."""
    require_dev_env()
    from api.db.queries import ClientQueries, SessionQueries, MessageQueries, OrderQueries
    from api.db.connection import execute_query
    import json as _json

    results = {"steps": []}
    session_id = None
    client_id = None

    try:
        # 1. Get or create test client
        client = ClientQueries.find_by_phone("TEST_BILLETTERIE_BOT")
        if not client:
            client = ClientQueries.create("TEST_BILLETTERIE_BOT", first_name="Test Bot")
        client_id = client["id"]
        results["steps"].append({"step": "client", "id": client_id})

        # 2. Create a fresh session
        session = SessionQueries.create(client_id, status="BOT_ACTIVE", intent="BILLETTERIE")
        session_id = session["id"]
        results["steps"].append({"step": "session", "id": session_id, "status": session["status"]})

        # 3. Insert realistic billetterie conversation messages
        msgs = [
            ("client", "Bonjour, je voudrais réserver un billet d'avion"),
            ("bot", "Bonjour ! Avec plaisir, je vais vous aider pour votre réservation. Quel est votre trajet ? (ville de départ et destination)"),
            ("client", "Douala vers Paris"),
            ("bot", "Parfait ! Quelles sont vos dates de voyage souhaitées ?"),
            ("client", "Départ le 15 juillet, retour le 30 juillet"),
            ("bot", "C'est noté. Combien de passagers voyageront ?"),
            ("client", "2 passagers adultes"),
            ("bot", "En quelle classe souhaitez-vous voyager ? (Économique, Affaires, Première)"),
            ("client", "Classe économique"),
            ("bot", "Pour finaliser votre dossier, pourrais-je avoir votre nom complet s'il vous plaît ?"),
            ("client", "Jean-Pierre Kamga"),
            ("bot", "Merci M. Kamga. Votre commande a bien été prise en compte. Nous vous recontacterons très prochainement."),
        ]
        for sender, content in msgs:
            MessageQueries.create(session_id=session_id, client_id=client_id, sender=sender, content=content)
        results["steps"].append({"step": "messages", "count": len(msgs)})

        # 4. Call generate_handoff_summary (this calls the LLM)
        summary_str = await djama_agent.generate_handoff_summary(session_id)
        clean = summary_str.replace("```json", "").replace("```", "").strip()
        summary = _json.loads(clean)
        results["steps"].append({
            "step": "handoff_summary",
            "raw": summary_str[:500],
            "parsed_order_type": summary.get("order_type"),
            "parsed_client_name": summary.get("client_name"),
            "parsed_origin": summary.get("origin"),
            "parsed_destination": summary.get("destination"),
            "parsed_shipping_mode": summary.get("shipping_mode"),
        })

        # 5. Create order using the same logic as _finalize_order
        order_type = summary.get("order_type", "AUTRE")
        order_data = {
            "origin": summary.get("origin"),
            "destination": summary.get("destination"),
            "weight_kg": summary.get("weight_kg"),
            "dimensions": summary.get("dimensions"),
            "goods_nature": summary.get("goods_nature"),
            "shipping_mode": summary.get("shipping_mode"),
            "notes": summary.get("notes", "Test billetterie"),
        }
        est_price_raw = summary.get("estimated_price")
        est_price = int(est_price_raw) if est_price_raw and str(est_price_raw).isdigit() else None

        order = OrderQueries.create(client_id, order_type, order_data, est_price)
        results["steps"].append({
            "step": "order_created",
            "order_number": order.get("order_number"),
            "order_type": order.get("order_type"),
            "status": order.get("status"),
        })

        # 6. Verify the order type is BILLETTERIE
        is_correct = order.get("order_type") == "BILLETTERIE"
        results["test_passed"] = is_correct
        results["verdict"] = "BILLETTERIE correctly classified!" if is_correct else f"Got {order.get('order_type')} instead of BILLETTERIE"

    except Exception as e:
        import traceback
        results["steps"].append({"step": "error", "error": str(e), "traceback": traceback.format_exc()})
        results["test_passed"] = False
        results["verdict"] = f"Error: {e}"

    # 7. Cleanup
    try:
        if session_id:
            execute_query("DELETE FROM messages WHERE session_id = %s", (session_id,))
            execute_query("DELETE FROM sessions WHERE id = %s", (session_id,))
        if client_id:
            execute_query("DELETE FROM orders WHERE client_id = %s", (client_id,))
            execute_query("DELETE FROM clients WHERE id = %s", (client_id,))
        results["cleanup"] = "done"
    except Exception as ce:
        results["cleanup"] = f"error: {ce}"

    return results


@app.post("/api/debug/test-vision")
async def test_vision_flow():
    """End-to-end test: simulate a photo upload and verify the bot doesn't ask for weight if it's in the photo."""
    require_dev_env()
    from api.db.queries import ClientQueries, SessionQueries, MessageQueries, OrderQueries
    from api.db.connection import execute_query
    import json as _json

    results = {"steps": []}
    session_id = None
    client_id = None

    try:
        # 1. Get or create test client
        client = ClientQueries.find_by_phone("TEST_VISION_BOT")
        if not client:
            client = ClientQueries.create("TEST_VISION_BOT", first_name="Test Vision")
        client_id = client["id"]
        
        # 2. Create session
        session = SessionQueries.create(client_id, status="BOT_ACTIVE", intent="FRET")
        session_id = session["id"]

        # 3. Simulate vision data extraction (as if a photo with weight=20kg and dims=50x50x50 was uploaded)
        vision_data = {
            "dimensions": {"length_cm": 50, "width_cm": 50, "height_cm": 50},
            "weight_kg": 20,
            "goods_nature": "Vêtements",
            "quantity": 1,
            "hazard_icons": [],
            "is_sensitive": False,
            "confidence": "high"
        }

        # 4. First interaction: user sends photo and asks for price
        MessageQueries.create(session_id=session_id, client_id=client_id, sender="client", content="Voici la photo de mon colis pour Douala. Quel est le prix ?")
        
        # 5. Build context including vision data
        context = djama_agent._build_context(client, session, "TEST_VISION_BOT", vision_data=vision_data)
        results["steps"].append({"step": "context", "content": context})
        
        # 6. Ask AI for response
        bot_response = await djama_agent._get_ai_response("TEST_VISION_BOT", "Voici la photo de mon colis pour Douala. Quel est le prix ?", context)
        results["steps"].append({"step": "bot_response", "content": bot_response})
        
        # 7. Verification: The bot should NOT ask for weight or dimensions, but SHOULD ask for Origin (since destination is Douala)
        bot_lower = bot_response.lower()
        asked_weight = "poids" in bot_lower
        asked_dims = "dimension" in bot_lower
        asked_origin = "départ" in bot_lower or "origine" in bot_lower or "où" in bot_lower
        
        results["test_passed"] = (not asked_weight) and (not asked_dims) and asked_origin
        results["verdict"] = f"Weight asked: {asked_weight}, Dims asked: {asked_dims}, Origin asked: {asked_origin}"

    except Exception as e:
        import traceback
        results["steps"].append({"step": "error", "error": str(e), "traceback": traceback.format_exc()})
        results["test_passed"] = False

    # 8. Cleanup
    try:
        if session_id:
            execute_query("DELETE FROM messages WHERE session_id = %s", (session_id,))
            execute_query("DELETE FROM sessions WHERE id = %s", (session_id,))
        if client_id:
            execute_query("DELETE FROM orders WHERE client_id = %s", (client_id,))
            execute_query("DELETE FROM clients WHERE id = %s", (client_id,))
    except Exception:
        pass

    return results


@app.post("/api/migrate")
async def run_migration(request: Request):
    """One-shot migration: convert order_type ENUM to TEXT + add is_read column. Admin only."""
    agent = await get_current_agent(request)
    require_auth(agent)
    if agent.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Réservé aux admins")
    from api.db.connection import execute_ddl
    results = []

    try:
        execute_ddl("ALTER TABLE orders ALTER COLUMN order_type TYPE TEXT;")
        results.append("order_type converted to TEXT")
    except Exception as e:
        results.append(f"order_type conversion: {e}")

    try:
        execute_ddl("ALTER TABLE orders ADD COLUMN is_read BOOLEAN DEFAULT false;")
        results.append("is_read column added")
    except Exception as e:
        results.append(f"is_read column: {e}")

    try:
        execute_ddl("ALTER TABLE sessions ALTER COLUMN session_intent TYPE TEXT;")
        results.append("session_intent converted to TEXT")
    except Exception as e:
        results.append(f"session_intent conversion: {e}")

    return {"status": "ok", "results": results}

@app.get("/api/dashboard/orders/badges")
async def get_order_badges():
    """Get count of unread (is_read=false) orders grouped by type."""
    from api.db.connection import execute_query
    try:
        # Try with is_read column first
        res = execute_query(
            "SELECT order_type, COUNT(*) as count FROM orders WHERE is_read = false GROUP BY order_type",
            fetch_all=True
        )
    except Exception:
        # Fallback if is_read column doesn't exist yet: count all NOUVEAU orders
        try:
            res = execute_query(
                "SELECT order_type, COUNT(*) as count FROM orders WHERE status = 'NOUVEAU' GROUP BY order_type",
                fetch_all=True
            )
        except Exception:
            return {"status": "ok", "badges": {}}
    badges = {r["order_type"]: r["count"] for r in (res or [])}
    total = sum(badges.values())
    badges["TOTAL"] = total
    return {"status": "ok", "badges": badges}

@app.post("/api/dashboard/orders/{order_id}/read")
async def mark_order_read(order_id: str):
    """Mark an order as read."""
    from api.db.connection import execute_query
    execute_query("UPDATE orders SET is_read = true WHERE id = %s", (order_id,), fetch_one=False)
    return {"status": "ok"}

class OrderStatusUpdate(BaseModel):
    status: str

@app.post("/api/dashboard/orders/{order_id}/status")
async def update_order_status(order_id: str, payload: OrderStatusUpdate):
    """Update the status of an order."""
    from api.db.queries import OrderQueries
    updated = OrderQueries.update_status(order_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"status": "ok", "order_status": payload.status}

@app.get("/api/dashboard/orders")
async def get_orders(order_type: Optional[str] = None, status: Optional[str] = None):
    """Get orders for the order management board."""
    from api.db.connection import execute_query

    conditions = ["1=1"]
    params = []

    if order_type:
        # Map new dashboard tab keys to also include legacy ENUM values
        type_map = {
            "FRET_AERIEN": ["FRET_AERIEN", "FRET"],
            "FRET_MARITIME": ["FRET_MARITIME"],
        }
        types_to_match = type_map.get(order_type, [order_type])
        placeholders = ", ".join(["%s"] * len(types_to_match))
        conditions.append(f"o.order_type IN ({placeholders})")
        params.extend(types_to_match)
    if status:
        conditions.append("o.status = %s")
        params.append(status)

    try:
        orders = execute_query(
            f"""SELECT o.*, c.phone_number, c.first_name, c.last_name
            FROM orders o JOIN clients c ON o.client_id = c.id
            WHERE {' AND '.join(conditions)}
            ORDER BY o.is_read ASC, o.created_at DESC LIMIT 50""",
            tuple(params) if params else None,
            fetch_all=True
        )
    except Exception:
        # Fallback if is_read column doesn't exist yet
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
    """Update app settings. Requires agent auth."""
    agent = await get_current_agent(request)
    require_auth(agent)
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


@app.get("/api/dashboard/ai/prompt")
async def get_ai_prompt():
    """Get the current AI system prompt (DB override or hardcoded default)."""
    from api.db.connection import execute_query
    from api.bot.prompts import SYSTEM_PROMPT
    row = execute_query(
        "SELECT value FROM settings WHERE key = 'system_prompt'",
        fetch_one=True
    )
    prompt = row["value"] if row else SYSTEM_PROMPT
    is_custom = bool(row)
    return {"prompt": prompt, "is_custom": is_custom}


@app.post("/api/dashboard/ai/prompt")
async def save_ai_prompt(request: Request):
    """Save a custom AI system prompt to the DB. Requires auth."""
    agent = await get_current_agent(request)
    require_auth(agent)
    from api.db.connection import execute_query
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Le prompt ne peut pas être vide")
    execute_query(
        """INSERT INTO settings (id, key, value)
        VALUES (gen_random_uuid(), 'system_prompt', %s)
        ON CONFLICT (key) DO UPDATE SET value = %s""",
        (prompt, prompt)
    )
    return {"status": "saved"}


@app.delete("/api/dashboard/ai/prompt")
async def reset_ai_prompt(request: Request):
    """Reset the AI system prompt to the hardcoded default."""
    agent = await get_current_agent(request)
    require_auth(agent)
    from api.db.connection import execute_query
    execute_query("DELETE FROM settings WHERE key = 'system_prompt'")
    return {"status": "reset"}
