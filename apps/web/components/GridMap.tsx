"use client";
import { useMemo } from "react";
import NodeBubble from "./NodeBubble";
import LineSegment from "./LineSegment";
import AssetIcon from "./AssetIcon";
import type {
  GridNode,
  GridLine,
  GeneratorAsset,
  HourResult,
  Hub,
} from "@/lib/types";

interface GridMapProps {
  nodes: GridNode[];
  lines: GridLine[];
  generators: GeneratorAsset[];
  hub: Hub;
  hourResult: HourResult;
  selectedId: string | null;
  onSelectNode: (id: string) => void;
  onSelectLine: (id: string) => void;
  onSelectAsset: (id: string) => void;
}

// Map viewport: 700 x 480 SVG units (padded)
const SVG_W = 700;
const SVG_H = 480;
const PADDING = 60;

// Scale the raw node coordinates (from JSON) to fit the SVG viewport
function scaleNodes(nodes: GridNode[]) {
  if (nodes.length === 0) return {};
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const scaleX = (SVG_W - PADDING * 2) / rangeX;
  const scaleY = (SVG_H - PADDING * 2) / rangeY;

  const out: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    out[n.id] = {
      x: PADDING + (n.x - minX) * scaleX,
      y: PADDING + (n.y - minY) * scaleY,
    };
  }
  return out;
}

export default function GridMap({
  nodes,
  lines,
  generators,
  hub,
  hourResult,
  selectedId,
  onSelectNode,
  onSelectLine,
  onSelectAsset,
}: GridMapProps) {
  const coords = useMemo(() => scaleNodes(nodes), [nodes]);
  const hubPrice = hourResult.hub_price;

  // Group generators by node
  const gensByNode = useMemo(() => {
    const out: Record<string, GeneratorAsset[]> = {};
    for (const g of generators) {
      out[g.node_id] = out[g.node_id] || [];
      out[g.node_id].push(g);
    }
    return out;
  }, [generators]);

  return (
    <svg
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      width="100%"
      height="100%"
      style={{ maxHeight: "100%" }}
    >
      <defs>
        <filter id="nodeShadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.15" />
        </filter>
        <filter id="assetShadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.1" />
        </filter>
        {/* Subtle grid background */}
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path
            d="M 40 0 L 0 0 0 40"
            fill="none"
            stroke="#f0f4f8"
            strokeWidth="0.5"
          />
        </pattern>
      </defs>

      {/* Background */}
      <rect width={SVG_W} height={SVG_H} fill="#fafbfc" rx={12} />
      <rect width={SVG_W} height={SVG_H} fill="url(#grid)" rx={12} />

      {/* Zone labels */}
      <text x={80} y={30} fontSize={10} fill="#cbd5e1" fontWeight="600" fontFamily="system-ui">
        WEST ZONE
      </text>
      <text x={310} y={30} fontSize={10} fill="#cbd5e1" fontWeight="600" fontFamily="system-ui">
        CENTRAL
      </text>
      <text x={540} y={30} fontSize={10} fill="#cbd5e1" fontWeight="600" fontFamily="system-ui">
        EAST ZONE
      </text>

      {/* Lines (drawn first, under nodes) */}
      {lines.map((line) => {
        if (line.outage) return null;
        const from = coords[line.from_node_id];
        const to = coords[line.to_node_id];
        if (!from || !to) return null;

        return (
          <LineSegment
            key={line.id}
            lineId={line.id}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            flowMw={hourResult.line_flow_mw[line.id] ?? 0}
            capacityMw={line.capacity_mw}
            loadingPct={hourResult.line_loading_pct[line.id] ?? 0}
            isBinding={hourResult.binding_lines.includes(line.id)}
            isSelected={selectedId === line.id}
            onClick={() => onSelectLine(line.id)}
          />
        );
      })}

      {/* Asset icons (offset from node center) */}
      {nodes.map((node) => {
        const pos = coords[node.id];
        if (!pos) return null;
        const gens = gensByNode[node.id] || [];
        return gens.map((gen, i) => {
          const offset = gens.length === 1 ? 0 : (i - (gens.length - 1) / 2) * 50;
          return (
            <AssetIcon
              key={gen.id}
              type={gen.type}
              x={pos.x + offset}
              y={pos.y - 72}
              dispatchMw={hourResult.dispatch_by_asset[gen.id] ?? 0}
              availableMw={hourResult.available_by_asset[gen.id] ?? 0}
              isSelected={selectedId === gen.id}
              onClick={() => onSelectAsset(gen.id)}
            />
          );
        });
      })}

      {/* Nodes */}
      {nodes.map((node) => {
        const pos = coords[node.id];
        if (!pos) return null;
        const isHubNode = hub.constituent_node_ids.includes(node.id);
        const isHubCenter = node.id === "N3"; // HubPoint specifically

        return (
          <NodeBubble
            key={node.id}
            nodeId={node.id}
            name={node.name}
            x={pos.x}
            y={pos.y}
            lmp={hourResult.lmp_by_node[node.id] ?? 0}
            hubPrice={hubPrice}
            isSelected={selectedId === node.id}
            isHub={isHubCenter}
            onClick={() => onSelectNode(node.id)}
          />
        );
      })}

      {/* Hour watermark */}
      <text
        x={SVG_W - 12}
        y={SVG_H - 10}
        textAnchor="end"
        fontSize={9}
        fill="#e2e8f0"
        fontFamily="system-ui"
      >
        Hour {hourResult.hour.toString().padStart(2, "0")}:00
      </text>
    </svg>
  );
}
