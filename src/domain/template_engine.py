# =============================================================================
# VM Automation - Template Engine
# =============================================================================
"""
Moteur de templates pour générer les fichiers d'installation automatique.
Utilise Jinja2 pour le rendu des templates unattend.xml, preseed, cloud-init.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from src.common.config import settings
from src.common.exceptions import ValidationError
from src.common.logging import get_logger

logger = get_logger(__name__)

# Chemin vers les templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


class TemplateEngine:
    """
    Moteur de templates pour l'installation automatique des OS.
    
    Supporte:
    - Windows: unattend.xml (Answer files)
    - Debian/Ubuntu: preseed.cfg
    - Cloud images: cloud-init (YAML)
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """
        Initialise le moteur de templates.
        
        Args:
            templates_dir: Chemin vers le dossier des templates (optionnel)
        """
        self.templates_dir = templates_dir or TEMPLATES_DIR
        
        self._env = Environment(
            loader=FileSystemLoader([
                str(self.templates_dir / "unattend"),
                str(self.templates_dir / "preseed"),
                str(self.templates_dir / "cloud-init"),
                str(self.templates_dir / "kickstart"),
            ]),
            autoescape=select_autoescape(["xml", "html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        logger.debug("template_engine_initialized", templates_dir=str(self.templates_dir))

    def render(self, template_name: str, variables: dict[str, Any]) -> str:
        """
        Rend un template avec les variables fournies.
        
        Args:
            template_name: Nom du fichier template
            variables: Dictionnaire des variables à injecter
            
        Returns:
            Contenu du template rendu
            
        Raises:
            ValidationError: Si le template n'existe pas ou si le rendu échoue
        """
        try:
            template = self._env.get_template(template_name)
            rendered = template.render(**variables)
            
            logger.info(
                "template_rendered",
                template=template_name,
                variables_count=len(variables),
            )
            
            return rendered
            
        except TemplateNotFound:
            raise ValidationError(
                f"Template '{template_name}' not found",
                {"template": template_name, "search_path": str(self.templates_dir)},
            )
        except Exception as e:
            logger.error(
                "template_render_failed",
                template=template_name,
                error=str(e),
            )
            raise ValidationError(
                f"Failed to render template '{template_name}': {e}",
                {"template": template_name},
            )

    def render_windows_unattend(
        self,
        hostname: str,
        admin_password: str,
        locale: str = "fr-FR",
        timezone: str = "Romance Standard Time",
        static_ip: bool = False,
        ip_address: str | None = None,
        gateway: str | None = None,
        dns_server_1: str = "8.8.8.8",
        dns_server_2: str | None = None,
        subnet_prefix: int = 24,
        join_domain: bool = False,
        domain_name: str | None = None,
        domain_user: str | None = None,
        domain_password: str | None = None,
        domain_ou: str | None = None,
        product_key: str | None = None,
        windows_edition: str = "Windows Server 2022 SERVERSTANDARD",
        post_install_commands: list[dict[str, str]] | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère un fichier unattend.xml pour Windows Server.
        
        Args:
            hostname: Nom de la machine
            admin_password: Mot de passe administrateur
            locale: Locale (fr-FR, en-US, etc.)
            timezone: Fuseau horaire Windows
            static_ip: Utiliser une IP statique
            ip_address: Adresse IP (si static_ip)
            gateway: Passerelle (si static_ip)
            dns_server_1: Premier serveur DNS
            dns_server_2: Second serveur DNS (optionnel)
            subnet_prefix: Préfixe réseau (24 = /24 = 255.255.255.0)
            join_domain: Joindre un domaine AD
            domain_name: Nom du domaine AD
            domain_user: Utilisateur pour joindre le domaine
            domain_password: Mot de passe pour joindre le domaine
            domain_ou: OU cible dans AD
            product_key: Clé produit Windows
            windows_edition: Edition Windows à installer
            post_install_commands: Commandes post-installation
            
        Returns:
            Contenu du fichier unattend.xml
        """
        variables = {
            "hostname": hostname,
            "admin_password": admin_password,
            "locale": locale,
            "timezone": timezone,
            "static_ip": static_ip,
            "ip_address": ip_address,
            "gateway": gateway,
            "dns_server_1": dns_server_1,
            "dns_server_2": dns_server_2,
            "subnet_prefix": subnet_prefix,
            "join_domain": join_domain,
            "domain_name": domain_name,
            "domain_user": domain_user,
            "domain_password": domain_password,
            "domain_ou": domain_ou,
            "product_key": product_key,
            "windows_edition": windows_edition,
            "post_install_commands": post_install_commands or [],
            "keyboard_layout": "040c:0000040c" if locale.startswith("fr") else "0409:00000409",
            **extra_vars,
        }
        
        return self.render("windows_server_2022.xml", variables)

    def render_debian_preseed(
        self,
        hostname: str,
        username: str = "admin",
        user_password: str = "TempP@ss123!",
        locale: str = "fr_FR.UTF-8",
        timezone: str = "Europe/Paris",
        keyboard_layout: str = "fr",
        static_ip: bool = False,
        ip_address: str | None = None,
        netmask: str = "255.255.255.0",
        gateway: str | None = None,
        dns_servers: str = "8.8.8.8 8.8.4.4",
        domain: str = "localdomain",
        packages: str = "openssh-server sudo curl wget vim htop net-tools python3 python3-pip qemu-guest-agent",
        ssh_authorized_keys: list[str] | None = None,
        post_install_commands: list[str] | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère un fichier preseed.cfg pour Debian.
        
        Args:
            hostname: Nom de la machine
            username: Utilisateur principal
            user_password: Mot de passe utilisateur
            locale: Locale
            timezone: Fuseau horaire
            keyboard_layout: Layout clavier
            static_ip: Utiliser une IP statique
            ip_address: Adresse IP (si static_ip)
            netmask: Masque réseau
            gateway: Passerelle
            dns_servers: Serveurs DNS (espace comme séparateur)
            domain: Domaine
            packages: Paquets à installer
            ssh_authorized_keys: Clés SSH autorisées
            post_install_commands: Commandes post-installation
            
        Returns:
            Contenu du fichier preseed.cfg
        """
        variables = {
            "hostname": hostname,
            "username": username,
            "user_password": user_password,
            "locale": locale,
            "language": locale.split("_")[0],
            "country": locale.split("_")[1].split(".")[0] if "_" in locale else "FR",
            "timezone": timezone,
            "keyboard_layout": keyboard_layout,
            "static_ip": static_ip,
            "ip_address": ip_address,
            "netmask": netmask,
            "gateway": gateway,
            "dns_servers": dns_servers,
            "domain": domain,
            "packages": packages,
            "ssh_authorized_keys": ssh_authorized_keys or [],
            "post_install_commands": post_install_commands or [],
            **extra_vars,
        }
        
        return self.render("debian_12.cfg", variables)

    def render_cloud_init(
        self,
        hostname: str,
        username: str = "admin",
        user_password: str | None = None,
        user_password_hash: str | None = None,
        locale: str = "fr_FR.UTF-8",
        timezone: str = "Europe/Paris",
        static_ip: bool = False,
        ip_address: str | None = None,
        subnet_prefix: int = 24,
        gateway: str | None = None,
        dns_server_1: str = "8.8.8.8",
        dns_server_2: str | None = None,
        domain: str = "localdomain",
        ssh_authorized_keys: list[str] | None = None,
        ssh_password_auth: bool = True,
        extra_packages: list[str] | None = None,
        post_install_commands: list[str] | None = None,
        extra_files: list[dict[str, str]] | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère une configuration cloud-init.
        
        Args:
            hostname: Nom de la machine
            username: Utilisateur principal
            user_password: Mot de passe en clair (sera hashé)
            user_password_hash: Hash du mot de passe (prioritaire)
            locale: Locale
            timezone: Fuseau horaire
            static_ip: Utiliser une IP statique
            ip_address: Adresse IP
            subnet_prefix: Préfixe réseau
            gateway: Passerelle
            dns_server_1: Premier DNS
            dns_server_2: Second DNS
            domain: Domaine
            ssh_authorized_keys: Clés SSH autorisées
            ssh_password_auth: Autoriser l'auth par mot de passe SSH
            extra_packages: Paquets additionnels
            post_install_commands: Commandes post-installation
            extra_files: Fichiers à créer
            
        Returns:
            Contenu du fichier cloud-init YAML
        """
        variables = {
            "hostname": hostname,
            "username": username,
            "user_password": user_password,
            "user_password_hash": user_password_hash,
            "locale": locale,
            "timezone": timezone,
            "static_ip": static_ip,
            "ip_address": ip_address,
            "subnet_prefix": subnet_prefix,
            "gateway": gateway,
            "dns_server_1": dns_server_1,
            "dns_server_2": dns_server_2,
            "domain": domain,
            "ssh_authorized_keys": ssh_authorized_keys or [],
            "ssh_password_auth": ssh_password_auth,
            "extra_packages": extra_packages or [],
            "post_install_commands": post_install_commands or [],
            "extra_files": extra_files or [],
            **extra_vars,
        }
        
        return self.render("debian_cloud_init.yaml", variables)

    def render_ubuntu_autoinstall(
        self,
        hostname: str,
        username: str = "admin",
        user_password_hash: str | None = None,
        locale: str = "fr_FR.UTF-8",
        timezone: str = "Europe/Paris",
        keyboard_layout: str = "fr",
        static_ip: bool = False,
        ip_address: str | None = None,
        subnet_prefix: int = 24,
        gateway: str | None = None,
        dns_server_1: str = "8.8.8.8",
        dns_server_2: str | None = None,
        domain: str = "localdomain",
        ssh_authorized_keys: list[str] | None = None,
        ssh_password_auth: bool = True,
        extra_packages: list[str] | None = None,
        post_install_commands: list[str] | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère une configuration autoinstall pour Ubuntu 24.04+.
        
        Args:
            hostname: Nom de la machine
            username: Utilisateur principal
            user_password_hash: Hash du mot de passe (mkpasswd -m sha-512)
            locale: Locale
            timezone: Fuseau horaire
            keyboard_layout: Layout clavier
            static_ip: Utiliser une IP statique
            ip_address: Adresse IP
            subnet_prefix: Préfixe réseau
            gateway: Passerelle
            dns_server_1: Premier DNS
            dns_server_2: Second DNS
            domain: Domaine
            ssh_authorized_keys: Clés SSH autorisées
            ssh_password_auth: Autoriser l'auth par mot de passe SSH
            extra_packages: Paquets additionnels
            post_install_commands: Commandes post-installation
            
        Returns:
            Contenu du fichier autoinstall YAML
        """
        variables = {
            "hostname": hostname,
            "username": username,
            "user_password_hash": user_password_hash,
            "locale": locale,
            "timezone": timezone,
            "keyboard_layout": keyboard_layout,
            "static_ip": static_ip,
            "ip_address": ip_address,
            "subnet_prefix": subnet_prefix,
            "gateway": gateway,
            "dns_server_1": dns_server_1,
            "dns_server_2": dns_server_2,
            "domain": domain,
            "ssh_authorized_keys": ssh_authorized_keys or [],
            "ssh_password_auth": ssh_password_auth,
            "extra_packages": extra_packages or [],
            "post_install_commands": post_install_commands or [],
            **extra_vars,
        }
        
        return self.render("ubuntu_autoinstall.yaml", variables)

    def list_templates(self) -> dict[str, list[str]]:
        """
        Liste tous les templates disponibles.
        
        Returns:
            Dictionnaire par catégorie avec les noms de templates
        """
        result: dict[str, list[str]] = {
            "unattend": [],
            "preseed": [],
            "cloud-init": [],
            "kickstart": [],
        }
        
        for category in result.keys():
            category_dir = self.templates_dir / category
            if category_dir.exists():
                result[category] = [
                    f.name for f in category_dir.iterdir() 
                    if f.is_file() and not f.name.startswith(".")
                ]
        
        return result


# Instance singleton
_template_engine: TemplateEngine | None = None


def get_template_engine() -> TemplateEngine:
    """Retourne l'instance singleton du moteur de templates."""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine
