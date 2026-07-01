import React, { useState } from "react";
import { authApi } from "../api/client";

interface Props {
  currentUser: any;
  isHebrew?: boolean;
  onClose: () => void;
  onSaved: (user: any) => void;
}

const AGE_GROUPS = ["18-25", "26-35", "36-50", "50+"];
const HORIZONS = [
  { months: 3, label_he: "קצר מועד (3 חודשים)", label_en: "Short term (3M)" },
  { months: 6, label_he: "חצי שנה", label_en: "6 Months" },
  { months: 12, label_he: "שנה", label_en: "1 Year" },
  { months: 36, label_he: "3 שנים", label_en: "3 Years" },
  { months: 60, label_he: "5 שנים", label_en: "5 Years" },
  { months: 120, label_he: "10+ שנים", label_en: "10+ Years" },
];
const RISK_PROFILES = [
  { value: "CONSERVATIVE", label_he: "שמרני 🛡️", label_en: "Conservative 🛡️" },
  { value: "PASSIVE", label_he: "מאוזן ⚖️", label_en: "Balanced ⚖️" },
  { value: "AGGRESSIVE", label_he: "אגרסיבי 🚀", label_en: "Aggressive 🚀" },
  { value: "HYBRID", label_he: "היברידי 🔄", label_en: "Hybrid 🔄" },
];

export default function RiskProfileModal({ currentUser, isHebrew = true, onClose, onSaved }: Props) {
  const [ageGroup, setAgeGroup] = useState<string>(currentUser?.age_group || "");
  const [horizonMonths, setHorizonMonths] = useState<number>(currentUser?.investment_horizon_months || 12);
  const [riskProfile, setRiskProfile] = useState<string>(currentUser?.risk_profile || "PASSIVE");
  const [allowsShort, setAllowsShort] = useState<boolean>(currentUser?.allows_short || false);
  const [allowsVolatile, setAllowsVolatile] = useState<boolean>(currentUser?.allows_volatile || false);
  const [saving, setSaving] = useState(false);

  const t = (he: string, en: string) => (isHebrew ? he : en);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await authApi.updateProfile({
        age_group: ageGroup || undefined,
        investment_horizon_months: horizonMonths,
        risk_profile: riskProfile as any,
        allows_short: allowsShort,
        allows_volatile: allowsVolatile,
      });
      onSaved(updated);
      onClose();
    } catch (e: any) {
      alert(t("שגיאה בשמירה", "Failed to save"));
    } finally {
      setSaving(false);
    }
  };

  const overlay: React.CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000,
    display: "flex", alignItems: "center", justifyContent: "center",
  };
  const modal: React.CSSProperties = {
    background: "#0f172a", border: "1px solid #334155", borderRadius: 16,
    padding: 32, maxWidth: 500, width: "90%", maxHeight: "90vh", overflowY: "auto",
  };

  const section = (label: string) => (
    <div style={{ color: "#64748b", fontSize: 12, marginTop: 24, marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
  );

  const chip = (value: string, current: string, label: string, onClick: () => void) => (
    <button key={value} onClick={onClick} style={{
      padding: "8px 16px", borderRadius: 20, border: "none", cursor: "pointer", marginRight: 8, marginBottom: 8,
      background: current === value ? "#3b82f6" : "#1e293b",
      color: current === value ? "#fff" : "#94a3b8",
      fontWeight: current === value ? 600 : 400,
    }}>{label}</button>
  );

  return (
    <div style={overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={modal}>
        <h2 style={{ color: "#fff", marginTop: 0 }}>{t("פרופיל סיכון אישי", "Personal Risk Profile")}</h2>
        <p style={{ color: "#64748b", fontSize: 13, marginBottom: 0 }}>
          {t("פרטים אלה מאפשרים לניתוח AI להתאים את ההמלצות אישית עבורך.", "These details let the AI tailor its recommendations to your situation.")}
        </p>

        {section(t("קבוצת גיל", "Age Group"))}
        <div>{AGE_GROUPS.map(a => chip(a, ageGroup, a, () => setAgeGroup(a)))}</div>

        {section(t("אופק השקעה", "Investment Horizon"))}
        <div>
          {HORIZONS.map(h => chip(
            String(h.months), String(horizonMonths),
            isHebrew ? h.label_he : h.label_en,
            () => setHorizonMonths(h.months)
          ))}
        </div>

        {section(t("פרופיל סיכון", "Risk Profile"))}
        <div>
          {RISK_PROFILES.map(r => chip(r.value, riskProfile, isHebrew ? r.label_he : r.label_en, () => setRiskProfile(r.value)))}
        </div>

        {section(t("העדפות מסחר", "Trading Preferences"))}
        <div style={{ display: "flex", gap: 24 }}>
          {[
            { label: t("מניות תנודתיות", "Volatile stocks"), value: allowsVolatile, set: setAllowsVolatile },
            { label: t("פוזיציות שורט", "Short positions"), value: allowsShort, set: setAllowsShort },
          ].map(({ label, value, set }) => (
            <label key={label} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "#94a3b8" }}>
              <input type="checkbox" checked={value} onChange={e => set(e.target.checked)} />
              {label}
            </label>
          ))}
        </div>

        <div style={{ marginTop: 32, display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #334155", background: "transparent", color: "#94a3b8", cursor: "pointer" }}>
            {t("ביטול", "Cancel")}
          </button>
          <button onClick={save} disabled={saving} style={{ padding: "10px 24px", borderRadius: 8, border: "none", background: "#3b82f6", color: "#fff", cursor: "pointer", fontWeight: 600 }}>
            {saving ? t("שומר...", "Saving...") : t("שמור", "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}
