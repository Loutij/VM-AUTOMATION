# =============================================================================
# VM Automation - Email Service
# =============================================================================
"""
Service d'envoi d'emails via SMTP pour les notifications de déploiement.
Templates HTML avec inline styles sur <td> pour compatibilité Outlook/Word.
"""

import html as html_mod
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any

from src.common.config import settings
from src.common.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Outlook-compatible HTML builder (everything on <td>, no div styling)
# ---------------------------------------------------------------------------

_FONT = "Arial,Helvetica,sans-serif"
_MONO = "'Courier New',Courier,monospace"


def _td(content: str, **kw) -> str:
    """Build a <td> with inline style from kwargs."""
    parts = []
    if "bg" in kw:
        parts.append(f"background-color:{kw['bg']}")
    if "color" in kw:
        parts.append(f"color:{kw['color']}")
    if "pad" in kw:
        parts.append(f"padding:{kw['pad']}")
    if "font" in kw:
        parts.append(f"font-family:{kw['font']}")
    if "size" in kw:
        parts.append(f"font-size:{kw['size']}")
    if "weight" in kw:
        parts.append(f"font-weight:{kw['weight']}")
    if "align" in kw:
        parts.append(f"text-align:{kw['align']}")
    if "valign" in kw:
        parts.append(f"vertical-align:{kw['valign']}")
    if "width" in kw:
        parts.append(f"width:{kw['width']}")
    if "border_b" in kw:
        parts.append(f"border-bottom:{kw['border_b']}")
    if "border_l" in kw:
        parts.append(f"border-left:{kw['border_l']}")
    if "border_t" in kw:
        parts.append(f"border-top:{kw['border_t']}")
    if "ls" in kw:
        parts.append(f"letter-spacing:{kw['ls']}")
    if "lh" in kw:
        parts.append(f"line-height:{kw['lh']}")
    if "extra" in kw:
        parts.append(kw["extra"])
    style = ";".join(parts)
    colspan = f' colspan="{kw["colspan"]}"' if "colspan" in kw else ""
    return f'<td{colspan} style="{style};">{content}</td>'


def _row(*cells: str) -> str:
    return f'<tr>{"".join(cells)}</tr>'


def _table(content: str, width: str = "100%", extra: str = "") -> str:
    ex = f" {extra}" if extra else ""
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="{width}"{ex}>'
        f'{content}</table>'
    )


def _logo_block() -> str:
    """Logo OTO Technology."""
    shapes = (
        _table(_row(
            _td("&#9675;", font=_FONT, size="18px", color="#1e293b", pad="0 4px 0 0", weight="bold"),
            _td("&#9679;", font=_FONT, size="18px", color="#1e293b", pad="0 4px 0 0"),
            _td("&#9632;", font=_FONT, size="18px", color="#3b7bf8", pad="0"),
        ), width="auto")
    )
    brand = (
        f'<span style="font-family:{_FONT};font-size:18px;font-weight:bold;'
        f'letter-spacing:2px;color:#1e293b;text-transform:uppercase;">VM Automation</span>'
        f'<br>'
        f'<span style="font-family:{_FONT};font-size:9px;font-weight:600;'
        f'letter-spacing:3px;color:#94a3b8;text-transform:uppercase;">OTO Technology</span>'
    )
    return _table(_row(
        _td(f'{shapes}<br>{brand}', bg="#ffffff", pad="28px 32px", align="center",
            border_b="2px solid #e5e7eb")
    ))


def _status_block(label: str, sub: str, label_color: str, dot_char: str,
                  bg: str, left_border: str) -> str:
    """Status bar."""
    dot = (
        f'<span style="font-size:16px;color:{label_color};line-height:1;">{dot_char}</span>'
    )
    text = (
        f'<span style="font-family:{_FONT};font-size:13px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;color:{label_color};">{label}</span>'
        f'<br>'
        f'<span style="font-family:{_MONO};font-size:11px;color:#94a3b8;">{sub}</span>'
    )
    inner = _table(_row(
        _td(dot, pad="0 12px 0 0", valign="middle", width="30px"),
        _td(text, valign="middle"),
    ))
    return _table(_row(
        _td(inner, bg=bg, pad="14px 32px", border_b="1px solid #e5e7eb",
            border_l=f"4px solid {left_border}")
    ))


def _section_label(title: str) -> str:
    """Section title."""
    return _table(_row(
        _td(title, font=_FONT, size="9px", weight="800", color="#3b7bf8",
            pad="0 0 12px 0",
            extra="text-transform:uppercase;letter-spacing:2.5px")
    ))


