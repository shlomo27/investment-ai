import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../../store";
import { logoutUser } from "../../store/slices/authSlice";

const Navbar: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user } = useAppSelector((state) => state.auth);
  const { unreadCount } = useAppSelector((state) => state.notifications);
  const isHe = user?.preferred_language === "he";

  const handleLogout = async () => {
    await dispatch(logoutUser());
    navigate("/login");
  };

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h2 className="font-semibold text-sm text-gray-300">
          {isHe ? "מערכת ייעוץ השקעות AI" : "Investment AI Platform"}
        </h2>
      </div>

      <div className="flex items-center gap-4">
        <Link
          to="/recommendations"
          className="relative p-2 text-gray-400 hover:text-white"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Link>

        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-sm font-bold">
            {user?.full_name?.[0]?.toUpperCase()}
          </div>
          <span className="text-sm text-gray-300 hidden md:block">{user?.full_name}</span>
        </div>

        <button
          onClick={handleLogout}
          className="text-gray-400 hover:text-white text-sm border border-gray-700 rounded-lg px-3 py-1.5"
        >
          {isHe ? "יציאה" : "Logout"}
        </button>
      </div>
    </header>
  );
};

export default Navbar;
