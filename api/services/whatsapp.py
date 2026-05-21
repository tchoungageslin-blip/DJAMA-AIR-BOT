import httpx
from typing import Optional
from api.config import settings


class WhatsAppService:
    """Service for sending messages via Vendrix.net WhatsApp API."""

    def __init__(self):
        self.api_url = settings.VENDRIX_API_URL
        self.api_key = settings.VENDRIX_API_KEY
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def send_text_message(self, to: str, message: str) -> dict:
        """Send a text message to a WhatsApp number."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.api_url}/messages",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def send_interactive_buttons(self, to: str, body: str, buttons: list) -> dict:
        """Send interactive button message.
        buttons: list of {"id": "btn_id", "title": "Button Text"}
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                        for btn in buttons[:3]  # WhatsApp limit: 3 buttons max
                    ]
                }
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.api_url}/messages",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def send_interactive_list(self, to: str, body: str, button_text: str, sections: list) -> dict:
        """Send interactive list message.
        sections: [{"title": "Section", "rows": [{"id": "row_id", "title": "Row", "description": "Desc"}]}]
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.api_url}/messages",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def send_urgent_notification(self, to: str, client_phone: str, summary: str) -> dict:
        """Send urgent handoff notification to the configured number."""
        message = (
            f"🚨 HANDOFF URGENT\n\n"
            f"Client: {client_phone}\n"
            f"Résumé: {summary}\n\n"
            f"Connectez-vous au dashboard pour prendre en charge."
        )
        return await self.send_text_message(to, message)

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """Download media file from WhatsApp."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First get the media URL
            response = await client.get(
                f"{self.api_url}/media/{media_id}",
                headers=self.headers
            )
            response.raise_for_status()
            media_url = response.json().get("url")

            if media_url:
                # Download the actual file
                file_response = await client.get(
                    media_url,
                    headers=self.headers
                )
                file_response.raise_for_status()
                return file_response.content
        return None


whatsapp_service = WhatsAppService()
