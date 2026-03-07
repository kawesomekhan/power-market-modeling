// TypeScript types mirroring the Python simulation entities.
// Keep in sync with services/sim-python/app/core/entities.py

export interface GridNode {
  id: string;
  name: string;
  x: number;
  y: number;
  zone_id: string | null;
}

export interface GridLine {
  id: string;
  name: string;
  from_node_id: string;
  to_node_id: string;
  capacity_mw: number;
  outage: boolean;
}

export interface GeneratorAsset {
  id: string;
  name: string;
  type: "solar" | "wind" | "gas_cc" | "gas_peaker" | "hydro" | "battery";
  node_id: string;
  capacity_mw: number;
  variable_cost: number;
}

export interface LoadEntity {
  id: string;
  name: string;
  type: "city" | "town" | "factory" | "data_center";
  node_id: string;
}

export interface Hub {
  id: string;
  name: string;
  constituent_node_ids: string[];
}

export interface EventRecord {
  type: "congestion" | "curtailment" | "peaker_dispatch" | "negative_basis" | "price_spike";
  asset_ids: string[];
  line_ids: string[];
  message: string;
}

export interface HourResult {
  hour: number;
  lmp_by_node: Record<string, number>;
  hub_price: number;
  energy_component: number;
  congestion_component_by_node: Record<string, number>;
  basis_by_node: Record<string, number>;
  line_flow_mw: Record<string, number>;
  line_loading_pct: Record<string, number>;
  binding_lines: string[];
  dispatch_by_asset: Record<string, number>;
  available_by_asset: Record<string, number>;
  curtailment_by_asset: Record<string, number>;
  marginal_asset_id: string | null;
  demand_by_node: Record<string, number>;
  events: EventRecord[];
}

export interface AssetPnL {
  asset_id: string;
  asset_name: string;
  node_id: string;
  total_revenue_usd: number;
  total_dispatch_mwh: number;
  total_curtailment_mwh: number;
  avg_capture_price: number;
  avg_hub_price: number;
  avg_basis: number;
}

export interface SimulationResponse {
  scenario_id: string;
  variant: string;
  scenario_name: string;
  scenario_description: string;
  nodes: GridNode[];
  lines: GridLine[];
  generators: GeneratorAsset[];
  loads: LoadEntity[];
  hub: Hub;
  hours: HourResult[];
  daily_pnl: Record<string, AssetPnL>;
}

export type Variant = "base" | "more_solar" | "bigger_line" | "hot_evening";

export const VARIANT_LABELS: Record<Variant, string> = {
  base: "Base Case",
  more_solar: "More Solar",
  bigger_line: "Bigger Line",
  hot_evening: "Hot Evening",
};

export const VARIANT_DESCRIPTIONS: Record<Variant, string> = {
  base: "Standard sunny day — midday congestion on the export line",
  more_solar: "Double solar capacity — more curtailment, lower SunnyValley basis",
  bigger_line: "Upgraded export line — congestion disappears, prices converge",
  hot_evening: "Extra evening load — peaker runs harder, city prices spike",
};

// Color palette for node prices
export function nodeColor(lmp: number, hubPrice: number): string {
  const basis = lmp - hubPrice;
  if (lmp < 5) return "#60a5fa";      // bright blue — very cheap / curtailed
  if (basis < -10) return "#93c5fd";  // light blue — below hub
  if (basis > 20) return "#f97316";   // orange — well above hub
  if (lmp > 70) return "#ef4444";     // red — price spike
  return "#fbbf24";                   // amber — near hub
}

export function lineColor(loadingPct: number, isBinding: boolean): string {
  if (isBinding) return "#ef4444";     // red — congested
  if (loadingPct > 0.8) return "#f97316"; // orange — heavy
  if (loadingPct > 0.5) return "#fbbf24"; // amber — moderate
  return "#86efac";                    // green — light
}