def _info_table_row(label: str, value: str, mono: bool = False) -> str:
    """Info table row."""
    vfont = _MONO if mono else _FONT
    return _row(
        _td(label, font=_FONT, size="10px", weight="700", color="#94a3b8",
            pad="9px 12px 9px 0", width="38%", border_b="1px solid #f1f5f9",
            valign="middle",
            extra="text-transform:uppercase;letter-spacing:1.5px"),
        _td(value, font=vfont, size="12px", color="#1e293b",
            pad="9px 0", border_b="1px solid #f1f5f9", valign="middle"),
    )


def _tag_html(text: str, bg: str, color: str, border: str) -> str:
    """Inline tag/badge."""
    return (
        f'<span style="font-family:{_FONT};font-size:9px;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:1px;padding:3px 8px;'
        f'background-color:{bg};color:{color};border:1px solid {border};">'
        f'{text}</span>'
    )


def _metrics_row(cpu: str, ram: str, disk: str, duration: str) -> str:
    """4 metric boxes in a table row."""
    def box(val: str, lbl: str, color: str) -> str:
        return _td(
            f'<span style="font-family:{_MONO};font-size:20px;font-weight:900;'
            f'color:{color};line-height:1;">{val}</span><br>'
            f'<span style="font-family:{_FONT};font-size:9px;font-weight:700;'
            f'color:#94a3b8;text-transform:uppercase;letter-spacing:1.5px;">{lbl}</span>',
            bg="#f8fafc", pad="14px 8px", align="center", width="25%",
            border_b="1px solid #e2e8f0",
        )
    return _table(
        _row(
            box(cpu, "vCPU", "#3b7bf8"),
            _td("", width="8px"),
            box(ram, "RAM", "#3b7bf8"),
            _td("", width="8px"),
            box(disk, "Disque", "#16a34a"),
            _td("", width="8px"),
            box(duration, "Durée", "#d97706"),
        )
    )


def _log_block(log_html: str) -> str:
    """Log block."""
    return _table(_row(
        _td(log_html, bg="#f8fafc", pad="14px 16px", font=_MONO,
            size="11px", lh="2.0", color="#64748b",
            border_b="1px solid #e2e8f0")
    ))


def _log_line(ts: str, level: str, msg: str) -> str:
    """Single formatted log line."""
    colors = {
        "OK": "#16a34a", "DONE": "#16a34a", "SUCCESS": "#16a34a",
        "INFO": "#2563eb",
        "WARN": "#d97706", "WARNING": "#d97706",
        "ERR": "#dc2626", "ERROR": "#dc2626", "FAIL": "#dc2626",
    }
    lc = colors.get(level.upper(), "#2563eb")
    return (
        f'<span style="color:#94a3b8;">[{ts}]</span> '
        f'<span style="color:{lc};font-weight:bold;">{level:<5s}</span> '
        f'<span style="color:#64748b;">{msg}</span><br>'
    )


def _cta_buttons(primary_href: str, primary_text: str,
                 ghost_href: str, ghost_text: str) -> str:
    """CTA buttons row."""
    primary = (
        f'<a href="{primary_href}" style="display:inline-block;background-color:#3b7bf8;'
        f'color:#ffffff;text-decoration:none;font-family:{_FONT};font-size:11px;'
        f'font-weight:800;text-transform:uppercase;letter-spacing:1.5px;'
        f'padding:12px 28px;mso-padding-alt:12px 28px;">{primary_text}</a>'
    )
    ghost = (
        f'<a href="{ghost_href}" style="display:inline-block;background-color:#ffffff;'
        f'color:#64748b;text-decoration:none;font-family:{_FONT};font-size:10px;'
        f'font-weight:700;text-transform:uppercase;letter-spacing:1.2px;'
        f'padding:10px 20px;border:1px solid #e2e8f0;'
        f'mso-padding-alt:10px 20px;">{ghost_text}</a>'
    )
    return _table(_row(
        _td(f'{primary}&nbsp;&nbsp;&nbsp;{ghost}', align="center", pad="12px 0 20px")
    ))


def _footer_block() -> str:
    """Footer."""
    year = datetime.utcnow().year
    return _table(_row(
        _td(
            f'<span style="font-family:{_MONO};font-size:10px;color:#94a3b8;'
            f'text-transform:uppercase;letter-spacing:2px;">VM Automation V2.0</span>'
            f'<br>'
            f'<span style="font-family:{_FONT};font-size:10px;color:#94a3b8;">'
            f'&copy; {year} OTO Technology</span>',
            bg="#f8fafc", pad="18px 32px", align="center", border_t="1px solid #e5e7eb"
        )
    ))


