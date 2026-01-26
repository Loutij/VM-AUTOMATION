# =============================================================================
# VM Automation - PowerShell Wrapper
# =============================================================================
"""
Wrapper pour l'exécution de commandes PowerShell sur des hôtes distants via WinRM.
Utilisé pour communiquer avec les hôtes Hyper-V.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.common.config import settings
from src.common.exceptions import PowerShellError, PowerShellTimeoutError
from src.common.logging import get_logger

logger = get_logger(__name__)

# Essayer d'importer winrm (optionnel pour le développement sur Linux)
try:
    import winrm
    WINRM_AVAILABLE = True
except ImportError:
    WINRM_AVAILABLE = False
    logger.warning("pywinrm_not_available", message="WinRM not installed, PowerShell execution will be mocked")


@dataclass
class PowerShellResult:
    """Résultat d'une exécution PowerShell."""

    stdout: str
    stderr: str
    exit_code: int
    success: bool

    @property
    def output(self) -> str:
        """Retourne stdout si succès, stderr sinon."""
        return self.stdout if self.success else self.stderr

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "success": self.success,
        }


class PowerShellExecutor:
    """
    Exécuteur de commandes PowerShell via WinRM.
    
    Supporte l'exécution synchrone et asynchrone de scripts PowerShell
    sur des hôtes Windows distants.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        use_ssl: bool = True,
        port: int | None = None,
    ) -> None:
        """
        Initialise l'exécuteur PowerShell.
        
        Args:
            host: Adresse de l'hôte Windows
            username: Nom d'utilisateur (format DOMAIN\\user ou user@domain)
            password: Mot de passe
            use_ssl: Utiliser HTTPS (port 5986) au lieu de HTTP (port 5985)
            port: Port personnalisé (optionnel)
        """
        self.host = host
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.port = port or (5986 if use_ssl else 5985)
        
        self._session: Any = None

    @property
    def endpoint(self) -> str:
        """URL de l'endpoint WinRM."""
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/wsman"

    def _get_session(self) -> Any:
        """Crée ou retourne la session WinRM existante."""
        if not WINRM_AVAILABLE:
            raise PowerShellError(
                "pywinrm is not installed. Install it with: pip install pywinrm"
            )
        
        if self._session is None:
            transport = "ssl" if self.use_ssl else "ntlm"
            self._session = winrm.Session(
                self.endpoint,
                auth=(self.username, self.password),
                transport=transport,
                server_cert_validation="ignore" if self.use_ssl else None,
            )
            logger.debug(
                "winrm_session_created",
                host=self.host,
                port=self.port,
                use_ssl=self.use_ssl,
            )
        
        return self._session

    def execute(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """
        Exécute un script PowerShell de manière synchrone.
        
        Args:
            script: Script PowerShell à exécuter
            timeout: Timeout en secondes (optionnel)
            
        Returns:
            PowerShellResult avec stdout, stderr et code de sortie
            
        Raises:
            PowerShellError: Si l'exécution échoue
            PowerShellTimeoutError: Si le timeout est dépassé
        """
        timeout = timeout or settings.vm_creation_timeout
        
        logger.debug(
            "powershell_executing",
            host=self.host,
            script_length=len(script),
            timeout=timeout,
        )
        
        try:
            session = self._get_session()
            
            # Encoder le script en base64 pour éviter les problèmes d'encodage
            import base64
            encoded_script = base64.b64encode(
                script.encode("utf-16-le")
            ).decode("ascii")
            
            # Exécuter avec -EncodedCommand
            result = session.run_ps(script)
            
            ps_result = PowerShellResult(
                stdout=result.std_out.decode("utf-8", errors="replace").strip(),
                stderr=result.std_err.decode("utf-8", errors="replace").strip(),
                exit_code=result.status_code,
                success=result.status_code == 0,
            )
            
            if ps_result.success:
                logger.debug(
                    "powershell_success",
                    host=self.host,
                    exit_code=ps_result.exit_code,
                )
            else:
                logger.warning(
                    "powershell_error",
                    host=self.host,
                    exit_code=ps_result.exit_code,
                    stderr=ps_result.stderr[:500],
                )
            
            return ps_result
            
        except Exception as e:
            logger.error(
                "powershell_execution_failed",
                host=self.host,
                error=str(e),
                exc_info=True,
            )
            raise PowerShellError(
                f"PowerShell execution failed: {e}",
                command=script[:200],
            ) from e

    async def execute_async(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """
        Exécute un script PowerShell de manière asynchrone.
        
        Utilise un thread pool pour ne pas bloquer l'event loop.
        
        Args:
            script: Script PowerShell à exécuter
            timeout: Timeout en secondes
            
        Returns:
            PowerShellResult
        """
        timeout = timeout or settings.vm_creation_timeout
        
        loop = asyncio.get_event_loop()
        
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self.execute, script, timeout),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise PowerShellTimeoutError(timeout, script[:200])

    def test_connection(self) -> bool:
        """
        Teste la connexion à l'hôte distant.
        
        Returns:
            True si la connexion est OK
        """
        try:
            result = self.execute("Write-Output 'Connection OK'", timeout=30)
            return result.success and "Connection OK" in result.stdout
        except Exception as e:
            logger.warning(
                "powershell_connection_test_failed",
                host=self.host,
                error=str(e),
            )
            return False

    async def test_connection_async(self) -> bool:
        """Teste la connexion de manière asynchrone."""
        try:
            result = await self.execute_async(
                "Write-Output 'Connection OK'",
                timeout=30,
            )
            return result.success and "Connection OK" in result.stdout
        except Exception:
            return False

    def close(self) -> None:
        """Ferme la session WinRM."""
        self._session = None
        logger.debug("winrm_session_closed", host=self.host)


class MockPowerShellExecutor(PowerShellExecutor):
    """
    Mock du PowerShellExecutor pour les tests et le développement.
    
    Simule les réponses PowerShell sans connexion réelle.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Ne pas appeler le parent pour éviter les erreurs
        self.host = kwargs.get("host", "mock-host")
        self.username = kwargs.get("username", "mock-user")
        self.password = kwargs.get("password", "mock-pass")
        self.use_ssl = kwargs.get("use_ssl", True)
        self.port = kwargs.get("port", 5986)
        self._responses: dict[str, PowerShellResult] = {}

    def set_response(self, pattern: str, result: PowerShellResult) -> None:
        """Configure une réponse mock pour un pattern de commande."""
        self._responses[pattern] = result

    def execute(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """Retourne une réponse mock."""
        logger.debug(
            "mock_powershell_executing",
            host=self.host,
            script_length=len(script),
        )
        
        # Chercher une réponse configurée
        for pattern, result in self._responses.items():
            if pattern in script:
                return result
        
        # Réponse par défaut
        return PowerShellResult(
            stdout="Mock execution successful",
            stderr="",
            exit_code=0,
            success=True,
        )

    async def execute_async(
        self,
        script: str,
        timeout: int | None = None,
    ) -> PowerShellResult:
        """Retourne une réponse mock async."""
        return self.execute(script, timeout)

    def test_connection(self) -> bool:
        """Toujours retourne True en mock."""
        return True

    async def test_connection_async(self) -> bool:
        """Toujours retourne True en mock."""
        return True


def create_powershell_executor(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    use_ssl: bool | None = None,
    use_mock: bool = False,
) -> PowerShellExecutor:
    """
    Factory pour créer un exécuteur PowerShell.
    
    Utilise les valeurs de configuration par défaut si non spécifiées.
    
    Args:
        host: Hôte cible (défaut: settings.hyperv_host)
        username: Utilisateur (défaut: settings.hyperv_user)
        password: Mot de passe (défaut: settings.hyperv_password)
        use_ssl: Utiliser SSL (défaut: settings.hyperv_use_ssl)
        use_mock: Utiliser le mock au lieu de WinRM réel
        
    Returns:
        Instance de PowerShellExecutor ou MockPowerShellExecutor
    """
    host = host or settings.hyperv_host
    username = username or settings.hyperv_user
    password = password or settings.hyperv_password.get_secret_value()
    use_ssl = use_ssl if use_ssl is not None else settings.hyperv_use_ssl
    
    if use_mock or not WINRM_AVAILABLE:
        logger.info("using_mock_powershell_executor", host=host)
        return MockPowerShellExecutor(
            host=host,
            username=username,
            password=password,
            use_ssl=use_ssl,
        )
    
    return PowerShellExecutor(
        host=host,
        username=username,
        password=password,
        use_ssl=use_ssl,
    )
