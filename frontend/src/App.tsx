import React, { useEffect } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { useAppDispatch, useAppSelector } from "./store";
import { fetchCurrentUser } from "./store/slices/authSlice";
import { fetchUnreadCount } from "./store/slices/notificationsSlice";

// Pages
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Dashboard from "./pages/Dashboard";
import FundDashboard from "./pages/FundDashboard";
import Portfolio from "./pages/Portfolio";
import Recommendations from "./pages/Recommendations";
import ResearchReport from "./pages/ResearchReport";
import TechnicalAnalysisPage from "./pages/TechnicalAnalysisPage";
import Orders from "./pages/Orders";
import Watchlist from "./pages/Watchlist";
import MasterList from "./pages/MasterList";

// Layout
import Navbar from "./components/Layout/Navbar";
import Sidebar from "./components/Layout/Sidebar";

// Services
import { initPushNotifications } from "./services/pushNotifications";
import { authApi } from "./api/client";

// ─── Protected Routes ───────────────────────────────────────────────────────────

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAppSelector((state) => state.auth);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading, user } = useAppSelector((state) => state.auth);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!user?.is_admin) return <Navigate to="/master-list" replace />;
  return <>{children}</>;
};

// ─── Main Layout ────────────────────────────────────────────────────────────────

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex">
      <Sidebar />
      <div className="flex-1 flex flex-col min-h-screen">
        <Navbar />
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
};

// ─── App Component ──────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const dispatch = useAppDispatch();
  const { isAuthenticated, user } = useAppSelector((state) => state.auth);

  useEffect(() => {
    if (localStorage.getItem("access_token")) {
      dispatch(fetchCurrentUser());
    }
  }, [dispatch]);

  useEffect(() => {
    if (isAuthenticated) {
      dispatch(fetchUnreadCount());
      const interval = setInterval(() => {
        dispatch(fetchUnreadCount());
      }, 60000);

      // Initialize push notifications (silently skipped if Firebase not configured)
      initPushNotifications(async (token) => {
        await authApi.updateProfile({ push_token: token });
      }).catch(() => {});

      return () => clearInterval(interval);
    }
  }, [isAuthenticated, dispatch]);

  return (
    <Router>
      <Routes>
        {/* Public routes */}
        <Route
          path="/login"
          element={
            isAuthenticated ? <Navigate to="/fund" replace /> : <Login />
          }
        />

        {/* Onboarding - authenticated but not yet onboarded */}
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              {user?.is_onboarded ? (
                <Navigate to={user?.is_admin ? "/fund" : "/master-list"} replace />
              ) : (
                <Onboarding />
              )}
            </ProtectedRoute>
          }
        />

        {/* Protected routes with layout */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              {user && !user.is_onboarded ? (
                <Navigate to="/onboarding" replace />
              ) : (
                <AppLayout>
                  <Dashboard />
                </AppLayout>
              )}
            </ProtectedRoute>
          }
        />
        <Route
          path="/portfolio"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Portfolio />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/recommendations"
          element={
            <AdminRoute>
              <AppLayout>
                <Recommendations />
              </AppLayout>
            </AdminRoute>
          }
        />
        <Route
          path="/orders"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Orders />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/watchlist"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Watchlist />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/fund"
          element={
            <AdminRoute>
              <AppLayout>
                <FundDashboard />
              </AppLayout>
            </AdminRoute>
          }
        />
        <Route
          path="/research/:id"
          element={
            <ProtectedRoute>
              <AppLayout>
                <ResearchReport />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/technical/:id"
          element={
            <ProtectedRoute>
              <AppLayout>
                <TechnicalAnalysisPage />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/master-list"
          element={
            <ProtectedRoute>
              <AppLayout>
                <MasterList />
              </AppLayout>
            </ProtectedRoute>
          }
        />

        {/* Catch-all: admin → fund dashboard, client → master list */}
        <Route
          path="/"
          element={
            !isAuthenticated
              ? <Navigate to="/login" replace />
              : user?.is_admin
              ? <Navigate to="/fund" replace />
              : <Navigate to="/master-list" replace />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
};

export default App;
