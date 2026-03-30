import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MainLayout } from './components/layout';
import { ToastProvider } from './components/ui';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';

// Lazy-loaded pages (code splitting)
const Dashboard = React.lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Hypervisors = React.lazy(() => import('./pages/Hypervisors').then(m => ({ default: m.Hypervisors })));
const VirtualMachines = React.lazy(() => import('./pages/VirtualMachines').then(m => ({ default: m.VirtualMachines })));
const Templates = React.lazy(() => import('./pages/Templates').then(m => ({ default: m.Templates })));
const Deployments = React.lazy(() => import('./pages/Deployments').then(m => ({ default: m.Deployments })));
const NewDeployment = React.lazy(() => import('./pages/NewDeployment').then(m => ({ default: m.NewDeployment })));
const Marketplace = React.lazy(() => import('./pages/Marketplace').then(m => ({ default: m.Marketplace })));
const Settings = React.lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })));
const Help = React.lazy(() => import('./pages/Help').then(m => ({ default: m.Help })));
const Login = React.lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const VMConsolePage = React.lazy(() => import('./pages/VMConsole').then(m => ({ default: m.VMConsolePage })));
const VNCConsolePage = React.lazy(() => import('./pages/VNCConsole').then(m => ({ default: m.VNCConsolePage })));
const AdminUsers = React.lazy(() => import('./pages/AdminUsers').then(m => ({ default: m.AdminUsers })));

// Loading spinner for Suspense fallback
function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

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
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>
            <BrowserRouter>
            <ErrorBoundary>
            <Suspense fallback={<LoadingSpinner />}>
            <Routes>
              {/* Route publique */}
              <Route path="/login" element={<Login />} />

              {/* Console VM (fullscreen, hors layout) */}
              <Route
                path="/vms/:vmId/console"
                element={
                  <ProtectedRoute>
                    <VMConsolePage />
                  </ProtectedRoute>
                }
              />

              {/* VNC Console (fullscreen, hors layout) */}
              <Route
                path="/vms/:vmId/vnc"
                element={
                  <ProtectedRoute>
                    <VNCConsolePage />
                  </ProtectedRoute>
                }
              />

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
                <Route path="/admin/users" element={<AdminUsers />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/help" element={<Help />} />
              </Route>
            </Routes>
            </Suspense>
            </ErrorBoundary>
            </BrowserRouter>
          </ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
