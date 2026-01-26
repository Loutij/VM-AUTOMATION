import { Header } from '../components/layout';
import { HelpCircle } from 'lucide-react';

export function Help() {
  return (
    <div className="min-h-screen bg-dark-900">
      <Header title="Aide" />
      <div className="p-6">
        <div className="card p-12 text-center">
          <HelpCircle size={48} className="mx-auto mb-4 text-dark-400" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Centre d'aide
          </h2>
          <p className="text-dark-400">
            Documentation et support pour VM Automation Tool.
          </p>
        </div>
      </div>
    </div>
  );
}
