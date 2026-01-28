import { useState, useEffect } from 'react';
import {
  Bell,
  Monitor,
  Server,
  Globe,
  Save,
  RotateCcw,
  Download,
  Upload,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  User,
  Key,
  Info,
  Shield,
  HardDrive,
  Cpu,
  Database,
  Mail,
  Send,
  Loader2,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Button, Input, Select, Switch, useToast } from '../components/ui';
import { healthApi, apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { AppSettings, HealthCheck } from '../types';
import { DEFAULT_SETTINGS } from '../types';

const SETTINGS_STORAGE_KEY = 'vm_automation_settings';

// Hook personnalisé pour gérer les settings
function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(() => {
    const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (stored) {
      try {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
      } catch {
        return DEFAULT_SETTINGS;
      }
    }
    return DEFAULT_SETTINGS;
  });

  const saveSettings = (newSettings: AppSettings) => {
    setSettings(newSettings);
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(newSettings));
  };

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS);
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(DEFAULT_SETTINGS));
  };

  return { settings, saveSettings, resetSettings };
}

// Section Card Component
function SettingsSection({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ElementType;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-6">
      <div className="flex items-start gap-4 mb-6">
        <div className="w-10 h-10 bg-primary-600/20 rounded-lg flex items-center justify-center flex-shrink-0">
          <Icon size={20} className="text-primary-500" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          {description && <p className="text-sm text-dark-400 mt-1">{description}</p>}
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

export function Settings() {
  const { settings, saveSettings, resetSettings } = useSettings();
  const { user } = useAuth();
  const { addToast } = useToast();
  
  // États locaux pour les formulaires
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [hasChanges, setHasChanges] = useState(false);
  const [healthStatus, setHealthStatus] = useState<HealthCheck | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current: '',
    new: '',
    confirm: '',
  });
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  
  // États pour la configuration email
  const [smtpConfig, setSmtpConfig] = useState<{
    host: string;
    port: number;
    use_ssl: boolean;
    user: string;
    from_addr: string;
    enabled: boolean;
  } | null>(null);
  const [testEmail, setTestEmail] = useState('');
  const [isSendingTestEmail, setIsSendingTestEmail] = useState(false);
  const [isLoadingSMTP, setIsLoadingSMTP] = useState(true);

  // Détecter les changements
  useEffect(() => {
    setHasChanges(JSON.stringify(localSettings) !== JSON.stringify(settings));
  }, [localSettings, settings]);

  // Charger la configuration SMTP
  useEffect(() => {
    const loadSMTPConfig = async () => {
      try {
        const response = await apiClient.get('/settings/smtp');
        setSmtpConfig(response.data);
      } catch (error) {
        console.error('Failed to load SMTP config:', error);
      } finally {
        setIsLoadingSMTP(false);
      }
    };
    loadSMTPConfig();
  }, []);

  // Mettre à jour un paramètre
  const updateSetting = <K extends keyof AppSettings>(
    key: K,
    value: AppSettings[K]
  ) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
  };

  // Mettre à jour un paramètre imbriqué
  const updateNestedSetting = <K extends keyof AppSettings>(
    key: K,
    nestedKey: keyof AppSettings[K],
    value: AppSettings[K][keyof AppSettings[K]]
  ) => {
    setLocalSettings((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] as object),
        [nestedKey]: value,
      },
    }));
  };

  // Sauvegarder les paramètres
  const handleSave = () => {
    saveSettings(localSettings);
    addToast({
      type: 'success',
      title: 'Paramètres enregistrés',
      message: 'Vos préférences ont été sauvegardées.',
    });
    setHasChanges(false);
  };

  // Réinitialiser les paramètres
  const handleReset = () => {
    resetSettings();
    setLocalSettings(DEFAULT_SETTINGS);
    addToast({
      type: 'info',
      title: 'Paramètres réinitialisés',
      message: 'Les paramètres par défaut ont été restaurés.',
    });
  };

  // Vérifier la connexion API
  const checkApiHealth = async () => {
    setIsCheckingHealth(true);
    try {
      const health = await healthApi.check();
      setHealthStatus(health);
      addToast({
        type: health.status === 'healthy' ? 'success' : 'warning',
        title: health.status === 'healthy' ? 'API disponible' : 'API partiellement disponible',
        message: `Base de données: ${health.checks?.database?.status === 'healthy' ? 'OK' : 'Erreur'}, Redis: ${health.checks?.redis?.status === 'healthy' ? 'OK' : 'Erreur'}`,
      });
    } catch {
      setHealthStatus(null);
      addToast({
        type: 'error',
        title: 'API indisponible',
        message: 'Impossible de contacter le serveur.',
      });
    } finally {
      setIsCheckingHealth(false);
    }
  };

  // Exporter la configuration
  const handleExport = () => {
    const exportData = {
      settings: localSettings,
      exportedAt: new Date().toISOString(),
      version: '1.0',
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vm-automation-settings-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addToast({
      type: 'success',
      title: 'Configuration exportée',
    });
  };

  // Importer la configuration
  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        if (data.settings) {
          setLocalSettings({ ...DEFAULT_SETTINGS, ...data.settings });
          addToast({
            type: 'success',
            title: 'Configuration importée',
            message: 'Cliquez sur "Enregistrer" pour appliquer les changements.',
          });
        } else {
          throw new Error('Format invalide');
        }
      } catch {
        addToast({
          type: 'error',
          title: 'Erreur d\'importation',
          message: 'Le fichier de configuration est invalide.',
        });
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  };

  // Changer le mot de passe
  const handleChangePassword = async () => {
    if (passwordForm.new !== passwordForm.confirm) {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: 'Les mots de passe ne correspondent pas.',
      });
      return;
    }

    if (passwordForm.new.length < 8) {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: 'Le mot de passe doit contenir au moins 8 caractères.',
      });
      return;
    }

    setIsChangingPassword(true);
    try {
      await apiClient.post('/auth/change-password', {
        current_password: passwordForm.current,
        new_password: passwordForm.new,
      });
      addToast({
        type: 'success',
        title: 'Mot de passe modifié',
        message: 'Votre mot de passe a été mis à jour avec succès.',
      });
      setPasswordForm({ current: '', new: '', confirm: '' });
    } catch {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: 'Impossible de changer le mot de passe. Vérifiez le mot de passe actuel.',
      });
    } finally {
      setIsChangingPassword(false);
    }
  };

  // Envoyer un email de test
  const handleSendTestEmail = async () => {
    if (!testEmail) {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: 'Veuillez entrer une adresse email.',
      });
      return;
    }

    setIsSendingTestEmail(true);
    try {
      const response = await apiClient.post('/settings/smtp/test', {
        email: testEmail,
      });
      
      if (response.data.success) {
        addToast({
          type: 'success',
          title: 'Email envoyé',
          message: response.data.message,
        });
        setTestEmail('');
      } else {
        addToast({
          type: 'error',
          title: 'Échec de l\'envoi',
          message: response.data.message,
        });
      }
    } catch (error: any) {
      addToast({
        type: 'error',
        title: 'Erreur',
        message: error.response?.data?.detail || 'Impossible d\'envoyer l\'email de test.',
      });
    } finally {
      setIsSendingTestEmail(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Paramètres" />
      
      <div className="p-4 sm:p-6 max-w-4xl mx-auto">
        {/* Barre d'actions sticky */}
        {hasChanges && (
          <div className="sticky top-0 z-10 mb-6 p-4 bg-primary-600/10 border border-primary-500/20 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-primary-400">
              <AlertTriangle size={20} />
              <span>Vous avez des modifications non enregistrées</span>
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setLocalSettings(settings)}
                leftIcon={<RotateCcw size={16} />}
              >
                Annuler
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                leftIcon={<Save size={16} />}
              >
                Enregistrer
              </Button>
            </div>
          </div>
        )}

        <div className="space-y-6">
          {/* Paramètres généraux */}
          <SettingsSection
            icon={Globe}
            title="Paramètres généraux"
            description="Langue et préférences régionales"
          >
            <Select
              label="Langue"
              value={localSettings.language}
              onChange={(e) => updateSetting('language', e.target.value as 'fr' | 'en')}
              options={[
                { value: 'fr', label: 'Français' },
                { value: 'en', label: 'English' },
              ]}
              helperText="La langue de l'interface utilisateur"
            />
            <Select
              label="Thème"
              value={localSettings.theme}
              onChange={(e) => updateSetting('theme', e.target.value as 'dark' | 'light' | 'system')}
              options={[
                { value: 'dark', label: 'Sombre' },
                { value: 'light', label: 'Clair' },
                { value: 'system', label: 'Automatique (système)' },
              ]}
              helperText="Apparence de l'application"
            />
          </SettingsSection>

          {/* Notifications */}
          <SettingsSection
            icon={Bell}
            title="Notifications"
            description="Configurez les alertes et notifications"
          >
            <Switch
              label="Activer les notifications"
              description="Recevoir des notifications pour les événements importants"
              checked={localSettings.notifications.enabled}
              onChange={(checked) => updateNestedSetting('notifications', 'enabled', checked)}
            />
            <div className={`space-y-4 pl-4 border-l-2 border-dark-700 ${!localSettings.notifications.enabled ? 'opacity-50 pointer-events-none' : ''}`}>
              <Switch
                label="Déploiement terminé"
                description="Notification quand un déploiement est complété avec succès"
                checked={localSettings.notifications.deploymentComplete}
                onChange={(checked) => updateNestedSetting('notifications', 'deploymentComplete', checked)}
                disabled={!localSettings.notifications.enabled}
              />
              <Switch
                label="Déploiement échoué"
                description="Notification quand un déploiement échoue"
                checked={localSettings.notifications.deploymentFailed}
                onChange={(checked) => updateNestedSetting('notifications', 'deploymentFailed', checked)}
                disabled={!localSettings.notifications.enabled}
              />
              <Switch
                label="Changement d'état VM"
                description="Notification quand une VM démarre ou s'arrête"
                checked={localSettings.notifications.vmStateChange}
                onChange={(checked) => updateNestedSetting('notifications', 'vmStateChange', checked)}
                disabled={!localSettings.notifications.enabled}
              />
              <Switch
                label="Son de notification"
                description="Jouer un son lors des notifications"
                checked={localSettings.notifications.sound}
                onChange={(checked) => updateNestedSetting('notifications', 'sound', checked)}
                disabled={!localSettings.notifications.enabled}
              />
            </div>
          </SettingsSection>

          {/* Notifications Email */}
          <SettingsSection
            icon={Mail}
            title="Notifications Email"
            description="Configuration SMTP pour les notifications de déploiement"
          >
            {isLoadingSMTP ? (
              <div className="flex items-center gap-2 text-dark-400 py-4">
                <Loader2 size={16} className="animate-spin" />
                Chargement de la configuration...
              </div>
            ) : smtpConfig ? (
              <div className="space-y-4">
                {/* Statut */}
                <div className="flex items-center justify-between p-4 bg-dark-700/50 rounded-lg">
                  <div className="flex items-center gap-3">
                    {smtpConfig.enabled ? (
                      <CheckCircle size={20} className="text-green-500" />
                    ) : (
                      <XCircle size={20} className="text-dark-400" />
                    )}
                    <div>
                      <p className="font-medium text-white">
                        {smtpConfig.enabled ? 'Notifications email activées' : 'Notifications email désactivées'}
                      </p>
                      <p className="text-sm text-dark-400">
                        {smtpConfig.host}:{smtpConfig.port} {smtpConfig.use_ssl ? '(SSL)' : ''}
                      </p>
                    </div>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs ${
                    smtpConfig.enabled 
                      ? 'bg-green-500/20 text-green-400' 
                      : 'bg-dark-600 text-dark-400'
                  }`}>
                    {smtpConfig.enabled ? 'Actif' : 'Inactif'}
                  </span>
                </div>

                {/* Configuration actuelle */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="p-3 bg-dark-700/30 rounded">
                    <span className="text-dark-400 block mb-1">Serveur SMTP</span>
                    <span className="text-white font-mono">{smtpConfig.host}</span>
                  </div>
                  <div className="p-3 bg-dark-700/30 rounded">
                    <span className="text-dark-400 block mb-1">Port</span>
                    <span className="text-white font-mono">{smtpConfig.port}</span>
                  </div>
                  <div className="p-3 bg-dark-700/30 rounded">
                    <span className="text-dark-400 block mb-1">Utilisateur</span>
                    <span className="text-white font-mono">{smtpConfig.user || '-'}</span>
                  </div>
                  <div className="p-3 bg-dark-700/30 rounded">
                    <span className="text-dark-400 block mb-1">Expéditeur</span>
                    <span className="text-white font-mono">{smtpConfig.from_addr || '-'}</span>
                  </div>
                </div>

                {/* Test email */}
                <div className="border-t border-dark-700 pt-4">
                  <h4 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                    <Send size={16} />
                    Envoyer un email de test
                  </h4>
                  <div className="flex gap-2">
                    <Input
                      value={testEmail}
                      onChange={(e) => setTestEmail(e.target.value)}
                      placeholder="votre-email@exemple.com"
                      type="email"
                      className="flex-1"
                    />
                    <Button
                      onClick={handleSendTestEmail}
                      isLoading={isSendingTestEmail}
                      disabled={!testEmail || !smtpConfig.user}
                      leftIcon={<Send size={16} />}
                    >
                      Envoyer
                    </Button>
                  </div>
                  <p className="text-xs text-dark-400 mt-2">
                    Un email de test sera envoyé pour vérifier la configuration SMTP.
                  </p>
                </div>

                {/* Info configuration */}
                <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                  <p className="text-sm text-blue-400">
                    <strong>Note :</strong> La configuration SMTP se fait via les variables d'environnement du serveur 
                    (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_ENABLED). 
                    Contactez votre administrateur pour modifier ces paramètres.
                  </p>
                </div>
              </div>
            ) : (
              <div className="text-center py-4 text-dark-400">
                <Mail size={24} className="mx-auto mb-2 opacity-50" />
                <p>Configuration SMTP non disponible</p>
                <p className="text-sm">Configurez les variables d'environnement SMTP sur le serveur</p>
              </div>
            )}
          </SettingsSection>

          {/* Valeurs par défaut des déploiements */}
          <SettingsSection
            icon={Server}
            title="Valeurs par défaut des déploiements"
            description="Configuration par défaut pour les nouvelles machines virtuelles"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label="CPU (cœurs)"
                type="number"
                min={1}
                max={32}
                value={localSettings.defaultDeployment.cpu_count}
                onChange={(e) => updateNestedSetting('defaultDeployment', 'cpu_count', parseInt(e.target.value) || 2)}
                leftIcon={<Cpu size={18} />}
              />
              <Input
                label="Mémoire (Mo)"
                type="number"
                min={512}
                max={131072}
                step={512}
                value={localSettings.defaultDeployment.ram_gb}
                onChange={(e) => updateNestedSetting('defaultDeployment', 'ram_gb', parseInt(e.target.value) || 4)}
                leftIcon={<Server size={18} />}
                helperText={`${localSettings.defaultDeployment.ram_gb} Go`}
              />
              <Input
                label="Disque (Go)"
                type="number"
                min={20}
                max={2048}
                value={localSettings.defaultDeployment.disk_gb}
                onChange={(e) => updateNestedSetting('defaultDeployment', 'disk_gb', parseInt(e.target.value) || 60)}
                leftIcon={<HardDrive size={18} />}
              />
              <Input
                label="Switch réseau"
                value={localSettings.defaultDeployment.network_switch}
                onChange={(e) => updateNestedSetting('defaultDeployment', 'network_switch', e.target.value)}
                placeholder="Default Switch"
              />
            </div>
          </SettingsSection>

          {/* Affichage */}
          <SettingsSection
            icon={Monitor}
            title="Affichage"
            description="Options d'affichage et de rafraîchissement"
          >
            <Select
              label="Éléments par page"
              value={localSettings.display.itemsPerPage.toString()}
              onChange={(e) => updateNestedSetting('display', 'itemsPerPage', parseInt(e.target.value))}
              options={[
                { value: '10', label: '10 éléments' },
                { value: '25', label: '25 éléments' },
                { value: '50', label: '50 éléments' },
                { value: '100', label: '100 éléments' },
              ]}
            />
            <Switch
              label="Rafraîchissement automatique"
              description="Mettre à jour automatiquement les données"
              checked={localSettings.display.autoRefresh}
              onChange={(checked) => updateNestedSetting('display', 'autoRefresh', checked)}
            />
            {localSettings.display.autoRefresh && (
              <Select
                label="Intervalle de rafraîchissement"
                value={localSettings.display.refreshInterval.toString()}
                onChange={(e) => updateNestedSetting('display', 'refreshInterval', parseInt(e.target.value))}
                options={[
                  { value: '10', label: '10 secondes' },
                  { value: '30', label: '30 secondes' },
                  { value: '60', label: '1 minute' },
                  { value: '300', label: '5 minutes' },
                ]}
              />
            )}
          </SettingsSection>

          {/* Statut de l'API */}
          <SettingsSection
            icon={Database}
            title="Connexion API"
            description="Vérifiez l'état de la connexion au serveur"
          >
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 bg-dark-700/50 rounded-lg">
              <div className="flex items-center gap-3">
                {healthStatus ? (
                  healthStatus.status === 'healthy' ? (
                    <CheckCircle size={24} className="text-green-500" />
                  ) : (
                    <AlertTriangle size={24} className="text-yellow-500" />
                  )
                ) : (
                  <XCircle size={24} className="text-dark-500" />
                )}
                <div>
                  <p className="font-medium text-white">
                    {healthStatus
                      ? healthStatus.status === 'healthy'
                        ? 'API connectée'
                        : 'API partiellement disponible'
                      : 'Statut inconnu'}
                  </p>
                  {healthStatus && (
                    <p className="text-sm text-dark-400">
                      DB: {healthStatus.checks?.database?.status === 'healthy' ? '✓' : '✗'} | 
                      Redis: {healthStatus.checks?.redis?.status === 'healthy' ? '✓' : '✗'} | 
                      Celery: {healthStatus.checks?.celery?.status === 'healthy' ? '✓' : '✗'}
                    </p>
                  )}
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={checkApiHealth}
                isLoading={isCheckingHealth}
                leftIcon={<RefreshCw size={16} />}
              >
                Tester la connexion
              </Button>
            </div>
          </SettingsSection>

          {/* Compte utilisateur */}
          <SettingsSection
            icon={User}
            title="Compte utilisateur"
            description="Gérez votre compte et votre sécurité"
          >
            {user && (
              <div className="p-4 bg-dark-700/50 rounded-lg mb-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-primary-600/20 rounded-full flex items-center justify-center">
                    <User size={24} className="text-primary-500" />
                  </div>
                  <div>
                    <p className="font-medium text-white">{user.full_name || user.username}</p>
                    <p className="text-sm text-dark-400">{user.email}</p>
                    {user.is_superuser && (
                      <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 bg-yellow-500/20 text-yellow-500 text-xs rounded">
                        <Shield size={12} />
                        Administrateur
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
            
            <div className="border-t border-dark-700 pt-4">
              <h4 className="text-sm font-medium text-dark-200 mb-4 flex items-center gap-2">
                <Key size={16} />
                Changer le mot de passe
              </h4>
              <div className="space-y-4">
                <Input
                  label="Mot de passe actuel"
                  type="password"
                  value={passwordForm.current}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })}
                  placeholder="••••••••"
                />
                <Input
                  label="Nouveau mot de passe"
                  type="password"
                  value={passwordForm.new}
                  onChange={(e) => setPasswordForm({ ...passwordForm, new: e.target.value })}
                  placeholder="••••••••"
                  helperText="Minimum 8 caractères"
                />
                <Input
                  label="Confirmer le mot de passe"
                  type="password"
                  value={passwordForm.confirm}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
                  placeholder="••••••••"
                  error={passwordForm.confirm && passwordForm.new !== passwordForm.confirm ? 'Les mots de passe ne correspondent pas' : undefined}
                />
                <Button
                  variant="secondary"
                  onClick={handleChangePassword}
                  isLoading={isChangingPassword}
                  disabled={!passwordForm.current || !passwordForm.new || !passwordForm.confirm}
                  leftIcon={<Key size={16} />}
                >
                  Modifier le mot de passe
                </Button>
              </div>
            </div>
          </SettingsSection>

          {/* Import/Export */}
          <SettingsSection
            icon={HardDrive}
            title="Sauvegarde et restauration"
            description="Exportez ou importez votre configuration"
          >
            <div className="flex flex-col sm:flex-row gap-4">
              <Button
                variant="secondary"
                onClick={handleExport}
                leftIcon={<Download size={18} />}
                className="flex-1"
              >
                Exporter la configuration
              </Button>
              <div className="flex-1 relative">
                <input
                  type="file"
                  accept=".json"
                  onChange={handleImport}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                />
                <Button
                  variant="secondary"
                  leftIcon={<Upload size={18} />}
                  className="w-full pointer-events-none"
                >
                  Importer une configuration
                </Button>
              </div>
            </div>
            <p className="text-sm text-dark-400">
              La configuration exportée inclut vos préférences locales (thème, notifications, valeurs par défaut).
              Elle n'inclut pas les données sensibles comme les mots de passe.
            </p>
          </SettingsSection>

          {/* À propos */}
          <SettingsSection
            icon={Info}
            title="À propos"
            description="Informations sur l'application"
          >
            <div className="space-y-3">
              <div className="flex justify-between items-center py-2 border-b border-dark-700">
                <span className="text-dark-400">Version</span>
                <span className="text-white font-mono">1.0.0</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-dark-700">
                <span className="text-dark-400">Environnement</span>
                <span className="text-white font-mono">{import.meta.env.MODE}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-dark-700">
                <span className="text-dark-400">API URL</span>
                <span className="text-white font-mono text-sm">{import.meta.env.VITE_API_URL || '/api/v1'}</span>
              </div>
            </div>
          </SettingsSection>

          {/* Actions de réinitialisation */}
          <div className="card p-6 border-red-500/20 bg-red-500/5">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 bg-red-500/20 rounded-lg flex items-center justify-center flex-shrink-0">
                <AlertTriangle size={20} className="text-red-500" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white">Zone de danger</h3>
                <p className="text-sm text-dark-400 mt-1 mb-4">
                  Ces actions sont irréversibles. Procédez avec précaution.
                </p>
                <Button
                  variant="danger"
                  onClick={handleReset}
                  leftIcon={<RotateCcw size={18} />}
                >
                  Réinitialiser tous les paramètres
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