def _signature() -> str:
    """Signature line."""
    return _table(_row(
        _td(
            f'<span style="font-family:{_FONT};font-size:10px;color:#94a3b8;line-height:1.8;">'
            f'Notification automatique &mdash; '
            f'<span style="color:#3b7bf8;font-weight:bold;">VM Automation v2.0</span>'
            f'<br>Ne pas répondre &middot; '
            f'<a href="mailto:support@oto-technology.fr" style="color:#3b7bf8;'
            f'text-decoration:none;">support@oto-technology.fr</a>'
            f'</span>',
            pad="16px 0 0", align="center", border_t="1px solid #f1f5f9"
        )
    ))


def _wrap(inner: str) -> str:
    """Full HTML document wrapper — Outlook compatible."""
    return (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
        '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n<head>\n'
        '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        '<title>VM Automation</title>\n'
        '<!--[if mso]><style>table{border-collapse:collapse;}td{font-family:Arial,sans-serif;}'
        '</style><![endif]-->\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background-color:#f1f5f9;'
        f'font-family:{_FONT};-webkit-text-size-adjust:100%;">\n'
        # Outer wrapper table for centering
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="background-color:#f1f5f9;">'
        f'<tr><td align="center" style="padding:40px 16px;">\n'
        # Main card table
        f'<!--[if mso]><table cellpadding="0" cellspacing="0" border="0" width="600">'
        f'<tr><td><![endif]-->\n'
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:600px;width:100%;background-color:#ffffff;'
        f'border:1px solid #e2e8f0;">\n'
        f'<tr><td>\n'
        f'{inner}\n'
        f'</td></tr>\n</table>\n'
        f'<!--[if mso]></td></tr></table><![endif]-->\n'
        f'</td></tr></table>\n'
        '</body>\n</html>'
    )


