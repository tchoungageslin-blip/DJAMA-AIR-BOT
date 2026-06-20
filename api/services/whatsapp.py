import logging
import httpx
from typing import Optional
from api.config import settings

logger = logging.getLogger("djama.whatsapp")


class WhatsAppService:
    """Service for sending messages via Vendrix or Meta WhatsApp Cloud API.
    
    Provider selection:
    - If VENDRIX_API_KEY starts with 'vx_live' or 'vx_test' → use Vendrix
    - Otherwise → use Meta Cloud API (requires WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_TOKEN)
    """

    def __init__(self):
        self.api_version = "v19.0"
        vendrix_key = settings.VENDRIX_API_KEY or ""
        self.use_vendrix = vendrix_key.startswith("vx_live") or vendrix_key.startswith("vx_test")

        if self.use_vendrix:
            # Vendrix mode: align with Gateway reply endpoint
            base = (settings.VENDRIX_API_URL or "https://vendrix.net").rstrip("/")
            self.send_url = f"{base}/api/v1/gateway/reply"
            self.media_url_base = f"{base}/api/v1/media"
            self.access_token = vendrix_key
            self.api_url = self.send_url
            logger.info("MODE=Vendrix send_url=%s", self.send_url)
        else:
            # Meta Cloud API mode
            self.phone_number_id = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
            self.access_token = settings.WHATSAPP_TOKEN or ""
            if self.phone_number_id:
                self.send_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
            else:
                self.send_url = f"https://graph.facebook.com/{self.api_version}/MISSING_PHONE_ID/messages"
                logger.warning("No phone_number_id configured for Meta API!")
            self.media_url_base = None
            self.api_url = self.send_url
            logger.info("MODE=Meta send_url=%s", self.send_url)

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _format_phone(self, to: str) -> str:
        """Vendrix expects E.164 format with leading '+'"""
        if not to:
            return to
        t = to.strip()
        return t if t.startswith("+") else f"+{t}"

    async def send_text_message(self, to: str, message: str) -> dict:
        """Send a text message."""
        if self.use_vendrix:
            # Vendrix Gateway reply payload
            payload = {"to": self._format_phone(to), "type": "text", "text": message}
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": message}
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.send_url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_interactive_buttons(self, to: str, body: str, buttons: list) -> dict:
        """Send interactive button message.
        buttons: list of {"id": "btn_id", "title": "Button Text"}
        """
        if self.use_vendrix:
            # Fallback to a plain text list of options in Gateway mode
            choices = "\n".join([f"{i+1}. {btn['title']}" for i, btn in enumerate(buttons[:3])])
            text = f"{body}\n\n{choices}"
            return await self.send_text_message(to, text)
        else:
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
                    }
                }
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.send_url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_interactive_list(self, to: str, body: str, button_text: str, sections: list) -> dict:
        """Send interactive list message."""
        if self.use_vendrix:
            # Fallback to plain text listing
            lines = [body, ""]
            idx = 1
            for sec in sections:
                title = sec.get("title")
                rows = sec.get("rows", [])
                if title:
                    lines.append(f"{title}:")
                for row in rows:
                    lines.append(f"{idx}. {row.get('title', '')}")
                    idx += 1
            return await self.send_text_message(to, "\n".join(lines))

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": sections}
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.send_url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_urgent_notification(self, to: str, client_phone: str, summary: str) -> dict:
        """Send urgent handoff notification to the configured number."""
        message = (
            f"HANDOFF URGENT\n\n"
            f"Client: {client_phone}\n"
            f"Résumé: {summary}\n\n"
            f"Connectez-vous au dashboard pour prendre en charge."
        )
        return await self.send_text_message(to, message)

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """Download media file via Vendrix or Meta Graph API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if self.use_vendrix:
                # Vendrix exposes media directly by ID
                response = await client.get(
                    f"{self.media_url_base}/{media_id}",
                    headers={"Authorization": f"Bearer {self.access_token}"}
                )
                response.raise_for_status()
                return response.content
            else:
                # Meta: first resolve media URL, then download
                meta_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
                response = await client.get(
                    meta_url,
                    headers={"Authorization": f"Bearer {self.access_token}"}
                )
                response.raise_for_status()
                media_url = response.json().get("url")
                if media_url:
                    file_response = await client.get(
                        media_url,
                        headers={"Authorization": f"Bearer {self.access_token}"}
                    )
                    file_response.raise_for_status()
                    return file_response.content
        return None


whatsapp_service = WhatsAppService()
