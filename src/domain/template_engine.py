# =============================================================================
# VM Automation - Template Engine
# =============================================================================
"""
Moteur de templates pour générer les fichiers d'installation automatique.
Utilise Jinja2 pour le rendu des templates unattend.xml, preseed, cloud-init.
"""

import hashlib
import os
import re
import shlex
import subprocess
from html import escape as html_escape
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from src.common.config import settings
from src.common.exceptions import ValidationError
from src.common.logging import get_logger

logger = get_logger(__name__)

# Chemin vers les templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# --- Input validation and sanitization helpers ---

# Hostname: RFC 952/1123 — alphanumeric and hyphens, 1-15 chars for Windows compat
_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,14}$')
# Username: alphanumeric, underscore, hyphen, 1-32 chars
_USERNAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_\-]{0,31}$')
# Password: reject shell metacharacters that could break interpolation contexts
_PASSWORD_DANGEROUS_RE = re.compile(r'[`$\\"\x00-\x08\x0b\x0c\x0e-\x1f]')


def _validate_hostname(hostname: str) -> str:
    """Validate hostname for use in templates. Raises ValidationError if invalid."""
    if not _HOSTNAME_RE.match(hostname):
        raise ValidationError(
            f"Invalid hostname: {hostname!r}. Must be 1-15 alphanumeric/hyphen chars, "
            "starting with alphanumeric.",
            {"hostname": hostname},
        )
    return hostname


def _validate_username(username: str) -> str:
    """Validate username for use in templates. Raises ValidationError if invalid."""
    if not _USERNAME_RE.match(username):
        raise ValidationError(
            f"Invalid username: {username!r}. Must be 1-32 chars, alphanumeric/underscore/hyphen, "
            "starting with a letter or underscore.",
            {"username": username},
        )
    return username


def _validate_password(password: str) -> str:
    """Validate password doesn't contain dangerous shell metacharacters."""
    if _PASSWORD_DANGEROUS_RE.search(password):
        raise ValidationError(
            "Password contains characters that are not allowed (backtick, dollar, "
            "backslash, double-quote, or control characters).",
            {},
        )
    return password


def _sanitize_for_xml(value: str) -> str:
    """Escape special XML characters in a value for safe embedding in XML."""
    return html_escape(value, quote=True)


def _sanitize_for_shell(value: str) -> str:
    """Sanitize a value for safe use in shell command interpolation."""
    return shlex.quote(value)


