# app/services/gmail_service.py
"""
Shared Gmail API service extracted from onboarding.py.
Uses Service Account with domain-wide delegation to send emails as no-reply@entersys.mx.
"""
import os
import ssl
import time
import base64
import logging
from typing import List, Optional, Tuple
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import settings

logger = logging.getLogger(__name__)

# Errors that indicate a stale/broken connection worth retrying
_TRANSIENT_ERROR_MARKERS = (
    "broken pipe",
    "unexpected_eof_while_reading",
    "connection reset",
    "connection aborted",
    "badstatusline",
    "remotedisconnected",
)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1  # seconds


class GmailService:
    """Reusable Gmail API service for sending emails."""

    SCOPES = ['https://www.googleapis.com/auth/gmail.send']

    def __init__(self):
        self._service = None

    def _get_service(self, force_new=False):
        """Creates Gmail API service using Service Account with domain-wide delegation."""
        if self._service is not None and not force_new:
            return self._service

        service_account_file = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "/app/service-account.json"
        )
        delegated_user = settings.SMTP_FROM_EMAIL  # no-reply@entersys.mx

        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=self.SCOPES
        )
        delegated_credentials = credentials.with_subject(delegated_user)
        self._service = build('gmail', 'v1', credentials=delegated_credentials)
        return self._service

    def _reset_service(self):
        """Force recreation of the Gmail API service on next call."""
        self._service = None

    @staticmethod
    def _is_transient_error(error: Exception) -> bool:
        """Check if the error is a transient connection issue worth retrying."""
        error_str = str(error).lower()
        if any(marker in error_str for marker in _TRANSIENT_ERROR_MARKERS):
            return True
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return True
        if isinstance(error, ssl.SSLError):
            return True
        if isinstance(error, OSError) and error.errno == 32:  # EPIPE
            return True
        return False

    def _send_with_retry(self, raw_message: str, to_emails: List[str]) -> dict:
        """Send raw message via Gmail API with retry on transient errors."""
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                service = self._get_service(force_new=(attempt > 1))
                result = service.users().messages().send(
                    userId='me',
                    body={'raw': raw_message}
                ).execute()
                return result
            except Exception as e:
                last_error = e
                if self._is_transient_error(e) and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        f"Gmail API transient error (attempt {attempt}/{MAX_RETRIES}), "
                        f"retrying in {wait}s: {e}"
                    )
                    self._reset_service()
                    time.sleep(wait)
                else:
                    raise
        raise last_error

    def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[dict]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Send an email via Gmail API.

        Args:
            to_emails: List of recipient emails
            subject: Email subject
            html_content: HTML body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            attachments: Optional list of {"filename": str, "content": base64_str}

        Returns:
            Tuple of (success, message_id, error_message)
        """
        try:
            # Build MIME message
            if attachments:
                msg = MIMEMultipart('mixed')
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

                for attachment in attachments:
                    filename = attachment.get("filename", "attachment")
                    content_b64 = attachment.get("content", "")
                    try:
                        content_bytes = base64.b64decode(content_b64)
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(content_bytes)
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                        msg.attach(part)
                    except Exception as e:
                        logger.warning(f"Could not attach file {filename}: {e}")
            else:
                msg = MIMEMultipart('alternative')
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

            msg['Subject'] = subject
            msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg['To'] = ', '.join(to_emails)

            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)

            # Encode for Gmail API
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

            # Send via Gmail API with retry on transient errors
            result = self._send_with_retry(raw_message, to_emails)

            message_id = result.get('id')
            logger.info(f"Email sent via Gmail API to {to_emails}, Message ID: {message_id}")
            return True, message_id, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error sending email via Gmail API to {to_emails}: {error_msg}")
            self._reset_service()
            return False, None, error_msg


# Singleton instance
gmail_service = GmailService()
