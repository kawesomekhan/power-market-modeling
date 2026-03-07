"""
FastAPI simulation service.

Endpoints:
    GET /scenarios                                  — list available scenarios
    GET /simulate?scenario=sunny_valley&variant=base — run 24-hour simulation
    GET /simulate/hour/{hour}?scenario=...&variant=  — single-hour result
    GET /explain/node/{node_id}?scenario=...&variant=&hour= — node inspector
    GET /explain/asset/{asset_id}?scenario=...&variant=&hour= — asset inspector
    GET /validate?scenario=...&hour=               — LMP perturbation check (dev)
"""

from __future__ import annotations
from dataclasses import asdict
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Import simulation stack (pure, no circular deps)
from ..core.scenario import load_scenario, list_scenarios
from ..market.dispatch import solve_hour, validate_lmps
from ..finance.settlement import build_hour_result, compute_asset_daily_pnl
from ..explain.events import detect_events, explain_node, explain_asset
from ..core.entities import SimulationResult

app = FastAPI(
    title="Power Market Simulation Engine",
    description="DC dispatch + LMP + settlement API for the power market game",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_simulation(scenario_id: str, variant: str) -> SimulationResult:
    """Run the full 24-hour simulation and return a SimulationResult."""
    scenario = load_scenario(scenario_id, variant)
    hour_results = []

    for hour in range(24):
        try:
            dr = solve_hour(scenario, hour)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"Hour {hour} solve failed: {e}")

        hr = build_hour_result(scenario, hour, dr)
        hr.events = detect_events(scenario, hr)
        hour_results.append(hr)

    return SimulationResult(
        scenario_id=scenario_id,
        variant=variant,
        hours=hour_results,
    )


def _hour_result_to_dict(hr) -> dict:
    """Serialize an HourResult to a JSON-safe dict."""
    return {
        "hour": hr.hour,
        "lmp_by_node": hr.lmp_by_node,
        "hub_price": round(hr.hub_price, 2),
        "energy_component": round(hr.energy_component, 2),
        "congestion_component_by_node": {
            k: round(v, 2) for k, v in hr.congestion_component_by_node.items()
        },
        "basis_by_node": {k: round(v, 2) for k, v in hr.basis_by_node.items()},
        "line_flow_mw": {k: round(v, 1) for k, v in hr.line_flow_mw.items()},
        "line_loading_pct": {k: round(v, 4) for k, v in hr.line_loading_pct.items()},
        "binding_lines": hr.binding_lines,
        "dispatch_by_asset": {k: round(v, 1) for k, v in hr.dispatch_by_asset.items()},
        "available_by_asset": {k: round(v, 1) for k, v in hr.available_by_asset.items()},
        "curtailment_by_asset": {k: round(v, 1) for k, v in hr.curtailment_by_asset.items()},
        "marginal_asset_id": hr.marginal_asset_id,
        "demand_by_node": {k: round(v, 1) for k, v in hr.demand_by_node.items()},
        "events": [
            {
                "type": ev.type,
                "asset_ids": ev.asset_ids,
                "line_ids": ev.line_ids,
                "message": ev.message,
            }
            for ev in hr.events
        ],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/scenarios")
def get_scenarios():
    """List all available scenarios and their variants."""
    return list_scenarios()


@app.get("/simulate")
def simulate(
    scenario: str = Query("sunny_valley", description="Scenario ID"),
    variant: str = Query("base", description="Variant name"),
):
    """
    Run the full 24-hour simulation for a scenario/variant combination.
    Returns all hourly results + metadata for the UI to render.
    """
    sim = _run_simulation(scenario, variant)

    # Collect scenario metadata for the frontend (node positions, line defs, etc.)
    sc = load_scenario(scenario, variant)

    return {
        "scenario_id": sim.scenario_id,
        "variant": sim.variant,
        "scenario_name": sc.name,
        "scenario_description": sc.description,
        "nodes": [
            {"id": n.id, "name": n.name, "x": n.x, "y": n.y, "zone_id": n.zone_id}
            for n in sc.nodes
        ],
        "lines": [
            {
                "id": l.id,
                "name": l.name,
                "from_node_id": l.from_node_id,
                "to_node_id": l.to_node_id,
                "capacity_mw": l.capacity_mw,
                "outage": l.outage,
            }
            for l in sc.lines
        ],
        "generators": [
            {
                "id": g.id,
                "name": g.name,
                "type": g.type,
                "node_id": g.node_id,
                "capacity_mw": g.capacity_mw,
                "variable_cost": g.variable_cost,
            }
            for g in sc.generators
        ],
        "loads": [
            {
                "id": d.id,
                "name": d.name,
                "type": d.type,
                "node_id": d.node_id,
            }
            for d in sc.loads
        ],
        "hub": {
            "id": sc.hub.id,
            "name": sc.hub.name,
            "constituent_node_ids": sc.hub.constituent_node_ids,
        },
        "hours": [_hour_result_to_dict(hr) for hr in sim.hours],
        "daily_pnl": compute_asset_daily_pnl(sc, sim.hours),
    }


@app.get("/simulate/hour/{hour}")
def simulate_hour(
    hour: int,
    scenario: str = Query("sunny_valley"),
    variant: str = Query("base"),
):
    """Return results for a single hour only."""
    if not 0 <= hour <= 23:
        raise HTTPException(status_code=400, detail="Hour must be 0–23")

    sim = _run_simulation(scenario, variant)
    return _hour_result_to_dict(sim.hours[hour])


@app.get("/explain/node/{node_id}")
def get_node_explanation(
    node_id: str,
    hour: int = Query(..., description="Hour 0–23"),
    scenario: str = Query("sunny_valley"),
    variant: str = Query("base"),
):
    """Inspector panel data for a clicked node (causal headline + numbers)."""
    sim = _run_simulation(scenario, variant)
    sc = load_scenario(scenario, variant)

    if hour < 0 or hour > 23:
        raise HTTPException(status_code=400, detail="Hour must be 0–23")

    try:
        return explain_node(sc, sim.hours[hour], node_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")


@app.get("/explain/asset/{asset_id}")
def get_asset_explanation(
    asset_id: str,
    hour: int = Query(..., description="Hour 0–23"),
    scenario: str = Query("sunny_valley"),
    variant: str = Query("base"),
):
    """Inspector panel data for a clicked asset."""
    sim = _run_simulation(scenario, variant)
    sc = load_scenario(scenario, variant)

    if hour < 0 or hour > 23:
        raise HTTPException(status_code=400, detail="Hour must be 0–23")

    result = explain_asset(sc, sim.hours[hour], asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/validate")
def validate(
    scenario: str = Query("sunny_valley"),
    variant: str = Query("base"),
    hour: int = Query(12, description="Hour to validate (default: noon)"),
):
    """
    Run LMP perturbation validation for development.
    Verifies that dual variables match the true marginal cost of demand.
    """
    sc = load_scenario(scenario, variant)
    results = validate_lmps(sc, hour)

    all_valid = all(r.get("valid", False) for r in results.values())
    return {
        "hour": hour,
        "all_valid": all_valid,
        "node_results": results,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "power-market-sim"}
