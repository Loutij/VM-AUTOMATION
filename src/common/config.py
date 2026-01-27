# =============================================================================
# VM Automation - Configuration Settings
# =============================================================================
"""
Configuration centralisée utilisant Pydantic Settings.
Charge les variables d'environnement depuis .env ou l'environnement système.
"""

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
        default=SecretStr("change-me-in-production"),
        description="Clé secrète pour JWT",
    )
    api_algorithm: str = Field(default="HS256", description="Algorithme JWT")
    api_access_token_expire_minutes: int = Field(
        default=30, description="Durée de validité du token en minutes"
    )
    cors_origins: str = Field(
        default="*",
        description="Origines CORS autorisées (comma-separated ou * pour toutes)",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Retourne les origines CORS sous forme de liste."""
        if not self.cors_origins or self.cors_origins.strip() == "*":
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
        default="C:\\HyperV\\VirtualMachines",
        description="Chemin de stockage des VMs",
    )
    hyperv_vhdx_path: str = Field(
        default="C:\\HyperV\\VirtualHardDisks",
        description="Chemin de stockage des disques",
    )
    hyperv_iso_path: str = Field(
        default="C:\\HyperV\\ISOs", description="Chemin des ISOs"
    )
    hyperv_default_switch: str = Field(
        default="Default Switch", description="Switch réseau par défaut"
    )

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
        default=SecretStr("TempP@ss123!"),
        description="Mot de passe admin par défaut pour les VMs",
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


@lru_cache
def get_settings() -> Settings:
    """
    Retourne l'instance singleton des settings.
    Utilise lru_cache pour ne charger qu'une seule fois.
    """
    return Settings()


# Alias pour accès rapide
settings = get_settings()
