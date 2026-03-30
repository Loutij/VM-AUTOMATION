import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

// Composant OTO Mark pour la page login
function OTOLoginMark() {
  return (
    <div className="flex items-center justify-center gap-2 mb-6">
      {/* Cercle avec encoche */}
      <div className="w-8 h-8 border-[3px] border-gray-900 dark:border-white rounded-full border-r-transparent rotate-45" />
      {/* Cercle plein */}
      <div className="w-8 h-8 rounded-full bg-gray-900 dark:bg-white" />
      {/* Carré bleu */}
      <div className="w-8 h-8 rounded-sm bg-oto-500" />
    </div>
  );
}

export function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError((err as Error).message || 'Erreur de connexion');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white dark:bg-dark-900 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background grid pattern - OTO style */}
      <div 
        className="absolute inset-0 opacity-[0.03] dark:opacity-[0.02]"
        style={{
          backgroundImage: `
            linear-gradient(to right, currentColor 1px, transparent 1px),
            linear-gradient(to bottom, currentColor 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      />
      
      {/* Accent shapes */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-oto-500/10 rounded-full blur-3xl" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-oto-500/5 rounded-full blur-3xl" />

      <div className="w-full max-w-md relative z-10">
        {/* Logo et titre */}
        <div className="text-center mb-8">
          <OTOLoginMark />
          <h1 className="text-3xl font-black uppercase tracking-tight text-gray-900 dark:text-white">
            VM Automation
          </h1>
          <p className="text-gray-500 dark:text-dark-400 mt-2 text-sm uppercase tracking-widest">
            OTO Technology
          </p>
        </div>

        {/* Formulaire */}
        <div className="bg-white dark:bg-dark-800 rounded-2xl border border-light-200 dark:border-dark-700 p-8 shadow-xl dark:shadow-none">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Message d'erreur */}
            {error && (
              <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-lg p-4 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Username */}
            <div>
              <label htmlFor="username" className="block text-sm font-semibold text-gray-700 dark:text-dark-200 mb-2 uppercase tracking-wide">
                Nom d'utilisateur
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-light-50 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent transition-all"
                placeholder="admin"
                required
                autoComplete="username"
                autoFocus
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-semibold text-gray-700 dark:text-dark-200 mb-2 uppercase tracking-wide">
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 pr-12 bg-light-50 dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:border-transparent transition-all"
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-dark-400 hover:text-gray-600 dark:hover:text-dark-200 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting || !username || !password}
              className="w-full py-3.5 px-4 bg-oto-500 hover:bg-oto-600 active:bg-oto-700 text-white font-bold uppercase tracking-wide rounded-lg shadow-lg shadow-oto-500/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Connexion...
                </>
              ) : (
                'Se connecter'
              )}
            </button>
          </form>

          {/* Info */}
          <div className="mt-6 pt-6 border-t border-light-200 dark:border-dark-700">
            <p className="text-sm text-gray-500 dark:text-dark-500 text-center">
              Première utilisation ? Utilisez les identifiants par défaut ou créez un compte via l'API.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-8">
          <p className="text-gray-400 dark:text-dark-500 text-xs uppercase tracking-widest">
            VM Automation v0.1.0
          </p>
          <p className="text-gray-300 dark:text-dark-600 text-xs mt-1">
            © OTO Technology
          </p>
        </div>
      </div>
    </div>
  );
}
