import { Header } from '../components/layout';
import { Server } from 'lucide-react';

export function Hypervisors() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Hyperviseurs" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <Server size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Gestion des Hyperviseurs
          </h2>
          <p className="text-dark-400">
            Cette page permettra de gérer les connexions Hyper-V et VMware.
          </p>
        </div>
      </div>
    </div>
  );
}
