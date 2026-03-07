"use client";
import { motion, AnimatePresence } from "framer-motion";
import type {
  GridNode,
  GridLine,
  GeneratorAsset,
  HourResult,
  Hub,
  AssetPnL,
} from "@/lib/types";

interface InspectorPanelProps {
  selectedId: string | null;
  nodes: GridNode[];
  lines: GridLine[];
  generators: GeneratorAsset[];
  hub: Hub;
  hourResult: HourResult;
  dailyPnl: Record<string, AssetPnL>;
  onClose: () => void;
}

function Row({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex justify-between items-baseline py-1.5 border-b border-slate-100 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <div className="text-right">
        <span className="text-sm font-semibold text-slate-800">{value}</span>
        {sub && <div className="text-xs text-slate-400">{sub}</div>}
      </div>
    </div>
  );
}

function NodeInspector({
  node,
  hub,
  hr,
}: {
  node: GridNode;
  hub: Hub;
  hr: HourResult;
}) {
  const lmp = hr.lmp_by_node[node.id] ?? 0;
  const hubPrice = hr.hub_price;
  const basis = hr.basis_by_node[node.id] ?? 0;
  const congestion = hr.congestion_component_by_node[node.id] ?? 0;
  const demand = hr.demand_by_node[node.id] ?? 0;

  // Causal headline (shown first)
  let headline = "";
  const bindingExports = hr.binding_lines.filter((lid) => {
    // Crude check: binding line starts from this node
    return lid.includes(node.id.toLowerCase()) || lid.includes("N1") && node.id === "N1";
  });

  if (basis < -8 && hr.binding_lines.length > 0) {
    headline = `${node.name} is cheap — its export line is constrained.`;
  } else if (basis > 8) {
    headline = `${node.name} is expensive — it can't get enough cheap imports.`;
  } else if (lmp > 70) {
    headline = `${node.name} has high prices — expensive generation is setting the price.`;
  } else if (Math.abs(basis) < 3) {
    headline = `${node.name} is in balance with hub — no significant congestion.`;
  } else {
    headline = `${node.name} price: $${Math.round(lmp)}/MWh`;
  }

  const isHubNode = hub.constituent_node_ids.includes(node.id);

  return (
    <div>
      {/* Causal headline — shown FIRST */}
      <p className="text-sm text-slate-700 leading-relaxed mb-4 px-1">{headline}</p>

      {/* Numbers below */}
      <div className="space-y-0">
        <Row label="Node LMP" value={`$${lmp.toFixed(2)}/MWh`} />
        <Row
          label="Hub price"
          value={`$${hubPrice.toFixed(2)}/MWh`}
          sub={isHubNode ? "This node is a hub constituent" : undefined}
        />
        <Row
          label="Basis (node − hub)"
          value={`${basis >= 0 ? "+" : ""}$${basis.toFixed(2)}/MWh`}
          sub={basis < -5 ? "Negative — node earns less than hub" : basis > 5 ? "Positive — node earns more than hub" : "Near zero"}
        />
        <Row label="Energy component" value={`$${hr.energy_component.toFixed(2)}/MWh`} sub="= hub price" />
        <Row
          label="Congestion component"
          value={`${congestion >= 0 ? "+" : ""}$${congestion.toFixed(2)}/MWh`}
          sub={congestion < -5 ? "Export-constrained node" : congestion > 5 ? "Import-constrained node" : "No congestion penalty"}
        />
        <Row label="Local demand" value={`${demand.toFixed(0)} MW`} />
      </div>

      {hr.binding_lines.length > 0 && (
        <div className="mt-3 px-3 py-2 bg-red-50 rounded-lg border border-red-100">
          <p className="text-xs text-red-700">
            ⚠️ Congestion active on: {hr.binding_lines.join(", ")}
          </p>
        </div>
      )}
    </div>
  );
}

