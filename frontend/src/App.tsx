import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import UsageStats from './pages/UsageStats';
import ApiKeys from './pages/ApiKeys';
import AccountSettings from './pages/AccountSettings';
import LandingPage from './pages/LandingPage';
import Register from './pages/Register';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsOfService from './pages/TermsOfService';

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/privacy-policy" element={<PrivacyPolicy />} />
      <Route path="/terms-of-service" element={<TermsOfService />} />
      <Route path="/setup-organization" element={<Login />} /> {/* Handle token redirect via Login component logic */}
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <Layout>
              <Dashboard />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/usage"
        element={
          <RequireAuth>
            <Layout>
              <UsageStats />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/keys"
        element={
          <RequireAuth>
            <Layout>
              <ApiKeys />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/account"
        element={
          <RequireAuth>
            <Layout>
              <AccountSettings />
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <ThemeProvider defaultTheme="system" storageKey="sunbird-ui-theme">
        <AuthProvider>
          <AppRoutes />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