class EmailService:
    """Service d'envoi d'emails SMTP."""

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.use_ssl = settings.smtp_ssl
        self.user = settings.smtp_user
        self.password = settings.smtp_password.get_secret_value()
        self.from_addr = settings.smtp_from or settings.smtp_user
        self.enabled = settings.smtp_enabled

    def _create_smtp_connection(self):
        if self.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            server.starttls()
        if self.user and self.password:
            server.login(self.user, self.password)
        return server

    def send_email(self, to: str, subject: str, body_text: str,
                   body_html: str | None = None) -> bool:
        if not self.enabled:
            logger.info("email_disabled", to=to, subject=subject)
            return False
        if not to:
            logger.warning("email_no_recipient", subject=subject)
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = to
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            if body_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))
            with self._create_smtp_connection() as server:
                server.sendmail(self.from_addr, [to], msg.as_string())
            logger.info("email_sent", to=to, subject=subject)
            return True
        except Exception as exc:
            logger.error("email_send_failed", to=to, subject=subject, error=str(exc))
            return False

    # ------------------------------------------------------------------ #
    #  Deployment completed                                               #
    # ------------------------------------------------------------------ #
    def send_deployment_completed(self, user_email: str, vm_name: str,
                                  deployment_details: dict[str, Any]) -> bool:
        subject = f"[VM Automation] Déploiement terminé — {vm_name}"
        d = deployment_details
        dep_id = d.get("deployment_id", "N/A")
        ip = d.get("ip_address") or "Non attribuée"
        hyp = d.get("hypervisor_name", "N/A")
        dur = d.get("duration", "N/A")
        usr = d.get("admin_username", "otoroot")
        pwd = d.get("admin_password", "tooroto")
        cpu = d.get("cpu_count", "N/A")
        ram = d.get("ram_gb", "N/A")
        disk = d.get("disk_gb", "N/A")
        os_t = d.get("os_type", "N/A")
        os_f = d.get("os_family", "N/A")
        tpl = d.get("template_name", "N/A")
        t0 = d.get("started_at", "N/A")
        t1 = d.get("completed_at", datetime.utcnow().isoformat())
        logs: list = d.get("logs", [])
        dash = d.get("dashboard_url", "")

        esc = html_mod.escape
        e_vm, e_dep, e_ip = esc(str(vm_name)), esc(str(dep_id)), esc(str(ip))
        e_hyp, e_dur = esc(str(hyp)), esc(str(dur))
        e_usr, e_pwd = esc(str(usr)), esc(str(pwd))
        e_cpu, e_ram, e_disk = esc(str(cpu)), esc(str(ram)), esc(str(disk))
        e_os, e_fam, e_tpl = esc(str(os_t)), esc(str(os_f)), esc(str(tpl))
        e_t0, e_t1, e_email = esc(str(t0)), esc(str(t1)), esc(str(user_email))

        os_tag = _tag_html(e_os,
                           "#f0fdf4" if "win" in os_f.lower() else "#eff6ff",
                           "#16a34a" if "win" in os_f.lower() else "#2563eb",
                           "#bbf7d0" if "win" in os_f.lower() else "#bfdbfe")
        hyp_tag = _tag_html(e_hyp, "#f5f3ff", "#7c3aed", "#ddd6fe")

        # Logs
        log_h = ""
        for entry in (logs[-10:] if logs else []):
            if isinstance(entry, dict):
                log_h += _log_line(
                    esc(str(entry.get("timestamp", ""))),
                    str(entry.get("level", entry.get("status", "INFO"))),
                    esc(str(entry.get("message", ""))))
            else:
                log_h += f'<span style="color:#64748b;">{esc(str(entry))}</span><br>'
        if not log_h:
            log_h = '<span style="color:#94a3b8;">Aucune entrée de log.</span>'

        d_href = esc(str(dash)) if dash else "#"
        l_href = f"{d_href}/logs" if dash else "#"

        # Plain text
        body_text = (
            f"Déploiement réussi — {vm_name}\n{'=' * 50}\n\n"
            f"Job #{dep_id} · Terminé en {dur}\n\n"
            f"  Nom VM        : {vm_name}\n  Hyperviseur   : {hyp}\n"
            f"  OS            : {os_t} ({os_f})\n  Template      : {tpl}\n"
            f"  IP            : {ip}\n  Identifiants  : {usr} / {pwd}\n"
            f"  Horodatage    : {t0} → {t1}\n\n"
            f"  vCPU: {cpu} · RAM: {ram} GB · Disque: {disk} GB\n\n"
            f"Changez le mot de passe dès la première connexion.\n\n"
            f"---\nVM Automation v2.0 · © OTO Technology\n"
        )

        # HTML
        h = _logo_block()
        h += _status_block("Déploiement réussi",
                           f"Job #{e_dep} &middot; Terminé en {e_dur}",
                           "#16a34a", "&#9679;", "#f0fdf4", "#22c55e")

        # Body padding wrapper
        h += '<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>'
        h += f'<td style="padding:28px 32px;">'

        # Info table
        h += _section_label("Détails de la machine virtuelle")
        h += '<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:24px;">'
        h += _info_table_row("Nom VM", f'<strong>{e_vm}</strong>')
        h += _info_table_row("Hyperviseur", hyp_tag)
        h += _info_table_row("OS", os_tag)
        h += _info_table_row("Template", e_tpl, mono=True)
        h += _info_table_row("IP assignée", f'<strong>{e_ip}</strong>', mono=True)
        h += _info_table_row("Identifiants", f'{e_usr} / {e_pwd}', mono=True)
        h += _info_table_row("Déclenché par", e_email)
        h += _info_table_row("Horodatage", f'{e_t0} &rarr; {e_t1}')
        h += '</table>'

        # Metrics
        h += _section_label("Ressources provisionnées")
        h += _metrics_row(e_cpu, f"{e_ram} GB", f"{e_disk} GB", e_dur)
        h += '<br>'

        # Logs
        h += _section_label("Dernières lignes de log")
        h += _log_block(log_h)
        h += '<br>'

        # Warning
        h += _table(_row(
            _td(
                f'<span style="font-family:{_FONT};font-size:11px;color:#92400e;">'
                f'&#9888; Changez le mot de passe administrateur dès la première connexion.'
                f'</span>',
                bg="#fffbeb", pad="12px 16px", border_b="1px solid #fde68a"
            )
        ))
        h += '<br>'

        # CTA
        h += _cta_buttons(d_href, "Voir dans le dashboard", l_href, "Logs complets")

        # Signature
        h += _signature()

        h += '</td></tr></table>'
        h += _footer_block()

        return self.send_email(user_email, subject, body_text, _wrap(h))

    # ------------------------------------------------------------------ #
    #  Deployment failed                                                  #
    # ------------------------------------------------------------------ #
    def send_deployment_failed(self, user_email: str, vm_name: str,
                               error_message: str,
                               deployment_details: dict[str, Any] | None = None) -> bool:
        subject = f"[VM Automation] Échec du déploiement — {vm_name}"
        d = deployment_details or {}
        dep_id = d.get("deployment_id", "N/A")
        hyp = d.get("hypervisor_name", "N/A")
        os_t = d.get("os_type", "N/A")
        os_f = d.get("os_family", "N/A")
        t0 = d.get("started_at", "N/A")
        t1 = d.get("failed_at", d.get("completed_at", datetime.utcnow().isoformat()))
        step = d.get("current_step", "N/A")
        dash = d.get("dashboard_url", "")
        logs: list = d.get("logs", [])

        esc = html_mod.escape
        e_vm, e_dep = esc(str(vm_name)), esc(str(dep_id))
        e_err, e_hyp = esc(str(error_message)), esc(str(hyp))
        e_os, e_fam = esc(str(os_t)), esc(str(os_f))
        e_t0, e_t1, e_step = esc(str(t0)), esc(str(t1)), esc(str(step))

        log_h = ""
        for entry in (logs[-10:] if logs else []):
            if isinstance(entry, dict):
                log_h += _log_line(
                    esc(str(entry.get("timestamp", ""))),
                    str(entry.get("level", entry.get("status", "INFO"))),
                    esc(str(entry.get("message", ""))))
            else:
                log_h += f'<span style="color:#64748b;">{esc(str(entry))}</span><br>'

        d_href = esc(str(dash)) if dash else "#"
        r_href = f"{d_href}/retry" if dash else "#"

        body_text = (
            f"Déploiement échoué — {vm_name}\n{'=' * 50}\n\n"
            f"Job #{dep_id}\n\nERREUR:\n{error_message}\n\n"
            f"  Nom VM      : {vm_name}\n  Hyperviseur : {hyp}\n"
            f"  OS          : {os_t} ({os_f})\n  Étape       : {step}\n"
            f"  Démarré     : {t0}\n  Échoué      : {t1}\n\n"
            f"---\nVM Automation v2.0 · © OTO Technology\n"
        )

        h = _logo_block()
        h += _status_block("Déploiement échoué",
                           f"Job #{e_dep} &middot; Étape : {e_step}",
                           "#dc2626", "&#9679;", "#fef2f2", "#ef4444")

        h += '<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>'
        h += f'<td style="padding:28px 32px;">'

        # Error block
        h += _section_label("Erreur")
        h += _table(_row(
            _td(f'<span style="font-family:{_MONO};font-size:12px;color:#991b1b;'
                f'line-height:1.7;word-break:break-all;">{e_err}</span>',
                bg="#fef2f2", pad="16px", border_b="1px solid #fecaca")
        ))
        h += '<br>'

        # Info
        h += _section_label("Détails du déploiement")
        h += '<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:24px;">'
        h += _info_table_row("Nom VM", f'<strong>{e_vm}</strong>')
        h += _info_table_row("Hyperviseur", _tag_html(e_hyp, "#f5f3ff", "#7c3aed", "#ddd6fe"))
        h += _info_table_row("OS", f'{e_os} ({e_fam})')
        h += _info_table_row("Étape échouée", f'<strong style="color:#dc2626;">{e_step}</strong>')
        h += _info_table_row("Démarré", e_t0)
        h += _info_table_row("Échoué", e_t1)
        h += '</table>'

        if log_h:
            h += _section_label("Dernières lignes de log")
            h += _log_block(log_h)
            h += '<br>'

        h += _cta_buttons(d_href, "Voir les logs", r_href, "Relancer")
        h += _signature()

        h += '</td></tr></table>'
        h += _footer_block()

        return self.send_email(user_email, subject, body_text, _wrap(h))

    # ------------------------------------------------------------------ #
    #  Test email                                                         #
    # ------------------------------------------------------------------ #
    def send_test_email(self, to: str) -> bool:
        subject = "[VM Automation] Test de configuration email"
        body_text = (
            "Ceci est un email de test de VM Automation.\n"
            "Configuration SMTP correcte.\n\n---\nVM Automation\n"
        )

        h = _logo_block()
        h += _status_block("Test de configuration", f"SMTP &middot; {self.host}",
                           "#2563eb", "&#9679;", "#eff6ff", "#3b7bf8")
        h += _table(_row(
            _td(
                f'<span style="font-size:42px;">&#10003;</span><br><br>'
                f'<span style="font-family:{_FONT};font-size:18px;font-weight:700;'
                f'color:#16a34a;">Configuration réussie</span><br>'
                f'<span style="font-family:{_FONT};font-size:13px;color:#64748b;">'
                f'La configuration SMTP fonctionne correctement.</span>',
                pad="40px 32px", align="center"
            )
        ))
        h += _footer_block()

        original = self.enabled
        self.enabled = True
        try:
            return self.send_email(to, subject, body_text, _wrap(h))
        finally:
            self.enabled = original


# Instance singleton
email_service = EmailService()
