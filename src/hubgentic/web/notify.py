"""Email alerts for new leads from the marketing site.

Off unless HUBGENTIC_SMTP_HOST is set. On the VPS the settings live in
/etc/hubgentic/hubgentic.env (root-only), loaded by the systemd unit.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

log = logging.getLogger("hubgentic.notify")


@dataclass
class Mailer:
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    recipients: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, default_recipients: set[str] | None = None) -> Mailer | None:
        host = os.environ.get("HUBGENTIC_SMTP_HOST", "").strip()
        if not host:
            return None
        user = os.environ.get("HUBGENTIC_SMTP_USER", "").strip()
        notify = os.environ.get("HUBGENTIC_LEAD_NOTIFY", "")
        recipients = [e.strip() for e in notify.split(",") if e.strip()] or sorted(default_recipients or [])
        if not recipients:
            log.warning("SMTP configured but no recipients (HUBGENTIC_LEAD_NOTIFY); lead alerts are off")
            return None
        return cls(
            host=host,
            port=int(os.environ.get("HUBGENTIC_SMTP_PORT", "587")),
            user=user,
            password=os.environ.get("HUBGENTIC_SMTP_PASSWORD", ""),
            sender=os.environ.get("HUBGENTIC_SMTP_FROM", "").strip() or user,
            recipients=recipients,
        )

    def send(self, subject: str, body: str, reply_to: str | None = None) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        context = ssl.create_default_context()
        if self.port == 465:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=20)
        with server:
            if self.port != 465:
                server.starttls(context=context)
            if self.user:
                server.login(self.user, self.password)
            server.send_message(msg)

    def send_lead(self, lead: dict, admin_url: str) -> None:
        """Background task: never raises, so a mail outage can't lose a lead (it's already stored)."""
        lines = [
            f"Name:      {lead['name']}",
            f"Email:     {lead['email']}",
            f"Company:   {lead.get('company') or '—'}",
            f"Segment:   {lead.get('segment') or '—'}",
            f"Interests: {lead.get('interests') or '—'}",
            f"Language:  {lead['lang']}",
            "",
            lead.get("message") or "(no message)",
            "",
            f"All leads: {admin_url}",
        ]
        who = lead["name"] + (f" ({lead['company']})" if lead.get("company") else "")
        try:
            self.send(f"New lead: {who}", "\n".join(lines), reply_to=lead["email"])
        except Exception:
            log.exception("could not send lead alert for %s", lead["email"])
