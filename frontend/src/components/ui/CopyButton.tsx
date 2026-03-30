import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

interface CopyButtonProps {
  text: string;
  size?: 'sm' | 'md';
}

export function CopyButton({ text, size = 'md' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const iconSize = size === 'sm' ? 14 : 18;
  const btnSize = size === 'sm' ? 'p-1' : 'p-1.5';

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`${btnSize} rounded-md text-gray-400 dark:text-dark-400 hover:text-gray-600 dark:hover:text-dark-200 hover:bg-light-200 dark:hover:bg-dark-700 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-oto-500 focus:ring-offset-1 dark:focus:ring-offset-dark-900`}
      title={copied ? 'Copie !' : 'Copier'}
    >
      {copied ? (
        <Check size={iconSize} className="text-green-500" />
      ) : (
        <Copy size={iconSize} />
      )}
    </button>
  );
}
