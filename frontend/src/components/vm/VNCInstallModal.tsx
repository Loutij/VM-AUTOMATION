import { useState, useCallback } from 'react';
import { Modal } from '../ui/Modal';

interface VNCInstallModalProps {
  isOpen: boolean;
  onClose: () => void;
  vmId: string;
  vmName: string;
  osFamily?: string;
  onInstall: (config: { port: number; username: string; password: string }) => Promise<void>;
}

export function VNCInstallModal({ isOpen, onClose, vmId: _vmId, vmName, osFamily, onInstall }: VNCInstallModalProps) {
  const [port, setPort] = useState(5900);
  const [username, setUsername] = useState('otoroot');
  const [password, setPassword] = useState('tooroto');
  const [installing, setInstalling] = useState(false);
  const [result, setResult] = useState<{ success: boolean; error?: string } | null>(null);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setResult(null);
    try {
      await onInstall({ port, username, password });
      setResult({ success: true });
    } catch (err: any) {
      setResult({ success: false, error: err?.message || 'Installation failed' });
    } finally {
      setInstalling(false);
    }
  }, [port, username, password, onInstall]);

  const isWindows = osFamily === 'windows';

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Installer ${isWindows ? 'RDP' : 'VNC'} — ${vmName}`}>
      <div className="space-y-4">
        {isWindows ? (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Active le Bureau à distance (RDP) sur la VM Windows. Port par défaut : 3389.
          </p>
        ) : (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Port VNC</label>
              <input
                type="number"
                value={port}
                onChange={e => setPort(Number(e.target.value))}
                min={5900}
                max={5999}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-lg bg-white dark:bg-dark-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Utilisateur SSH</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-lg bg-white dark:bg-dark-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mot de passe</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-dark-600 rounded-lg bg-white dark:bg-dark-700 text-gray-900 dark:text-white"
              />
            </div>
          </>
        )}

        {result && (
          <div className={`p-3 rounded-lg text-sm ${result.success ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'}`}>
            {result.success ? 'Installation réussie !' : `Erreur : ${result.error}`}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-700 rounded-lg">
            Fermer
          </button>
          <button
            onClick={handleInstall}
            disabled={installing}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {installing ? 'Installation...' : `Installer ${isWindows ? 'RDP' : 'VNC'}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
