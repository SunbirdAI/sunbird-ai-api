import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Key,
  Settings,
  BookOpen,
  LogOut,
  Menu,
  X, User,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

export default function Layout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, logout } = useAuth();
  // const { theme, setTheme } = useTheme();
  const location = useLocation();

  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'API Keys', href: '/keys', icon: Key },
    { name: 'Account', href: '/account', icon: Settings },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black transition-colors duration-300">
      {/* Header */}
      <header className="fixed top-0 z-40 w-full bg-white dark:bg-black border-b border-gray-200 dark:border-white/10 h-16 flex items-center justify-between px-4 sm:px-6 lg:px-8 transition-colors duration-300">
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="lg:hidden p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <span className="sr-only">Open sidebar</span>
            {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
          <div className="flex items-center gap-2 font-bold text-xl ">
            <img src="/logo.png" className='w-8 h-8 object-cover' alt="" />
            <span>Sunbird AI</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 transition-colors"
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </button>
           */}
           {/* border-l */}
          <div className="flex items-center gap-3 pl-4  border-gray-200 dark:border-white/10">
            <div className="hidden md:block text-right">
              <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.username || 'User'}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{user?.organization || 'Organization'}</p>
            </div>
            <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center text-primary-700 dark:text-primary-400 border border-primary-200 dark:border-primary-800">
              <User size={18} />
            </div>
          </div>
        </div>
      </header>

     

      {/* Main Content */}
      <article >
         {/* Sidebar */}
      <aside
        className={`fixed top-16 left-0 z-50 h-[calc(100vh-4rem)] bg-white dark:bg-black border-r border-gray-200 dark:border-white/10 transition-all duration-300 lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        } ${sidebarCollapsed ? 'w-16' : 'w-64'}`}
      >
        <nav className="h-full flex flex-col justify-between p-2">
          <div className="space-y-1">
            {navigation.map((item) => (
              <div key={item.name} className="relative group">
                <Link
                  to={item.href}
                  className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive(item.href)
                      ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400'
                      : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5'
                  } ${sidebarCollapsed ? 'justify-center' : ''}`}
                  onClick={() => setSidebarOpen(false)}
                >
                  <item.icon size={20} className="flex-shrink-0" />
                  {!sidebarCollapsed && <span>{item.name}</span>}
                </Link>
                {/* Tooltip for collapsed state */}
                {sidebarCollapsed && (
                  <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-white text-white dark:text-black text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 pointer-events-none">
                    {item.name}
                    <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-gray-900 dark:border-r-white"></div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="space-y-1 pt-4 border-t border-gray-200 dark:border-white/10">
            <div className="relative group">
              <a
                href="https://docs.sunbird.ai"
                target="_blank"
                rel="noopener noreferrer"
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5 transition-colors ${
                  sidebarCollapsed ? 'justify-center' : ''
                }`}
              >
                <BookOpen size={20} className="flex-shrink-0" />
                {!sidebarCollapsed && <span>Documentation</span>}
              </a>
              {sidebarCollapsed && (
                <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-white dark:text-black text-white text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 pointer-events-none">
                  Documentation
                  <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-gray-900 dark:border-r-white"></div>
                </div>
              )}
            </div>
            
            <div className="relative group">
              <button
                onClick={logout}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 transition-colors ${
                  sidebarCollapsed ? 'justify-center' : ''
                }`}
              >
                <LogOut size={20} className="flex-shrink-0" />
                {!sidebarCollapsed && <span>Sign Out</span>}
              </button>
              {sidebarCollapsed && (
                <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-white dark:text-black text-white text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 pointer-events-none">
                  Sign Out
                  <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-gray-900 dark:border-r-white"></div>
                </div>
              )}
            </div>
            
            {/* Collapse Toggle - Desktop only */}
            <div className="relative group">
              <button
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                className={`hidden lg:flex w-full items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5 transition-colors mt-2 ${
                  sidebarCollapsed ? 'justify-center' : ''
                }`}
              >
                {sidebarCollapsed ? <ChevronRight size={20} className="flex-shrink-0" /> : <><ChevronLeft size={20} className="flex-shrink-0" /><span>Collapse</span></>}
              </button>
              {sidebarCollapsed && (
                <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-white dark:text-black text-white text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 pointer-events-none">
                  Expand
                  <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-gray-900 dark:border-r-white"></div>
                </div>
              )}
            </div>
          </div>
        </nav>
      </aside>
      
      <main className={`pt-16 pb-24 min-h-screen transition-all duration-300  ${sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-64'}`}>
        <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
          {children}
        </div>
        <footer className={`border-t border-gray-200 dark:border-white/10 py-6 text-center text-sm text-gray-500 dark:text-gray-400 fixed bottom-0 left-0 right-0 z-40 bg-gray-50 dark:bg-black ${sidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'}`}>
          <p>&copy; {new Date().getFullYear()} Sunbird AI. All rights reserved.</p>
        </footer>
      </main>
</article>
      {/* Overlay for mobile sidebar */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}
