import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MainLayout } from './components/layout';
import { ToastProvider } from './components/ui';
import {
  Dashboard,
  Hypervisors,
  VirtualMachines,
  Templates,
  Deployments,
  Settings,
  Help,
} from './pages';

// Configuration React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000, // 30 secondes
      retry: 3,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<MainLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/hypervisors" element={<Hypervisors />} />
              <Route path="/vms" element={<VirtualMachines />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/deployments" element={<Deployments />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/help" element={<Help />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
