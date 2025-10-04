"""Email sending utilities for the FastAPI service.

This module provides an ``EmailSender`` class capable of authenticating
with Gmail either by using a classic app password or via OAuth2 refresh
credentials issued from Google Cloud.  The OAuth2 flow is especially
useful on Render/Vercel where Google blocks the use of less secure app
passwords.
"""
from __future__ import annotations

import base64
import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Iterable, Optional

# The google-auth dependency is optional – we only need it when OAuth2 is
# configured.  Import lazily so that environments that still rely on classic
# app passwords (or simply don't have google-auth installed) can keep working.
try:  # pragma: no cover - optional dependency shim
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:  # pragma: no cover - handled gracefully at runtime
    Request = None  # type: ignore[assignment]
    Credentials = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class EmailSender:
    """Helper responsible for composing and sending e-mails."""

    def __init__(self) -> None:
        # SMTP configuration
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.from_name = os.environ.get("SMTP_FROM_NAME", "IncaNeurobaeza")

        # Authentication data
        self.email = os.environ.get("SMTP_EMAIL", "")
        self.password = os.environ.get("SMTP_PASS")

        # OAuth2 (Google Cloud) credentials – optional but preferred.
        self.client_id = os.environ.get("GMAIL_CLIENT_ID")
        self.client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
        self.refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
        self.token_uri = os.environ.get(
            "GMAIL_TOKEN_URI", "https://oauth2.googleapis.com/token"
        )

        if not self.email:
            logger.warning(
                "SMTP_EMAIL is not configured; e-mail sending will fail until it is set."
            )

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------
    def _get_oauth_access_token(self) -> Optional[str]:
        """Return a fresh OAuth access token when credentials are present."""

        if Credentials is None or Request is None:
            logger.debug(
                "google-auth not installed; skipping Gmail OAuth refresh and using classic auth if available."
            )
            return None

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            return None

        try:
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=["https://mail.google.com/"],
            )
            credentials.refresh(Request())
            logger.debug("Successfully refreshed Gmail OAuth token.")
            return credentials.token
        except Exception:  # pragma: no cover - logging detailed error
            logger.exception("Failed to refresh Gmail OAuth token.")
            return None

    def diagnose_configuration(self) -> dict:
        """Provide a detailed diagnosis of the SMTP/OAuth configuration."""

        google_auth_available = Credentials is not None and Request is not None
        oauth_fields = {
            "client_id": bool(self.client_id),
            "client_secret": bool(self.client_secret),
            "refresh_token": bool(self.refresh_token),
            "token_uri": bool(self.token_uri),
        }
        oauth_ready = all(oauth_fields.values())

        issues: list[str] = []

        if not self.email:
            issues.append(
                "SMTP_EMAIL está vacío. Configura un remitente válido para poder autenticarte."
            )

        if oauth_ready and not google_auth_available:
            issues.append(
                "Las variables OAuth están presentes pero falta la librería google-auth. Ejecuta 'pip install google-auth google-auth-oauthlib'."
            )

        if not oauth_ready and not self.password:
            issues.append(
                "No hay contraseña SMTP ni credenciales OAuth completas; el servicio no podrá iniciar sesión."
            )

        diagnostics = {
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "from_name": self.from_name,
            "email_configured": bool(self.email),
            "password_configured": bool(self.password),
            "google_auth_available": google_auth_available,
            "oauth_fields": oauth_fields,
            "oauth_ready": oauth_ready,
        }

        return {"diagnostics": diagnostics, "issues": issues}

    @staticmethod
    def _build_oauth2_string(username: str, access_token: str) -> str:
        auth_string = f"user={username}\1auth=Bearer {access_token}\1\1"
        return base64.b64encode(auth_string.encode()).decode()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def send_html_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: Optional[Iterable[dict]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Send an HTML email with optional text and attachments."""

        logger.info("Preparing e-mail to %s with subject %s", to_email, subject)

        if not self.email:
            error_msg = (
                "SMTP_EMAIL no está configurado; no es posible autenticar contra el servidor."
            )
            logger.error(error_msg)
            return False, error_msg

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        display_name = (self.from_name or "").strip()
        if display_name and display_name.lower() != self.email.lower():
            message["From"] = formataddr((display_name, self.email))
        else:
            message["From"] = self.email
        message["To"] = to_email

        if text_body:
            message.attach(MIMEText(text_body, "plain", "utf-8"))

        message.attach(MIMEText(html_body, "html", "utf-8"))

        if attachments:
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                filename = attachment.get("filename")
                content = attachment.get("content")
                if not filename or content is None:
                    continue
                part = MIMEBase("application", "octet-stream")
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", f"attachment; filename={filename}"
                )
                message.attach(part)

        auth_method = None

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()

                # Prefer OAuth2 if configured, otherwise fallback to app password.
                access_token = self._get_oauth_access_token()
                if access_token:
                    auth_string = self._build_oauth2_string(self.email, access_token)
                    code, response = server.docmd("AUTH", f"XOAUTH2 {auth_string}")
                    if code != 235:
                        raise smtplib.SMTPAuthenticationError(code, response)
                    auth_method = "oauth2"
                    logger.info("Authenticated with Gmail using OAuth2.")
                elif self.password:
                    server.login(self.email, self.password)
                    auth_method = "password"
                    logger.info("Authenticated with Gmail using app password.")
                else:
                    raise RuntimeError("No SMTP credentials configured.")

                server.sendmail(self.email, [to_email], message.as_string())

            logger.info("Email sent successfully to %s", to_email)
            return True, None

        except smtplib.SMTPAuthenticationError as exc:
            if auth_method == "oauth2":
                error_msg = (
                    "Error de autenticación SMTP mediante OAuth2. Revisa el CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN y que el refresh siga activo."
                )
            elif auth_method == "password":
                error_msg = (
                    "Error de autenticación SMTP con contraseña. Verifica que la contraseña de aplicación sea correcta y que el doble factor siga habilitado."
                )
            else:
                error_msg = f"Error de autenticación SMTP: {exc}"
        except RuntimeError as exc:
            error_msg = (
                f"Configuración SMTP incompleta: {exc}. Visita /email/status para ver un diagnóstico detallado."
            )
        except smtplib.SMTPRecipientsRefused as exc:
            error_msg = f"Destinatario rechazado: {exc}"
        except smtplib.SMTPServerDisconnected as exc:
            error_msg = f"Servidor desconectado: {exc}"
        except Exception as exc:  # pragma: no cover - general safeguard
            error_msg = (
                f"Error general enviando email: {exc}. Consulta /email/status para validar la configuración."
            )

        logger.error(error_msg)
        return False, error_msg


# Instancia global del servicio
email_service = EmailSender()
