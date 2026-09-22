/**
 * A sort picker that opens a list, instead of cycling on each tap.
 *
 * The button used to advance through the options one press at a time, so
 * reaching the third option meant pressing twice and guessing what came next.
 * With more than three options that stops being usable at all.
 *
 * On a phone it opens as a bottom sheet — thumb reach, and consistent with
 * the navigation's "More" sheet. On desktop it anchors under the button.
 */
import React, { useEffect, useRef, useState } from "react";
import { useT } from "../i18n/t";

export type SortOption<K extends string> = {
  key: K;
  label: string;
  /** One line under the label saying what the order actually means. */
  hint?: string;
};

type Props<K extends string> = {
  options: SortOption<K>[];
  value: K;
  onChange: (key: K) => void;
  isHe: boolean;
  /** Compact label for the closed button. */
  shortLabel: string;
};

function SortMenu<K extends string>({
  options,
  value,
  onChange,
  isHe,
  shortLabel,
}: Props<K>) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape. Without this the menu stays open
  // behind whatever the user taps next, and on a phone it covers the list
  // they were trying to read.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = options.find((o) => o.key === value);

  const item = (o: SortOption<K>) => (
    <button
      key={o.key}
      onClick={() => {
        onChange(o.key);
        setOpen(false);
      }}
      className={`w-full text-start px-4 py-3 md:py-2.5 flex items-start gap-2 transition-colors ${
        o.key === value
          ? "bg-blue-600/15 text-blue-300"
          : "text-gray-300 hover:bg-gray-800"
      }`}
    >
      <span className="w-4 shrink-0 text-center leading-5">
        {o.key === value ? "✓" : ""}
      </span>
      <span className="min-w-0">
        <span className="block text-sm leading-5">{o.label}</span>
        {o.hint && (
          <span className="block text-[11px] text-gray-500 leading-4 mt-0.5">
            {o.hint}
          </span>
        )}
      </span>
    </button>
  );

  return (
    <div ref={wrapRef} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${
          open
            ? "bg-gray-800 text-white border-gray-600"
            : "bg-gray-900 text-gray-300 border-gray-800 hover:border-gray-600"
        }`}
      >
        {/* The caret is the affordance: it says a list opens, where a bare
            arrow read as "press to change to something unspecified". */}
        <span className="md:hidden">↕ {shortLabel} ▾</span>
        <span className="hidden md:inline">
          ↕ {t("Sort: ", "מיון: ")}
          {current?.label ?? shortLabel} ▾
        </span>
      </button>

      {open && (
        <>
          {/* Phone: bottom sheet. */}
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/60"
            onClick={() => setOpen(false)}
          >
            <div
              dir={isHe ? "rtl" : "ltr"}
              className="absolute bottom-0 inset-x-0 bg-gray-900 border-t border-gray-800 rounded-t-2xl py-2 max-h-[70vh] overflow-y-auto"
              style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 4.5rem)" }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-10 h-1 bg-gray-700 rounded-full mx-auto my-2" />
              <p className="px-4 pb-2 text-xs text-gray-500">
                {t("Sort by", "מיין לפי")}
              </p>
              {options.map(item)}
            </div>
          </div>

          {/* Desktop: anchored dropdown. */}
          <div
            dir={isHe ? "rtl" : "ltr"}
            role="listbox"
            className="hidden md:block absolute z-40 mt-1 end-0 w-64 bg-gray-900 border border-gray-800 rounded-xl shadow-xl overflow-hidden py-1"
          >
            {options.map(item)}
          </div>
        </>
      )}
    </div>
  );
}

export default SortMenu;
