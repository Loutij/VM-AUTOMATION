import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

interface UseKeyboardShortcutsOptions {
  onToggleCommandPalette: () => void;
}

/**
 * Hook pour les raccourcis clavier globaux.
 * N'intercepte pas si l'utilisateur est dans un input/textarea.
 */
export function useKeyboardShortcuts({ onToggleCommandPalette }: UseKeyboardShortcutsOptions) {
  const navigate = useNavigate();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const tagName = target.tagName.toLowerCase();
      const isEditable = tagName === 'input' || tagName === 'textarea' || target.isContentEditable;

      // Ctrl+K / Cmd+K : toujours intercepter (meme dans un input)
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        onToggleCommandPalette();
        return;
      }

      // Ne pas intercepter les autres raccourcis si l'utilisateur est dans un champ editable
      if (isEditable) return;

      // Ctrl+N / Cmd+N : nouveau deploiement
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        navigate('/deployments/new');
        return;
      }

      // Ctrl+, / Cmd+, : ouvrir les parametres
      if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        e.preventDefault();
        navigate('/settings');
        return;
      }

      // ? : afficher l'aide
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        navigate('/help');
        return;
      }
    },
    [navigate, onToggleCommandPalette]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
}
