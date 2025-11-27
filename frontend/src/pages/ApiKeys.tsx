import { useState, useEffect } from 'react';
import { ColumnDef } from '@tanstack/react-table';
import { Copy, Plus, Check } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import DataTable from '../components/DataTable';

interface ApiKey {
  id: string;
  name: string;
  key: string;
  created: string;
  lastUsed?: string;
}

export default function ApiKeys() {
  const { user } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchApiKeys = async () => {
      try {
        // Get the current token which is the API key
        const token = localStorage.getItem('access_token');
        if (token) {
          // For now, display the current access token as the API key
          setKeys([{
            id: '1',
            name: 'Current API Key',
            key: token,
            created: new Date().toISOString().split('T')[0],
            lastUsed: 'Active'
          }]);
        }
      } catch (error) {
        console.error('Failed to fetch API keys:', error);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchApiKeys();
    }
  }, [user]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const revokeKey = async (id: string) => {
    if (confirm('Are you sure you want to revoke this API key? This action cannot be undone.')) {
      setKeys(keys.filter(k => k.id !== id));
      // TODO: Call backend to revoke the key
    }
  };

  const apiKeyColumns: ColumnDef<ApiKey>[] = [
    {
      accessorKey: 'name',
      header: 'Name',
    },
    {
      accessorKey: 'key',
      header: 'Key',
      cell: ({ row }) => (
        <div className="flex items-center gap-2 font-mono text-gray-700 dark:text-gray-300">
          <span className="truncate max-w-xs">{row.original.key.substring(0, 20)}...</span>
          <button 
            onClick={() => copyToClipboard(row.original.key, row.original.id)}
            className="p-1 hover:bg-gray-100 dark:hover:bg-white/10 rounded transition-colors"
            title="Copy key"
          >
            {copiedId === row.original.id ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
      )
    },
    {
      accessorKey: 'created',
      header: 'Created',
    },
    {
      accessorKey: 'lastUsed',
      header: 'Last Used',
      cell: ({ row }) => row.original.lastUsed || 'Never'
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => (
        <button 
          onClick={() => revokeKey(row.original.id)}
          className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium"
        >
          Revoke
        </button>
      )
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">Loading API keys...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">API Keys</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage your API keys for authentication.</p>
        </div>
        <button 
          onClick={() => alert('Generate new key functionality coming soon')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Generate New Key
        </button>
      </div>

      <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
        <DataTable
          data={keys}
          columns={apiKeyColumns}
          itemsPerPage={10}
          searchable={true}
          emptyMessage="No API keys found. Generate one to get started."
        />
      </div>

      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">Using Your API Key</h3>
        <p className="text-sm text-blue-700 dark:text-blue-400 mb-3">
          Include your API key in the Authorization header of your requests:
        </p>
        <code className="block bg-white dark:bg-black/50 p-3 rounded text-xs font-mono text-gray-900 dark:text-gray-100 border border-blue-200 dark:border-blue-800">
          Authorization: Bearer YOUR_API_KEY
        </code>
      </div>
    </div>
  );
}
