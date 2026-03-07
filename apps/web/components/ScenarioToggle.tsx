"use client";
import type { Variant } from "@/lib/types";
import { VARIANT_LABELS, VARIANT_DESCRIPTIONS } from "@/lib/types";

interface ScenarioToggleProps {
  current: Variant;
  onChange: (v: Variant) => void;
  isLoading: boolean;
}

const VARIANTS: Variant[] = ["base", "more_solar", "bigger_line", "hot_evening"];

export default function ScenarioToggle({
  current,
  onChange,
  isLoading,
}: ScenarioToggleProps) {
  return (
    <div className="flex gap-2 flex-wrap">
      {VARIANTS.map((v) => (
        <button
          key={v}
          disabled={isLoading}
          onClick={() => onChange(v)}
          title={VARIANT_DESCRIPTIONS[v]}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
            current === v
              ? "bg-indigo-600 text-white shadow-sm"
              : "bg-white text-slate-600 border border-slate-200 hover:border-indigo-300 hover:text-indigo-600"
          } ${isLoading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        >
          {isLoading && current === v ? "…" : VARIANT_LABELS[v]}
        </button>
      ))}
    </div>
  );
}
