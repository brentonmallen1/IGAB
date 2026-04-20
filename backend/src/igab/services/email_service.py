import email.mime.multipart
import email.mime.text
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from igab.config import settings

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


class EmailService:
    def _enabled(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_USER)

    async def send(
        self,
        to: str,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        if not self._enabled():
            return

        template = _jinja_env.get_template(template_name)
        html_body = template.render(**context)

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(email.mime.text.MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            use_tls=settings.SMTP_TLS,
        )
