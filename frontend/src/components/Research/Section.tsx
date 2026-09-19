/**
 * A collapsible report section.
 *
 * The research page opened every section at once, so the reader met several
 * screens of prose with no hierarchy — everything looked equally important
 * and there was no way to tell what could be skipped.
 *
 * Collapsed by default, with a one-line summary always visible, so the page
 * becomes a list of headings you can scan and open what you want. Nothing is
 * removed; it is one tap away.
 */
import React, { useState } from "react";

type Props = {
  title: string;
  /** Always visible, closed or open — the reason to open it, or not to. */
  summary?: string;
  /** A short value shown on the right of the header, e.g. "112%" or "בינוני". */
  badge?: React.ReactNode;
  /** Sections a reader should not have to go looking for. */
  defaultOpen?: boolean;
  /** Tints the left border — for risk sections, for example. */
  tone?: "default" | "warn" | "good";
  isHe: boolean;
  children: React.ReactNode;
};

const TONES: Record<string, string> = {
  default: "border-gray-800",
  warn: "border-red-900/40",
  good: "border-green-900/40",
};

const Section: React.FC<Props> = ({
  title,
  summary,
  badge,
  defaultOpen = false,
  tone = "default",
  isHe,
  children,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`bg-gray-900 rounded-2xl border ${TONES[tone]} overflow-hidden`}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full text-start px-5 py-4 flex items-start gap-3 hover:bg-gray-800/40 transition-colors"
      >
        <span
          className={`text-gray-500 text-xs mt-1 shrink-0 transition-transform ${
            open ? "rotate-90" : ""
          } ${isHe ? "rotate-180" : ""}`}
          aria-hidden
        >
          ▶
        </span>

        <span className="flex-1 min-w-0">
          <span className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-sm text-gray-200">{title}</span>
            {badge}
          </span>
          {/* Stays visible when collapsed: a heading alone does not tell you
              whether it is worth opening. */}
          {summary && (
            <span className="block text-xs text-gray-500 leading-relaxed mt-1">
              {summary}
            </span>
          )}
        </span>
      </button>

      {open && <div className="px-5 pb-5 pt-0">{children}</div>}
    </div>
  );
};

export default Section;
