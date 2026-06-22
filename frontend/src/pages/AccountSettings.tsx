import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { User, Mail, Lock, Moon, Sun, Laptop, CreditCard, Eye, EyeOff, Building, Briefcase } from 'lucide-react';
import axios from 'axios';

const ORGANIZATION_TYPES = ['NGO', 'Government', 'Private Sector', 'Research', 'Individual', 'Other'];
const PRESET_SECTORS = ['Health', 'Agriculture', 'Energy', 'Environment', 'Education', 'Governance'];

export default function AccountSettings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    organization: user?.organization || '',
    organization_type: user?.organization_type || '',
  });
  const [selectedSectors, setSelectedSectors] = useState<string[]>(user?.sector || []);
  const [customSector, setCustomSector] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');
  const [profileError, setProfileError] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);
  const [passwordData, setPasswordData] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
    setProfileError('');
    setProfileSuccess('');
    setProfileLoading(true);

    try {
      await axios.put('/auth/profile', {
        full_name: formData.full_name || undefined,
        organization: formData.organization || undefined,
        organization_type: formData.organization_type || undefined,
        sector: selectedSectors.length > 0 ? selectedSectors : undefined,
      });
      setProfileSuccess('Profile updated successfully!');
    } catch (err: any) {
      setProfileError(err.response?.data?.detail || 'Failed to update profile.');
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (passwordData.newPassword !== passwordData.confirmPassword) {
      setPasswordError('New passwords do not match');
      return;
    }

    setPasswordLoading(true);

    try {
      const response = await axios.post('/auth/change-password', {
        old_password: passwordData.oldPassword,
        new_password: passwordData.newPassword,
      });

      if (response.data.success) {
        setPasswordSuccess('Password changed successfully!');
        setPasswordData({ oldPassword: '', newPassword: '', confirmPassword: '' });
      } else {
        setPasswordError(response.data.message || 'Failed to change password');
      }
    } catch (err: any) {
      setPasswordError(err.response?.data?.detail || 'Failed to change password');
    } finally {
      setPasswordLoading(false);
    }
  };

  // Only show change password for credentials users (not Google/OAuth)
  // The backend returns 'Google', 'GitHub', or 'Credentials'
  const isOAuthUser = user?.oauth_type === 'Google' || user?.oauth_type === 'GitHub';
  const canChangePassword = !isOAuthUser;
  const canChangeEmail = !isOAuthUser;

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Account Settings</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage your profile and preferences.</p>
      </div>

      <div className="bg-white dark:bg-secondary rounded-xl p-6 shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 space-y-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Profile Information</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          {profileError && (
            <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
              {profileError}
            </div>
          )}
          {profileSuccess && (
            <div className="bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 p-3 rounded-lg text-sm">
              {profileSuccess}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Username
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Full Name
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                placeholder="John Doe"
                disabled={profileLoading}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className={`w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white ${!canChangeEmail ? 'opacity-50 cursor-not-allowed' : ''}`}
                disabled={!canChangeEmail}
                title={!canChangeEmail ? "Email cannot be changed for OAuth accounts" : ""}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Organization
            </label>
            <div className="relative">
              <Building className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                placeholder="Organization Name"
                disabled={profileLoading}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Organization Type
            </label>
            <div className="relative">
              <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <select
                value={formData.organization_type}
                onChange={(e) => setFormData({ ...formData, organization_type: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white appearance-none"
                disabled={profileLoading}
              >
                <option value="">Select type...</option>
                {ORGANIZATION_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Impact Sectors
            </label>
            <div className="flex flex-wrap gap-2 mt-1">
              {[...PRESET_SECTORS, ...selectedSectors.filter((s) => !PRESET_SECTORS.includes(s))].map((sector) => (
                <button
                  key={sector}
                  type="button"
                  onClick={() => toggleSector(sector)}
                  disabled={profileLoading}
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
                disabled={profileLoading}
              />
              <button
                type="button"
                onClick={addCustomSector}
                disabled={profileLoading}
                className="px-3 py-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Add
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Account Type
            </label>
            <div className="relative">
              <CreditCard className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={user?.account_type || 'Standard'}
                readOnly
                className="w-full pl-9 pr-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none text-gray-500 dark:text-gray-400 cursor-not-allowed"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={profileLoading}
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {profileLoading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>

      <div className="bg-white dark:bg-secondary rounded-xl p-6 shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 space-y-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Appearance</h2>
        
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => setTheme('light')}
            className={`p-4 rounded-lg border flex flex-col items-center gap-2 transition-all ${
              theme === 'light'
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
                : 'border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Sun className="w-6 h-6" />
            <span className="text-sm font-medium">Light</span>
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={`p-4 rounded-lg border flex flex-col items-center gap-2 transition-all ${
              theme === 'dark'
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
                : 'border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Moon className="w-6 h-6" />
            <span className="text-sm font-medium">Dark</span>
          </button>
          <button
            onClick={() => setTheme('system')}
            className={`p-4 rounded-lg border flex flex-col items-center gap-2 transition-all ${
              theme === 'system'
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
                : 'border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Laptop className="w-6 h-6" />
            <span className="text-sm font-medium">System</span>
          </button>
        </div>
      </div>

      {canChangePassword && (
        <div className="bg-white dark:bg-secondary rounded-xl p-6 shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 space-y-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Change Password</h2>
          
          <form onSubmit={handlePasswordChange} className="space-y-4">
            {passwordError && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
                {passwordError}
              </div>
            )}

            {passwordSuccess && (
              <div className="bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 p-3 rounded-lg text-sm">
                {passwordSuccess}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Current Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type={showOldPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  value={passwordData.oldPassword}
                  onChange={(e) => setPasswordData({ ...passwordData, oldPassword: e.target.value })}
                  className="w-full pl-9 pr-12 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                  disabled={passwordLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowOldPassword(!showOldPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  disabled={passwordLoading}
                >
                  {showOldPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                New Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type={showNewPassword ? "text" : "password"}
                  placeholder="••••••••"
                  required
                  value={passwordData.newPassword}
                  onChange={(e) => setPasswordData({ ...passwordData, newPassword: e.target.value })}
                  className="w-full pl-9 pr-12 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                  disabled={passwordLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  disabled={passwordLoading}
                >
                  {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Confirm New Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  value={passwordData.confirmPassword}
                  onChange={(e) => setPasswordData({ ...passwordData, confirmPassword: e.target.value })}
                  className="w-full pl-9 pr-12 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                  disabled={passwordLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  disabled={passwordLoading}
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={passwordLoading}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {passwordLoading ? 'Changing Password...' : 'Change Password'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
