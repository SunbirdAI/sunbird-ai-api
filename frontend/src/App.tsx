import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';

import ApiKeys from './pages/ApiKeys';
import AccountSettings from './pages/AccountSettings';
import LandingPage from './pages/LandingPage';
import Register from './pages/Register';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsOfService from './pages/TermsOfService';
import { Loader2 } from 'lucide-react';
import PageTitle from './components/PageTitle';

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">
      <Loader2 size={24} className="animate-spin mr-2"/>
      Loading...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<PageTitle title="Home"><LandingPage /></PageTitle>} />
      <Route path="/login" element={<PageTitle title="Login"><Login /></PageTitle>} />
      <Route path="/register" element={<PageTitle title="Register"><Register /></PageTitle>} />
      <Route path="/forgot-password" element={<PageTitle title="Forgot Password"><ForgotPassword /></PageTitle>} />
      <Route path="/reset-password" element={<PageTitle title="Reset Password"><ResetPassword /></PageTitle>} />
      <Route path="/privacy_policy" element={<PageTitle title="Privacy Policy"><PrivacyPolicy /></PageTitle>} />
      <Route path="/terms_of_service" element={<PageTitle title="Terms of Service"><TermsOfService /></PageTitle>} />
      <Route path="/setup-organization" element={<PageTitle title="Setup Organization"><Login /></PageTitle>} /> {/* Handle token redirect via Login component logic */}
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <Layout>
              <PageTitle title="Dashboard">
                <Dashboard />
              </PageTitle>
            </Layout>
          </RequireAuth>
        }
      />

      <Route
        path="/keys"
        element={
          <RequireAuth>
            <Layout>
              <PageTitle title="API Keys">
                <ApiKeys />
              </PageTitle>
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/account"
        element={
          <RequireAuth>
            <Layout>
              <PageTitle title="Account Settings">
                <AccountSettings />
              </PageTitle>
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
