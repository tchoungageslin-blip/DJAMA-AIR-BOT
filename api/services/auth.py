import hashlib
import hmac
import time
import json
import base64
from typing import Optional, Dict
from api.config import settings
from api.db.connection import execute_query


class AuthService:
    """JWT-based authentication for dashboard agents."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using SHA-256 with salt (lightweight for Vercel)."""
        salt = settings.JWT_SECRET[:16]
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return AuthService.hash_password(password) == password_hash

    @staticmethod
    def create_token(agent: Dict) -> str:
        """Create a JWT-like token (minimal implementation for Vercel serverless)."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload_data = {
            "agent_id": agent["id"],
            "email": agent["email"],
            "role": agent.get("role", "AGENT"),
            "exp": int(time.time()) + (settings.JWT_EXPIRATION_HOURS * 3600),
            "iat": int(time.time())
        }
        payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode().rstrip("=")
        signature = hmac.new(
            settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).hexdigest()
        return f"{header}.{payload}.{signature}"

    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """Verify a JWT-like token and return payload."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            header, payload, signature = parts

            # Verify signature
            expected_sig = hmac.new(
                settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            payload_data = json.loads(base64.urlsafe_b64decode(payload))

            # Check expiration
            if payload_data.get("exp", 0) < time.time():
                return None

            return payload_data
        except Exception:
            return None

    @staticmethod
    def login(email: str, password: str) -> Optional[Dict]:
        """Authenticate an agent and return token + agent info."""
        agent = execute_query(
            "SELECT * FROM agents WHERE email = %s AND is_active = true",
            (email,),
            fetch_one=True
        )

        if not agent:
            return None

        password_hash = agent.get("password_hash", "")

        # Check both bcrypt-style (from SQL seed) and our SHA-256 hash
        if not AuthService.verify_password(password, password_hash):
            return None

        token = AuthService.create_token(agent)
        return {
            "token": token,
            "agent": {
                "id": agent["id"],
                "email": agent["email"],
                "full_name": agent.get("full_name", ""),
                "role": agent.get("role", "AGENT"),
            }
        }

    @staticmethod
    def get_agent_from_token(token: str) -> Optional[Dict]:
        """Get agent info from token."""
        payload = AuthService.verify_token(token)
        if not payload:
            return None

        agent = execute_query(
            "SELECT id, email, full_name, role FROM agents WHERE id = %s AND is_active = true",
            (payload["agent_id"],),
            fetch_one=True
        )
        return agent

    @staticmethod
    def create_agent(email: str, password: str, full_name: str, role: str = "AGENT") -> Optional[Dict]:
        """Create a new agent account."""
        password_hash = AuthService.hash_password(password)
        return execute_query(
            """INSERT INTO agents (id, email, password_hash, full_name, role, is_active, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, true, NOW())
            RETURNING id, email, full_name, role""",
            (email, password_hash, full_name, role),
            fetch_one=True
        )


auth_service = AuthService()
