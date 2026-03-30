import { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Monitor, Terminal, X } from 'lucide-react';
import { VMConsole } from '../components/vm/VMConsole';
import { VMTerminal } from '../components/vm/VMTerminal';
import { vmsApi } from '../services/api';

type ConsoleTab = 'vnc' | 'terminal';

export function VMConsolePage() {
  const { vmId } = useParams<{ vmId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<ConsoleTab>(
    searchParams.get('tab') === 'terminal' ? 'terminal' : 'vnc'
  );

  const { data: vm } = useQuery({
    queryKey: ['vm', vmId],
    queryFn: () => vmsApi.get(vmId!),
    enabled: !!vmId,
  });

  if (!vmId) {
    return <div className="text-white p-4">VM ID manquant</div>;
  }

  return (
    <div className="h-screen flex flex-col bg-gray-900">
      {/* Tab bar */}
      <div className="flex items-center bg-gray-800 border-b border-gray-700 px-2">
        <button
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'vnc'
              ? 'text-blue-400 border-blue-400 bg-gray-900/50'
              : 'text-gray-400 border-transparent hover:text-gray-200 hover:border-gray-600'
          }`}
          onClick={() => setActiveTab('vnc')}
        >
          <Monitor size={16} />
          VNC
        </button>
        <button
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'terminal'
              ? 'text-green-400 border-green-400 bg-gray-900/50'
              : 'text-gray-400 border-transparent hover:text-gray-200 hover:border-gray-600'
          }`}
          onClick={() => setActiveTab('terminal')}
        >
          <Terminal size={16} />
          Terminal
        </button>

        <div className="flex-1" />

        <span className="text-gray-400 text-sm mr-4">{vm?.name || vmId}</span>

        <button
          className="text-gray-400 hover:text-white p-2 rounded transition-colors"
          onClick={() => navigate('/vms')}
          title="Fermer"
        >
          <X size={18} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'vnc' ? (
          <VMConsole vmId={vmId} vmName={vm?.name} />
        ) : (
          <VMTerminal vmId={vmId} vmName={vm?.name} />
        )}
      </div>
    </div>
  );
}
