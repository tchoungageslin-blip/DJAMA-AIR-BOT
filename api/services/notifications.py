import asyncio
import logging
import httpx
from api.config import settings
from api.services.whatsapp import whatsapp_service
from api.db.connection import execute_query

logger = logging.getLogger("djama.notifications")


class NotificationService:
    """
    Dispatches notifications across all channels simultaneously:
      1. WhatsApp (agent manager number)
      2. Email via Resend
      3. Dashboard (polling log — triggers sound + browser push on frontend)
    WhatsApp and email are fired in parallel via asyncio.gather().
    """

    # ============================================
    # PUBLIC API
    # ============================================

    async def notify_new_order(self, client_phone: str, session_id: str,
                               summary: str, order_data: dict = None) -> None:
        """New qualified order — triggers Ding on dashboard."""
        await self._dispatch(
            event_type="new_order",
            client_phone=client_phone,
            session_id=session_id,
            summary=summary,
            order_data=order_data,
            email_subject="Nouvelle commande reçue",
            wa_prefix="NOUVELLE COMMANDE",
        )

    async def notify_handoff(self, client_phone: str, session_id: str,
                             summary: str, tags: list = None) -> None:
        """Handoff / sensitive case — triggers Alarm on dashboard."""
        tag_str = " | ".join(tags) if tags else ""
        is_sensitive = bool(tags and "CAS_SENSIBLE" in tags)
        event_type = "sensitive" if is_sensitive else "handoff"

        await self._dispatch(
            event_type=event_type,
            client_phone=client_phone,
            session_id=session_id,
            summary=f"{summary}\nTags: {tag_str}" if tag_str else summary,
            email_subject="CAS SENSIBLE — Action requise" if is_sensitive else "Handoff requis",
            wa_prefix="CAS SENSIBLE — HANDOFF URGENT" if is_sensitive else "HANDOFF URGENT",
        )

    # ============================================
    # DISPATCH CORE — parallel execution
    # ============================================

    async def _dispatch(self, event_type: str, client_phone: str, session_id: str,
                        summary: str, order_data: dict = None,
                        email_subject: str = "", wa_prefix: str = "") -> None:
        """
        Fire all channels simultaneously.
        DB settings are fetched first (sync), then WA + email run in parallel.
        """
        # Fetch settings synchronously (psycopg2 is sync)
        notification_number = self._get_setting("notification_whatsapp_number")
        notification_email = (
            self._get_setting("notification_email") or settings.NOTIFICATION_EMAIL_TO
        )

        # Log to dashboard immediately (frontend polls this)
        self._log(event_type, "dashboard", "all_agents", summary, session_id, sent=True)

        # Build parallel tasks
        tasks = []

        if notification_number:
            tasks.append(self._wa_task(
                event_type, notification_number, client_phone, summary, session_id, wa_prefix
            ))

        if notification_email and settings.RESEND_API_KEY:
            tasks.append(self._email_task(
                event_type, notification_email, email_subject,
                client_phone, summary, order_data, session_id
            ))

        # Fire WA + email at the same time
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("Notification channel failed: %s: %s", type(r).__name__, r)

    # ============================================
    # CHANNEL TASKS
    # ============================================

    async def _wa_task(self, event_type: str, number: str, client_phone: str,
                       summary: str, session_id: str, prefix: str) -> None:
        wa_digits = client_phone.lstrip("+")
        wa_link = f"https://wa.me/{wa_digits}"
        msg = (
            f"{prefix}\n\n"
            f"Client: {wa_link}\n"
            f"Résumé: {summary}\n\n"
            f"Connectez-vous au dashboard pour traiter."
        )
        try:
            await whatsapp_service.send_text_message(number, msg)
            self._log(event_type, "whatsapp", number, summary, session_id, sent=True)
        except Exception as e:
            self._log(event_type, "whatsapp", number, f"FAILED: {e}", session_id, sent=False)
            raise

    async def _email_task(self, event_type: str, to: str, subject: str,
                          client_phone: str, summary: str,
                          order_data: dict, session_id: str) -> None:
        try:
            html = self._build_email_html(event_type, client_phone, summary, order_data)
            await self._send_resend(to, subject, html)
            self._log(event_type, "email", to, summary, session_id, sent=True)
        except Exception as e:
            self._log(event_type, "email", to, f"FAILED: {e}", session_id, sent=False)
            raise

    # ============================================
    # RESEND EMAIL
    # ============================================

    async def _send_resend(self, to: str, subject: str, html: str) -> None:
        from_addr = settings.RESEND_FROM_EMAIL or "onboarding@resend.dev"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"Djama Air Logistics <{from_addr}>",
                    "to": [to],
                    "subject": f"[Djama Air] {subject}",
                    "html": html,
                },
            )
            response.raise_for_status()

    def _build_email_html(self, event_type: str, client_phone: str,
                          summary: str, order_data: dict = None) -> str:
        is_urgent = event_type in ("handoff", "sensitive")
        accent = "#dc2626" if is_urgent else "#2563eb"
        icon = "🚨" if is_urgent else "📦"
        title = (
            "Handoff Urgent" if event_type == "handoff" else
            "Cas Sensible Détecté" if event_type == "sensitive" else
            "Nouvelle Commande"
        )

        rows_html = ""
        if order_data:
            for key, label in [
                ("origin", "Origine"), ("destination", "Destination"),
                ("weight_kg", "Poids (kg)"), ("goods_nature", "Nature marchandise"),
                ("shipping_mode", "Mode d'expédition"), ("notes", "Notes"),
            ]:
                val = order_data.get(key)
                if val:
                    rows_html += (
                        f"<tr><td style='padding:10px 16px;border-bottom:1px solid #f3f4f6;"
                        f"color:#6b7280;font-size:13px;white-space:nowrap;'>{label}</td>"
                        f"<td style='padding:10px 16px;border-bottom:1px solid #f3f4f6;"
                        f"font-size:13px;font-weight:500;color:#111827;'>{val}</td></tr>"
                    )

        dashboard_url = settings.APP_URL + "/dashboard"

        return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:32px 16px;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);">
        <tr>
          <td style="background:{accent};padding:28px 32px;text-align:center;">
            <p style="margin:0 0 6px;font-size:32px;">{icon}</p>
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{title}</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:24px;">
              <tr style="background:#f9fafb;">
                <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;color:#6b7280;font-size:13px;">Client</td>
                <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;font-size:13px;font-weight:600;color:#111827;">{client_phone}</td>
              </tr>
              <tr>
                <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;color:#6b7280;font-size:13px;vertical-align:top;">Résumé</td>
                <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;font-size:13px;color:#374151;line-height:1.5;">{summary}</td>
              </tr>
              {rows_html}
            </table>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td align="center">
                <a href="{dashboard_url}" style="display:inline-block;background:{accent};color:#fff;font-size:14px;font-weight:600;padding:13px 36px;border-radius:8px;text-decoration:none;">
                  Ouvrir le Dashboard &rarr;
                </a>
              </td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px;border-top:1px solid #f3f4f6;text-align:center;">
            <p style="margin:0;color:#9ca3af;font-size:12px;">
              Djama Air Logistics &bull; Notifications automatiques
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    # ============================================
    # HELPERS
    # ============================================

    @staticmethod
    def _get_setting(key: str) -> str:
        result = execute_query(
            "SELECT value FROM settings WHERE key = %s", (key,), fetch_one=True
        )
        return result["value"] if result else ""

    @staticmethod
    def _log(notif_type: str, channel: str, recipient: str,
             message: str, session_id: str = None, sent: bool = False) -> None:
        execute_query(
            """INSERT INTO notifications (id, type, channel, recipient, message, session_id, sent, sent_at, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())""",
            (notif_type, channel, recipient, message, session_id, sent, sent),
        )


notification_service = NotificationService()
