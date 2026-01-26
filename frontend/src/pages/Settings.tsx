import { Header } from '../components/layout';
import { Settings as SettingsIcon } from 'lucide-react';

export function Settings() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Paramètres" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <SettingsIcon size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Paramètres de l'application
          </h2>
          <p className="text-dark-400">
            Configuration générale, connexions et préférences.
          </p>
        </div>
      </div>
    </div>
  );
}
