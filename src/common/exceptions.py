# =============================================================================
# VM Automation - Custom Exceptions
# =============================================================================
"""
Exceptions personnalisées pour l'application.
Permet une gestion d'erreurs cohérente et des messages clairs.
"""

from typing import Any


class VMAutomationError(Exception):
    """Exception de base pour toutes les erreurs de l'application."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code or "VMAUTOMATION_ERROR"
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'exception en dictionnaire pour les réponses API."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# Erreurs de Configuration
# =============================================================================


class ConfigurationError(VMAutomationError):
    """Erreur de configuration de l'application."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "CONFIG_ERROR", details)


# =============================================================================
# Erreurs d'Authentification
# =============================================================================


class AuthenticationError(VMAutomationError):
    """Erreur d'authentification."""

    def __init__(self, message: str = "Échec de l'authentification") -> None:
        super().__init__(message, "AUTH_ERROR")


class AuthorizationError(VMAutomationError):
    """Erreur d'autorisation (permissions insuffisantes)."""

    def __init__(self, message: str = "Permission refusée") -> None:
        super().__init__(message, "AUTHZ_ERROR")


class TokenExpiredError(AuthenticationError):
    """Token JWT expiré."""

    def __init__(self) -> None:
        super().__init__("Le token a expiré")
        self.code = "TOKEN_EXPIRED"


class InvalidTokenError(AuthenticationError):
    """Token JWT invalide."""

    def __init__(self) -> None:
        super().__init__("Token invalide")
        self.code = "INVALID_TOKEN"


# =============================================================================
# Erreurs de Base de Données
# =============================================================================


class DatabaseError(VMAutomationError):
    """Erreur liée à la base de données."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "DB_ERROR", details)


class NotFoundError(VMAutomationError):
    """Ressource non trouvée."""

    def __init__(
        self, resource_type: str, resource_id: str | None = None
    ) -> None:
        message = f"{resource_type} non trouvé(e)"
        if resource_id:
            message = f"{resource_type} avec l'id '{resource_id}' non trouvé(e)"
        super().__init__(message, "NOT_FOUND", {"resource_type": resource_type})


class AlreadyExistsError(VMAutomationError):
    """Ressource déjà existante."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        super().__init__(
            f"{resource_type} '{identifier}' existe déjà",
            "ALREADY_EXISTS",
            {"resource_type": resource_type, "identifier": identifier},
        )


# =============================================================================
# Erreurs Hyperviseur
# =============================================================================


class HypervisorError(VMAutomationError):
    """Erreur liée à l'hyperviseur."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "HYPERVISOR_ERROR", details)


class HypervisorConnectionError(HypervisorError):
    """Impossible de se connecter à l'hyperviseur."""

    def __init__(self, host: str, reason: str | None = None) -> None:
        message = f"Impossible de se connecter à l'hyperviseur '{host}'"
        if reason:
            message += f": {reason}"
        super().__init__(message, {"host": host})
        self.code = "HYPERVISOR_CONNECTION_ERROR"


class VMCreationError(HypervisorError):
    """Erreur lors de la création d'une VM."""

    def __init__(self, vm_name: str, reason: str) -> None:
        super().__init__(
            f"Échec de création de la VM '{vm_name}' : {reason}",
            {"vm_name": vm_name, "reason": reason},
        )
        self.code = "VM_CREATION_ERROR"


class VMNotFoundError(HypervisorError):
    """VM non trouvée sur l'hyperviseur."""

    def __init__(self, vm_name: str, hypervisor: str | None = None) -> None:
        details: dict[str, Any] = {"vm_name": vm_name}
        message = f"VM '{vm_name}' non trouvée"
        if hypervisor:
            message += f" sur l'hyperviseur '{hypervisor}'"
            details["hypervisor"] = hypervisor
        super().__init__(message, details)
        self.code = "VM_NOT_FOUND"


class VMOperationError(HypervisorError):
    """Erreur lors d'une opération sur une VM."""

    def __init__(self, vm_name: str, operation: str, reason: str) -> None:
        super().__init__(
            f"Échec de l'opération '{operation}' sur la VM '{vm_name}' : {reason}",
            {"vm_name": vm_name, "operation": operation, "reason": reason},
        )
        self.code = "VM_OPERATION_ERROR"


# =============================================================================
# Erreurs PowerShell
# =============================================================================


class PowerShellError(VMAutomationError):
    """Erreur lors de l'exécution d'une commande PowerShell."""

    def __init__(
        self,
        message: str,
        command: str | None = None,
        exit_code: int | None = None,
        stderr: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if command:
            details["command"] = command[:500]  # Tronquer les longues commandes
        if exit_code is not None:
            details["exit_code"] = exit_code
        if stderr:
            details["stderr"] = stderr[:1000]  # Tronquer les longs messages
        super().__init__(message, "POWERSHELL_ERROR", details)


class PowerShellTimeoutError(PowerShellError):
    """Timeout lors de l'exécution PowerShell."""

    def __init__(self, timeout: int, command: str | None = None) -> None:
        super().__init__(
            f"Commande PowerShell expirée après {timeout} secondes",
            command=command,
        )
        self.code = "POWERSHELL_TIMEOUT"


# =============================================================================
# Erreurs de Déploiement
# =============================================================================


class DeploymentError(VMAutomationError):
    """Erreur liée au déploiement."""

    def __init__(
        self,
        message: str,
        deployment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if deployment_id:
            details["deployment_id"] = deployment_id
        if step:
            details["step"] = step
        super().__init__(message, "DEPLOYMENT_ERROR", details)


class DeploymentStepError(DeploymentError):
    """Erreur lors d'une étape de déploiement."""

    def __init__(self, deployment_id: str, step: str, reason: str) -> None:
        super().__init__(
            f"Étape de déploiement '{step}' échouée : {reason}",
            deployment_id=deployment_id,
            step=step,
        )
        self.code = "DEPLOYMENT_STEP_ERROR"


class DeploymentTimeoutError(DeploymentError):
    """Timeout lors du déploiement."""

    def __init__(self, deployment_id: str, step: str, timeout: int) -> None:
        super().__init__(
            f"Étape de déploiement '{step}' expirée après {timeout} secondes",
            deployment_id=deployment_id,
            step=step,
        )
        self.code = "DEPLOYMENT_TIMEOUT"


# =============================================================================
# Erreurs de Validation
# =============================================================================


class ValidationError(VMAutomationError):
    """Erreur de validation des données."""

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        details: dict[str, Any] = {}
        if fields:
            details["fields"] = fields
        super().__init__(message, "VALIDATION_ERROR", details)


class ResourceBusyError(VMAutomationError):
    """Ressource occupée / verrouillée."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(
            f"{resource_type} '{resource_id}' est actuellement occupé(e)",
            "RESOURCE_BUSY",
            {"resource_type": resource_type, "resource_id": resource_id},
        )
