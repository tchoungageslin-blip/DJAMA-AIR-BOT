import httpx
from typing import Optional
from api.config import settings


class WhatsAppService:
    """Service for sending messages via standard Meta WhatsApp Cloud API."""

    def __init__(self):
        self.api_version = "v19.0"
        # Primary: Meta WhatsApp Cloud API credentials
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
        self.access_token = settings.WHATSAPP_TOKEN or settings.VENDRIX_API_KEY or ""

        # Build API URL
        if self.phone_number_id and self.phone_number_id.replace(" ", "").isdigit():
            self.api_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id.strip()}"
        elif settings.VENDRIX_API_URL and settings.VENDRIX_API_URL != "https://api.vendrix.net":
            self.api_url = settings.VENDRIX_API_URL
        else:
            self.api_url = f"https://graph.facebook.com/{self.api_version}/MISSING_PHONE_ID"
            print(f"[WHATSAPP WARNING] No phone_number_id configured! Token set: {bool(self.access_token)}")

        print(f"[WHATSAPP INIT] api_url={self.api_url}, token_len={len(self.access_token)}")

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def send_text_message(self, to: str, message: str) -> dict:
        """Send a text message to a WhatsApp number."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": message}
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
        """Send interactive list message."""
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
        """Download media file from WhatsApp Cloud API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First get the media URL from Graph API
            meta_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
            response = await client.get(
                meta_url,
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            response.raise_for_status()
            media_url = response.json().get("url")

            if media_url:
                # Download the actual file from the media URL using bearer token
                file_response = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {self.access_token}"}
                )
                file_response.raise_for_status()
                return file_response.content
        return None


whatsapp_service = WhatsAppService()
