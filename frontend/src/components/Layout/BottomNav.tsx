/**
 * Bottom tab bar — the phone's navigation.
 *
 * The sidebar collapses to a 64px icon strip below `md`, which on a 390px
 * screen spends a sixth of the width on permanent chrome and still leaves
 * the icons unlabelled. Phones navigate from the bottom: it is where the
 * thumb is, it is what every native app does, and it frees the full width
 * for content.
 *
 * Five tabs is the practical maximum before labels stop fitting, so the
 * less-used destinations live behind "More" rather than being dropped —
 * a screen with no route to it is a screen that does not exist.
 *
 * Hidden at `md` and up, where the sidebar takes over.
 */
import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAppSelector, useAppDispatch } from "../../store";
import { logoutUser } from "../../store/slices/authSlice";

type Tab = { to: string; icon: string; he: string; en: string };

const TABS: Tab[] = [
  { to: "/recommendations", icon: "🤖", he: "סיגנלים", en: "Signals" },
  { to: "/watchlist", icon: "👁", he: "מעקב", en: "Watchlist" },
  { to: "/dashboard", icon: "🏠", he: "סקירה", en: "Overview" },
  { to: "/performance", icon: "📈", he: "ביצועים", en: "Results" },
];

const MORE: Tab[] = [
  { to: "/portfolio", icon: "📊", he: "תיק השקעות", en: "Portfolio" },
  { to: "/orders", icon: "📑", he: "עסקאות", en: "Orders" },
  { to: "/settings", icon: "⚙️", he: "הגדרות", en: "Settings" },
];

const BottomNav: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user } = useAppSelector((s) => s.auth);
  const { unreadCount } = useAppSelector((s) => s.notifications);
  const isHe = user?.preferred_language === "he";
  const isAdmin = user?.is_admin ?? false;

  const [moreOpen, setMoreOpen] = useState(false);

  const more: Tab[] = isAdmin
    ? [{ to: "/fund", icon: "🎯", he: "לוח ניהול", en: "Admin" }, ...MORE]
    : MORE;

  const handleLogout = async () => {
    setMoreOpen(false);
    await dispatch(logoutUser());
    navigate("/login");
  };

  return (
    <>
      {/* ── More sheet ── */}
      {moreOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/60"
          onClick={() => setMoreOpen(false)}
        >
          <div
            dir={isHe ? "rtl" : "ltr"}
            className="absolute bottom-0 inset-x-0 bg-gray-900 border-t border-gray-800 rounded-t-2xl p-3"
            // Clears the home indicator, plus room for the bar itself.
            style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 5rem)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-10 h-1 bg-gray-700 rounded-full mx-auto mb-3" />
            {more.map((t) => (
              <button
                key={t.to}
                onClick={() => {
                  setMoreOpen(false);
                  navigate(t.to);
                }}
                className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-gray-300 hover:bg-gray-800 text-start"
              >
                <span className="text-lg w-6 text-center">{t.icon}</span>
                <span className="text-sm">{isHe ? t.he : t.en}</span>
              </button>
            ))}
            <div className="border-t border-gray-800 my-2" />
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-red-400 hover:bg-gray-800 text-start"
            >
              <span className="text-lg w-6 text-center">⏻</span>
              <span className="text-sm">{isHe ? "יציאה" : "Log out"}</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Tab bar ── */}
      <nav
        dir={isHe ? "rtl" : "ltr"}
        className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-gray-900/95 backdrop-blur border-t border-gray-800 flex"
        // Without this the bar sits under the iPhone home indicator and the
        // last tab is unreachable.
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            onClick={() => setMoreOpen(false)}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[3.25rem] relative ${
                isActive ? "text-blue-400" : "text-gray-500"
              }`
            }
          >
            <span className="text-lg leading-none">{t.icon}</span>
            <span className="text-[10px] leading-none">{isHe ? t.he : t.en}</span>
            {t.to === "/recommendations" && unreadCount > 0 && (
              <span className="absolute top-1 end-[22%] bg-red-500 text-white text-[9px] rounded-full min-w-[15px] h-[15px] px-1 flex items-center justify-center">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </NavLink>
        ))}

        <button
          onClick={() => setMoreOpen((v) => !v)}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[3.25rem] ${
            moreOpen ? "text-blue-400" : "text-gray-500"
          }`}
        >
          <span className="text-lg leading-none">☰</span>
          <span className="text-[10px] leading-none">{isHe ? "עוד" : "More"}</span>
        </button>
      </nav>
    </>
  );
};

export default BottomNav;
