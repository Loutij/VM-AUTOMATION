import { useState } from 'react';
import {
  HelpCircle,
  Book,
  Rocket,
  Server,
  Monitor,
  FileCode,
  Zap,
  MessageCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Search,
  Terminal,
  AlertTriangle,
  CheckCircle,
  Keyboard,
  Clock,
  Shield,
  Settings,
  RefreshCw,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Input } from '../components/ui';

// Types
interface DocSection {
  id: string;
  title: string;
  icon: React.ElementType;
  content: React.ReactNode;
}

interface FAQItem {
  question: string;
  answer: React.ReactNode;
}

interface ShortcutItem {
  keys: string[];
  description: string;
}

// Composant FAQ accordéon
function FAQAccordion({ items }: { items: FAQItem[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div
          key={index}
          className="border border-dark-600 rounded-lg overflow-hidden"
        >
          <button
            onClick={() => setOpenIndex(openIndex === index ? null : index)}
            className="w-full flex items-center justify-between p-4 text-left hover:bg-dark-700/50 transition-colors"
          >
            <span className="font-medium text-white">{item.question}</span>
            {openIndex === index ? (
              <ChevronDown size={20} className="text-dark-400 flex-shrink-0" />
            ) : (
              <ChevronRight size={20} className="text-dark-400 flex-shrink-0" />
            )}
          </button>
          {openIndex === index && (
            <div className="px-4 pb-4 text-dark-300 border-t border-dark-600">
              <div className="pt-4">{item.answer}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Données FAQ
const faqItems: FAQItem[] = [
  {
    question: "Comment créer ma première machine virtuelle ?",
    answer: (
      <div className="space-y-2">
        <p>Pour créer une VM, suivez ces étapes :</p>
        <ol className="list-decimal list-inside space-y-1 ml-2">
          <li>Configurez d'abord un <strong>hyperviseur</strong> dans la section Hyperviseurs</li>
          <li>Créez ou importez un <strong>template OS</strong> dans la section Templates</li>
          <li>Allez dans <strong>Déploiements</strong> et cliquez sur "Nouveau déploiement"</li>
          <li>Suivez l'assistant en 5 étapes pour configurer votre VM</li>
        </ol>
      </div>
    ),
  },
  {
    question: "Comment configurer la connexion Hyper-V ?",
    answer: (
      <div className="space-y-2">
        <p>L'application se connecte via WinRM (PowerShell Remote). Assurez-vous que :</p>
        <ul className="list-disc list-inside space-y-1 ml-2">
          <li>WinRM est activé sur l'hôte Hyper-V (<code className="bg-dark-700 px-1 rounded">Enable-PSRemoting -Force</code>)</li>
          <li>Le certificat SSL est configuré pour HTTPS (port 5986)</li>
          <li>L'utilisateur a les droits d'administration Hyper-V</li>
          <li>Le pare-feu autorise les connexions WinRM</li>
        </ul>
      </div>
    ),
  },
  {
    question: "Pourquoi mon déploiement échoue à l'installation OS ?",
    answer: (
      <div className="space-y-2">
        <p>Vérifiez les points suivants :</p>
        <ul className="list-disc list-inside space-y-1 ml-2">
          <li>Le chemin vers l'ISO est correct et accessible depuis l'hyperviseur</li>
          <li>Le template unattend.xml est valide (pas d'erreur de syntaxe)</li>
          <li>Les Integration Services Hyper-V sont installés</li>
          <li>La VM a suffisamment de ressources (RAM, CPU, disque)</li>
          <li>Consultez les logs détaillés dans la page Déploiements</li>
        </ul>
      </div>
    ),
  },
  {
    question: "Comment joindre une VM au domaine Active Directory ?",
    answer: (
      <div className="space-y-2">
        <p>Lors de la création du déploiement, dans l'étape "Options" :</p>
        <ol className="list-decimal list-inside space-y-1 ml-2">
          <li>Activez l'option "Joindre un domaine Active Directory"</li>
          <li>Entrez le nom du domaine (ex: mondomaine.local)</li>
          <li>Fournissez les identifiants d'un compte autorisé</li>
          <li>Optionnellement, spécifiez l'OU cible</li>
        </ol>
        <p className="text-sm text-dark-400 mt-2">
          Note : Assurez-vous que la VM peut résoudre le DNS du domaine.
        </p>
      </div>
    ),
  },
  {
    question: "Comment installer des logiciels automatiquement ?",
    answer: (
      <div className="space-y-2">
        <p>L'application utilise Chocolatey pour Windows. Lors du déploiement :</p>
        <ol className="list-decimal list-inside space-y-1 ml-2">
          <li>Sélectionnez un profil logiciel (Minimal, Outils, Développement, etc.)</li>
          <li>Ou laissez vide pour une installation sans logiciels supplémentaires</li>
        </ol>
        <p className="mt-2">Profils disponibles :</p>
        <ul className="list-disc list-inside space-y-1 ml-2 text-sm">
          <li><strong>Minimal</strong> : 7-Zip, Notepad++</li>
          <li><strong>Outils système</strong> : + Sysinternals</li>
          <li><strong>Développement</strong> : Git, VS Code, Node.js, Python</li>
          <li><strong>Serveur Web</strong> : IIS, URL Rewrite</li>
          <li><strong>Base de données</strong> : SQL Server Express, SSMS</li>
          <li><strong>Monitoring</strong> : Zabbix Agent</li>
        </ul>
      </div>
    ),
  },
  {
    question: "Où sont stockés les fichiers VHD/VHDX ?",
    answer: (
      <p>
        Par défaut, les disques virtuels sont créés dans le dossier configuré sur l'hyperviseur
        (généralement <code className="bg-dark-700 px-1 rounded">C:\HyperV\VirtualHardDisks</code>).
        Le chemin peut être personnalisé dans les paramètres de l'hyperviseur ou lors du déploiement.
      </p>
    ),
  },
  {
    question: "Comment voir les logs d'un déploiement ?",
    answer: (
      <p>
        Dans la page <strong>Déploiements</strong>, cliquez sur le bouton "Voir logs" (icône document) 
        dans la colonne Actions du déploiement concerné. Une fenêtre affichera l'historique 
        détaillé de chaque étape avec horodatage.
      </p>
    ),
  },
  {
    question: "Puis-je annuler un déploiement en cours ?",
    answer: (
      <p>
        Oui, dans la page Déploiements, cliquez sur le bouton "Annuler" pour les déploiements 
        en statut "En cours". L'annulation tente de nettoyer les ressources créées mais 
        une vérification manuelle peut être nécessaire.
      </p>
    ),
  },
];

// Raccourcis clavier
const shortcuts: ShortcutItem[] = [
  { keys: ['Ctrl', 'K'], description: 'Ouvrir la recherche globale' },
  { keys: ['Ctrl', 'N'], description: 'Nouveau déploiement' },
  { keys: ['Ctrl', ','], description: 'Ouvrir les paramètres' },
  { keys: ['Esc'], description: 'Fermer les modales/dropdowns' },
  { keys: ['?'], description: 'Afficher cette aide' },
];

// Contenu des sections de documentation
const docSections: DocSection[] = [
  {
    id: 'getting-started',
    title: 'Démarrage rapide',
    icon: Rocket,
    content: (
      <div className="space-y-6">
        <p className="text-dark-300">
          VM Automation permet de déployer des machines virtuelles Windows et Linux 
          de manière 100% automatique sur Hyper-V. Voici comment démarrer :
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <div className="w-10 h-10 bg-blue-500/20 rounded-lg flex items-center justify-center mb-3">
              <span className="text-blue-400 font-bold">1</span>
            </div>
            <h4 className="font-medium text-white mb-2">Configurer l'hyperviseur</h4>
            <p className="text-sm text-dark-400">
              Ajoutez votre serveur Hyper-V avec les identifiants WinRM.
            </p>
          </div>
          
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <div className="w-10 h-10 bg-green-500/20 rounded-lg flex items-center justify-center mb-3">
              <span className="text-green-400 font-bold">2</span>
            </div>
            <h4 className="font-medium text-white mb-2">Créer un template</h4>
            <p className="text-sm text-dark-400">
              Définissez un template OS avec le chemin vers l'ISO d'installation.
            </p>
          </div>
          
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center mb-3">
              <span className="text-purple-400 font-bold">3</span>
            </div>
            <h4 className="font-medium text-white mb-2">Lancer un déploiement</h4>
            <p className="text-sm text-dark-400">
              Créez une VM avec l'assistant de déploiement en 5 étapes.
            </p>
          </div>
        </div>
        
        <div className="p-4 bg-primary-600/10 border border-primary-500/20 rounded-lg">
          <div className="flex items-start gap-3">
            <CheckCircle size={20} className="text-primary-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-white">Prérequis</h4>
              <ul className="mt-2 text-sm text-dark-300 space-y-1">
                <li>• Serveur Hyper-V avec WinRM activé (HTTPS port 5986)</li>
                <li>• ISOs d'installation Windows/Linux accessibles</li>
                <li>• Compte avec droits administrateur Hyper-V</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'hypervisors',
    title: 'Gestion des hyperviseurs',
    icon: Server,
    content: (
      <div className="space-y-4">
        <p className="text-dark-300">
          Les hyperviseurs sont les serveurs physiques ou virtuels qui hébergeront vos VMs.
          Actuellement, seul Hyper-V est supporté (VMware vSphere prévu).
        </p>
        
        <h4 className="font-medium text-white mt-6">Ajouter un hyperviseur</h4>
        <ol className="list-decimal list-inside space-y-2 text-dark-300 ml-2">
          <li>Allez dans <strong>Hyperviseurs</strong> et cliquez sur "Ajouter"</li>
          <li>Entrez un nom descriptif (ex: "Hyper-V Production")</li>
          <li>Renseignez l'adresse IP ou le hostname du serveur</li>
          <li>Fournissez les identifiants d'un compte administrateur</li>
          <li>Cliquez sur "Tester la connexion" pour vérifier</li>
        </ol>
        
        <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg mt-4">
          <div className="flex items-start gap-3">
            <AlertTriangle size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-white">Configuration WinRM requise</h4>
              <p className="mt-1 text-sm text-dark-300">
                Sur le serveur Hyper-V, exécutez ces commandes PowerShell en administrateur :
              </p>
              <pre className="mt-2 p-3 bg-dark-800 rounded text-xs text-green-400 overflow-x-auto">
{`Enable-PSRemoting -Force
Set-Item WSMan:\\localhost\\Service\\AllowUnencrypted $false
winrm quickconfig -transport:https`}
              </pre>
            </div>
          </div>
        </div>
        
        <h4 className="font-medium text-white mt-6">Actions disponibles</h4>
        <ul className="space-y-2 text-dark-300">
          <li className="flex items-center gap-2">
            <RefreshCw size={16} className="text-blue-400" />
            <span><strong>Synchroniser</strong> - Rafraîchit la liste des VMs depuis l'hyperviseur</span>
          </li>
          <li className="flex items-center gap-2">
            <Settings size={16} className="text-gray-400" />
            <span><strong>Modifier</strong> - Change les paramètres de connexion</span>
          </li>
          <li className="flex items-center gap-2">
            <Shield size={16} className="text-green-400" />
            <span><strong>Tester</strong> - Vérifie que la connexion fonctionne</span>
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: 'vms',
    title: 'Machines virtuelles',
    icon: Monitor,
    content: (
      <div className="space-y-4">
        <p className="text-dark-300">
          La page VMs affiche toutes les machines virtuelles créées par l'application,
          avec leur statut en temps réel et les actions disponibles.
        </p>
        
        <h4 className="font-medium text-white mt-6">États possibles</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 bg-dark-700/50 rounded-lg text-center">
            <span className="inline-block w-3 h-3 bg-green-500 rounded-full mb-2"></span>
            <p className="text-sm text-white">Running</p>
            <p className="text-xs text-dark-400">VM démarrée</p>
          </div>
          <div className="p-3 bg-dark-700/50 rounded-lg text-center">
            <span className="inline-block w-3 h-3 bg-red-500 rounded-full mb-2"></span>
            <p className="text-sm text-white">Off</p>
            <p className="text-xs text-dark-400">VM arrêtée</p>
          </div>
          <div className="p-3 bg-dark-700/50 rounded-lg text-center">
            <span className="inline-block w-3 h-3 bg-yellow-500 rounded-full mb-2"></span>
            <p className="text-sm text-white">Paused</p>
            <p className="text-xs text-dark-400">VM en pause</p>
          </div>
          <div className="p-3 bg-dark-700/50 rounded-lg text-center">
            <span className="inline-block w-3 h-3 bg-blue-500 rounded-full mb-2"></span>
            <p className="text-sm text-white">Saved</p>
            <p className="text-xs text-dark-400">État sauvegardé</p>
          </div>
        </div>
        
        <h4 className="font-medium text-white mt-6">Actions sur les VMs</h4>
        <ul className="space-y-2 text-dark-300">
          <li><strong>Démarrer</strong> - Allume une VM arrêtée</li>
          <li><strong>Arrêter</strong> - Éteint proprement la VM (shutdown)</li>
          <li><strong>Redémarrer</strong> - Redémarre la VM</li>
          <li><strong>Forcer l'arrêt</strong> - Coupe l'alimentation (équivalent power off)</li>
          <li><strong>Supprimer</strong> - Supprime la VM et ses fichiers associés</li>
        </ul>
      </div>
    ),
  },
  {
    id: 'templates',
    title: 'Templates OS',
    icon: FileCode,
    content: (
      <div className="space-y-4">
        <p className="text-dark-300">
          Les templates définissent la configuration de base pour installer un système d'exploitation.
          Ils incluent le chemin vers l'ISO et les paramètres d'installation automatique.
        </p>
        
        <h4 className="font-medium text-white mt-6">Systèmes supportés</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <h5 className="font-medium text-blue-400 mb-2">Windows</h5>
            <ul className="text-sm text-dark-300 space-y-1">
              <li>• Windows Server 2019/2022</li>
              <li>• Windows 10/11 (bientôt)</li>
              <li>• Installation via autounattend.xml</li>
            </ul>
          </div>
          <div className="p-4 bg-orange-500/10 border border-orange-500/20 rounded-lg">
            <h5 className="font-medium text-orange-400 mb-2">Linux</h5>
            <ul className="text-sm text-dark-300 space-y-1">
              <li>• Ubuntu 22.04/24.04 (autoinstall)</li>
              <li>• Debian 12 (preseed)</li>
              <li>• RHEL/Rocky Linux 9 (kickstart - bientôt)</li>
            </ul>
          </div>
        </div>
        
        <h4 className="font-medium text-white mt-6">Créer un template</h4>
        <ol className="list-decimal list-inside space-y-2 text-dark-300 ml-2">
          <li>Cliquez sur "Nouveau template"</li>
          <li>Choisissez la famille OS (Windows/Linux)</li>
          <li>Entrez le chemin complet vers l'ISO sur l'hyperviseur</li>
          <li>Définissez les ressources minimales (CPU, RAM, disque)</li>
          <li>Le template d'installation (unattend/preseed) sera généré automatiquement</li>
        </ol>
      </div>
    ),
  },
  {
    id: 'deployments',
    title: 'Déploiements',
    icon: Zap,
    content: (
      <div className="space-y-4">
        <p className="text-dark-300">
          Un déploiement est le processus complet de création d'une VM : création de la machine,
          installation de l'OS, configuration post-installation et installation des logiciels.
        </p>
        
        <h4 className="font-medium text-white mt-6">Étapes du déploiement</h4>
        <div className="space-y-3">
          {[
            { step: 1, name: 'Création VM', desc: 'Création de la VM vide avec disque et réseau' },
            { step: 2, name: 'Installation OS', desc: 'Démarrage et installation automatique du système' },
            { step: 3, name: 'Post-installation', desc: 'Configuration réseau, jointure domaine, services' },
            { step: 4, name: 'Logiciels', desc: 'Installation des packages sélectionnés via Chocolatey' },
          ].map((item) => (
            <div key={item.step} className="flex items-start gap-3 p-3 bg-dark-700/50 rounded-lg">
              <div className="w-8 h-8 bg-primary-600/20 rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-primary-500 font-bold text-sm">{item.step}</span>
              </div>
              <div>
                <p className="font-medium text-white">{item.name}</p>
                <p className="text-sm text-dark-400">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
        
        <h4 className="font-medium text-white mt-6">Statuts de déploiement</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-2 bg-blue-500/10 rounded text-center">
            <Clock size={16} className="mx-auto mb-1 text-blue-400" />
            <p className="text-xs text-blue-400">En attente</p>
          </div>
          <div className="p-2 bg-yellow-500/10 rounded text-center">
            <RefreshCw size={16} className="mx-auto mb-1 text-yellow-400" />
            <p className="text-xs text-yellow-400">En cours</p>
          </div>
          <div className="p-2 bg-green-500/10 rounded text-center">
            <CheckCircle size={16} className="mx-auto mb-1 text-green-400" />
            <p className="text-xs text-green-400">Terminé</p>
          </div>
          <div className="p-2 bg-red-500/10 rounded text-center">
            <AlertTriangle size={16} className="mx-auto mb-1 text-red-400" />
            <p className="text-xs text-red-400">Échoué</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'troubleshooting',
    title: 'Dépannage',
    icon: Terminal,
    content: (
      <div className="space-y-6">
        <p className="text-dark-300">
          Solutions aux problèmes courants rencontrés lors de l'utilisation de VM Automation.
        </p>
        
        <div className="space-y-4">
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <h4 className="font-medium text-white flex items-center gap-2">
              <AlertTriangle size={16} className="text-red-400" />
              Erreur de connexion WinRM
            </h4>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Symptôme :</strong> "Unable to connect to WinRM" ou timeout
            </p>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Solutions :</strong>
            </p>
            <ul className="list-disc list-inside text-sm text-dark-400 ml-2 space-y-1">
              <li>Vérifiez que le port 5986 est ouvert dans le pare-feu</li>
              <li>Assurez-vous que le service WinRM est démarré</li>
              <li>Vérifiez le certificat SSL (<code className="bg-dark-800 px-1 rounded">winrm enumerate winrm/config/listener</code>)</li>
              <li>Testez avec : <code className="bg-dark-800 px-1 rounded">Test-WSMan -ComputerName [IP] -UseSSL</code></li>
            </ul>
          </div>
          
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <h4 className="font-medium text-white flex items-center gap-2">
              <AlertTriangle size={16} className="text-yellow-400" />
              Installation OS bloquée
            </h4>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Symptôme :</strong> Le déploiement reste bloqué à "Installation OS"
            </p>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Solutions :</strong>
            </p>
            <ul className="list-disc list-inside text-sm text-dark-400 ml-2 space-y-1">
              <li>Connectez-vous à la console de la VM pour voir les erreurs</li>
              <li>Vérifiez que l'ISO est valide et non corrompue</li>
              <li>Augmentez la RAM si l'installeur manque de mémoire</li>
              <li>Vérifiez que l'ISO OEMDRV est bien monté (Windows)</li>
            </ul>
          </div>
          
          <div className="p-4 bg-dark-700/50 rounded-lg border border-dark-600">
            <h4 className="font-medium text-white flex items-center gap-2">
              <AlertTriangle size={16} className="text-blue-400" />
              PowerShell Direct ne fonctionne pas
            </h4>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Symptôme :</strong> Erreur lors des opérations post-installation
            </p>
            <p className="text-sm text-dark-300 mt-2">
              <strong>Solutions :</strong>
            </p>
            <ul className="list-disc list-inside text-sm text-dark-400 ml-2 space-y-1">
              <li>Assurez-vous que les Integration Services sont à jour</li>
              <li>Vérifiez que la VM est bien de génération 2</li>
              <li>Activez Guest Services : <code className="bg-dark-800 px-1 rounded">Enable-VMIntegrationService -VMName [nom] -Name "Guest Service Interface"</code></li>
            </ul>
          </div>
        </div>
      </div>
    ),
  },
];

// Composant principal
export function Help() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSection, setActiveSection] = useState<string>('getting-started');

  // Filtrer les sections basé sur la recherche
  const filteredSections = searchQuery
    ? docSections.filter(
        (section) =>
          section.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          String(section.content).toLowerCase().includes(searchQuery.toLowerCase())
      )
    : docSections;

  // Filtrer les FAQ basé sur la recherche
  const filteredFAQ = searchQuery
    ? faqItems.filter(
        (item) =>
          item.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
          String(item.answer).toLowerCase().includes(searchQuery.toLowerCase())
      )
    : faqItems;

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Aide" />
      
      <div className="p-4 sm:p-6">
        {/* Hero section */}
        <div className="card p-8 mb-6 text-center bg-gradient-to-br from-oto-100 dark:from-primary-600/10 to-purple-100 dark:to-purple-600/10 border-oto-200 dark:border-primary-500/20">
          <HelpCircle size={48} className="mx-auto mb-4 text-oto-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
            Centre d'aide VM Automation
          </h1>
          <p className="text-gray-500 dark:text-dark-400 max-w-xl mx-auto">
            Documentation complète pour déployer vos machines virtuelles Windows et Linux
            de manière automatisée sur Hyper-V.
          </p>
          
          {/* Barre de recherche */}
          <div className="mt-6 max-w-md mx-auto">
            <Input
              placeholder="Rechercher dans la documentation..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Search size={18} />}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar navigation */}
          <div className="lg:col-span-1">
            <div className="card p-4 sticky top-6">
              <h3 className="text-sm font-semibold text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-3">
                Navigation
              </h3>
              <nav className="space-y-1">
                {docSections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                      activeSection === section.id
                        ? 'bg-oto-100 dark:bg-primary-600/20 text-oto-600 dark:text-primary-500'
                        : 'text-gray-600 dark:text-dark-300 hover:bg-light-100 dark:hover:bg-dark-700/50 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    <section.icon size={18} />
                    <span className="text-sm">{section.title}</span>
                  </button>
                ))}
              </nav>
              
              {/* Liens externes */}
              <div className="mt-6 pt-4 border-t border-light-200 dark:border-dark-700">
                <h3 className="text-sm font-semibold text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-3">
                  Ressources
                </h3>
                <div className="space-y-2">
                  <a
                    href="https://github.com/Loutij/oto-netbox"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-sm text-gray-600 dark:text-dark-300 hover:text-oto-500 transition-colors"
                  >
                    <ExternalLink size={14} />
                    GitHub Repository
                  </a>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-sm text-gray-600 dark:text-dark-300 hover:text-oto-500 transition-colors"
                  >
                    <ExternalLink size={14} />
                    API Documentation
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Main content */}
          <div className="lg:col-span-3 space-y-6">
            {/* Section active */}
            {filteredSections.length > 0 && (
              <div className="card p-6">
                {filteredSections
                  .filter((s) => !searchQuery || s.id === activeSection || searchQuery)
                  .map((section) => (
                    <div
                      key={section.id}
                      className={searchQuery ? 'mb-8 last:mb-0' : activeSection === section.id ? '' : 'hidden'}
                    >
                      <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 bg-oto-100 dark:bg-primary-600/20 rounded-lg flex items-center justify-center">
                          <section.icon size={20} className="text-oto-500" />
                        </div>
                        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{section.title}</h2>
                      </div>
                      {section.content}
                    </div>
                  ))}
              </div>
            )}

            {/* FAQ */}
            <div className="card p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-yellow-100 dark:bg-yellow-500/20 rounded-lg flex items-center justify-center">
                  <MessageCircle size={20} className="text-yellow-600 dark:text-yellow-500" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Questions fréquentes</h2>
                  <p className="text-sm text-gray-500 dark:text-dark-400">Réponses aux questions les plus courantes</p>
                </div>
              </div>
              <FAQAccordion items={filteredFAQ} />
            </div>

            {/* Raccourcis clavier */}
            <div className="card p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-purple-100 dark:bg-purple-500/20 rounded-lg flex items-center justify-center">
                  <Keyboard size={20} className="text-purple-600 dark:text-purple-500" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Raccourcis clavier</h2>
                  <p className="text-sm text-gray-500 dark:text-dark-400">Naviguez plus rapidement dans l'application</p>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {shortcuts.map((shortcut, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-light-100 dark:bg-dark-700/50 rounded-lg"
                  >
                    <span className="text-gray-600 dark:text-dark-300">{shortcut.description}</span>
                    <div className="flex items-center gap-1">
                      {shortcut.keys.map((key, i) => (
                        <span key={i}>
                          <kbd className="px-2 py-1 bg-white dark:bg-dark-600 border border-light-300 dark:border-dark-500 rounded text-xs text-gray-900 dark:text-white font-mono">
                            {key}
                          </kbd>
                          {i < shortcut.keys.length - 1 && (
                            <span className="mx-1 text-gray-400 dark:text-dark-500">+</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Contact/Support */}
            <div className="card p-6 bg-gradient-to-r from-oto-50 dark:from-primary-600/10 to-blue-50 dark:to-blue-600/10 border-oto-200 dark:border-primary-500/20">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 bg-oto-100 dark:bg-primary-600/20 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Book size={24} className="text-oto-500" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Besoin d'aide supplémentaire ?</h3>
                  <p className="text-gray-600 dark:text-dark-300 mt-1">
                    Consultez la documentation complète ou contactez l'équipe Infrastructure IT.
                  </p>
                  <div className="flex flex-wrap gap-3 mt-4">
                    <a
                      href="https://github.com/Loutij/oto-netbox/issues"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-oto-600 hover:bg-oto-700 text-white rounded-lg text-sm transition-colors"
                    >
                      <MessageCircle size={16} />
                      Signaler un problème
                    </a>
                    <a
                      href="/docs/UNATTENDED_INSTALL.md"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-dark-600 hover:bg-gray-200 dark:hover:bg-dark-500 text-gray-900 dark:text-white rounded-lg text-sm transition-colors"
                    >
                      <Book size={16} />
                      Guide technique
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
