import logging
import httpx
from typing import Optional
from api.config import settings

logger = logging.getLogger("djama.whatsapp")


class WhatsAppService:
    """Send messages via Meta WhatsApp Cloud API (Graph API v20)."""

    API_VERSION = "v20.0"
    GRAPH_BASE = "https://graph.facebook.com"

    def __init__(self):
        self.phone_number_id = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
        self.access_token = (settings.WHATSAPP_TOKEN or "").strip()
        if self.phone_number_id:
            self.send_url = f"{self.GRAPH_BASE}/{self.API_VERSION}/{self.phone_number_id}/messages"
            logger.info("WhatsApp Meta mode — phone_id=%s", self.phone_number_id)
        else:
            self.send_url = ""
            logger.warning("WHATSAPP_PHONE_NUMBER_ID not set — messages will fail!")

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(self, to: str, message: str) -> dict:
        """Send a plain text message."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        return await self._post(payload)

    async def send_interactive_buttons(self, to: str, body: str, buttons: list) -> dict:
        """Send up to 3 quick-reply buttons."""
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
                        for btn in buttons[:3]
                    ]
                },
            },
        }
        return await self._post(payload)

    async def send_interactive_list(self, to: str, body: str, button_text: str, sections: list) -> dict:
        """Send a list picker message."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": sections},
            },
        }
        return await self._post(payload)

    async def send_urgent_notification(self, to: str, client_phone: str, summary: str) -> dict:
        """Send a handoff alert to the manager number."""
        message = (
            f"HANDOFF URGENT\n\n"
            f"Client: {client_phone}\n"
            f"Résumé: {summary}\n\n"
            f"Connectez-vous au dashboard pour prendre en charge."
        )
        return await self.send_text_message(to, message)

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """Download a media file: resolve URL via Graph API, then download."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: get the temporary media URL
            meta_url = f"{self.GRAPH_BASE}/{self.API_VERSION}/{media_id}"
            res = await client.get(meta_url, headers=self._headers)
            res.raise_for_status()
            media_url = res.json().get("url")
            if not media_url:
                return None
            # Step 2: download the file (must include the auth header)
            file_res = await client.get(media_url, headers=self._headers)
            file_res.raise_for_status()
            return file_res.content

    async def _post(self, payload: dict) -> dict:
        if not self.send_url:
            raise RuntimeError("WhatsApp send_url not configured — set WHATSAPP_PHONE_NUMBER_ID")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.send_url, json=payload, headers=self._headers)
            if response.status_code >= 400:
                logger.error("WhatsApp API error %s: %s", response.status_code, response.text)
            response.raise_for_status()
            return response.json()


whatsapp_service = WhatsAppService()
