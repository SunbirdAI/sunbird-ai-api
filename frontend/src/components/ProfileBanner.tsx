import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { User } from 'lucide-react';
import axios from 'axios';

export default function ProfileBanner() {
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    const checkProfileStatus = async () => {
      try {
        const response = await axios.get('/auth/profile/status');
        setShowBanner(!response.data.is_complete);
      } catch {
        setShowBanner(false);
      }
    };
    checkProfileStatus();
  }, []);

  if (!showBanner) return null;

  return (
    <div className="bg-gradient-to-r from-primary-500/10 to-primary-500/5 border border-primary-500/20 rounded-xl p-4 mb-6 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 flex-1">
        <div className="w-9 h-9 rounded-lg bg-primary-500/15 flex items-center justify-center flex-shrink-0">
          <User className="w-[18px] h-[18px] text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">
            Complete your profile
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Add your organization type and impact sectors to help us understand how Sunbird AI is being used.
          </p>
        </div>
      </div>
      <Link
        to="/complete-profile"
        className="px-5 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm shadow-primary-500/20 whitespace-nowrap"
      >
        Update Profile
      </Link>
    </div>
  );
}
