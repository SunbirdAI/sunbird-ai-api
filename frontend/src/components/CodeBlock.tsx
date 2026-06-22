import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('bash', bash);

type Language = 'python' | 'json' | 'bash';

interface CodeBlockProps {
  code: string;
  language?: Language;
  label?: string;
}

function useResolvedTheme(): 'light' | 'dark' {
  const [resolved, setResolved] = useState<'light' | 'dark'>(() =>
    typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
      ? 'dark'
      : 'light',
  );

  useEffect(() => {
    const root = document.documentElement;
    const update = () => setResolved(root.classList.contains('dark') ? 'dark' : 'light');
    update();
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return resolved;
}

export default function CodeBlock({ code, language = 'python', label }: CodeBlockProps) {
  const resolvedTheme = useResolvedTheme();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silently ignore — clipboard API can fail in insecure contexts
    }
  };

  const displayLabel = label ?? language.toUpperCase();
  const style = resolvedTheme === 'dark' ? oneDark : oneLight;

  return (
    <div className="group relative my-4 rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-white/10 bg-white/50 dark:bg-black/30">
        <span className="text-xs font-mono font-medium text-gray-500 dark:text-gray-400 tracking-wide">
          {displayLabel}
        </span>
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? (
            <>
              <Check size={14} className="text-primary-600 dark:text-primary-400" />
              Copied
            </>
          ) : (
            <>
              <Copy size={14} />
              Copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={style}
        customStyle={{
          margin: 0,
          padding: '1rem 1.25rem',
          background: 'transparent',
          fontSize: '0.875rem',
          lineHeight: '1.6',
        }}
        codeTagProps={{
          style: {
            fontFamily:
              'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
          },
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