def _sanitize_shell_command(cmd: str) -> str:
    """Validate a shell command is not obviously malicious.

    Rejects commands containing common injection patterns while allowing
    legitimate admin commands.
    """
    # Remove null bytes
    cmd = cmd.replace('\x00', '')
    # Reject commands with obvious injection patterns
    dangerous_patterns = [
        '$(', '`',       # command substitution
        '&&', '||',      # command chaining (unless legitimately needed)
        '|',             # pipe
        ';',             # command separator
        '\n',            # newline injection
        '>', '>>',       # output redirection
        '<',             # input redirection
    ]
    for pattern in dangerous_patterns:
        if pattern in cmd:
            raise ValidationError(
                f"Shell command contains disallowed pattern {pattern!r}: {cmd!r}",
                {"command": cmd},
            )
    return cmd


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
        # Register custom sanitization filters for use in Jinja2 templates
        self._env.filters["shell_quote"] = shlex.quote
        self._env.filters["xml_escape"] = _sanitize_for_xml
        
        logger.debug("template_engine_initialized", templates_dir=str(self.templates_dir))

    @staticmethod
    def _sha512_crypt(password: str, salt: str | None = None) -> str:
        """Generate a SHA-512 crypt hash compatible with /etc/shadow ($6$) using openssl."""
        cmd = ["openssl", "passwd", "-6"]
        if salt:
            cmd.extend(["-salt", salt])
        cmd.extend(["-stdin"])
        result = subprocess.run(
            cmd,
            input=password,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"openssl passwd failed: {result.stderr}")
        return result.stdout.strip()

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
        admin_username: str = "otoroot",
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
        template_name: str | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère un fichier unattend.xml pour Windows.

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
            template_name: Nom du template OS (pour sélection automatique du fichier unattend)

        Returns:
            Contenu du fichier unattend.xml
        """
        # Validate and sanitize inputs for XML context
        _validate_hostname(hostname)
        _validate_username(admin_username)

        # Sanitize post-install commands for XML embedding
        sanitized_post_cmds = []
        for cmd_dict in (post_install_commands or []):
            sanitized = {}
            for k, v in cmd_dict.items():
                sanitized[k] = _sanitize_for_xml(v)
            sanitized_post_cmds.append(sanitized)

        variables = {
            "hostname": _sanitize_for_xml(hostname),
            "admin_password": _sanitize_for_xml(admin_password),
            "admin_username": _sanitize_for_xml(admin_username),
            "locale": _sanitize_for_xml(locale),
            "timezone": _sanitize_for_xml(timezone),
            "static_ip": static_ip,
            "ip_address": _sanitize_for_xml(ip_address) if ip_address else ip_address,
            "gateway": _sanitize_for_xml(gateway) if gateway else gateway,
            "dns_server_1": _sanitize_for_xml(dns_server_1),
            "dns_server_2": _sanitize_for_xml(dns_server_2) if dns_server_2 else dns_server_2,
            "subnet_prefix": subnet_prefix,
            "join_domain": join_domain,
            "domain_name": _sanitize_for_xml(domain_name) if domain_name else domain_name,
            "domain_user": _sanitize_for_xml(domain_user) if domain_user else domain_user,
            "domain_password": _sanitize_for_xml(domain_password) if domain_password else domain_password,
            "domain_ou": _sanitize_for_xml(domain_ou) if domain_ou else domain_ou,
            "product_key": _sanitize_for_xml(product_key) if product_key else product_key,
            "windows_edition": _sanitize_for_xml(windows_edition),
            "post_install_commands": sanitized_post_cmds,
            "keyboard_layout": "040c:0000040c" if locale.startswith("fr") else "0409:00000409",
            **extra_vars,
        }

        # Sélectionner le bon fichier unattend selon l'OS
        unattend_file = self._select_windows_unattend(template_name, windows_edition)
        return self.render(unattend_file, variables)

    def _select_windows_unattend(self, template_name: str | None, windows_edition: str) -> str:
        """Sélectionne le fichier unattend.xml approprié selon l'OS."""
        name_lower = (template_name or "").lower()
        edition_lower = windows_edition.lower()

        if "11" in name_lower or "windows 11" in edition_lower:
            return "windows_11.xml"
        if "10" in name_lower or "windows 10" in edition_lower:
            return "windows_10.xml"
        if "2019" in name_lower or "2019" in edition_lower:
            return "windows_server_2019.xml"
        if "2025" in name_lower or "2025" in edition_lower:
            return "windows_server_2025.xml"
        # Default: Server 2022
        return "windows_server_2022.xml"

    def render_debian_preseed(
        self,
        hostname: str,
        username: str = "otoroot",
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
        packages: str = "openssh-server sudo curl wget vim htop net-tools python3 python3-pip hyperv-daemons",
        ssh_authorized_keys: list[str] | None = None,
        post_install_commands: list[str] | None = None,
        os_type: str = "debian_12",
        **extra_vars: Any,
    ) -> str:
        """
        Génère un fichier preseed.cfg pour Debian.

        Args:
            hostname: Nom de la machine
            username: Utilisateur principal
            user_password: Mot de passe utilisateur (sera hashé SHA-512 pour Debian 13+)
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
            os_type: Type d'OS (debian_12, debian_13, etc.)

        Returns:
            Contenu du fichier preseed.cfg
        """
        # Validate inputs
        _validate_hostname(hostname)
        _validate_username(username)
        _validate_password(user_password)

        # Hash SHA-512 du mot de passe pour Debian 13+
        user_password_crypted = self._sha512_crypt(user_password)

        # Choisir le template selon la version Debian
        template_name = "debian_13.cfg" if "13" in os_type else "debian_12.cfg"

        # Sanitize post-install commands
        sanitized_post_cmds = []
        for cmd in (post_install_commands or []):
            sanitized_post_cmds.append(_sanitize_shell_command(cmd))

        variables = {
            "hostname": hostname,
            "username": username,
            "user_password": user_password,
            "user_password_crypted": user_password_crypted,
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
            "post_install_commands": sanitized_post_cmds,
            **extra_vars,
        }

        return self.render(template_name, variables)

    def render_cloud_init(
        self,
        hostname: str,
        username: str = "otoroot",
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
        # Validate inputs
        _validate_hostname(hostname)
        _validate_username(username)
        if user_password:
            _validate_password(user_password)

        # Générer le hash SHA-512 si non fourni (comme render_ubuntu_autoinstall)
        if not user_password_hash and user_password:
            user_password_hash = self._sha512_crypt(user_password)

        # Sanitize post-install commands
        sanitized_post_cmds = []
        for cmd in (post_install_commands or []):
            sanitized_post_cmds.append(_sanitize_shell_command(cmd))

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
            "post_install_commands": sanitized_post_cmds,
            "extra_files": extra_files or [],
            **extra_vars,
        }

        return self.render("debian_cloud_init.yaml", variables)

    def render_ubuntu_autoinstall(
        self,
        hostname: str,
        username: str = "otoroot",
        user_password: str | None = None,
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
        late_commands: list[str] | None = None,
        **extra_vars: Any,
    ) -> str:
        """
        Génère une configuration autoinstall pour Ubuntu 24.04+.
        Construit le YAML programmatiquement pour éviter les problèmes Jinja2 trim_blocks.
        """
        # Validate inputs
        _validate_hostname(hostname)
        _validate_username(username)
        if user_password:
            _validate_password(user_password)

        # Résoudre le hash du mot de passe
        if not user_password_hash:
            pw = user_password or "tooroto"
            user_password_hash = self._sha512_crypt(pw)

        lines: list[str] = []
        lines.append("#cloud-config")
        lines.append("autoinstall:")
        lines.append("  version: 1")
        lines.append(f"  locale: {locale}")
        lines.append("  keyboard:")
        lines.append(f"    layout: {keyboard_layout}")
        lines.append("")

        # Réseau - utiliser match par driver pour compatibilité Hyper-V
        if static_ip and ip_address:
            lines.append("  network:")
            lines.append("    version: 2")
            lines.append("    ethernets:")
            lines.append("      any:")
            lines.append("        match:")
            lines.append("          name: '*'")
            lines.append("        addresses:")
            lines.append(f"          - {ip_address}/{subnet_prefix}")
            if gateway:
                lines.append(f"        routes:")
                lines.append(f"          - to: default")
                lines.append(f"            via: {gateway}")
            lines.append("        nameservers:")
            lines.append("          addresses:")
            lines.append(f"            - {dns_server_1}")
            if dns_server_2:
                lines.append(f"            - {dns_server_2}")
            lines.append("          search:")
            lines.append(f"            - {domain}")
        lines.append("")

        # Stockage
        lines.append("  storage:")
        lines.append("    layout:")
        lines.append("      name: lvm")
        lines.append("      sizing-policy: all")
        lines.append("")

        # Identité
        lines.append("  identity:")
        lines.append(f"    hostname: {hostname}")
        lines.append(f"    username: {username}")
        lines.append(f"    password: '{user_password_hash}'")
        lines.append("")

        # SSH
        lines.append("  ssh:")
        lines.append("    install-server: true")
        lines.append(f"    allow-pw: {str(ssh_password_auth).lower()}")
        if ssh_authorized_keys:
            lines.append("    authorized-keys:")
            for key in ssh_authorized_keys:
                lines.append(f"      - {key}")
        lines.append("")

        # Paquets
        lines.append("  packages:")
        base_pkgs = [
            "openssh-server", "sudo", "curl", "wget", "vim",
            "htop", "net-tools", "python3", "git",
            "linux-tools-virtual", "linux-cloud-tools-virtual",
        ]
        for pkg in base_pkgs:
            lines.append(f"    - {pkg}")
        for pkg in (extra_packages or []):
            if pkg not in base_pkgs:
                lines.append(f"    - {pkg}")
        lines.append("")

        # Mises à jour
        lines.append("  updates: security")
        lines.append("")

        # user-data (cloud-init)
        lines.append("  user-data:")
        lines.append(f"    timezone: {timezone}")
        lines.append("    package_reboot_if_required: false")
        lines.append("")

        # late-commands
        lines.append("  late-commands:")
        lines.append("    - curtin in-target --target=/target -- systemctl enable ssh")
        lines.append(f"    - curtin in-target --target=/target -- sh -c 'echo \"{username} ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/{username}'")
        lines.append(f"    - curtin in-target --target=/target -- chmod 440 /etc/sudoers.d/{username}")
        lines.append("    - curtin in-target --target=/target -- apt-get install -y linux-tools-virtual linux-cloud-tools-virtual")
        for cmd in (late_commands or []):
            lines.append(f"    - {_sanitize_shell_command(cmd)}")
        for cmd in (post_install_commands or []):
            lines.append(f"    - curtin in-target --target=/target -- {_sanitize_shell_command(cmd)}")

        rendered = "\n".join(lines) + "\n"

        logger.info(
            "ubuntu_autoinstall_rendered",
            hostname=hostname,
            username=username,
        )

        return rendered

    def render_rhel_kickstart(
        self,
        hostname: str,
        username: str = "otoroot",
        user_password: str = "tooroto",
        timezone: str = "Europe/Paris",
        locale: str = "fr_FR.UTF-8",
        keyboard: str = "fr",
        network_config: dict | None = None,
        disk_size_gb: int = 60,
        packages: list[str] | None = None,
        post_commands: list[str] | None = None,
        ssh_keys: list[str] | None = None,
        domain_join: dict | None = None,
        root_password: str | None = None,
    ) -> str:
        """
        Génère dynamiquement un fichier kickstart pour RHEL/Rocky.

        Le contenu est construit programmatiquement sans template Jinja2,
        en se basant sur le format standard des kickstart RHEL 9.

        Args:
            hostname: Nom de la machine
            username: Utilisateur principal (défaut: admin)
            user_password: Mot de passe utilisateur (défaut: changeme)
            timezone: Fuseau horaire (défaut: Europe/Paris)
            locale: Locale système (défaut: fr_FR.UTF-8)
            keyboard: Layout clavier (défaut: fr)
            network_config: Configuration réseau (dict avec ip, netmask, gateway, dns)
            disk_size_gb: Taille du disque en Go (défaut: 60)
            packages: Paquets supplémentaires à installer
            post_commands: Commandes post-installation personnalisées
            ssh_keys: Clés SSH publiques à injecter
            domain_join: Configuration de jonction AD (dict avec domain, user, password, ou)
            root_password: Mot de passe root (défaut: identique à user_password)

        Returns:
            Contenu du fichier kickstart
        """
        # Validate inputs
        _validate_hostname(hostname)
        _validate_username(username)
        _validate_password(user_password)
        if root_password:
            _validate_password(root_password)

        # Mot de passe root : utiliser le paramètre dédié ou le mot de passe utilisateur
        effective_root_password = root_password or user_password

        lines: list[str] = []

        # --- En-tête ---
        lines.append("#version=RHEL9")
        lines.append("# Fichier kickstart généré par VM-Automation")
        lines.append("")

        # --- Méthode d'installation ---
        lines.append("# Méthode d'installation")
        lines.append("cdrom")
        lines.append("")

        # --- Acceptation EULA ---
        lines.append("# Acceptation de la licence")
        lines.append("eula --agreed")
        lines.append("")

        # --- Langue et clavier ---
        lines.append("# Langue du système")
        lines.append(f"lang {locale}")
        lines.append("")
        lines.append("# Configuration clavier")
        lines.append(f"keyboard --xlayouts='{keyboard}'")
        lines.append("")

        # --- Configuration réseau ---
        lines.append("# Configuration réseau")
        if network_config and network_config.get("ip"):
            ip = network_config["ip"]
            netmask = network_config.get("netmask", "255.255.255.0")
            gateway = network_config.get("gateway", "")
            dns = network_config.get("dns", "8.8.8.8")
            net_line = (
                f"network --bootproto=static --device=eth0"
                f" --ip={ip} --netmask={netmask}"
                f" --gateway={gateway} --nameserver={dns}"
                f" --hostname={hostname} --activate"
            )
            lines.append(net_line)
        else:
            lines.append(
                f"network --bootproto=dhcp --device=eth0"
                f" --hostname={hostname} --activate"
            )
        lines.append("")

        # --- Mot de passe root ---
        lines.append("# Mot de passe root")
        lines.append(f"rootpw --plaintext {effective_root_password}")
        lines.append("")

        # --- Fuseau horaire ---
        lines.append("# Fuseau horaire")
        lines.append(f"timezone {timezone} --utc")
        lines.append("")

        # --- Partitionnement ---
        lines.append("# Partitionnement")
        lines.append("ignoredisk --only-use=sda")
        lines.append("clearpart --all --initlabel --drives=sda")
        lines.append("autopart --type=lvm")
        lines.append("")

        # --- Bootloader ---
        lines.append("# Chargeur de démarrage")
        lines.append('bootloader --location=mbr --boot-drive=sda --append="crashkernel=auto"')
        lines.append("")

        # --- Pare-feu et SELinux ---
        lines.append("# Pare-feu désactivé pendant l'installation")
        lines.append("firewall --disabled")
        lines.append("")
        lines.append("# SELinux en mode enforcing")
        lines.append("selinux --enforcing")
        lines.append("")

        # --- Services ---
        lines.append("# Services activés")
        lines.append('services --enabled="sshd,chronyd"')
        lines.append("")

        # --- Première exécution désactivée ---
        lines.append("# Pas d'assistant au premier démarrage")
        lines.append("firstboot --disabled")
        lines.append("")

        # --- Redémarrage ---
        lines.append("# Redémarrage après installation")
        lines.append("reboot --eject")
        lines.append("")

        # --- Section %packages ---
        lines.append("# Sélection des paquets")
        lines.append("%packages")
        # Paquets de base obligatoires
        base_packages = [
            "@^minimal-environment",
            "@standard",
            "openssh-server",
            "openssh-clients",
            "sudo",
            "python3",
            "curl",
            "wget",
            "vim-enhanced",
            "net-tools",
            "bind-utils",
            "chrony",
            "bash-completion",
            "tar",
            "unzip",
        ]
        for pkg in base_packages:
            lines.append(pkg)

        # Paquets supplémentaires
        if packages:
            for pkg in packages:
                if pkg not in base_packages:
                    lines.append(pkg)

        lines.append("%end")
        lines.append("")

        # --- Section %post ---
        lines.append("# Script post-installation")
        lines.append("%post --interpreter=/bin/bash --log=/root/ks-post.log")
        lines.append("")
        lines.append('echo "=== Post-installation kickstart ==="')
        lines.append("")

        # Configuration SSH
        lines.append("# Configuration SSH")
        lines.append(
            "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config"
        )
        lines.append(
            "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config"
        )
        lines.append("systemctl enable sshd")
        lines.append("systemctl restart sshd")
        lines.append("")

        # Pare-feu
        lines.append("# Configuration pare-feu")
        lines.append("systemctl enable firewalld")
        lines.append("systemctl start firewalld")
        lines.append("firewall-cmd --permanent --add-service=ssh")
        lines.append("firewall-cmd --reload")
        lines.append("")

        # Création utilisateur avec sudo (username already validated above)
        lines.append("# Création de l'utilisateur avec accès sudo")
        lines.append(f"useradd -m -G wheel {username}")
        safe_pw = user_password.replace("'", "'\\''")
        lines.append(f"echo '{username}:{safe_pw}' | chpasswd")
        lines.append(
            f'echo "{username} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/{username}'
        )
        lines.append(f"chmod 440 /etc/sudoers.d/{username}")
        lines.append("")

        # Injection des clés SSH
        if ssh_keys:
            lines.append("# Injection des clés SSH")
            # Clés pour root
            lines.append("mkdir -p /root/.ssh")
            lines.append("chmod 700 /root/.ssh")
            lines.append("cat > /root/.ssh/authorized_keys << 'SSHEOF'")
            for key in ssh_keys:
                lines.append(key)
            lines.append("SSHEOF")
            lines.append("chmod 600 /root/.ssh/authorized_keys")
            lines.append("")
            # Clés pour l'utilisateur
            lines.append(f"mkdir -p /home/{username}/.ssh")
            lines.append(f"chmod 700 /home/{username}/.ssh")
            lines.append(f"cat > /home/{username}/.ssh/authorized_keys << 'SSHEOF'")
            for key in ssh_keys:
                lines.append(key)
            lines.append("SSHEOF")
            lines.append(f"chmod 600 /home/{username}/.ssh/authorized_keys")
            lines.append(f"chown -R {username}:{username} /home/{username}/.ssh")
            lines.append("")

        # Jonction au domaine AD via realmd/sssd
        if domain_join:
            domain_name = domain_join.get("domain", "")
            domain_user = domain_join.get("user", "")
            domain_password = domain_join.get("password", "")
            # Validate domain join params
            if domain_user:
                _validate_username(domain_user)
            if domain_password:
                _validate_password(domain_password)
            safe_domain_pw = domain_password.replace("'", "'\\''")
            lines.append("# Jonction au domaine Active Directory via realmd/sssd")
            lines.append(
                "dnf install -y realmd sssd oddjob oddjob-mkhomedir adcli"
                " samba-common-tools krb5-workstation"
            )
            lines.append(
                f"echo '{safe_domain_pw}' | realm join --user={domain_user} {domain_name}"
            )
            lines.append("authselect select sssd with-mkhomedir --force")
            lines.append("systemctl enable sssd")
            lines.append("systemctl start sssd")
            lines.append("")

        # Commandes post-installation personnalisées
        if post_commands:
            lines.append("# Commandes post-installation personnalisées")
            for cmd in post_commands:
                lines.append(_sanitize_shell_command(cmd))
            lines.append("")

        lines.append('echo "=== Post-installation terminée ==="')
        lines.append("")
        lines.append("%end")

        rendered = "\n".join(lines) + "\n"

        logger.info(
            "kickstart_rendered",
            hostname=hostname,
            packages_count=len(packages or []),
            has_ssh_keys=bool(ssh_keys),
            has_domain_join=bool(domain_join),
        )

        return rendered

    def render_rocky_kickstart(self, **kwargs: Any) -> str:
        """Génère un kickstart Rocky Linux (compatible RHEL)."""
        return self.render_rhel_kickstart(**kwargs)

    def render_linux_config(
        self,
        os_type: str,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """
        Génère la configuration d'installation automatique Linux selon le type d'OS.

        Dispatche vers le renderer approprié en fonction du type d'OS détecté.

        Args:
            os_type: Type d'OS (ex: "ubuntu", "debian", "rhel", "rocky", "centos", etc.)
            **kwargs: Paramètres transmis au renderer spécifique

        Returns:
            Tuple (contenu, type_config) où type_config est l'un de :
            "preseed", "kickstart", "autoinstall", "cloud-init"
        """
        os_type_lower = os_type.lower()

        if "ubuntu" in os_type_lower:
            return self.render_ubuntu_autoinstall(**kwargs), "autoinstall"
        elif "debian" in os_type_lower:
            return self.render_debian_preseed(**kwargs), "preseed"
        elif any(x in os_type_lower for x in ("rhel", "red hat")):
            return self.render_rhel_kickstart(**kwargs), "kickstart"
        elif any(x in os_type_lower for x in ("rocky", "centos", "alma")):
            return self.render_rocky_kickstart(**kwargs), "kickstart"
        else:
            return self.render_cloud_init(**kwargs), "cloud-init"

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
