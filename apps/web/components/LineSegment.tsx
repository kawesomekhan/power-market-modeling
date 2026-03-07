"use client";
import { motion } from "framer-motion";
import { lineColor } from "@/lib/types";

interface LineSegmentProps {
  lineId: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  flowMw: number;
  capacityMw: number;
  loadingPct: number;
  isBinding: boolean;
  isSelected: boolean;
  onClick: () => void;
}

export default function LineSegment({
  lineId,
  x1,
  y1,
  x2,
  y2,
  flowMw,
  capacityMw,
  loadingPct,
  isBinding,
  isSelected,
  onClick,
}: LineSegmentProps) {
  const color = lineColor(loadingPct, isBinding);
  const strokeWidth = isBinding ? 5 : isSelected ? 4 : 3;

  // Midpoint for click target and loading label
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;

  // Direction vector for flow arrow
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / len;
  const uy = dy / len;

  // Arrow at the midpoint (pointing from → to)
  const arrowLen = 10;
  const arrowSign = flowMw >= 0 ? 1 : -1;
  const ax = mx + arrowSign * ux * arrowLen;
  const ay = my + arrowSign * uy * arrowLen;
  const perpX = -uy * 5;
  const perpY = ux * 5;

  const arrowPoints = `${ax},${ay} ${mx - arrowSign * ux * 4 + perpX},${
    my - arrowSign * uy * 4 + perpY
  } ${mx - arrowSign * ux * 4 - perpX},${my - arrowSign * uy * 4 - perpY}`;

  return (
    <g onClick={onClick} style={{ cursor: "pointer" }}>
      {/* Invisible wider click target */}
      <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={18} stroke="transparent" />

      {/* Main line */}
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />

      {/* Binding pulse overlay */}
      {isBinding && (
        <motion.line
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke="#ef4444"
          strokeWidth={strokeWidth + 3}
          strokeLinecap="round"
          strokeOpacity={0}
          animate={{ strokeOpacity: [0, 0.6, 0] }}
          transition={{ repeat: Infinity, duration: 1.2, ease: "easeInOut" }}
        />
      )}

      {/* Flow direction arrow */}
      {Math.abs(flowMw) > 5 && (
        <polygon points={arrowPoints} fill={color} />
      )}

      {/* Loading label */}
      <g transform={`translate(${mx}, ${my})`}>
        <rect
          x={-22}
          y={-9}
          width={44}
          height={16}
          rx={4}
          fill="white"
          fillOpacity={0.9}
          stroke={color}
          strokeWidth={1}
        />
        <text
          textAnchor="middle"
          y={4}
          fontSize={9}
          fontWeight="600"
          fill={isBinding ? "#ef4444" : "#374151"}
          fontFamily="system-ui, sans-serif"
        >
          {Math.round(loadingPct * 100)}% · {Math.round(Math.abs(flowMw))}MW
        </text>
      </g>

      {/* Selection highlight */}
      {isSelected && (
        <line
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke="#6366f1"
          strokeWidth={strokeWidth + 4}
          strokeLinecap="round"
          strokeOpacity={0.3}
        />
      )}
    </g>
  );
}
