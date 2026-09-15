import React, { useEffect } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useNavigate,
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
import Settings from "./pages/Settings";
import Performance from "./pages/Performance";
import NotFound from "./pages/NotFound";
import ResetPassword from "./pages/ResetPassword";

// Layout
import Navbar from "./components/Layout/Navbar";
import Sidebar from "./components/Layout/Sidebar";
import BottomNav from "./components/Layout/BottomNav";

// Services
import { initPushNotifications } from "./services/pushNotifications";
import { pushNavigate, setPushNavigator } from "./services/pushNavigation";
import { initPurchases } from "./services/purchases";
import { authApi } from "./api/client";
import { useWebSocket } from "./hooks/useWebSocket";

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
  if (!user?.is_admin) return <Navigate to="/recommendations" replace />;
  return <>{children}</>;
};

// ─── Main Layout ────────────────────────────────────────────────────────────────

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    // min-w-0 on the content column: without it a wide child (a table, a
    // chart) forces the flex row wider than the screen and the whole page
    // scrolls sideways — which is what the phone screenshot showed.
    <div className="min-h-screen bg-gray-950 text-gray-100 flex overflow-x-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col min-h-screen">
        <Navbar />
        {/* pb-tabbar (index.css) clears the fixed tab bar and the home
            indicator on phones only — the last card would otherwise sit
            permanently underneath it. */}
        <main className="flex-1 min-w-0 p-3 md:p-6 overflow-x-hidden pb-tabbar">
          {children}
        </main>
      </div>
      <BottomNav />
    </div>
  );
};

// ─── App Component ──────────────────────────────────────────────────────────────

// ─── Push Deep Links ────────────────────────────────────────────────────────────

/**
 * Publishes the router's navigate() to the push layer. Lives inside <Router>
 * because useNavigate only exists there; App itself renders the Router and so
 * sits above it. Renders nothing.
 */
const PushNavigationBridge: React.FC = () => {
  const navigate = useNavigate();
  useEffect(() => {
    setPushNavigator((path) => navigate(path));
    return () => setPushNavigator(null);
  }, [navigate]);
  return null;
};

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
      // pushNavigate is passed so tapping an alert opens that stock's
      // research page rather than wherever the app was last left.
      initPushNotifications(async (token) => {
        await authApi.updateProfile({ push_token: token });
      }, pushNavigate).catch(() => {});

      return () => clearInterval(interval);
    }
  }, [isAuthenticated, dispatch]);

  // Bind the store SDK to this account. The billing webhook maps RevenueCat's
  // app_user_id back to a row by this id, so without the bind a purchase lands
  // on an anonymous RevenueCat identity that belongs to no account here and
  // nothing is ever granted.
  //
  // Its own effect, keyed on the id: `user` is still null for a moment after
  // isAuthenticated flips, so binding inside the effect above would skip the
  // call on every fresh login and only work on a later re-render.
  useEffect(() => {
    if (isAuthenticated && user?.id) {
      initPurchases(user.id).catch(() => {});
    }
  }, [isAuthenticated, user?.id]);

  // Real-time WebSocket connection for authenticated users
  useWebSocket(isAuthenticated ? user?.id : undefined, { enabled: isAuthenticated });

  return (
    <Router>
      <PushNavigationBridge />
      <Routes>
        {/* Public routes */}
        <Route
          path="/login"
          element={
            isAuthenticated ? <Navigate to="/fund" replace /> : <Login />
          }
        />

        {/* Password reset — public: the whole point is that the user cannot
            sign in, so this must sit outside ProtectedRoute. */}
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Onboarding - authenticated but not yet onboarded */}
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              {user?.is_onboarded ? (
                <Navigate to={user?.is_admin ? "/fund" : "/recommendations"} replace />
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
            <ProtectedRoute>
              <AppLayout>
                <Recommendations />
              </AppLayout>
            </ProtectedRoute>
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
          path="/settings"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Settings />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/performance"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Performance />
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
              : <Navigate to="/recommendations" replace />
          }
        />
        <Route
          path="*"
          element={
            <ProtectedRoute>
              <AppLayout>
                <NotFound />
              </AppLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </Router>
  );
};

export default App;
