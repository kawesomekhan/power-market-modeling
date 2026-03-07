"use client";
import { motion } from "framer-motion";
import { nodeColor } from "@/lib/types";

interface NodeBubbleProps {
  nodeId: string;
  name: string;
  x: number;
  y: number;
  lmp: number;
  hubPrice: number;
  isSelected: boolean;
  isHub: boolean;
  onClick: () => void;
}

const GEN_ICONS: Record<string, string> = {
  solar: "☀️",
  wind: "💨",
  gas_cc: "⚡",
  gas_peaker: "🔥",
};

export default function NodeBubble({
  nodeId,
  name,
  x,
  y,
  lmp,
  hubPrice,
  isSelected,
  isHub,
  onClick,
}: NodeBubbleProps) {
  const color = nodeColor(lmp, hubPrice);
  const basis = lmp - hubPrice;
  const shortName = name.length > 9 ? name.slice(0, 9) : name;

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={onClick}
      style={{ cursor: "pointer" }}
    >
      {/* Selection ring */}
      {isSelected && (
        <motion.circle
          r={34}
          fill="none"
          stroke="#6366f1"
          strokeWidth={3}
          strokeDasharray="6 3"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 8, ease: "linear" }}
          style={{ transformOrigin: "0 0" }}
        />
      )}

      {/* Main node circle */}
      <motion.circle
        r={26}
        fill={color}
        stroke={isSelected ? "#6366f1" : "#fff"}
        strokeWidth={isSelected ? 3 : 2}
        filter="url(#nodeShadow)"
        animate={{ scale: isSelected ? 1.1 : 1 }}
        transition={{ type: "spring", stiffness: 200 }}
      />

      {/* Hub marker */}
      {isHub && (
        <circle r={29} fill="none" stroke="#a78bfa" strokeWidth={2} strokeDasharray="4 2" />
      )}

      {/* Price label */}
      <text
        y={-2}
        textAnchor="middle"
        fontSize={12}
        fontWeight="700"
        fill={lmp < 5 ? "#1d4ed8" : "#1a1a1a"}
        fontFamily="system-ui, sans-serif"
      >
        ${Math.round(lmp)}
      </text>

      {/* Basis label */}
      {Math.abs(basis) > 2 && (
        <text
          y={11}
          textAnchor="middle"
          fontSize={9}
          fill={basis < 0 ? "#1d4ed8" : "#b45309"}
          fontFamily="system-ui, sans-serif"
          fontWeight="600"
        >
          {basis > 0 ? "+" : ""}{Math.round(basis)} basis
        </text>
      )}

      {/* Node name */}
      <text
        y={40}
        textAnchor="middle"
        fontSize={10}
        fill="#374151"
        fontWeight="600"
        fontFamily="system-ui, sans-serif"
      >
        {shortName}
      </text>

      {/* Hub label */}
      {isHub && (
        <text
          y={51}
          textAnchor="middle"
          fontSize={8}
          fill="#7c3aed"
          fontFamily="system-ui, sans-serif"
        >
          HUB ${Math.round(hubPrice)}
        </text>
      )}
    </g>
  );
}
