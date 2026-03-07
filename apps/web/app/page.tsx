"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import GridMap from "@/components/GridMap";
import Timeline from "@/components/Timeline";
import InspectorPanel from "@/components/InspectorPanel";
import ExplainCard from "@/components/ExplainCard";
import HUD from "@/components/HUD";
import { fetchSimulation } from "@/lib/api";
import type { SimulationResponse, Variant } from "@/lib/types";

const PLAY_INTERVAL_MS = 900;

export default function Home() {
  const [sim, setSim] = useState<SimulationResponse | null>(null);
  const [variant, setVariant] = useState<Variant>("base");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentHour, setCurrentHour] = useState(12); // Start at peak solar
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadSimulation = useCallback(async (v: Variant) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchSimulation("sunny_valley", v);
      setSim(data);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      setError(
        `Failed to load simulation: ${message}. Is the Python API running on port 8000?`
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSimulation(variant);
  }, [variant, loadSimulation]);

  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        setCurrentHour((h) => (h + 1) % 24);
      }, PLAY_INTERVAL_MS);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying]);

  const handleVariantChange = (v: Variant) => {
    setVariant(v);
    setIsPlaying(false);
    setSelectedId(null);
  };

  const handleSelect = (id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  };

  const hourResult = sim?.hours[currentHour];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50 flex flex-col p-4">
      <div className="max-w-[1400px] mx-auto w-full flex flex-col gap-4">

        {/* Main card */}
        <div className="bg-white rounded-2xl shadow-xl border border-slate-100 flex flex-col overflow-hidden">

          {/* HUD */}
          <HUD
            sim={sim}
            currentHour={currentHour}
            variant={variant}
            isLoading={isLoading}
            onVariantChange={handleVariantChange}
          />

          {/* Content row */}
          <div className="flex min-h-0" style={{ height: "520px" }}>

            {/* Left: Events */}
            <div className="w-64 border-r border-slate-100 flex flex-col flex-shrink-0">
              <div className="px-4 py-2 border-b border-slate-100">
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                  Market Events
                </h2>
              </div>
              <div className="flex-1 overflow-y-auto">
                {hourResult ? (
                  <ExplainCard events={hourResult.events} hour={currentHour} />
                ) : (
                  <div className="p-4 text-sm text-slate-400">Loading…</div>
                )}
              </div>
            </div>

            {/* Center: Map */}
            <div className="flex-1 relative p-4">
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10 rounded-xl">
                  <div className="text-slate-500 text-sm flex items-center gap-2">
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                      className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full"
                    />
                    Simulating…
                  </div>
                </div>
              )}

              {error && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10 rounded-xl p-8">
                  <div className="text-center max-w-sm">
                    <p className="text-red-600 font-semibold mb-2">Connection error</p>
                    <p className="text-slate-500 text-sm">{error}</p>
                    <p className="text-slate-400 text-xs mt-3 font-mono bg-slate-100 p-2 rounded">
                      cd services/sim-python<br />
                      uvicorn app.api.main:app --reload
                    </p>
                  </div>
                </div>
              )}

              {sim && hourResult && (
                <GridMap
                  nodes={sim.nodes}
                  lines={sim.lines}
                  generators={sim.generators}
                  hub={sim.hub}
                  hourResult={hourResult}
                  selectedId={selectedId}
                  onSelectNode={handleSelect}
                  onSelectLine={handleSelect}
                  onSelectAsset={handleSelect}
                />
              )}
            </div>

            {/* Right: Inspector */}
            <div className="w-72 border-l border-slate-100 flex-shrink-0 overflow-y-auto">
              {sim && hourResult && selectedId ? (
                <InspectorPanel
                  selectedId={selectedId}
                  nodes={sim.nodes}
                  lines={sim.lines}
                  generators={sim.generators}
                  hub={sim.hub}
                  hourResult={hourResult}
                  dailyPnl={sim.daily_pnl}
                  onClose={() => setSelectedId(null)}
                />
              ) : (
                <div className="p-6">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-3">
                    How to explore
                  </div>
                  <ul className="space-y-3 text-xs text-slate-500">
                    <li>🔵 Click a <strong>node</strong> to see its price and basis</li>
                    <li>〰️ Click a <strong>line</strong> to see flow and congestion</li>
                    <li>☀️ Click an <strong>asset</strong> for revenue breakdown</li>
                    <li>▶️ Press <strong>play</strong> to step through the 24-hour day</li>
                    <li>🔀 Switch <strong>variants</strong> to compare scenarios</li>
                  </ul>

                  {sim && (
                    <div className="mt-6 pt-4 border-t border-slate-100">
                      <p className="text-xs text-slate-400 font-semibold uppercase tracking-wide mb-2">
                        Try this
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Scrub to hour 12, then click the SunnyValley node. Notice the negative basis.
                        Then switch to <strong>Bigger Line</strong> to see congestion disappear.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Timeline */}
          {sim && (
            <Timeline
              hours={sim.hours}
              currentHour={currentHour}
              isPlaying={isPlaying}
              onHourChange={(h) => {
                setCurrentHour(h);
                setIsPlaying(false);
              }}
              onPlayPause={() => setIsPlaying((p) => !p)}
            />
          )}
        </div>

        <p className="text-center text-xs text-slate-400 pb-2">
          Sunny Valley to City · DC optimal dispatch · Nodal LMP pricing · MVP v0.1
        </p>
      </div>
    </div>
  );
}
