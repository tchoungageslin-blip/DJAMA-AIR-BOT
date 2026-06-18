import json
import traceback
from typing import Dict, Optional, Tuple
from openai import AsyncOpenAI
from api.config import settings
from api.bot.prompts import SYSTEM_PROMPT, HANDOFF_SUMMARY_PROMPT
from api.bot.pricing import pricing_engine
from api.bot.vision import vision_processor
from api.services.session import session_manager
from api.services.whatsapp import whatsapp_service
from api.services.notifications import notification_service
from api.db.queries import ClientQueries, SessionQueries, LeadQueries, MessageQueries


SENSITIVE_KEYWORDS = [
    "batterie", "battery", "pile", "lithium",
    "liquide", "liquid", "cosmétique", "cosmetic", "parfum", "perfume",
    "pharmaceutique", "pharmaceutical", "médicament", "medicine", "drug",
    "machine industrielle", "industrial machine",
]


class DjamaAgent:
    """Main AI agent orchestrating the conversation flow."""

    def _create_openai_client(self) -> AsyncOpenAI:
        """Create a fresh OpenAI client per request to avoid stale connections on Vercel serverless."""
        return AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            max_retries=2,
            timeout=25.0,
        )

    async def handle_message(self, phone_number: str, message_text: str,
                             media_data: bytes = None, media_type: str = None) -> str:
        """
        Main entry point: process an incoming message and return the bot response.
        """
        # 1. Check if bot is active for this session
        if not session_manager.is_bot_active_for_session(phone_number):
            return None  # Bot disabled, agent handles

        # 2. Identify or create client
        client = ClientQueries.find_by_phone(phone_number)
        if not client:
            client = ClientQueries.create(phone_number)

        # 3. Get or create session
        session = SessionQueries.get_active_session(client["id"])
        if not session:
            session = SessionQueries.create(client["id"])

        # 4. Store incoming message
        import base64
        media_url_db = None
        if media_data and media_type:
            try:
                base64_img = base64.b64encode(media_data).decode('utf-8')
                media_url_db = f"data:{media_type};base64,{base64_img}"
            except Exception:
                pass

        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="client",
            content=message_text or "[media]",
            media_url=media_url_db,
            media_type=media_type
        )

        # 5. Process media if present
        vision_data = None
        if media_data and media_type:
            vision_data = await self._process_media(media_data, media_type)
            if vision_data:
                # Check for sensitive content
                is_sensitive, reason = vision_processor.check_sensitive_content(vision_data)
                if is_sensitive:
                    return await self._trigger_handoff(
                        client, session, phone_number,
                        f"CAS SENSIBLE détecté via image: {reason}",
                        tags=["CAS_SENSIBLE", reason.upper()]
                    )

        # 6. Check for sensitive keywords in text
        if message_text:
            is_sensitive, keyword = self._check_sensitive_text(message_text)
            if is_sensitive:
                return await self._trigger_handoff(
                    client, session, phone_number,
                    f"CAS SENSIBLE détecté: {keyword}",
                    tags=["CAS_SENSIBLE", keyword.upper()]
                )

        # 7. Build context and get AI response
        context = self._build_context(client, session, phone_number, vision_data)
        response = await self._get_ai_response(phone_number, message_text, context)

        # 8. Check for manual handoff triggered by the LLM
        if "[ACTION: TRANSFERT]" in response:
            response = response.replace("[ACTION: TRANSFERT]", "").strip()
            # This is a normal order completion, NOT a hard handoff
            return await self._finalize_order(
                client, session, phone_number,
                response
            )

        # 9. Proactive name persistence: save client name to DB as soon as bot uses it
        if not client.get("first_name"):
            self._try_extract_and_save_name(client, response, message_text)

        # 10. Store bot response
        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="bot",
            content=response
        )

        # 11. Update session context in Redis
        session_manager.add_message_to_history(phone_number, "user", message_text or "[media envoyé]")
        session_manager.add_message_to_history(phone_number, "assistant", response)

        return response

    async def _process_media(self, media_data: bytes, media_type: str) -> Optional[Dict]:
        """Process incoming media (image/document) with vision AI."""
        try:
            result = await vision_processor.analyze_image(media_data, media_type)
            return result
        except Exception as e:
            print(f"[VISION ERROR] {e}")
            return None

    def _try_extract_and_save_name(self, client: Dict, bot_response: str, user_message: str) -> None:
        """Try to extract client name from conversation and persist to DB.
        Detects patterns like 'M. Kamga', 'Mme Dupont', or direct name mentions."""
        import re
        try:
            # Pattern 1: Bot addresses client by name in response (most reliable)
            patterns = [
                r"(?:Bonjour|Ravi|Content|Merci)\s+(?:M\.|Mme|Mr|Mrs|Monsieur|Madame)?\s*([A-ZÀ-Ü][a-zà-ü]+(?:[- ][A-ZÀ-Ü][a-zà-ü]+)*)",
                r"(?:M\.|Mme|Mr|Monsieur|Madame)\s+([A-ZÀ-Ü][a-zà-ü]+(?:[- ][A-ZÀ-Ü][a-zà-ü]+)*)",
            ]
            for pattern in patterns:
                match = re.search(pattern, bot_response)
                if match:
                    name = match.group(1).strip()
                    # Skip generic words that aren't names
                    skip = {"Air", "Logistics", "Djama", "Bonjour", "Bienvenue", "WhatsApp"}
                    if name and name not in skip and len(name) > 1:
                        ClientQueries.update(client["id"], first_name=name)
                        print(f"[MEMORY] Saved client name: {name} (from bot response)")
                        return

            # Pattern 2: User introduced themselves "je suis X" or "je m'appelle X"
            if user_message:
                intro_patterns = [
                    r"(?:je suis|je m'appelle|mon nom est|c'est|moi c'est)\s+([A-ZÀ-Ü][a-zà-ü]+(?:[- ][A-ZÀ-Ü][a-zà-ü]+)*)",
                ]
                for pattern in intro_patterns:
                    match = re.search(pattern, user_message, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                        if name and len(name) > 1:
                            ClientQueries.update(client["id"], first_name=name)
                            print(f"[MEMORY] Saved client name: {name} (from user message)")
                            return
        except Exception as e:
            print(f"[MEMORY] Name extraction error: {e}")

    def _check_sensitive_text(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if message text contains sensitive keywords."""
        text_lower = text.lower()
        for keyword in SENSITIVE_KEYWORDS:
            if keyword in text_lower:
                return True, keyword
        return False, None

    def _build_context(self, client: Dict, session: Dict, phone_number: str,
                       vision_data: Optional[Dict] = None) -> str:
        """Build additional context for the AI prompt including persistent client memory."""
        from api.db.queries import OrderQueries as _OQ
        context_parts = []

        # === PERSISTENT MEMORY (from PostgreSQL - survives across sessions) ===
        client_name = client.get("first_name") or ""
        client_last = client.get("last_name") or ""
        full_name = f"{client_name} {client_last}".strip()

        if full_name:
            context_parts.append(f"[MEMOIRE] Nom du client: {full_name}")
            context_parts.append(f"[MEMOIRE] Type client: {client.get('client_type', 'NEW')}")
        else:
            context_parts.append("[MEMOIRE] Client inconnu (nom pas encore collecte)")

        # Order history - critical for client valorization
        try:
            past_orders = _OQ.get_client_orders(client["id"], limit=5)
            if past_orders:
                context_parts.append(f"[MEMOIRE] Client fidele avec {len(past_orders)} commande(s) recente(s):")
                for o in past_orders:
                    data = o.get("data") or {}
                    if isinstance(data, str):
                        data = json.loads(data)
                    origin = data.get("origin", "?")
                    dest = data.get("destination", "?")
                    notes = data.get("notes", "")
                    date_str = str(o.get("created_at", ""))[:10]
                    context_parts.append(
                        f"  - {o['order_number']} ({o['order_type']}) {origin} -> {dest} | {o['status']} | {date_str}"
                    )
                    if notes:
                        context_parts.append(f"    Details: {notes[:100]}")
            else:
                context_parts.append("[MEMOIRE] Nouveau client, aucune commande precedente")
        except Exception:
            pass

        # Preferences
        prefs = ClientQueries.get_preferences(client["id"])
        if prefs:
            if prefs.get("frequent_destinations"):
                context_parts.append(f"[MEMOIRE] Destinations frequentes: {', '.join(prefs['frequent_destinations'])}")
            if prefs.get("frequent_goods"):
                context_parts.append(f"[MEMOIRE] Marchandises frequentes: {', '.join(prefs['frequent_goods'])}")

        # === SESSION CONTEXT (from Redis - current conversation only) ===
        redis_context = session_manager.get_context(phone_number)
        if redis_context:
            if redis_context.get("current_lead"):
                context_parts.append(f"[SESSION] Donnees en cours: {json.dumps(redis_context['current_lead'], ensure_ascii=False)}")

        # Vision data
        if vision_data:
            context_parts.append(f"[SESSION] Donnees extraites de l'image: {json.dumps(vision_data, ensure_ascii=False)}")
            if vision_data.get("weight_kg"):
                dims = vision_data.get("dimensions", {})
                estimate = pricing_engine.estimate_aerien(
                    weight=vision_data["weight_kg"],
                    origin="chine",
                    length_cm=dims.get("length_cm"),
                    width_cm=dims.get("width_cm"),
                    height_cm=dims.get("height_cm")
                )
                context_parts.append(f"[SESSION] Estimation calculee: {json.dumps(estimate, ensure_ascii=False)}")

        return "\n".join(context_parts)

    async def _get_ai_response(self, phone_number: str, user_message: str, context: str) -> str:
        """Get response from GPT-4o via OpenRouter."""
        # Build messages array with history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if context:
            messages.append({"role": "system", "content": f"CONTEXTE ACTUEL:\n{context}"})

        # Add conversation history from Redis
        history = session_manager.get_message_history(phone_number)
        for msg in history[-10:]:  # Last 10 messages for context window
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current message
        messages.append({"role": "user", "content": user_message or "[Le client a envoyé un média]"})

        # Fresh client per request to prevent stale serverless connections
        client = self._create_openai_client()
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AGENT LLM ERROR] {type(e).__name__}: {e}")
            print(f"[AGENT LLM TRACEBACK] {traceback.format_exc()}")
            raise
        finally:
            await client.close()

    async def _trigger_handoff(self, client: Dict, session: Dict,
                               phone_number: str, reason: str, tags: list = None,
                               handoff_message: str = None) -> str:
        """Trigger human handoff for sensitive cases or completed qualification."""
        from api.db.queries import OrderQueries

        # 1. Generate structured JSON summary from conversation
        summary_json_str = await self.generate_handoff_summary(session["id"])
        summary_data = {}
        
        try:
            # Parse JSON safely (sometimes LLM wraps in ```json)
            clean_str = summary_json_str.replace("```json", "").replace("```", "").strip()
            summary_data = json.loads(clean_str)
            
            # Create Order
            order_data = {
                "origin": summary_data.get("origin"),
                "destination": summary_data.get("destination"),
                "weight_kg": summary_data.get("weight_kg"),
                "dimensions": summary_data.get("dimensions"),
                "goods_nature": summary_data.get("goods_nature"),
                "fragility": summary_data.get("fragility", "STANDARD"),
                "shipping_mode": summary_data.get("shipping_mode"),
                "is_sensitive": summary_data.get("is_sensitive", False),
                "notes": summary_data.get("notes", reason)
            }
            order_type = summary_data.get("order_type", "AUTRE")
            print(f"[HANDOFF] LLM returned order_type={order_type}")
            est_price_raw = summary_data.get("estimated_price")
            est_price = int(est_price_raw) if est_price_raw and str(est_price_raw).isdigit() else None
            
            OrderQueries.create(client["id"], order_type, order_data, est_price)
            
            # Update client name if found and missing
            extracted_name = summary_data.get("client_name")
            if extracted_name and str(extracted_name).lower() != "null" and not client.get("first_name"):
                ClientQueries.update(client["id"], first_name=extracted_name)
                
        except Exception as e:
            print(f"[HANDOFF] Error parsing summary or creating order: {e}")
            print(f"[HANDOFF] Raw LLM output was: {summary_json_str}")
            summary_data = {"notes": f"{reason} | Erreur JSON: {summary_json_str}"}
            try:
                OrderQueries.create(
                    client["id"], 
                    "AUTRE", 
                    {"notes": summary_data["notes"], "error": str(e)}, 
                    None
                )
            except Exception as fallback_e:
                print(f"[HANDOFF] CRITICAL: Fallback order creation failed: {fallback_e}")

        # 2. Update session status
        SessionQueries.update_status(
            session["id"], "HUMAN_HANDOFF",
            ai_summary=summary_data.get("notes", reason)
        )

        # 3. Add tags
        if tags:
            for tag in tags:
                SessionQueries.add_tag(session["id"], tag)

        # 4. Disable bot for this session
        session_manager.disable_bot_for_session(phone_number)

        # 5. Send notifications
        await notification_service.notify_handoff(
            client_phone=phone_number,
            session_id=session["id"],
            summary=summary_data.get("notes", reason),
            tags=tags
        )

        # 6. Store the final handoff message from the bot in the DB
        final_response = handoff_message or (
            "Votre demande nécessite l'attention d'un conseiller spécialisé.\n\n"
            "Un membre de notre équipe va prendre le relais très rapidement. "
            "Merci de patienter un instant."
        )
        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="bot",
            content=final_response
        )

        return final_response

    async def _finalize_order(self, client: Dict, session: Dict, phone_number: str, bot_response: str) -> str:
        """Process a completed order qualification WITHOUT blocking the bot."""
        from api.db.queries import OrderQueries

        # 1. Generate structured JSON summary from conversation
        summary_json_str = await self.generate_handoff_summary(session["id"])
        summary_data = {}
        
        try:
            clean_str = summary_json_str.replace("```json", "").replace("```", "").strip()
            summary_data = json.loads(clean_str)
            
            # Create Order
            order_data = {
                "origin": summary_data.get("origin"),
                "destination": summary_data.get("destination"),
                "weight_kg": summary_data.get("weight_kg"),
                "dimensions": summary_data.get("dimensions"),
                "goods_nature": summary_data.get("goods_nature"),
                "fragility": summary_data.get("fragility", "STANDARD"),
                "shipping_mode": summary_data.get("shipping_mode"),
                "is_sensitive": summary_data.get("is_sensitive", False),
                "notes": summary_data.get("notes", "Commande finalisée")
            }
            order_type = summary_data.get("order_type", "AUTRE")
            print(f"[ORDER] LLM returned order_type={order_type} for session {session['id']}")
            est_price_raw = summary_data.get("estimated_price")
            est_price = int(est_price_raw) if est_price_raw and str(est_price_raw).isdigit() else None
            
            OrderQueries.create(client["id"], order_type, order_data, est_price)
            
            # Update client name if found and missing
            extracted_name = summary_data.get("client_name")
            if extracted_name and str(extracted_name).lower() != "null" and not client.get("first_name"):
                ClientQueries.update(client["id"], first_name=extracted_name)
                
        except Exception as e:
            print(f"[ORDER] Error parsing summary or creating order: {e}")
            print(f"[ORDER] Raw LLM output was: {summary_json_str}")
            summary_data = {"notes": f"Erreur système ou IA. Détails bruts: {summary_json_str}"}
            try:
                # Force fallback order creation to avoid silent drops
                OrderQueries.create(
                    client["id"], 
                    "AUTRE", 
                    {"notes": summary_data["notes"], "error": str(e)}, 
                    None
                )
            except Exception as fallback_e:
                print(f"[ORDER] CRITICAL: Fallback order creation failed: {fallback_e}")

        # Close the current session so next message starts fresh
        # This prevents mixing old conversation context with new requests
        SessionQueries.update_status(session["id"], "RESOLVED", ai_summary=summary_data.get("notes", "Commande finalisée"))

        # Clear Redis conversation history so next session starts clean
        session_manager.clear_context(phone_number)

        # Send notification to agents that a new order is ready
        await notification_service.notify_new_order(
            client_phone=phone_number,
            session_id=session["id"],
            summary=f"Nouvelle commande créée: {summary_data.get('notes', '')}",
            order_data=order_data,
        )

        # Store the bot response
        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="bot",
            content=bot_response
        )

        # Update Redis history so context continues
        session_manager.add_message_to_history(phone_number, "assistant", bot_response)

        return bot_response

    async def generate_handoff_summary(self, session_id: str) -> str:
        """Generate a structured summary for handoff."""
        messages = MessageQueries.get_session_messages(session_id)
        # Use only the last 15 messages to focus on the most recent request
        recent_messages = messages[-15:] if len(messages) > 15 else messages
        conversation = "\n".join([
            f"{'Client' if m['sender'] == 'client' else 'Bot'}: {m['content']}"
            for m in recent_messages
        ])

        client = self._create_openai_client()
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": HANDOFF_SUMMARY_PROMPT},
                    {"role": "user", "content": conversation}
                ],
                max_tokens=300,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        finally:
            await client.close()


djama_agent = DjamaAgent()
