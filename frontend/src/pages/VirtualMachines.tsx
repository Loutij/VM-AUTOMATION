import { Header } from '../components/layout';
import { Monitor } from 'lucide-react';

export function VirtualMachines() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Machines Virtuelles" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <Monitor size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Gestion des VMs
          </h2>
          <p className="text-dark-400">
            Cette page permettra de lister, créer et gérer les machines virtuelles.
          </p>
        </div>
      </div>
    </div>
  );
}
