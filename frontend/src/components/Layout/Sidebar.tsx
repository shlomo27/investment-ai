import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAppSelector } from "../../store";

interface NavItem {
  to: string;
  icon: string;
  label_he: string;
  label_en: string;
}

const ADMIN_ITEMS: NavItem[] = [
  { to: "/fund", icon: "🎯", label_he: "לוח ניהול", label_en: "Fund Dashboard" },
  { to: "/recommendations", icon: "🤖", label_he: "סיגנלים AI", label_en: "AI Signals" },
];

const CLIENT_ITEMS: NavItem[] = [
  { to: "/master-list", icon: "📋", label_he: "רשימת מאסטר", label_en: "Master List" },
  { to: "/dashboard", icon: "🏠", label_he: "סקירה כללית", label_en: "Overview" },
  { to: "/portfolio", icon: "📊", label_he: "תיק השקעות", label_en: "Portfolio" },
  { to: "/performance", icon: "📈", label_he: "ביצועי AI", label_en: "AI Performance" },
  { to: "/orders", icon: "📑", label_he: "עסקאות", label_en: "Orders" },
  { to: "/watchlist", icon: "👁", label_he: "מעקב", label_en: "Watchlist" },
];

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAppSelector((state) => state.auth);
  const { unreadCount } = useAppSelector((state) => state.notifications);
  const isHe = user?.preferred_language === "he";
  const isAdmin = user?.is_admin ?? false;

  const renderItem = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-sm ${
          isActive
            ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
            : "text-gray-400 hover:text-white hover:bg-gray-800"
        }`
      }
    >
      <span className="text-lg">{item.icon}</span>
      <span className="hidden md:block">{isHe ? item.label_he : item.label_en}</span>
      {item.to === "/recommendations" && unreadCount > 0 && (
        <span className="ml-auto bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center hidden md:flex">
          {unreadCount > 9 ? "9+" : unreadCount}
        </span>
      )}
    </NavLink>
  );

  return (
    <aside className="w-16 md:w-56 bg-gray-900 border-r border-gray-800 flex flex-col min-h-screen">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <span className="font-bold text-sm hidden md:block">Investment AI</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {/* Admin section */}
        {isAdmin && (
          <>
            <p className="hidden md:block text-xs text-gray-600 uppercase tracking-wider px-3 pb-1 pt-2">
              {isHe ? "ניהול" : "Admin"}
            </p>
            {ADMIN_ITEMS.map(renderItem)}
            <div className="border-t border-gray-800 my-2" />
          </>
        )}

        {/* Client section */}
        <p className="hidden md:block text-xs text-gray-600 uppercase tracking-wider px-3 pb-1 pt-2">
          {isHe ? "לקוח" : "Client"}
        </p>
        {CLIENT_ITEMS.map(renderItem)}
      </nav>

      {/* User Info + Settings */}
      <div className="p-3 border-t border-gray-800">
        <button
          onClick={() => navigate("/settings")}
          className="w-full flex items-center gap-3 px-2 py-1.5 rounded-xl hover:bg-gray-800 transition-colors text-start"
        >
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isAdmin ? "bg-yellow-600/50" : "bg-blue-600/50"}`}>
            {user?.full_name?.[0]?.toUpperCase()}
          </div>
          <div className="hidden md:block flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{user?.full_name}</p>
            <p className="text-xs text-gray-500">{isAdmin ? (isHe ? "מנהל" : "Admin") : (isHe ? "הגדרות" : "Settings")}</p>
          </div>
          <span className="hidden md:block text-gray-600 text-xs ml-auto">⚙️</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
