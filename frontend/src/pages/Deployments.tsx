import { Header } from '../components/layout';
import { Rocket } from 'lucide-react';

export function Deployments() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Déploiements" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <Rocket size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Gestion des Déploiements
          </h2>
          <p className="text-dark-400">
            Cette page permettra de suivre et gérer les déploiements de VMs.
          </p>
        </div>
      </div>
    </div>
  );
}
