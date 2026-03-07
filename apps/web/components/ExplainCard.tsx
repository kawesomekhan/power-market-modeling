"use client";
import { motion, AnimatePresence } from "framer-motion";
import type { EventRecord } from "@/lib/types";

const EVENT_ICONS: Record<string, string> = {
  congestion: "🚧",
  curtailment: "✂️",
  peaker_dispatch: "🔥",
  negative_basis: "📉",
  price_spike: "⚡",
};

const EVENT_COLORS: Record<string, string> = {
  congestion: "border-red-200 bg-red-50",
  curtailment: "border-amber-200 bg-amber-50",
  peaker_dispatch: "border-orange-200 bg-orange-50",
  negative_basis: "border-blue-200 bg-blue-50",
  price_spike: "border-purple-200 bg-purple-50",
};

const EVENT_TITLES: Record<string, string> = {
  congestion: "Line Congestion",
  curtailment: "Generation Curtailed",
  peaker_dispatch: "Peaker Running",
  negative_basis: "Negative Basis",
  price_spike: "Price Spike",
};

interface ExplainCardProps {
  events: EventRecord[];
  hour: number;
}

export default function ExplainCard({ events, hour }: ExplainCardProps) {
  if (events.length === 0) {
    return (
      <div className="p-4 text-sm text-slate-400 italic">
        No notable events this hour. Grid is operating normally.
      </div>
    );
  }

  return (
    <div className="space-y-2 p-3">
      <AnimatePresence mode="wait">
        {events.map((ev, i) => (
          <motion.div
            key={`${hour}-${ev.type}-${i}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ delay: i * 0.05 }}
            className={`rounded-xl border px-3 py-2.5 ${EVENT_COLORS[ev.type] || "border-slate-200 bg-slate-50"}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-base">{EVENT_ICONS[ev.type] || "ℹ️"}</span>
              <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">
                {EVENT_TITLES[ev.type] || ev.type}
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{ev.message}</p>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
