import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const ORGANIZATION_TYPES = ['NGO', 'Government', 'Private Sector', 'Research', 'Individual', 'Other'];
const PRESET_SECTORS = ['Health', 'Agriculture', 'Energy', 'Environment', 'Education', 'Governance'];

export default function CompleteProfile() {
  const { user, checkAuth } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    full_name: user?.full_name || '',
    organization: user?.organization === 'Unknown' ? '' : (user?.organization || ''),
    organization_type: user?.organization_type || '',
  });
  const [selectedSectors, setSelectedSectors] = useState<string[]>(user?.sector || []);
  const [customSector, setCustomSector] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggleSector = (sector: string) => {
    setSelectedSectors((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]
    );
  };

  const addCustomSector = () => {
    const trimmed = customSector.trim();
    if (trimmed && !selectedSectors.includes(trimmed)) {
      setSelectedSectors((prev) => [...prev, trimmed]);
      setCustomSector('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await axios.put('/auth/profile', {
        full_name: formData.full_name || undefined,
        organization: formData.organization || undefined,
        organization_type: formData.organization_type || undefined,
        sector: selectedSectors.length > 0 ? selectedSectors : undefined,
      });
      await checkAuth();
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-black px-4 py-12">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <img
            src="/logo.png"
            alt="Sunbird AI"
            className="h-10 w-10 rounded-full object-cover mx-auto mb-3"
          />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Complete Your Profile
          </h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Help us understand how you're using Sunbird AI so we can serve you better.
          </p>
        </div>

        <div className="bg-white dark:bg-secondary rounded-2xl shadow-lg dark:shadow-lg dark:shadow-black/10 p-8 border border-gray-100 dark:border-white/5">
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Full Name
              </label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                placeholder="John Doe"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Organization Name
              </label>
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                placeholder="Sunbird AI"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Organization Type
              </label>
              <select
                value={formData.organization_type}
                onChange={(e) => setFormData({ ...formData, organization_type: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white appearance-none"
                disabled={loading}
              >
                <option value="">Select type...</option>
                {ORGANIZATION_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Impact Sectors <span className="text-gray-400 font-normal">(select all that apply)</span>
              </label>
              <div className="flex flex-wrap gap-2 mt-2">
                {[...PRESET_SECTORS, ...selectedSectors.filter((s) => !PRESET_SECTORS.includes(s))].map((sector) => (
                  <button
                    key={sector}
                    type="button"
                    onClick={() => toggleSector(sector)}
                    disabled={loading}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      selectedSectors.includes(sector)
                        ? 'border-primary-500 bg-primary-500/10 text-primary-600 dark:text-primary-400'
                        : 'border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'
                    }`}
                  >
                    {sector} {selectedSectors.includes(sector) && '✓'}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 mt-2">
                <input
                  type="text"
                  value={customSector}
                  onChange={(e) => setCustomSector(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomSector())}
                  className="flex-1 px-3 py-1.5 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white text-sm placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="Add custom sector..."
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={addCustomSector}
                  disabled={loading}
                  className="px-3 py-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Add
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors shadow-lg shadow-primary-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Saving...' : 'Save & Continue to Dashboard'}
            </button>
          </form>

          <div className="mt-4 text-center">
            <button
              onClick={() => navigate('/dashboard')}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              Skip for now →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
