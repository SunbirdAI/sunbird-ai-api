import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Mail, Lock, ArrowRight } from 'lucide-react';
import axios from 'axios';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, checkAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    const errorMsg = params.get('error');

    if (token) {
      localStorage.setItem('access_token', token);
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      checkAuth().then(() => {
        navigate('/dashboard');
      });
    }

    if (errorMsg) {
      setError('Authentication failed. Please try again.');
    }
  }, [location, checkAuth, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // Redirect to Google OAuth endpoint
    window.location.href = '/auth/google/login?next=/dashboard';
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-black px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
        

        </div>

        <div className="bg-white dark:bg-secondary rounded-2xl shadow-lg dark:shadow-lg dark:shadow-black/10 p-8 border border-gray-100 dark:border-white/5 backdrop-blur-sm">
         <div className='gap-2 flex flex-col items-center justify-center mb-6'>
                     <img 
            src="/logo.png" 
            alt="Sunbird AI" 
            className="h-10 w-10 rounded-full object-cover"
          />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Sign  In</h2>
        
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Login to access your API dashboard
          </p>
         </div>
         
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
                {error}
              </div>
            )}
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Username or Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="username or email"
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Password
                </label>
                <Link to="/forgot-password" className="text-sm font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400">
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="••••••••"
                  disabled={loading}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign in'}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <div className="mt-6">
            <div className="relative">
              {/* <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t mx-1 border-gray-300 dark:border-white/10" />
              </div> */}
              <div className="relative flex justify-center items-center text-sm">
                 <div className="flex-1 h-px bg-gray-300 dark:bg-white/10"/>
                <span className="px-2 text-gray-500">
                  OR 
                </span> 
                <div className="flex-1 h-px bg-gray-300 dark:bg-white/10"/>
              </div>
            </div>

            <div className="mt-6">
              <button 
                onClick={handleGoogleLogin}
                type="button"
                className="w-full inline-flex justify-center items-center gap-2 py-2 px-4 border border-gray-300 dark:border-white/10 rounded-lg shadow-sm bg-white dark:bg-white/5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
              >
                <svg className='w-5 h-5'
      xmlns="http://www.w3.org/2000/svg"
      x="0px"
      y="0px"
      width="25"
      height="25"
      viewBox="0 0 48 48"
    >
      <path
        fill="#FFC107"
        d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z"
      ></path>
      <path
        fill="#FF3D00"
        d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z"
      ></path>
      <path
        fill="#4CAF50"
        d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z"
      ></path>
      <path
        fill="#1976D2"
        d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z"
      ></path>
    </svg>
                Sign in with Google
              </button>
            </div>
          </div>

          <div className="mt-6 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Don't have an account?{' '}
              <Link to="/register" className="font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400">
                Sign up
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
