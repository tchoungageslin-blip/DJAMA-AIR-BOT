from datetime import datetime
from typing import Optional, Dict, Any, List
from api.db.connection import execute_query


class ClientQueries:
    @staticmethod
    def find_by_phone(phone_number: str) -> Optional[Dict]:
        """Find client by phone number."""
        return execute_query(
            "SELECT * FROM clients WHERE phone_number = %s",
            (phone_number,),
            fetch_one=True
        )

    @staticmethod
    def create(phone_number: str, first_name: str = None, last_name: str = None, language: str = "fr") -> Dict:
        """Create a new client."""
        return execute_query(
            """INSERT INTO clients (id, phone_number, first_name, last_name, language, client_type, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, 'NEW', NOW(), NOW())
            RETURNING *""",
            (phone_number, first_name, last_name, language),
            fetch_one=True
        )

    @staticmethod
    def update(client_id: str, **kwargs) -> Optional[Dict]:
        """Update client fields."""
        set_clauses = []
        values = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        set_clauses.append("updated_at = NOW()")
        values.append(client_id)

        query = f"UPDATE clients SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
        return execute_query(query, tuple(values), fetch_one=True)

    @staticmethod
    def get_preferences(client_id: str) -> Optional[Dict]:
        """Get client preferences."""
        return execute_query(
            "SELECT * FROM preferences WHERE client_id = %s",
            (client_id,),
            fetch_one=True
        )

    @staticmethod
    def upsert_preferences(client_id: str, **kwargs) -> Dict:
        """Create or update client preferences."""
        existing = ClientQueries.get_preferences(client_id)
        if existing:
            set_clauses = []
            values = []
            for key, value in kwargs.items():
                set_clauses.append(f"{key} = %s")
                values.append(value)
            values.append(client_id)
            query = f"UPDATE preferences SET {', '.join(set_clauses)} WHERE client_id = %s RETURNING *"
            return execute_query(query, tuple(values), fetch_one=True)
        else:
            cols = ["id", "client_id"] + list(kwargs.keys())
            vals = ["gen_random_uuid()", "%s"] + ["%s"] * len(kwargs)
            params = [client_id] + list(kwargs.values())
            query = f"INSERT INTO preferences ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING *"
            return execute_query(query, tuple(params), fetch_one=True)


class SessionQueries:
    @staticmethod
    def get_active_session(client_id: str) -> Optional[Dict]:
        """Get the active session for a client (not closed/resolved)."""
        return execute_query(
            """SELECT * FROM sessions
            WHERE client_id = %s AND status NOT IN ('RESOLVED', 'CLOSED')
            ORDER BY created_at DESC LIMIT 1""",
            (client_id,),
            fetch_one=True
        )

    @staticmethod
    def create(client_id: str, status: str = "BOT_ACTIVE", intent: str = "UNKNOWN") -> Dict:
        """Create a new session."""
        return execute_query(
            """INSERT INTO sessions (id, client_id, status, current_intent, tags, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, '{}', NOW(), NOW())
            RETURNING *""",
            (client_id, status, intent),
            fetch_one=True
        )

    @staticmethod
    def update_status(session_id: str, status: str, **kwargs) -> Optional[Dict]:
        """Update session status and optional fields."""
        set_clauses = ["status = %s", "updated_at = NOW()"]
        values = [status]
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(session_id)
        query = f"UPDATE sessions SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
        return execute_query(query, tuple(values), fetch_one=True)

    @staticmethod
    def add_tag(session_id: str, tag: str) -> Optional[Dict]:
        """Add a tag to session."""
        return execute_query(
            "UPDATE sessions SET tags = array_append(tags, %s), updated_at = NOW() WHERE id = %s RETURNING *",
            (tag, session_id),
            fetch_one=True
        )

    @staticmethod
    def get_handoff_sessions() -> List[Dict]:
        """Get all sessions waiting for human handoff."""
        return execute_query(
            "SELECT s.*, c.phone_number, c.first_name, c.last_name FROM sessions s JOIN clients c ON s.client_id = c.id WHERE s.status = 'HUMAN_HANDOFF' ORDER BY s.updated_at ASC",
            fetch_all=True
        ) or []


class LeadQueries:
    @staticmethod
    def create_fret(client_id: str, session_id: str = None, **kwargs) -> Dict:
        """Create a new fret lead."""
        cols = ["id", "client_id", "session_id"] + [k for k in kwargs.keys()]
        placeholders = ["gen_random_uuid()", "%s", "%s"] + ["%s"] * len(kwargs)
        params = [client_id, session_id] + list(kwargs.values())
        cols.append("created_at")
        placeholders.append("NOW()")

        query = f"INSERT INTO leads_fret ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
        return execute_query(query, tuple(params), fetch_one=True)

    @staticmethod
    def create_billet(client_id: str, session_id: str = None, **kwargs) -> Dict:
        """Create a new billet lead."""
        cols = ["id", "client_id", "session_id"] + [k for k in kwargs.keys()]
        placeholders = ["gen_random_uuid()", "%s", "%s"] + ["%s"] * len(kwargs)
        params = [client_id, session_id] + list(kwargs.values())
        cols.append("created_at")
        placeholders.append("NOW()")

        query = f"INSERT INTO leads_billet ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
        return execute_query(query, tuple(params), fetch_one=True)

    @staticmethod
    def update_fret(lead_id: str, **kwargs) -> Optional[Dict]:
        """Update a fret lead."""
        set_clauses = []
        values = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(lead_id)
        query = f"UPDATE leads_fret SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
        return execute_query(query, tuple(values), fetch_one=True)


class OrderQueries:
    @staticmethod
    def create(client_id: str, order_type: str, data: dict, estimated_price: int = None) -> Dict:
        """Create a new order."""
        import json
        prefix = {"FRET": "FR", "BILLETTERIE": "BL", "PACK": "PK"}[order_type]
        # Generate order number
        count = execute_query(
            f"SELECT COUNT(*) as cnt FROM orders WHERE order_type = %s",
            (order_type,),
            fetch_one=True
        )
        number = (count["cnt"] if count else 0) + 1001
        order_number = f"{prefix}-{number}"

        return execute_query(
            """INSERT INTO orders (id, order_number, client_id, order_type, status, data, estimated_price, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, 'NOUVEAU', %s::jsonb, %s, NOW(), NOW())
            RETURNING *""",
            (order_number, client_id, order_type, json.dumps(data) if data else None, estimated_price),
            fetch_one=True
        )

    @staticmethod
    def update_status(order_id: str, status: str, **kwargs) -> Optional[Dict]:
        """Update order status."""
        set_clauses = ["status = %s", "updated_at = NOW()"]
        values = [status]
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(order_id)
        query = f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
        return execute_query(query, tuple(values), fetch_one=True)


class MessageQueries:
    @staticmethod
    def create(session_id: str, client_id: str, sender: str, content: str,
               media_url: str = None, media_type: str = None, metadata: dict = None) -> Dict:
        """Store a message."""
        import json
        meta_json = json.dumps(metadata) if metadata else None
        return execute_query(
            """INSERT INTO messages (id, session_id, client_id, sender, content, media_url, media_type, metadata, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            RETURNING *""",
            (session_id, client_id, sender, content, media_url, media_type, meta_json),
            fetch_one=True
        )

    @staticmethod
    def get_session_messages(session_id: str, limit: int = 50) -> List[Dict]:
        """Get messages for a session."""
        return execute_query(
            "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC LIMIT %s",
            (session_id, limit),
            fetch_all=True
        ) or []
