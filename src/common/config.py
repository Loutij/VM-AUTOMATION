# =============================================================================
# VM Automation - Configuration Settings
# =============================================================================
"""
Configuration centralisée utilisant Pydantic Settings.
Charge les variables d'environnement depuis .env ou l'environnement système.
"""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration principale de l'application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = Field(default="vm-automation", description="Nom de l'application")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Environnement d'exécution"
    )
    debug: bool = Field(default=False, description="Mode debug")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Niveau de logging"
    )

    # -------------------------------------------------------------------------
    # API Configuration
    # -------------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", description="Hôte de l'API")
    api_port: int = Field(default=8000, description="Port de l'API")
    api_secret_key: SecretStr = Field(
        description="Clé secrète pour JWT (obligatoire, définir API_SECRET_KEY)",
    )
    api_algorithm: str = Field(default="HS256", description="Algorithme JWT")
    api_access_token_expire_minutes: int = Field(
        default=30, description="Durée de validité du token en minutes"
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:4200",
        description="Comma-separated list of allowed CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Retourne les origines CORS sous forme de liste."""
        if not self.cors_origins or not self.cors_origins.strip():
            return ["http://localhost:3000", "http://localhost:5173"]
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # -------------------------------------------------------------------------
    # Database - PostgreSQL
    # -------------------------------------------------------------------------
    db_host: str = Field(default="localhost", description="Hôte PostgreSQL")
    db_port: int = Field(default=5432, description="Port PostgreSQL")
    db_name: str = Field(default="vmautomation", description="Nom de la base")
    db_user: str = Field(default="vmautomation", description="Utilisateur DB")
    db_password: SecretStr = Field(
        default=SecretStr(""), description="Mot de passe DB"
    )

    @property
    def database_url(self) -> str:
        """URL de connexion PostgreSQL pour SQLAlchemy (async)."""
        password = self.db_password.get_secret_value()
        return f"postgresql+asyncpg://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_sync(self) -> str:
        """URL de connexion PostgreSQL pour SQLAlchemy (sync - migrations)."""
        password = self.db_password.get_secret_value()
        return f"postgresql+psycopg2://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_host: str = Field(default="localhost", description="Hôte Redis")
    redis_port: int = Field(default=6379, description="Port Redis")
    redis_password: SecretStr = Field(default=SecretStr(""), description="Mot de passe Redis")
    redis_db: int = Field(default=0, description="Numéro de DB Redis")

    @property
    def redis_url(self) -> str:
        """URL de connexion Redis."""
        password = self.redis_password.get_secret_value()
        if password:
            return f"redis://:{password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    celery_broker_url: str = Field(
        default="redis://localhost:6379/0", description="URL du broker Celery"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1", description="Backend de résultats Celery"
    )

    # -------------------------------------------------------------------------
    # Hyper-V Configuration
    # -------------------------------------------------------------------------
    hyperv_host: str = Field(
        default="localhost", description="Hôte Hyper-V"
    )
    hyperv_user: str = Field(default="", description="Utilisateur Hyper-V")
    hyperv_password: SecretStr = Field(
        default=SecretStr(""), description="Mot de passe Hyper-V"
    )
    hyperv_use_ssl: bool = Field(default=True, description="Utiliser SSL pour WinRM")
    hyperv_vm_path: str = Field(
        default="D:\\HyperV\\VirtualMachines",
        description="Chemin de stockage des VMs",
    )
    hyperv_vhdx_path: str = Field(
        default="D:\\HyperV\\VirtualHardDisks",
        description="Chemin de stockage des disques",
    )
    hyperv_iso_path: str = Field(
        default="D:\\HyperV\\ISOs", description="Chemin des ISOs"
    )
    hyperv_temp_path: str = Field(
        default="D:\\HyperV\\Temp",
        description="Chemin temporaire pour remaster ISO, seed ISO, etc.",
    )
    hyperv_unattend_path: str = Field(
        default="D:\\HyperV\\Unattend",
        description="Chemin des fichiers unattend.xml",
    )
    hyperv_default_switch: str = Field(
        default="Default Switch", description="Switch réseau par défaut"
    )
    oscdimg_path: str = Field(
        default=r"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\oscdimg.exe",
        description="Path to oscdimg.exe on Hyper-V host",
    )

    # -------------------------------------------------------------------------
    # VMware ESXi / vSphere
    # -------------------------------------------------------------------------
    esxi_host: str = Field(default="", description="Adresse de l'hôte ESXi/vCenter")
    esxi_port: int = Field(default=443, description="Port de connexion vSphere API")
    esxi_user: str = Field(default="root", description="Utilisateur ESXi")
    esxi_password: SecretStr = Field(default=SecretStr(""), description="Mot de passe ESXi")
    esxi_use_ssl: bool = Field(default=True, description="Utiliser SSL")
    esxi_verify_ssl: bool = Field(default=False, description="Vérifier le certificat SSL (False pour self-signed)")
    esxi_datacenter: str = Field(default="", description="Nom du datacenter vSphere")
    esxi_cluster: str = Field(default="", description="Nom du cluster vSphere")
    esxi_default_datastore: str = Field(default="datastore1", description="Datastore par défaut")
    esxi_default_resource_pool: str = Field(default="", description="Resource pool par défaut")
    esxi_vm_folder: str = Field(default="", description="Dossier VM par défaut")
    esxi_iso_datastore: str = Field(default="", description="Datastore contenant les ISOs")
    esxi_iso_path: str = Field(default="ISOs", description="Chemin des ISOs dans le datastore")

    # -------------------------------------------------------------------------
    # Active Directory (Optionnel)
    # -------------------------------------------------------------------------
    ad_enabled: bool = Field(default=False, description="Activer l'intégration AD")
    ad_domain: str = Field(default="", description="Domaine AD")
    ad_user: str = Field(default="", description="Utilisateur AD")
    ad_password: SecretStr = Field(default=SecretStr(""), description="Mot de passe AD")
    ad_default_ou: str = Field(default="", description="OU par défaut pour les VMs")
    ad_dns_server: str = Field(default="", description="Serveur DNS AD")

    # -------------------------------------------------------------------------
    # Installation OS
    # -------------------------------------------------------------------------
    default_admin_password: SecretStr = Field(
        default=SecretStr("tooroto"),
        description="Mot de passe admin par défaut pour les VMs",
    )

    # -------------------------------------------------------------------------
    # Encryption
    # -------------------------------------------------------------------------
    encryption_key: str = Field(
        default="",
        description="Clé Fernet pour le chiffrement des mots de passe hyperviseurs (générée automatiquement si absente)",
    )
    default_timezone: str = Field(default="Europe/Paris", description="Timezone par défaut")
    default_locale: str = Field(default="fr-FR", description="Locale par défaut")

    # -------------------------------------------------------------------------
    # Performance
    # -------------------------------------------------------------------------
    max_concurrent_deployments: int = Field(
        default=5, description="Nombre max de déploiements simultanés"
    )
    vm_creation_timeout: int = Field(
        default=300, description="Timeout création VM (secondes)"
    )
    os_install_timeout: int = Field(
        default=3600, description="Timeout installation OS (secondes)"
    )
    post_install_timeout: int = Field(
        default=1800, description="Timeout post-installation (secondes)"
    )

    # -------------------------------------------------------------------------
    # VNC Configuration
    # -------------------------------------------------------------------------
    vnc_default_port: int = Field(default=5900, description="Default VNC port")
    vnc_max_sessions: int = Field(default=10, description="Max concurrent VNC sessions")
    vnc_session_timeout: int = Field(default=3600, description="VNC session timeout in seconds (1h)")
    vnc_proxy_enabled: bool = Field(default=True, description="Enable VNC WebSocket proxy")

    # -------------------------------------------------------------------------
    # Email SMTP (Notifications)
    # -------------------------------------------------------------------------
    smtp_host: str = Field(default="smtp.office365.com", description="Serveur SMTP")
    smtp_port: int = Field(default=587, description="Port SMTP")
    smtp_ssl: bool = Field(default=False, description="Utiliser SSL (false = STARTTLS)")
    smtp_user: str = Field(default="", description="Utilisateur SMTP")
    smtp_password: SecretStr = Field(default=SecretStr(""), description="Mot de passe SMTP")
    smtp_from: str = Field(default="", description="Adresse d'expédition")
    smtp_enabled: bool = Field(default=False, description="Activer les notifications email")
    notification_email: str = Field(
        default="",
        description="Adresse email de notification par défaut (fallback sans compte utilisateur)",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Retourne l'instance singleton des settings.
    Utilise lru_cache pour ne charger qu'une seule fois.
    """
    _settings = Settings()

    # Générer automatiquement la clé de chiffrement si absente
    if not _settings.encryption_key:
        if _settings.app_env == "production":
            raise ValueError(
                "ENCRYPTION_KEY must be set in production! "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        from cryptography.fernet import Fernet

        _settings.encryption_key = Fernet.generate_key().decode()
        logging.getLogger(__name__).warning(
            "encryption_key_not_set: Generated temporary key. "
            "Set ENCRYPTION_KEY in .env to persist."
        )

    # Avertir si API_SECRET_KEY utilise une valeur par défaut faible
    _secret = _settings.api_secret_key.get_secret_value()
    if _secret in ("dev-secret-key-change-in-production", "changeme", "secret"):
        logging.getLogger(__name__).warning(
            "API_SECRET_KEY uses a weak/default value ('%s'). "
            "Set a strong, random secret in .env for production!",
            _secret[:8] + "...",
        )

    # Avertir si le mot de passe admin par défaut n'a pas été changé
    if _settings.default_admin_password.get_secret_value() == "tooroto":
        logging.getLogger(__name__).warning(
            "default_admin_password utilise la valeur par défaut 'tooroto'. "
            "Définissez DEFAULT_ADMIN_PASSWORD dans .env pour la production."
        )

    return _settings


# Alias pour accès rapide
settings = get_settings()
