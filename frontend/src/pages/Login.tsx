import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { loginUser, registerUser } from "../store/slices/authSlice";

const Login: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { isLoading, error } = useAppSelector((state) => state.auth);

  const [mode, setMode] = useState<"login" | "register">("login");
  const [lang, setLang] = useState<"he" | "en">("he");

  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
    full_name: "",
    phone: "",
    preferred_language: "he",
  });

  const isHe = lang === "he";

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await dispatch(loginUser(loginForm));
    if (loginUser.fulfilled.match(result)) {
      const user = result.payload;
      navigate(user.is_onboarded ? "/dashboard" : "/onboarding");
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await dispatch(registerUser(registerForm));
    if (registerUser.fulfilled.match(result)) {
      navigate("/onboarding");
    }
  };

  return (
    <div
      className="min-h-screen bg-gray-950 flex items-center justify-center px-4"
      dir={isHe ? "rtl" : "ltr"}
    >
      {/* Language toggle */}
      <button
        onClick={() => setLang(isHe ? "en" : "he")}
        className="fixed top-4 right-4 text-gray-400 hover:text-white text-sm border border-gray-700 rounded px-3 py-1"
      >
        {isHe ? "EN" : "עב"}
      </button>

      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">
            {isHe ? "מערכת ייעוץ השקעות AI" : "Investment AI Platform"}
          </h1>
          <p className="text-gray-400 mt-1 text-sm">
            {isHe ? "ניהול תיק השקעות מבוסס בינה מלאכותית" : "AI-powered portfolio management"}
          </p>
        </div>

        {/* Mode Tabs */}
        <div className="flex bg-gray-900 rounded-xl p-1 mb-6">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
              mode === "login"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {isHe ? "כניסה" : "Login"}
          </button>
          <button
            onClick={() => setMode("register")}
            className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
              mode === "register"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {isHe ? "הרשמה" : "Register"}
          </button>
        </div>

        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">
              {error}
            </div>
          )}

          {mode === "login" ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "דוא\"ל" : "Email"}
                </label>
                <input
                  type="email"
                  value={loginForm.email}
                  onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder={isHe ? "הזן דוא\"ל" : "Enter email"}
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "סיסמה" : "Password"}
                </label>
                <input
                  type="password"
                  value={loginForm.password}
                  onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder={isHe ? "הזן סיסמה" : "Enter password"}
                  required
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium transition-colors"
              >
                {isLoading ? (isHe ? "מתחבר..." : "Logging in...") : (isHe ? "כניסה" : "Login")}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "שם מלא" : "Full Name"}
                </label>
                <input
                  type="text"
                  value={registerForm.full_name}
                  onChange={(e) => setRegisterForm({ ...registerForm, full_name: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "דוא\"ל" : "Email"}
                </label>
                <input
                  type="email"
                  value={registerForm.email}
                  onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "טלפון" : "Phone"} <span className="text-red-400">*</span>
                </label>
                <input
                  type="tel"
                  value={registerForm.phone}
                  onChange={(e) => setRegisterForm({ ...registerForm, phone: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="+972-50-000-0000"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {isHe ? "נדרש לקבלת התראות על המלצות" : "Required for receiving recommendation alerts"}
                </p>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {isHe ? "סיסמה" : "Password"}
                </label>
                <input
                  type="password"
                  value={registerForm.password}
                  onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  minLength={8}
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  {isHe ? "לפחות 8 תווים כולל ספרה" : "At least 8 characters including a number"}
                </p>
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-3 font-medium transition-colors"
              >
                {isLoading ? (isHe ? "נרשם..." : "Registering...") : (isHe ? "הרשמה" : "Register")}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-gray-600 mt-4">
          {isHe
            ? "המערכת אינה מספקת ייעוץ השקעות מוסדר. כל ההחלטות הן באחריות המשתמש."
            : "This platform does not provide regulated investment advice. All decisions are the user's responsibility."}
        </p>
      </div>
    </div>
  );
};

export default Login;
