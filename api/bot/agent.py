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
        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="client",
            content=message_text or "[media]",
            media_url=None,
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

        # 8. Store bot response
        MessageQueries.create(
            session_id=session["id"],
            client_id=client["id"],
            sender="bot",
            content=response
        )

        # 9. Update session context in Redis
        session_manager.add_message_to_history(phone_number, "user", message_text or "[media envoyé]")
        session_manager.add_message_to_history(phone_number, "assistant", response)

        return response

    async def _process_media(self, media_data: bytes, media_type: str) -> Optional[Dict]:
        """Process incoming media (image/document) with vision AI."""
        try:
            result = vision_processor.analyze_image(media_data, media_type)
            return result
        except Exception as e:
            return None

    def _check_sensitive_text(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if message text contains sensitive keywords."""
        text_lower = text.lower()
        for keyword in SENSITIVE_KEYWORDS:
            if keyword in text_lower:
                return True, keyword
        return False, None

    def _build_context(self, client: Dict, session: Dict, phone_number: str,
                       vision_data: Optional[Dict] = None) -> str:
        """Build additional context for the AI prompt."""
        context_parts = []

        # Client info
        if client.get("first_name"):
            context_parts.append(f"Client: {client.get('first_name', '')} {client.get('last_name', '')}")
            context_parts.append(f"Type: {client.get('client_type', 'NEW')}")

        # Preferences
        prefs = ClientQueries.get_preferences(client["id"])
        if prefs:
            if prefs.get("frequent_destinations"):
                context_parts.append(f"Destinations fréquentes: {', '.join(prefs['frequent_destinations'])}")
            if prefs.get("frequent_goods"):
                context_parts.append(f"Marchandises fréquentes: {', '.join(prefs['frequent_goods'])}")

        # Session state from Redis
        redis_context = session_manager.get_context(phone_number)
        if redis_context:
            if redis_context.get("current_lead"):
                context_parts.append(f"Données en cours: {json.dumps(redis_context['current_lead'], ensure_ascii=False)}")

        # Vision data
        if vision_data:
            context_parts.append(f"Données extraites de l'image: {json.dumps(vision_data, ensure_ascii=False)}")
            # Pre-calculate price if we have enough data
            if vision_data.get("weight_kg"):
                dims = vision_data.get("dimensions", {})
                estimate = pricing_engine.estimate_aerien(
                    weight=vision_data["weight_kg"],
                    origin="chine",
                    length_cm=dims.get("length_cm"),
                    width_cm=dims.get("width_cm"),
                    height_cm=dims.get("height_cm")
                )
                context_parts.append(f"Estimation calculée: {json.dumps(estimate, ensure_ascii=False)}")

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
                               phone_number: str, reason: str, tags: list = None) -> str:
        """Trigger human handoff for sensitive cases."""
        # Update session status
        SessionQueries.update_status(
            session["id"], "HUMAN_HANDOFF",
            ai_summary=reason
        )

        # Add tags
        if tags:
            for tag in tags:
                SessionQueries.add_tag(session["id"], tag)

        # Disable bot for this session
        session_manager.disable_bot_for_session(phone_number)

        # Send notifications
        await notification_service.notify_handoff(
            client_phone=phone_number,
            session_id=session["id"],
            summary=reason,
            tags=tags
        )

        # Return handoff message to client
        return (
            "⚠️ Votre demande nécessite l'attention d'un conseiller spécialisé.\n\n"
            "Un membre de notre équipe va prendre le relais très rapidement. "
            "Merci de patienter un instant. 🙏"
        )

    async def generate_handoff_summary(self, session_id: str) -> str:
        """Generate a structured summary for handoff."""
        messages = MessageQueries.get_session_messages(session_id)
        conversation = "\n".join([
            f"{'Client' if m['sender'] == 'client' else 'Bot'}: {m['content']}"
            for m in messages
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
