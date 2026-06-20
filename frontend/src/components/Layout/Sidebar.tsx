import React from "react";
import { NavLink } from "react-router-dom";
import { useAppSelector } from "../../store";

interface NavItem {
  to: string;
  icon: string;
  label_he: string;
  label_en: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/fund", icon: "🎯", label_he: "לוח קרן", label_en: "Fund Dashboard" },
  { to: "/dashboard", icon: "🏠", label_he: "לוח בקרה", label_en: "Overview" },
  { to: "/recommendations", icon: "💡", label_he: "סיגנלים", label_en: "Signals" },
  { to: "/portfolio", icon: "📊", label_he: "תיק השקעות", label_en: "Portfolio" },
  { to: "/orders", icon: "📋", label_he: "עסקאות", label_en: "Orders" },
  { to: "/watchlist", icon: "👁", label_he: "מעקב", label_en: "Watchlist" },
];

const Sidebar: React.FC = () => {
  const { user } = useAppSelector((state) => state.auth);
  const { unreadCount } = useAppSelector((state) => state.notifications);
  const isHe = user?.preferred_language === "he";

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
      <nav className="flex-1 py-4 px-2 space-y-1">
        {NAV_ITEMS.map((item) => (
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
        ))}
      </nav>

      {/* User Info */}
      <div className="p-3 border-t border-gray-800">
        <div className="flex items-center gap-3 px-2">
          <div className="w-7 h-7 bg-blue-600/50 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">
            {user?.full_name?.[0]?.toUpperCase()}
          </div>
          <div className="hidden md:block">
            <p className="text-xs font-medium truncate">{user?.full_name}</p>
            <p className="text-xs text-gray-500">{user?.risk_profile}</p>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
