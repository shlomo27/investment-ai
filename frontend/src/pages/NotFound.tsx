import React from "react";
import { useNavigate } from "react-router-dom";
import { useAppSelector } from "../store";

const NotFound: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAppSelector((s) => s.auth);
  const isHe = user?.preferred_language === "he";

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="flex flex-col items-center justify-center h-full py-24 text-center">
      <div className="text-6xl font-bold text-gray-700 mb-2">404</div>
      <p className="text-xl text-gray-400 mb-6">
        {isHe ? "הדף לא נמצא" : "Page not found"}
      </p>
      <button
        onClick={() => navigate(user?.is_admin ? "/fund" : "/master-list")}
        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-xl text-sm font-medium transition-colors"
      >
        {isHe ? "חזרה לדף הבית" : "Back to Home"}
      </button>
    </div>
  );
};

export default NotFound;
