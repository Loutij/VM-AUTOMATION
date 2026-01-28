import { useState, useRef, useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { MoreVertical } from 'lucide-react';
import { Button } from './Button';

interface DropdownItem {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  variant?: 'default' | 'danger';
  disabled?: boolean;
}

interface DropdownProps {
  items: DropdownItem[];
  trigger?: ReactNode;
}

export function Dropdown({ items, trigger }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const menuWidth = 192; // w-48 = 12rem = 192px
      
      // Calculate position
      let top = rect.bottom + 4;
      let left = rect.right - menuWidth;
      
      // Ensure menu doesn't go off-screen on the right
      if (left < 8) {
        left = 8;
      }
      
      // Ensure menu doesn't go off-screen at the bottom
      const menuHeight = items.length * 40; // Approximate height
      if (top + menuHeight > window.innerHeight - 8) {
        top = rect.top - menuHeight - 4;
      }
      
      setPosition({ top, left });
    }
  }, [isOpen, items.length]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(!isOpen);
  };

  const handleItemClick = (item: DropdownItem) => {
    if (!item.disabled) {
      item.onClick();
      setIsOpen(false);
    }
  };

  return (
    <>
      {trigger ? (
        <div ref={buttonRef as any} onClick={handleToggle}>
          {trigger}
        </div>
      ) : (
        <Button
          ref={buttonRef}
          variant="ghost"
          size="sm"
          onClick={handleToggle}
          className="!p-1.5"
        >
          <MoreVertical size={16} />
        </Button>
      )}

      {isOpen &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed w-48 bg-white dark:bg-dark-700 border border-light-300 dark:border-dark-600 rounded-lg shadow-xl py-1 animate-in fade-in zoom-in-95 duration-100"
            style={{
              top: position.top,
              left: position.left,
              zIndex: 99999,
            }}
          >
            {items.map((item, index) => (
              <button
                key={index}
                onClick={() => handleItemClick(item)}
                disabled={item.disabled}
                className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  item.variant === 'danger'
                    ? 'text-red-500 hover:bg-red-50 dark:hover:bg-dark-600'
                    : 'text-gray-700 dark:text-dark-200 hover:bg-light-100 dark:hover:bg-dark-600'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>,
          document.body
        )}
    </>
  );
}
