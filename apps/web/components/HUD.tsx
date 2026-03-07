"use client";
import type { SimulationResponse, HourResult, Variant } from "@/lib/types";
import ScenarioToggle from "./ScenarioToggle";

interface HUDProps {
  sim: SimulationResponse | null;
  currentHour: number;
  variant: Variant;
  isLoading: boolean;
  onVariantChange: (v: Variant) => void;
}

export default function HUD({
  sim,
  currentHour,
  variant,
  isLoading,
  onVariantChange,
}: HUDProps) {
  const hr: HourResult | null = sim?.hours[currentHour] ?? null;

  const totalGen = hr
    ? Object.values(hr.dispatch_by_asset).reduce((a, b) => a + b, 0)
    : 0;
  const totalDemand = hr
    ? Object.values(hr.demand_by_node).reduce((a, b) => a + b, 0)
    : 0;
  // Only count curtailment for renewable generators (solar/wind, variable_cost=0)
  const renewableIds = new Set(
    sim?.generators.filter((g) => g.variable_cost === 0).map((g) => g.id) ?? []
  );
  const totalCurtailment = hr
    ? Object.entries(hr.curtailment_by_asset)
        .filter(([id]) => renewableIds.has(id))
        .reduce((a, [, v]) => a + v, 0)
    : 0;

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-100 rounded-t-2xl">
      {/* Title + description */}
      <div className="flex items-center gap-4">
        <div>
          <h1 className="text-base font-bold text-slate-800">
            {sim?.scenario_name ?? "Power Market Simulator"}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 max-w-xs">
            {sim?.scenario_description?.slice(0, 80) ?? "Loading scenario…"}
          </p>
        </div>
      </div>

      {/* Global metrics */}
      {hr && (
        <div className="flex items-center gap-6 text-center">
          <div>
            <p className="text-lg font-bold text-indigo-600">
              ${hr.hub_price.toFixed(0)}
            </p>
            <p className="text-xs text-slate-500">Hub $/MWh</p>
          </div>
          <div>
            <p className="text-lg font-bold text-slate-700">
              {totalGen.toFixed(0)} MW
            </p>
            <p className="text-xs text-slate-500">Generation</p>
          </div>
          <div>
            <p className="text-lg font-bold text-slate-700">
              {totalDemand.toFixed(0)} MW
            </p>
            <p className="text-xs text-slate-500">Demand</p>
          </div>
          {totalCurtailment > 5 && (
            <div>
              <p className="text-lg font-bold text-amber-600">
                {totalCurtailment.toFixed(0)} MW
              </p>
              <p className="text-xs text-slate-500">Curtailed</p>
            </div>
          )}
        </div>
      )}

      {/* Scenario toggles */}
      <ScenarioToggle
        current={variant}
        onChange={onVariantChange}
        isLoading={isLoading}
      />
    </div>
  );
}
