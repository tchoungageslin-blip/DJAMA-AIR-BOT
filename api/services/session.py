import json
import redis
from typing import Optional, Dict, Any
from api.config import settings


class SessionManager:
    """Manages conversation context in Redis for real-time session state."""

    def __init__(self):
        self._redis = None

    @property
    def redis_client(self):
        if self._redis is None:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    def _key(self, phone_number: str) -> str:
        return f"session:{phone_number}"

    def get_context(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get the current conversation context for a phone number."""
        data = self.redis_client.get(self._key(phone_number))
        if data:
            return json.loads(data)
        return None

    def set_context(self, phone_number: str, context: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Set conversation context with TTL (default 1 hour)."""
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
        # Keep only last 20 messages in context for token efficiency
        if len(context["messages"]) > 20:
            context["messages"] = context["messages"][-20:]
        self.set_context(phone_number, context)

    def get_message_history(self, phone_number: str) -> list:
        """Get conversation history from context."""
        context = self.get_context(phone_number) or {}
        return context.get("messages", [])

    def clear_context(self, phone_number: str) -> None:
        """Clear the conversation context."""
        self.redis_client.delete(self._key(phone_number))

    def set_bot_enabled(self, enabled: bool) -> None:
        """Global kill-switch for the bot."""
        self.redis_client.set("bot:global_enabled", "1" if enabled else "0")

    def is_bot_enabled(self) -> bool:
        """Check if the bot is globally enabled."""
        val = self.redis_client.get("bot:global_enabled")
        if val is None:
            return True  # Default to enabled
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
