import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

interface Option {
  label: string;
  value: string;
  color?: string;
}

interface MultiSelectProps {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (selected: string[]) => void;
  className?: string;
}

export default function MultiSelect({
  label,
  options,
  selected,
  onChange,
  className = '',
}: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleOption = (value: string) => {
    const newSelected = selected.includes(value)
      ? selected.filter(item => item !== value)
      : [...selected, value];
    onChange(newSelected);
  };

  const selectAll = () => {
    onChange(options.map(opt => opt.value));
  };

  const clearAll = () => {
    onChange([]);
  };

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full md:w-64 px-4 py-2 bg-white dark:bg-secondary border border-gray-200 dark:border-white/10 rounded-lg shadow-sm hover:bg-gray-50 dark:hover:bg-white/5 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
      >
        <span className="text-sm text-gray-700 dark:text-gray-200 truncate">
          {selected.length === 0
            ? label
            : selected.length === options.length
            ? 'All Selected'
            : `${selected.length} Selected`}
        </span>
        <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute z-50 w-full md:w-72 mt-2 bg-white dark:bg-secondary border border-gray-200 dark:border-white/10 rounded-xl shadow-lg overflow-hidden animate-in fade-in zoom-in-95 duration-100">
          <div className="p-2 border-b border-gray-200 dark:border-white/10 flex items-center justify-between bg-gray-50 dark:bg-white/5">
            <button
              onClick={selectAll}
              className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
            >
              Select All
            </button>
            <button
              onClick={clearAll}
              className="text-xs font-medium text-red-600 hover:text-red-700 dark:text-red-400"
            >
              Clear
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto p-2 space-y-1">
            {options.map((option) => (
              <button
                key={option.value}
                onClick={() => toggleOption(option.value)}
                className="flex items-center w-full px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 transition-colors group"
              >
                <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 transition-colors ${
                  selected.includes(option.value)
                    ? 'bg-primary-600 border-primary-600'
                    : 'border-gray-300 dark:border-gray-600 group-hover:border-primary-500'
                }`}>
                  {selected.includes(option.value) && (
                    <Check className="w-3.5 h-3.5 text-white" />
                  )}
                </div>
                {option.color && (
                  <div
                    className="w-3 h-3 rounded-full mr-3 flex-shrink-0"
                    style={{ backgroundColor: option.color }}
                  />
                )}
                <span className="text-sm text-gray-700 dark:text-gray-200 truncate">
                  {option.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
