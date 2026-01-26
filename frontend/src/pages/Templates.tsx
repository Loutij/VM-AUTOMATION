import { Header } from '../components/layout';
import { FileCode } from 'lucide-react';

export function Templates() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Templates OS" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <FileCode size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Gestion des Templates
          </h2>
          <p className="text-dark-400">
            Cette page permettra de gérer les templates d'installation automatique.
          </p>
        </div>
      </div>
    </div>
  );
}
