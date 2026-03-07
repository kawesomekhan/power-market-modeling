"use client";

interface AssetIconProps {
  type: string;
  x: number;
  y: number;
  dispatchMw: number;
  availableMw: number;
  isSelected: boolean;
  onClick: () => void;
}

const ASSET_EMOJI: Record<string, string> = {
  solar: "☀️",
  wind: "💨",
  gas_cc: "⚡",
  gas_peaker: "🔥",
  battery: "🔋",
  hydro: "💧",
};

const ASSET_LABEL: Record<string, string> = {
  solar: "Solar",
  wind: "Wind",
  gas_cc: "CC Gas",
  gas_peaker: "Peaker",
  battery: "Battery",
  hydro: "Hydro",
};

export default function AssetIcon({
  type,
  x,
  y,
  dispatchMw,
  availableMw,
  isSelected,
  onClick,
}: AssetIconProps) {
  const emoji = ASSET_EMOJI[type] || "⚙️";
  const label = ASSET_LABEL[type] || type;
  const utilization = availableMw > 0 ? dispatchMw / availableMw : 0;

  // Color based on utilization
  const barColor =
    utilization > 0.95 ? "#22c55e" :
    utilization > 0.5 ? "#86efac" :
    utilization > 0.1 ? "#fbbf24" : "#d1d5db";

  const barWidth = 32;
  const barHeight = 4;

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={onClick}
      style={{ cursor: "pointer" }}
    >
      {/* Background pill */}
      <rect
        x={-22}
        y={-18}
        width={44}
        height={36}
        rx={8}
        fill={isSelected ? "#ede9fe" : "#f8fafc"}
        stroke={isSelected ? "#6366f1" : "#e2e8f0"}
        strokeWidth={isSelected ? 2 : 1}
        filter="url(#assetShadow)"
      />

      {/* Emoji */}
      <text y={2} textAnchor="middle" fontSize={14}>
        {emoji}
      </text>

      {/* Dispatch bar */}
      <g transform={`translate(${-barWidth / 2}, 10)`}>
        <rect width={barWidth} height={barHeight} rx={2} fill="#e2e8f0" />
        <rect
          width={barWidth * utilization}
          height={barHeight}
          rx={2}
          fill={barColor}
        />
      </g>

      {/* MW label */}
      <text
        y={-8}
        textAnchor="middle"
        fontSize={8}
        fill="#6b7280"
        fontFamily="system-ui, sans-serif"
      >
        {Math.round(dispatchMw)}MW
      </text>
    </g>
  );
}
