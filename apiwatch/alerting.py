"""
AlertManager: watches broadcasted log records and fires Slack and/or
Gmail alerts when one crosses the severity threshold configured in the
UI. Slack and Gmail are independent toggles - both can fire on the same
log. Credentials come from env vars only, never stored in the db, only
the channel toggles and threshold live there.
"""
import asyncio
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Dict, Optional

import aiohttp

LEVEL_RANK = {'CRITICAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3, 'DEBUG': 4, 'UNKNOWN': 5}

# shared between the Slack color bar and the email header color, so both
# channels agree on what "this is bad" looks like
LEVEL_STYLE = {
    'CRITICAL': {'color': '#e01e37', 'emoji': '🔴'},
    'ERROR':    {'color': '#ff5c5c', 'emoji': '🟠'},
    'WARNING':  {'color': '#ffb020', 'emoji': '🟡'},
    'INFO':     {'color': '#3ddc84', 'emoji': '🟢'},
    'DEBUG':    {'color': '#4db8ff', 'emoji': '🔵'},
    'UNKNOWN':  {'color': '#8892a0', 'emoji': '⚪'},
}


class AlertManager:
    def __init__(self, db):
        self.db = db

        self.slack_webhook = os.getenv('APIWATCH_SLACK_WEBHOOK_URL')

        self.gmail_user = os.getenv('APIWATCH_GMAIL_USER')
        self.gmail_app_password = os.getenv('APIWATCH_GMAIL_APP_PASSWORD')
        self.gmail_smtp_host = os.getenv('APIWATCH_GMAIL_SMTP_HOST', 'smtp.gmail.com')
        self.gmail_smtp_port = int(os.getenv('APIWATCH_GMAIL_SMTP_PORT', '587'))
        # if no explicit recipient is set, alerts go to the sending
        # account itself rather than forcing the user to fill in a
        # field that's often just going to be the same address anyway
        self.gmail_to = os.getenv('APIWATCH_ALERT_EMAIL_TO') or self.gmail_user

        # optional: if set, alert emails get a "View live logs" button
        # linking back to the dashboard. Omitted entirely if unset rather
        # than showing a dead/placeholder link.
        self.public_url = os.getenv('APIWATCH_PUBLIC_URL')

        self.cooldown_seconds = int(os.getenv('APIWATCH_ALERT_COOLDOWN_SECONDS', '300'))
        self._last_sent: Dict[str, float] = {}

        # asyncio.create_task() only holds a *weak* reference to the task
        # internally - if nothing else references it, it can get garbage
        # collected mid-flight before the Slack POST / SMTP call finishes.
        # Keeping our own strong reference here (and dropping it via the
        # done callback) is what makes the fire-and-forget dispatch below
        # actually safe rather than a silent, intermittent no-op.
        self._background_tasks: set = set()

    def availability(self) -> Dict[str, bool]:
        """
        What's actually usable based on env vars present, this is what
        the UI checks before letting someone enable a channel, so we
        never silently fail because credentials were never set.
        """
        return {
            'slack': bool(self.slack_webhook),
            'gmail': bool(self.gmail_user and self.gmail_app_password),
        }

    async def maybe_alert(self, record: dict):
        """
        Call this with every log record, no-ops fast if nothing applies.

        Everything up to and including the per-channel cooldown check
        stays awaited inline - it's all cheap (a settings lookup, dict
        comparisons) and the caller genuinely does need those checks to
        happen in order, e.g. so a burst of records in the same tick
        doesn't slip past the cooldown before self._last_sent gets
        updated.

        The actual network call (Slack webhook / SMTP) is the slow,
        unpredictable part, so that's the piece that gets detached into
        its own task per channel instead of being awaited here. Without
        this, a caller doing `await alert_manager.maybe_alert(record)` in
        the main log-ingestion loop would stall processing subsequent log
        lines for however long Slack or Gmail take to respond (up to the
        5s/10s timeouts below) - exactly when you least want ingestion
        and the live websocket broadcast to lag.

        Slack and Gmail are independent toggles - both can fire on the
        same record, each against its own cooldown clock, so one channel
        being on cooldown never blocks the other from sending.
        """
        settings = await self.db.get_alert_settings()
        if not settings:
            return

        # case-insensitive on both sides: env/UI-configured threshold and
        # the level actually stored can each come from apps that emit
        # INFO, info, or InFO depending on their own logging setup
        min_level = (settings.get('min_level') or 'ERROR').upper()
        level = (record.get('level') or 'UNKNOWN').upper()

        # only fire at-or-worse than the configured threshold, lower
        # rank number means more severe
        if LEVEL_RANK.get(level, 5) > LEVEL_RANK.get(min_level, 1):
            return

        avail = self.availability()
        channels = []
        if settings.get('slack_enabled') and avail.get('slack'):
            channels.append('slack')
        if settings.get('gmail_enabled') and avail.get('gmail'):
            channels.append('gmail')

        now = time.time()
        for channel in channels:
            last = self._last_sent.get(channel, 0)
            if now - last < self.cooldown_seconds:
                continue
            self._last_sent[channel] = now

            # dispatch and return immediately - the caller's await on
            # maybe_alert() resolves now, not once Slack/Gmail respond
            task = asyncio.create_task(self._dispatch(channel, record))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _dispatch(self, channel: str, record: dict):
        """
        Runs detached from the caller. The try/except still matters here
        even though nothing awaits this task - an exception raised inside
        a task nobody awaits doesn't propagate anywhere, it just gets
        logged by asyncio as "Task exception was never retrieved" the
        next time the task is garbage collected, which is easy to miss
        in production logs. Catching and printing it ourselves, in the
        same format the old inline version used, keeps that visible.
        """
        try:
            if channel == 'slack':
                await self._send_slack(record)
            elif channel == 'gmail':
                await self._send_gmail(record)
        except Exception as exc:
            print(f'[ApiWatchdog] alert send failed ({channel}): {exc}', flush=True)

    # ---------------- shared formatting ----------------
    def _style_for(self, level: str) -> dict:
        return LEVEL_STYLE.get(level, LEVEL_STYLE['UNKNOWN'])

    def _format_text(self, record: dict) -> str:
        """Plain-text body, used for Slack's fallback text and the
        text/plain half of the email's multipart/alternative."""
        body = (record.get('message') or record.get('raw') or '')[:300]
        return (
            f"[{record.get('level')}] {record.get('container_name')}\n"
            f"{body}\n"
            f"{record.get('timestamp')}"
        )

    # ---------------- Slack ----------------
    def _slack_payload(self, record: dict) -> dict:
        level = record.get('level') or 'UNKNOWN'
        style = self._style_for(level)
        body = (record.get('message') or record.get('raw') or '')[:500]
        container = record.get('container_name') or 'unknown container'
        timestamp = record.get('timestamp') or ''

        blocks = [
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': f"```{body}```"}
            },
            {
                'type': 'context',
                'elements': [
                    {'type': 'mrkdwn', 'text': f"{style['emoji']} *{level}* · `{container}` · 🕐 {timestamp}  ·  via api-watch"}
                ]
            }
        ]

        return {
            # top-level 'text' is what shows in places that don't render
            # blocks - mobile push notifications, channel previews, etc.
            # Slack requires this even when 'blocks' is present.
            'text': f"{style['emoji']} {level} in {container}",
            # 'attachments' (rather than a bare 'blocks' key) is what
            # gives the colored left-hand bar - still fully supported by
            # incoming webhooks even though block-only messages are more
            # commonly recommended for new integrations
            'attachments': [{'color': style['color'], 'blocks': blocks}]
        }

    async def _send_slack(self, record: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.slack_webhook,
                json=self._slack_payload(record),
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status >= 300:
                    print(f'[ApiWatchdog] slack alert rejected: {resp.status}', flush=True)

    # ---------------- Gmail ----------------
    def _format_html(self, record: dict) -> str:
        level = record.get('level') or 'UNKNOWN'
        style = self._style_for(level)
        body = escape((record.get('message') or record.get('raw') or '')[:500])
        container = escape(str(record.get('container_name') or 'unknown container'))
        timestamp = escape(str(record.get('timestamp') or ''))

        cta = ''
        if self.public_url:
            cta = f'''
            <tr><td style="padding-top:16px;">
              <a href="{escape(self.public_url)}" style="display:inline-block;padding:9px 18px;background:{style['color']};color:#0a0e14;text-decoration:none;border-radius:4px;font-family:'SFMono-Regular',Consolas,monospace;font-weight:bold;font-size:13px;">View live logs &rarr;</a>
            </td></tr>'''

        # inline CSS throughout - most mail clients (Gmail included)
        # strip <style> blocks, so anything that has to render correctly
        # needs to be a style="" attribute on the element itself
        return f'''<!DOCTYPE html>
<html>
  <body style="margin:0;padding:24px;background:#f4f4f2;font-family:-apple-system,'Segoe UI',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #e2e0d8;">
      <tr>
        <td style="background:{style['color']};padding:12px 20px;color:#0a0e14;font-weight:bold;font-family:'SFMono-Regular',Consolas,monospace;font-size:13px;letter-spacing:0.04em;">
          {style['emoji']} {escape(level)} ALERT
        </td>
      </tr>
      <tr>
        <td style="padding:20px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;color:#444444;margin-bottom:14px;">
            <tr>
              <td style="padding:2px 0;color:#8a8a85;width:90px;vertical-align:top;">Container</td>
              <td style="padding:2px 0;font-family:'SFMono-Regular',Consolas,monospace;">{container}</td>
            </tr>
            <tr>
              <td style="padding:2px 0;color:#8a8a85;vertical-align:top;">Time</td>
              <td style="padding:2px 0;font-family:'SFMono-Regular',Consolas,monospace;">{timestamp}</td>
            </tr>
          </table>
          <div style="background:#f6f5f2;border:1px solid #e2e0d8;border-radius:4px;padding:12px;font-family:'SFMono-Regular',Consolas,monospace;font-size:12px;line-height:1.5;color:#1a1a1a;white-space:pre-wrap;word-break:break-word;">{body}</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta}</table>
        </td>
      </tr>
      <tr>
        <td style="padding:12px 20px;border-top:1px solid #eeeeeb;color:#a3a39a;font-size:11px;font-family:'SFMono-Regular',Consolas,monospace;">
          via api-watch
        </td>
      </tr>
    </table>
  </body>
</html>'''

    def _send_gmail_sync(self, subject: str, text_body: str, html_body: str):
        # multipart/alternative with plain text attached first, HTML
        # second - clients render the last alternative they understand,
        # so this order lets rich clients use the HTML while anything
        # that can't (or that a user has set to prefer plain text) still
        # gets a fully readable fallback rather than raw markup
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.gmail_user
        msg['To'] = self.gmail_to
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(self.gmail_smtp_host, self.gmail_smtp_port, timeout=10) as server:
            server.starttls()
            server.login(self.gmail_user, self.gmail_app_password)
            server.send_message(msg)

    async def _send_gmail(self, record: dict):
        # smtplib is blocking, keep it off the event loop
        loop = asyncio.get_event_loop()
        level = record.get('level') or 'UNKNOWN'
        subject = f"[apiwatch] {level} in {record.get('container_name')}"
        text_body = self._format_text(record)
        html_body = self._format_html(record)
        await loop.run_in_executor(None, self._send_gmail_sync, subject, text_body, html_body)