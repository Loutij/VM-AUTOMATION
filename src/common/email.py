# =============================================================================
# VM Automation - Email Service
# =============================================================================
"""
Service d'envoi d'emails via SMTP pour les notifications de déploiement.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any

from src.common.config import settings
from src.common.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Service d'envoi d'emails SMTP."""
    
    def __init__(self):
        """Initialise le service email avec la configuration."""
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.use_ssl = settings.smtp_ssl
        self.user = settings.smtp_user
        self.password = settings.smtp_password.get_secret_value()
        self.from_addr = settings.smtp_from or settings.smtp_user
        self.enabled = settings.smtp_enabled
    
    def _create_smtp_connection(self):
        """Crée une connexion SMTP."""
        if self.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            server.starttls()
        
        if self.user and self.password:
            server.login(self.user, self.password)
        
        return server
    
    def send_email(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> bool:
        """
        Envoie un email.
        
        Args:
            to: Adresse email du destinataire
            subject: Sujet de l'email
            body_text: Corps du message en texte brut
            body_html: Corps du message en HTML (optionnel)
            
        Returns:
            True si l'envoi a réussi
        """
        if not self.enabled:
            logger.info("email_disabled", to=to, subject=subject)
            return False
        
        if not to:
            logger.warning("email_no_recipient", subject=subject)
            return False
        
        try:
            # Créer le message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = to
            
            # Ajouter le contenu texte
            part_text = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part_text)
            
            # Ajouter le contenu HTML si fourni
            if body_html:
                part_html = MIMEText(body_html, "html", "utf-8")
                msg.attach(part_html)
            
            # Envoyer
            with self._create_smtp_connection() as server:
                server.sendmail(self.from_addr, [to], msg.as_string())
            
            logger.info("email_sent", to=to, subject=subject)
            return True
            
        except Exception as e:
            logger.error("email_send_failed", to=to, subject=subject, error=str(e))
            return False
    
    def send_deployment_completed(
        self,
        user_email: str,
        vm_name: str,
        deployment_details: dict[str, Any],
    ) -> bool:
        """
        Envoie un email de notification de fin de déploiement réussi.
        
        Args:
            user_email: Email de l'utilisateur
            vm_name: Nom de la VM déployée
            deployment_details: Détails du déploiement
            
        Returns:
            True si l'envoi a réussi
        """
        subject = f"[VM Automation] Déploiement terminé - {vm_name}"
        
        # Extraire les informations
        ip_address = deployment_details.get("ip_address", "Non attribuée")
        hypervisor_name = deployment_details.get("hypervisor_name", "N/A")
        duration = deployment_details.get("duration", "N/A")
        admin_password = deployment_details.get("admin_password", "******")
        cpu_count = deployment_details.get("cpu_count", "N/A")
        ram_gb = deployment_details.get("ram_gb", "N/A")
        disk_gb = deployment_details.get("disk_gb", "N/A")
        os_type = deployment_details.get("os_type", "N/A")
        network_switch = deployment_details.get("network_switch", "N/A")
        started_at = deployment_details.get("started_at", "N/A")
        completed_at = deployment_details.get("completed_at", datetime.utcnow().isoformat())
        
        # Corps texte
        body_text = f"""Bonjour,

Votre machine virtuelle "{vm_name}" est maintenant prête à l'emploi.

== INFORMATIONS GÉNÉRALES ==
Nom de la VM: {vm_name}
Système d'exploitation: {os_type}
Hyperviseur: {hypervisor_name}
Démarré: {started_at}
Terminé: {completed_at}
Durée totale: {duration}

== CONFIGURATION MATÉRIELLE ==
Processeurs: {cpu_count} vCPU
Mémoire RAM: {ram_gb} Go
Disque: {disk_gb} Go

== RÉSEAU ==
Adresse IP: {ip_address}
Switch virtuel: {network_switch}

== IDENTIFIANTS PAR DÉFAUT ==
Utilisateur: .\\Administrateur
Mot de passe: {admin_password}

== CONNEXION ==
Connexion RDP: rdp://{ip_address}
Pour vous connecter, ouvrez une connexion Bureau à distance vers {ip_address}

IMPORTANT: Changez le mot de passe administrateur dès la première connexion.

---
Cet email a été envoyé automatiquement par VM Automation.
Ne répondez pas à ce message.
"""
        
        # Corps HTML
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header .status {{ background: #22c55e; color: white; padding: 4px 12px; border-radius: 20px; display: inline-block; margin-top: 10px; font-size: 14px; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 25px; }}
        .section-title {{ color: #1e40af; font-size: 16px; font-weight: 600; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        .info-item {{ background: #f8fafc; padding: 12px; border-radius: 8px; }}
        .info-label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .info-value {{ color: #1f2937; font-size: 14px; font-weight: 500; margin-top: 4px; }}
        .credentials {{ background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 16px; }}
        .credentials-title {{ color: #92400e; font-weight: 600; margin-bottom: 10px; }}
        .rdp-button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 500; margin-top: 15px; }}
        .rdp-button:hover {{ background: #1d4ed8; }}
        .warning {{ background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 12px; color: #991b1b; font-size: 13px; margin-top: 15px; }}
        .footer {{ background: #f8fafc; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 Déploiement Terminé</h1>
            <div class="status">✓ Succès</div>
        </div>
        <div class="content">
            <p style="color: #4b5563; margin-bottom: 25px;">
                Votre machine virtuelle <strong>{vm_name}</strong> est maintenant prête à l'emploi.
            </p>
            
            <div class="section">
                <div class="section-title">📋 Informations générales</div>
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">Nom de la VM</div>
                        <div class="info-value">{vm_name}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Système</div>
                        <div class="info-value">{os_type}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Hyperviseur</div>
                        <div class="info-value">{hypervisor_name}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Durée</div>
                        <div class="info-value">{duration}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">💻 Configuration matérielle</div>
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">Processeurs</div>
                        <div class="info-value">{cpu_count} vCPU</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Mémoire RAM</div>
                        <div class="info-value">{ram_gb} Go</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Disque</div>
                        <div class="info-value">{disk_gb} Go</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Switch réseau</div>
                        <div class="info-value">{network_switch}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">🌐 Réseau</div>
                <div class="info-item" style="text-align: center;">
                    <div class="info-label">Adresse IP</div>
                    <div class="info-value" style="font-size: 20px; font-family: monospace;">{ip_address}</div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">🔐 Identifiants</div>
                <div class="credentials">
                    <div class="credentials-title">Identifiants par défaut</div>
                    <div style="display: flex; gap: 20px;">
                        <div>
                            <div class="info-label">Utilisateur</div>
                            <div class="info-value">.\\Administrateur</div>
                        </div>
                        <div>
                            <div class="info-label">Mot de passe</div>
                            <div class="info-value" style="font-family: monospace;">{admin_password}</div>
                        </div>
                    </div>
                </div>
                <div class="warning">
                    ⚠️ <strong>Important :</strong> Changez le mot de passe administrateur dès la première connexion.
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="rdp://{ip_address}" class="rdp-button">🖥️ Se connecter en RDP</a>
            </div>
        </div>
        <div class="footer">
            <p>Cet email a été envoyé automatiquement par VM Automation.</p>
            <p>Ne répondez pas à ce message.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return self.send_email(user_email, subject, body_text, body_html)
    
    def send_deployment_failed(
        self,
        user_email: str,
        vm_name: str,
        error_message: str,
        deployment_details: dict[str, Any] | None = None,
    ) -> bool:
        """
        Envoie un email de notification d'échec de déploiement.
        
        Args:
            user_email: Email de l'utilisateur
            vm_name: Nom de la VM
            error_message: Message d'erreur
            deployment_details: Détails du déploiement (optionnel)
            
        Returns:
            True si l'envoi a réussi
        """
        subject = f"[VM Automation] Échec du déploiement - {vm_name}"
        
        details = deployment_details or {}
        hypervisor_name = details.get("hypervisor_name", "N/A")
        started_at = details.get("started_at", "N/A")
        failed_at = details.get("failed_at", datetime.utcnow().isoformat())
        step = details.get("current_step", "N/A")
        
        body_text = f"""Bonjour,

Le déploiement de la machine virtuelle "{vm_name}" a échoué.

== DÉTAILS ==
Nom de la VM: {vm_name}
Hyperviseur: {hypervisor_name}
Démarré: {started_at}
Échoué: {failed_at}
Étape: {step}

== ERREUR ==
{error_message}

Veuillez vérifier les logs de déploiement pour plus de détails.

---
Cet email a été envoyé automatiquement par VM Automation.
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ padding: 30px; }}
        .error-box {{ background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .error-box h3 {{ color: #991b1b; margin: 0 0 10px 0; }}
        .error-box pre {{ background: #fee2e2; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 13px; color: #7f1d1d; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; }}
        .info-item {{ background: #f8fafc; padding: 12px; border-radius: 8px; }}
        .info-label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; }}
        .info-value {{ color: #1f2937; font-size: 14px; font-weight: 500; margin-top: 4px; }}
        .footer {{ background: #f8fafc; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>❌ Échec du Déploiement</h1>
        </div>
        <div class="content">
            <p style="color: #4b5563;">
                Le déploiement de la machine virtuelle <strong>{vm_name}</strong> a échoué.
            </p>
            
            <div class="error-box">
                <h3>🔴 Erreur</h3>
                <pre>{error_message}</pre>
            </div>
            
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Hyperviseur</div>
                    <div class="info-value">{hypervisor_name}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Étape</div>
                    <div class="info-value">{step}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Démarré</div>
                    <div class="info-value">{started_at}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Échoué</div>
                    <div class="info-value">{failed_at}</div>
                </div>
            </div>
            
            <p style="color: #6b7280; margin-top: 20px; font-size: 14px;">
                Consultez les logs de déploiement dans l'interface VM Automation pour plus de détails.
            </p>
        </div>
        <div class="footer">
            <p>Cet email a été envoyé automatiquement par VM Automation.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return self.send_email(user_email, subject, body_text, body_html)
    
    def send_test_email(self, to: str) -> bool:
        """
        Envoie un email de test.
        
        Args:
            to: Adresse email de test
            
        Returns:
            True si l'envoi a réussi
        """
        subject = "[VM Automation] Test de configuration email"
        
        body_text = """Bonjour,

Ceci est un email de test envoyé par VM Automation.

Si vous recevez ce message, la configuration SMTP est correcte.

---
VM Automation
"""
        
        body_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 30px; text-align: center; }
        .content { padding: 30px; text-align: center; }
        .check { font-size: 48px; margin-bottom: 20px; }
        .footer { background: #f8fafc; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📧 Test Email</h1>
        </div>
        <div class="content">
            <div class="check">✅</div>
            <h2 style="color: #22c55e;">Configuration réussie !</h2>
            <p style="color: #6b7280;">
                La configuration SMTP de VM Automation fonctionne correctement.
            </p>
        </div>
        <div class="footer">
            <p>VM Automation</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Forcer l'envoi même si disabled pour le test
        original_enabled = self.enabled
        self.enabled = True
        try:
            return self.send_email(to, subject, body_text, body_html)
        finally:
            self.enabled = original_enabled


# Instance singleton
email_service = EmailService()
