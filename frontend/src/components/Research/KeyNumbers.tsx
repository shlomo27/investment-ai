/**
 * The numbers, as numbers.
 *
 * The committee's written notes carry the figures that decide the case —
 * Debt/Equity, Net Debt/EBITDA, the FCF range, the implied comps — buried in
 * one long paragraph. Read on a phone that is a wall of text, and the reader
 * either scrolls past the numbers or misreads them.
 *
 * Two sources, kept strictly apart:
 *
 *   Structured   values the system actually computed and stores as numbers.
 *                Always correct.
 *   Extracted    ratios pulled out of the prose by pattern. Clearly labelled
 *                as read from the notes, and shown only on a tight match.
 *
 * On a financial screen a confidently-wrong number is worse than no number,
 * so extraction is deliberately conservative: it requires the metric name and
 * its value to sit next to each other, takes the first match only, and shows
 * nothing when unsure. The full text stays one tap below, always.
 */
import React from "react";
import { useT } from "../../i18n/t";

export type Row = { label: string; value: string; hint?: string };

/**
 * Ratios worth lifting out. Each pattern anchors on the metric name and takes
 * a number within a few characters of it — a loose search would happily
 * match an unrelated figure elsewhere in the sentence.
 *
 * The separator class excludes "-" on purpose. The notes write negatives
 * tight against the label ("ROA-3.5%"), and a class that accepts "-" as
 * separator consumes the sign and reports a LOSS as a GAIN — which is the
 * single worst thing this component could do.
 */
const PATTERNS: { label: string; re: RegExp; suffix?: string }[] = [
  { label: "P/E", re: /\bP\s*\/\s*E\b[^\d\n-]{0,18}(\d+(?:\.\d+)?)\s*x?/i, suffix: "x" },
  { label: "P/B", re: /\bP\s*\/\s*B\b[^\d\n-]{0,18}(\d+(?:\.\d+)?)\s*x?/i, suffix: "x" },
  { label: "Debt/Equity", re: /\bDebt\s*\/\s*Equity\b[^\d\n-]{0,18}(\d+(?:\.\d+)?)\s*%?/i, suffix: "%" },
  { label: "Net Debt/EBITDA", re: /\bNet\s*Debt\s*\/\s*EBITDA\b[^\d\n-]{0,18}(\d+(?:\.\d+)?)\s*x?/i, suffix: "x" },
  { label: "ROE", re: /\bROE\b[^\d\n-]{0,18}(-?\d+(?:\.\d+)?)\s*%?/i, suffix: "%" },
  { label: "ROA", re: /\bROA\b[^\d\n-]{0,6}(-?\d+(?:\.\d+)?)\s*%?/i, suffix: "%" },
  { label: "Current Ratio", re: /\bCurrent\s*Ratio\b[^\d\n-]{0,18}(\d+(?:\.\d+)?)/i },
];

/** Ratios found in free text. Returns [] rather than guessing. */
export function extractRatios(text?: string | null): Row[] {
  if (!text) return [];
  const out: Row[] = [];
  for (const { label, re, suffix } of PATTERNS) {
    const m = text.match(re);
    if (!m) continue;
    const n = m[1];
    // A ratio of 0 is almost always a mis-parse rather than a real reading.
    if (!n || Number(n) === 0) continue;
    out.push({ label, value: suffix ? `${n}${suffix}` : n });
  }
  return out;
}

type Props = {
  isHe: boolean;
  /** Computed by the system — always accurate. */
  structured: Row[];
  /** Read out of the committee notes — labelled as such. */
  extracted: Row[];
};

const Table: React.FC<{ rows: Row[] }> = ({ rows }) => (
  <div className="divide-y divide-gray-800/70">
    {rows.map((r) => (
      <div key={r.label} className="flex items-baseline gap-3 py-2">
        <span className="text-xs text-gray-500 flex-1 min-w-0">{r.label}</span>
        {/* .num isolates the value as LTR: without it a negative reading
            like "-3.5%" is reordered to "3.5%-" inside the Hebrew row and
            reads as a gain. */}
        <span className="num text-sm font-semibold text-gray-100 font-mono tabular-nums shrink-0">
          {r.value}
        </span>
      </div>
    ))}
  </div>
);

const KeyNumbers: React.FC<Props> = ({ isHe, structured, extracted }) => {
  const t = useT();
  if (structured.length === 0 && extracted.length === 0) return null;

  return (
    <div className="space-y-4">
      {structured.length > 0 && <Table rows={structured} />}

      {extracted.length > 0 && (
        <div>
          <p className="text-[11px] text-gray-600 mb-1">
            {/* Says where these came from. They are read from prose, not
                computed, and the reader is entitled to know the difference. */}
            {t("Ratios read from the committee notes — full text below", "יחסים שזוהו בהערות הוועדה — הנוסח המלא למטה")}
          </p>
          <Table rows={extracted} />
        </div>
      )}
    </div>
  );
};

export default KeyNumbers;
