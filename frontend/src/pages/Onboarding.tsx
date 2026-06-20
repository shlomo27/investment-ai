import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "../store";
import { completeOnboarding } from "../store/slices/authSlice";
import { RiskProfile } from "../types";

const STEPS = ["welcome", "notifications"];

const Onboarding: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { user, isLoading, error } = useAppSelector((state) => state.auth);

  const [step, setStep] = useState(0);
  const [notifications, setNotifications] = useState({
    email: true,
    sms: false,
    push: false,
  });

  const handleComplete = async () => {
    const result = await dispatch(
      completeOnboarding({
        risk_profile: RiskProfile.AGGRESSIVE,
        risk_score: 85,
        investment_type: "BOTH",
        allows_volatile: true,
        allows_leveraged: true,
        allows_short: true,
        notification_email: notifications.email,
        notification_sms: notifications.sms,
        notification_push: notifications.push,
      })
    );
    if (completeOnboarding.fulfilled.match(result)) {
      navigate("/fund");
    }
  };

  const features = [
    { icon: "📊", label: "Long/Short Equity Strategy" },
    { icon: "🤖", label: "4-Agent AI Pipeline" },
    { icon: "🔍", label: "S&P 900 Universe Screening" },
    { icon: "⚡", label: "Real-Time Signal Alerts" },
    { icon: "📈", label: "Fundamental + Technical Analysis" },
    { icon: "🛡️", label: "Senior Committee Risk Review" },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-lg">
        {/* Progress */}
        <div className="mb-8">
          <div className="flex gap-2 mb-3">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1 flex-1 rounded-full transition-colors ${
                  i <= step ? "bg-blue-500" : "bg-gray-700"
                }`}
              />
            ))}
          </div>
          <p className="text-sm text-gray-400">
            Step {step + 1} of {STEPS.length}
          </p>
        </div>

        {/* ── Step 0: Welcome ──────────────────────────────────── */}
        {step === 0 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-xl">
                🎯
              </div>
              <div>
                <h2 className="text-xl font-bold">
                  Welcome, {user?.full_name}
                </h2>
                <p className="text-sm text-gray-400">
                  Investment AI — Hedge Fund Platform
                </p>
              </div>
            </div>

            <p className="text-gray-400 text-sm mt-4 mb-6 leading-relaxed">
              You now have access to the full AI-powered Long/Short equity
              research platform. The system continuously scans the S&P 900
              universe and surfaces actionable signals for your review.
            </p>

            <div className="grid grid-cols-2 gap-3 mb-8">
              {features.map((f) => (
                <div
                  key={f.label}
                  className="bg-gray-800 rounded-xl p-3 flex items-center gap-3"
                >
                  <span className="text-lg flex-shrink-0">{f.icon}</span>
                  <p className="text-xs text-gray-300 font-medium leading-snug">
                    {f.label}
                  </p>
                </div>
              ))}
            </div>

            <button
              onClick={() => setStep(1)}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-xl py-3 font-medium transition-colors"
            >
              Continue
            </button>
          </div>
        )}

        {/* ── Step 1: Notifications ─────────────────────────────── */}
        {step === 1 && (
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-xl font-bold mb-1">Alert Preferences</h2>
            <p className="text-gray-400 text-sm mb-6">
              Choose how you want to receive trade signals and system
              notifications.
            </p>

            <div className="space-y-4 mb-8">
              {[
                {
                  key: "email" as const,
                  icon: "✉️",
                  label: "Email",
                  desc: "Trade signals and daily summaries",
                },
                {
                  key: "sms" as const,
                  icon: "💬",
                  label: "SMS",
                  desc: "Urgent alerts only (high-conviction signals)",
                },
                {
                  key: "push" as const,
                  icon: "🔔",
                  label: "Push",
                  desc: "Mobile push notifications",
                },
              ].map((ch) => (
                <button
                  key={ch.key}
                  onClick={() =>
                    setNotifications({
                      ...notifications,
                      [ch.key]: !notifications[ch.key],
                    })
                  }
                  className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                    notifications[ch.key]
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <span className="text-xl">{ch.icon}</span>
                  <div className="flex-1">
                    <p className="font-medium">{ch.label}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{ch.desc}</p>
                  </div>
                  <div
                    className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                      notifications[ch.key]
                        ? "bg-blue-600 border-blue-600"
                        : "border-gray-600"
                    }`}
                  >
                    {notifications[ch.key] && (
                      <span className="text-white text-xs">✓</span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setStep(0)}
                className="flex-1 border border-gray-700 rounded-xl py-3 text-gray-400 hover:border-gray-600 transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleComplete}
                disabled={isLoading}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-xl py-3 font-medium transition-colors"
              >
                {isLoading ? "Setting up..." : "Launch Platform"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Onboarding;
