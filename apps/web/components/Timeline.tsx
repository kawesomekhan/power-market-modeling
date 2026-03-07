"use client";
import { useEffect, useRef } from "react";
import type { HourResult } from "@/lib/types";

interface TimelineProps {
  hours: HourResult[];
  currentHour: number;
  isPlaying: boolean;
  onHourChange: (hour: number) => void;
  onPlayPause: () => void;
}

function hourLabel(h: number): string {
  const suffix = h < 12 ? "am" : "pm";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display}${suffix}`;
}

export default function Timeline({
  hours,
  currentHour,
  isPlaying,
  onHourChange,
  onPlayPause,
}: TimelineProps) {
  const hr = hours[currentHour];

  return (
    <div className="flex items-center gap-4 px-6 py-3 bg-white border-t border-slate-100 rounded-b-2xl">
      {/* Play/Pause */}
      <button
        onClick={onPlayPause}
        className="w-10 h-10 rounded-full bg-indigo-500 hover:bg-indigo-600 text-white flex items-center justify-center shadow-sm transition-colors flex-shrink-0"
        title={isPlaying ? "Pause" : "Play"}
      >
        {isPlaying ? (
          <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
            <rect x="3" y="2" width="4" height="12" rx="1" />
            <rect x="9" y="2" width="4" height="12" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor">
            <path d="M3 2.5l10 5.5-10 5.5V2.5z" />
          </svg>
        )}
      </button>

      {/* Hour display */}
      <div className="text-sm font-semibold text-slate-600 w-24 flex-shrink-0">
        <div>{hourLabel(currentHour)}</div>
        <div className="text-xs font-normal text-slate-400">
          Hub ${Math.round(hr?.hub_price ?? 0)}/MWh
        </div>
      </div>

      {/* Slider + hour ticks */}
      <div className="flex-1 relative">
        {/* Price sparkline behind slider */}
        <svg
          width="100%"
          height="28"
          viewBox={`0 0 24 28`}
          preserveAspectRatio="none"
          className="absolute inset-0 w-full opacity-30"
        >
          {hours.length > 0 && (
            <polyline
              points={hours
                .map((h, i) => {
                  const maxLmp = Math.max(...hours.map((hh) => hh.hub_price));
                  const y = 28 - (h.hub_price / maxLmp) * 22;
                  return `${i},${y}`;
                })
                .join(" ")}
              fill="none"
              stroke="#6366f1"
              strokeWidth="0.5"
            />
          )}
        </svg>

        <input
          type="range"
          min={0}
          max={23}
          value={currentHour}
          onChange={(e) => onHourChange(Number(e.target.value))}
          className="w-full h-2 appearance-none bg-slate-200 rounded-full cursor-pointer relative z-10
            [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:w-5
            [&::-webkit-slider-thumb]:h-5
            [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-indigo-500
            [&::-webkit-slider-thumb]:shadow-md
            [&::-webkit-slider-thumb]:cursor-pointer"
          style={{
            background: `linear-gradient(to right, #6366f1 ${(currentHour / 23) * 100}%, #e2e8f0 ${(currentHour / 23) * 100}%)`,
          }}
        />

        {/* Hour tick labels */}
        <div className="flex justify-between mt-1">
          {[0, 6, 12, 18, 23].map((h) => (
            <span
              key={h}
              className="text-xs text-slate-400"
              style={{
                position: "absolute",
                left: `${(h / 23) * 100}%`,
                transform: "translateX(-50%)",
                top: "18px",
              }}
            >
              {hourLabel(h)}
            </span>
          ))}
        </div>
      </div>

      {/* Binding indicator */}
      <div className="flex-shrink-0 w-20 text-right">
        {hr?.binding_lines.length > 0 ? (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-600 bg-red-50 px-2 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            Congested
          </span>
        ) : (
          <span className="text-xs text-slate-400">No congestion</span>
        )}
      </div>
    </div>
  );
}