function AssetInspector({
  gen,
  hr,
  dailyPnl,
}: {
  gen: GeneratorAsset;
  hr: HourResult;
  dailyPnl: Record<string, AssetPnL>;
}) {
  const dispatch = hr.dispatch_by_asset[gen.id] ?? 0;
  const available = hr.available_by_asset[gen.id] ?? 0;
  const curtailment = hr.curtailment_by_asset[gen.id] ?? 0;
  const lmp = hr.lmp_by_node[gen.node_id] ?? 0;
  const hubPrice = hr.hub_price;
  const basis = hr.basis_by_node[gen.node_id] ?? 0;
  const revenue = dispatch * lmp;
  const pnl = dailyPnl[gen.id];

  // Causal headline
  let headline = "";
  if (available < 1) {
    headline = `${gen.name} is not producing this hour.`;
  } else if (curtailment > 5) {
    const pct = Math.round((curtailment / available) * 100);
    headline = `${gen.name} is curtailed ${pct}% — the export line is full.`;
  } else if (gen.variable_cost === 0 && dispatch > 1) {
    if (basis < -5) {
      headline = `${gen.name} is producing but earning $${Math.abs(basis).toFixed(0)}/MWh less than hub.`;
    } else {
      headline = `${gen.name} is fully dispatched and earning hub-level prices.`;
    }
  } else if (dispatch < 1) {
    headline = `${gen.name} is not dispatched — cheaper units are covering demand.`;
  } else {
    const margin = lmp - gen.variable_cost;
    headline = `${gen.name} is running at $${margin.toFixed(0)}/MWh margin above fuel cost.`;
  }

  return (
    <div>
      {/* Causal headline */}
      <p className="text-sm text-slate-700 leading-relaxed mb-4 px-1">{headline}</p>

      <div className="space-y-0">
        <Row label="Dispatch" value={`${dispatch.toFixed(0)} MW`} sub={`of ${available.toFixed(0)} MW available`} />
        <Row label="Curtailment" value={`${curtailment.toFixed(0)} MW`} sub={curtailment > 0 ? "⚠️ Output wasted" : "None"} />
        <Row label="Node LMP" value={`$${lmp.toFixed(2)}/MWh`} />
        <Row label="Hub price" value={`$${hubPrice.toFixed(2)}/MWh`} />
        <Row
          label="Basis"
          value={`${basis >= 0 ? "+" : ""}$${basis.toFixed(2)}/MWh`}
          sub={basis < -5 ? "Below hub — hedge would over-earn" : undefined}
        />
        <Row label="This-hour revenue" value={`$${revenue.toFixed(0)}`} />
        {gen.variable_cost > 0 && (
          <Row
            label="Margin over cost"
            value={`$${(lmp - gen.variable_cost).toFixed(2)}/MWh`}
            sub={`Fuel cost: $${gen.variable_cost}/MWh`}
          />
        )}
      </div>

      {/* Daily summary */}
      {pnl && (
        <div className="mt-4 pt-3 border-t border-slate-100">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wide mb-2">Daily Summary</p>
          <div className="space-y-0">
            <Row label="Total revenue" value={`$${pnl.total_revenue_usd.toLocaleString()}`} />
            <Row label="Total dispatched" value={`${pnl.total_dispatch_mwh.toFixed(0)} MWh`} />
            <Row label="Total curtailed" value={`${pnl.total_curtailment_mwh.toFixed(0)} MWh`} />
            <Row label="Avg capture price" value={`$${pnl.avg_capture_price.toFixed(2)}/MWh`} />
            <Row label="Avg hub price" value={`$${pnl.avg_hub_price.toFixed(2)}/MWh`} />
            <Row
              label="Daily avg basis"
              value={`${pnl.avg_basis >= 0 ? "+" : ""}$${pnl.avg_basis.toFixed(2)}/MWh`}
              sub={pnl.avg_basis < -3 ? "Persistent negative basis" : undefined}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function LineInspector({
  line,
  hr,
  nodes,
}: {
  line: GridLine;
  hr: HourResult;
  nodes: GridNode[];
}) {
  const flow = hr.line_flow_mw[line.id] ?? 0;
  const loading = hr.line_loading_pct[line.id] ?? 0;
  const isBinding = hr.binding_lines.includes(line.id);
  const fromNode = nodes.find((n) => n.id === line.from_node_id);
  const toNode = nodes.find((n) => n.id === line.to_node_id);
  const fromLmp = hr.lmp_by_node[line.from_node_id] ?? 0;
  const toLmp = hr.lmp_by_node[line.to_node_id] ?? 0;

  let headline = "";
  if (isBinding) {
    const priceSep = Math.abs(fromLmp - toLmp);
    headline = `${line.name} is congested (${Math.round(loading * 100)}% full). This creates a $${priceSep.toFixed(0)}/MWh price spread.`;
  } else if (loading > 0.8) {
    headline = `${line.name} is heavily loaded at ${Math.round(loading * 100)}% but not yet binding.`;
  } else {
    headline = `${line.name} has spare capacity (${Math.round(loading * 100)}% loaded). No congestion.`;
  }

  return (
    <div>
      <p className="text-sm text-slate-700 leading-relaxed mb-4 px-1">{headline}</p>
      <div className="space-y-0">
        <Row label="Current flow" value={`${Math.round(Math.abs(flow))} MW`} sub={flow >= 0 ? `${fromNode?.name} → ${toNode?.name}` : `${toNode?.name} → ${fromNode?.name}`} />
        <Row label="Capacity" value={`${line.capacity_mw} MW`} />
        <Row label="Loading" value={`${Math.round(loading * 100)}%`} sub={isBinding ? "🚧 Congested" : loading > 0.8 ? "⚠️ Heavy" : "✅ Clear"} />
        <Row label={`${fromNode?.name} LMP`} value={`$${fromLmp.toFixed(2)}/MWh`} />
        <Row label={`${toNode?.name} LMP`} value={`$${toLmp.toFixed(2)}/MWh`} />
        <Row label="Price spread" value={`$${Math.abs(fromLmp - toLmp).toFixed(2)}/MWh`} sub={isBinding ? "Congestion rent on this line" : "No rent"} />
      </div>
    </div>
  );
}

export default function InspectorPanel({
  selectedId,
  nodes,
  lines,
  generators,
  hub,
  hourResult,
  dailyPnl,
  onClose,
}: InspectorPanelProps) {
  const selectedNode = nodes.find((n) => n.id === selectedId);
  const selectedLine = lines.find((l) => l.id === selectedId);
  const selectedGen = generators.find((g) => g.id === selectedId);

  const title = selectedNode?.name ?? selectedLine?.name ?? selectedGen?.name ?? "Select an element";
  const subtitle = selectedNode ? "Pricing Location" : selectedLine ? "Transmission Line" : selectedGen ? selectedGen.type.replace("_", " ").toUpperCase() : "";

  return (
    <AnimatePresence>
      {selectedId && (
        <motion.div
          initial={{ x: 20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 20, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="w-72 bg-white rounded-2xl shadow-xl border border-slate-100 flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-4 py-3 bg-gradient-to-r from-indigo-50 to-purple-50 border-b border-slate-100 flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-500 font-semibold uppercase tracking-wide">{subtitle}</p>
              <h3 className="text-base font-bold text-slate-800">{title}</h3>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 mt-0.5 rounded-lg p-1 hover:bg-white/60 transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {selectedNode && (
              <NodeInspector node={selectedNode} hub={hub} hr={hourResult} />
            )}
            {selectedLine && (
              <LineInspector line={selectedLine} hr={hourResult} nodes={nodes} />
            )}
            {selectedGen && (
              <AssetInspector gen={selectedGen} hr={hourResult} dailyPnl={dailyPnl} />
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
