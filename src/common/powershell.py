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


def _decode_powershell_output(raw_bytes: bytes) -> str:
    """
    Décode la sortie PowerShell avec plusieurs encodages possibles.
    
    Windows PowerShell peut utiliser différents encodages selon la configuration :
    - UTF-8 (moderne)
    - UTF-16 (Windows natif, avec ou sans BOM)
    - cp1252 (Windows Western Europe)
    - cp850 (DOS/Console)
    - latin-1 (fallback)
    
    Args:
        raw_bytes: Bytes bruts de la sortie PowerShell
        
    Returns:
        Chaîne décodée correctement
    """
    if not raw_bytes:
        return ""
    
    # Détecter le BOM UTF-16 (FE FF pour BE ou FF FE pour LE)
    if len(raw_bytes) >= 2:
        bom = raw_bytes[:2]
        if bom == b'\xff\xfe':  # UTF-16 LE BOM
            try:
                return raw_bytes[2:].decode('utf-16-le').strip()
            except UnicodeDecodeError:
                pass
        elif bom == b'\xfe\xff':  # UTF-16 BE BOM
            try:
                return raw_bytes[2:].decode('utf-16-be').strip()
            except UnicodeDecodeError:
                pass
    
    # Détecter le BOM UTF-8 (EF BB BF)
    if len(raw_bytes) >= 3 and raw_bytes[:3] == b'\xef\xbb\xbf':
        try:
            return raw_bytes[3:].decode('utf-8').strip()
        except UnicodeDecodeError:
            pass
    
    # Détecter UTF-16 sans BOM (caractères alternés avec null bytes)
    # Si la longueur est paire et qu'on a beaucoup de null bytes, c'est probablement UTF-16
    if len(raw_bytes) >= 4 and len(raw_bytes) % 2 == 0:
        null_count = raw_bytes.count(b'\x00')
        null_ratio = null_count / len(raw_bytes)
        # Si plus de 20% de null bytes, c'est probablement UTF-16
        if null_ratio > 0.2:
            try:
                decoded = raw_bytes.decode('utf-16-le')
                # Vérifier que ça ressemble à du texte valide
                if any(word in decoded.lower() for word in ['error', 'failed', 'success', 'dism', 'windows', 'image', 'applying', 'deployment']):
                    return decoded.strip()
            except UnicodeDecodeError:
                pass
    
    # Liste des encodages à essayer dans l'ordre de priorité
    encodings = ['utf-8', 'utf-16-le', 'utf-16', 'cp1252', 'cp850', 'latin-1']
    
    for encoding in encodings:
        try:
            decoded = raw_bytes.decode(encoding)
            # Vérifier que le décodage n'a pas produit de caractères de remplacement
            # et qu'il ne contient pas trop de caractères non-ASCII suspects (comme des caractères chinois mal décodés)
            if '\ufffd' not in decoded:
                # Vérifier si le texte semble être du texte mal décodé (beaucoup de caractères non-ASCII isolés)
                ascii_ratio = sum(1 for c in decoded if ord(c) < 128) / len(decoded) if decoded else 0
                # Si c'est principalement de l'ASCII ou du texte français/anglais normal, c'est bon
                if ascii_ratio > 0.7 or any(word in decoded.lower() for word in ['error', 'failed', 'success', 'dism', 'windows', 'image', 'applying', 'deployment']):
                    return decoded.strip()
        except (UnicodeDecodeError, LookupError):
            continue
    
    # Fallback final avec remplacement des caractères invalides
    return raw_bytes.decode('utf-8', errors='replace').strip()

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
        verify_ssl: bool = False,
    ) -> None:
        """
        Initialise l'exécuteur PowerShell.

        Args:
            host: Adresse de l'hôte Windows
            username: Nom d'utilisateur (format DOMAIN\\user ou user@domain)
            password: Mot de passe
            use_ssl: Utiliser HTTPS (port 5986) au lieu de HTTP (port 5985)
            port: Port personnalisé (optionnel)
            verify_ssl: Valider le certificat SSL du serveur (défaut: False)
        """
        self.host = host
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.port = port or (5986 if use_ssl else 5985)
        self.verify_ssl = verify_ssl

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
            cert_validation = "validate" if self.verify_ssl else "ignore"
            self._session = winrm.Session(
                self.endpoint,
                auth=(self.username, self.password),
                transport=transport,
                server_cert_validation=cert_validation if self.use_ssl else None,
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
            
            # Exécuter le script via pywinrm (gère l'encodage en interne)
            result = session.run_ps(script)
            
            ps_result = PowerShellResult(
                stdout=_decode_powershell_output(result.std_out),
                stderr=_decode_powershell_output(result.std_err),
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
                loop.run_in_executor(None, self.execute, script, None),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise PowerShellTimeoutError(timeout, script[:200])

    async def execute_with_retry(
        self,
        script: str,
        timeout: int | None = None,
        max_retries: int = 3,
        initial_delay: float = 2.0,
    ) -> PowerShellResult:
        """
        Exécute un script PowerShell avec retry automatique sur erreurs de connexion.

        Ne retry que sur les erreurs de connexion WinRM (pas les erreurs de script).

        Args:
            script: Script PowerShell à exécuter
            timeout: Timeout en secondes
            max_retries: Nombre maximum de tentatives
            initial_delay: Délai initial entre les tentatives (en secondes)

        Returns:
            PowerShellResult
        """
        from src.common.resilience import retry_with_backoff

        # Only retry on connection-level errors, not script failures
        connection_errors = (
            PowerShellError,
            ConnectionError,
            OSError,
            TimeoutError,
        )

        async def _attempt() -> PowerShellResult:
            return await self.execute_async(script, timeout)

        return await retry_with_backoff(
            func=_attempt,
            max_retries=max_retries,
            initial_delay=initial_delay,
            retryable_exceptions=connection_errors,
        )

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
