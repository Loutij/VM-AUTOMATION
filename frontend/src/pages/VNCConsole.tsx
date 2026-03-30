import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Monitor } from 'lucide-react';
import { VNCViewer } from '../components/vm/VNCViewer';
import { vmsApi } from '../services/api';

export function VNCConsolePage() {
  const { vmId } = useParams<{ vmId: string }>();
  const navigate = useNavigate();

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
      {/* Header bar */}
      <div className="flex items-center bg-gray-800 border-b border-gray-700 px-2">
        <button
          className="flex items-center gap-2 px-3 py-2.5 text-sm text-gray-400 hover:text-white transition-colors"
          onClick={() => navigate('/vms')}
          title="Retour aux VMs"
        >
          <ArrowLeft size={16} />
          <span className="hidden sm:inline">Retour</span>
        </button>

        <div className="flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-blue-400">
          <Monitor size={16} />
          VNC
        </div>

        <div className="flex-1" />

        <span className="text-gray-400 text-sm mr-4">{vm?.name || vmId}</span>
      </div>

      {/* VNC Viewer */}
      <div className="flex-1 overflow-hidden">
        <VNCViewer vmId={vmId} vmName={vm?.name} />
      </div>
    </div>
  );
}
