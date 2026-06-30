import json
import logging
import redis
from typing import Optional, Dict, Any
from api.config import settings

logger = logging.getLogger("djama.session")


class SessionManager:
    """Manages conversation context in Redis for real-time session state.
    Falls back to in-memory dict when Redis is not configured."""

    def __init__(self):
        self._redis = None
        self._fallback = {}  # In-memory fallback when Redis unavailable
        self._use_fallback = not bool(settings.REDIS_URL)

    @property
    def redis_client(self):
        if self._use_fallback:
            return None
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )
                self._redis.ping()
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.warning("Redis unavailable (%s), using in-memory fallback", e)
                self._use_fallback = True
                return None
        else:
            # Verify connection is still alive on warm containers
            try:
                self._redis.ping()
            except Exception:
                logger.warning("Redis connection lost, reconnecting...")
                self._redis = None
                return self.redis_client  # Retry once
        return self._redis

    def _key(self, phone_number: str) -> str:
        return f"session:{phone_number}"

    def get_context(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get the current conversation context for a phone number."""
        if self._use_fallback:
            return self._fallback.get(self._key(phone_number))
        data = self.redis_client.get(self._key(phone_number))
        if data:
            return json.loads(data)
        return None

    def set_context(self, phone_number: str, context: Dict[str, Any], ttl_seconds: int = 86400) -> None:
        """Set conversation context with TTL (default 24 hours)."""
        if self._use_fallback:
            self._fallback[self._key(phone_number)] = context
            return
        self.redis_client.setex(
            self._key(phone_number),
            ttl_seconds,
            json.dumps(context, default=str)
        )

    def update_context(self, phone_number: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update specific fields in the conversation context."""
        context = self.get_context(phone_number) or {}
        context.update(updates)
        self.set_context(phone_number, context)
        return context

    def add_message_to_history(self, phone_number: str, role: str, content: str) -> None:
        """Add a message to the conversation history in context."""
        context = self.get_context(phone_number) or {}
        if "messages" not in context:
            context["messages"] = []
        context["messages"].append({"role": role, "content": content})
        if len(context["messages"]) > 20:
            context["messages"] = context["messages"][-20:]
        self.set_context(phone_number, context)

    def get_message_history(self, phone_number: str) -> list:
        """Get conversation history from context."""
        context = self.get_context(phone_number) or {}
        return context.get("messages", [])

    def clear_context(self, phone_number: str) -> None:
        """Clear the conversation context."""
        if self._use_fallback:
            self._fallback.pop(self._key(phone_number), None)
            return
        self.redis_client.delete(self._key(phone_number))

    def set_bot_enabled(self, enabled: bool) -> None:
        """Global kill-switch for the bot."""
        if self._use_fallback:
            self._fallback["bot:global_enabled"] = "1" if enabled else "0"
            return
        self.redis_client.set("bot:global_enabled", "1" if enabled else "0")

    def is_bot_enabled(self) -> bool:
        """Check if the bot is globally enabled."""
        if self._use_fallback:
            val = self._fallback.get("bot:global_enabled")
        else:
            val = self.redis_client.get("bot:global_enabled")
        if val is None:
            return True
        return val == "1"

    def disable_bot_for_session(self, phone_number: str) -> None:
        """Disable bot for a specific session (silent takeover)."""
        context = self.get_context(phone_number) or {}
        context["bot_disabled"] = True
        self.set_context(phone_number, context)

    def is_bot_active_for_session(self, phone_number: str) -> bool:
        """Check if bot is active for this specific session."""
        if not self.is_bot_enabled():
            return False
        context = self.get_context(phone_number) or {}
        return not context.get("bot_disabled", False)


session_manager = SessionManager()
