import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from api.config import settings
from api.services.whatsapp import whatsapp_service
from api.db.connection import execute_query


class NotificationService:
    """Handles sending notifications via all available channels."""

    @staticmethod
    def get_notification_number() -> str:
        """Get the configured urgent notification WhatsApp number from settings."""
        result = execute_query(
            "SELECT value FROM settings WHERE key = 'notification_whatsapp_number'",
            fetch_one=True
        )
        return result["value"] if result else ""

    @staticmethod
    def get_notification_email() -> str:
        """Get the configured notification email from settings."""
        result = execute_query(
            "SELECT value FROM settings WHERE key = 'notification_email'",
            fetch_one=True
        )
        return result["value"] if result else ""

    async def notify_handoff(self, client_phone: str, session_id: str, summary: str, tags: list = None) -> None:
        """Send handoff notification via all channels."""
        tag_str = " | ".join(tags) if tags else ""

        # 1. WhatsApp notification
        notification_number = self.get_notification_number()
        if notification_number:
            try:
                await whatsapp_service.send_urgent_notification(
                    to=notification_number,
                    client_phone=client_phone,
                    summary=f"{summary}\nTags: {tag_str}" if tag_str else summary
                )
                self._log_notification("handoff", "whatsapp", notification_number,
                                       f"Handoff: {client_phone}", session_id, sent=True)
            except Exception as e:
                self._log_notification("handoff", "whatsapp", notification_number,
                                       f"FAILED: {str(e)}", session_id, sent=False)

        # 2. Email notification
        notification_email = self.get_notification_email()
        if notification_email and settings.SMTP_HOST:
            try:
                self._send_email(
                    to=notification_email,
                    subject=f"🚨 Handoff requis - {client_phone}",
                    body=f"Client: {client_phone}\nSession: {session_id}\nRésumé: {summary}\nTags: {tag_str}"
                )
                self._log_notification("handoff", "email", notification_email,
                                       f"Handoff: {client_phone}", session_id, sent=True)
            except Exception as e:
                self._log_notification("handoff", "email", notification_email,
                                       f"FAILED: {str(e)}", session_id, sent=False)

        # 3. Dashboard notification (stored in DB for polling)
        self._log_notification("handoff", "dashboard", "all_agents",
                               summary, session_id, sent=True)

    def _send_email(self, to: str, subject: str, body: str) -> None:
        """Send email via SMTP."""
        msg = MIMEMultipart()
        msg["From"] = settings.NOTIFICATION_EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.NOTIFICATION_EMAIL_FROM, to, msg.as_string())

    @staticmethod
    def _log_notification(notif_type: str, channel: str, recipient: str,
                          message: str, session_id: str = None, sent: bool = False) -> None:
        """Log notification to database."""
        execute_query(
            """INSERT INTO notifications (id, type, channel, recipient, message, session_id, sent, sent_at, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())""",
            (notif_type, channel, recipient, message, session_id, sent, sent)
        )


notification_service = NotificationService()
