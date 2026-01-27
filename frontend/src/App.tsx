import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MainLayout } from './components/layout';
import { ToastProvider } from './components/ui';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import {
  Dashboard,
  Hypervisors,
  VirtualMachines,
  Templates,
  Deployments,
  NewDeployment,
  Marketplace,
  Settings,
  Help,
  Login,
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
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              {/* Route publique */}
              <Route path="/login" element={<Login />} />
              
              {/* Routes protégées */}
              <Route
                element={
                  <ProtectedRoute>
                    <MainLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Dashboard />} />
                <Route path="/hypervisors" element={<Hypervisors />} />
                <Route path="/vms" element={<VirtualMachines />} />
                <Route path="/templates" element={<Templates />} />
                <Route path="/deployments" element={<Deployments />} />
                <Route path="/deployments/new" element={<NewDeployment />} />
                <Route path="/marketplace" element={<Marketplace />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/help" element={<Help />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
