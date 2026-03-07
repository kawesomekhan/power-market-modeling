"""
Financial Settlement Layer

Computes hub prices, basis, asset revenue, and curtailment
from the raw dispatch results produced by the market solver.

This module is purely computational — it reads DispatchResult
and Scenario data and produces financial outputs. It does not
call the LP solver or modify scenario state.

Price decomposition (simplified — no losses in Phase 1):
    hub_price[hour]              = weighted avg of constituent node LMPs
    energy_component             = hub_price  (same thing, named for clarity)
    congestion_component[node]   = LMP[node] - hub_price
    basis[node]                  = LMP[node] - hub_price  (same as congestion_component)

Asset revenue (merchant, no hedges in Phase 1):
    revenue[asset][hour] = dispatch[asset][hour] * LMP[node_of_asset][hour]

Curtailment:
    curtailment[asset][hour] = available[asset][hour] - dispatch[asset][hour]
"""

from __future__ import annotations
from ..core.entities import Scenario, HourResult
from ..market.dispatch import DispatchResult


CONGESTION_THRESHOLD_LOADING = 0.95   # Line considered binding above this fraction


def build_hour_result(
    scenario: Scenario,
    hour: int,
    dr: DispatchResult,
) -> HourResult:
    """
    Convert a DispatchResult into a fully populated HourResult.
    """
    hub = scenario.hub
    active_lines = scenario.active_lines()
    line_map = {l.id: l for l in active_lines}

    # ── Hub price ──────────────────────────────────────────────────────────────
    weights = hub.effective_weights()
    hub_price = sum(
        weights[i] * dr.lmp.get(nid, 0.0)
        for i, nid in enumerate(hub.constituent_node_ids)
    )

    # ── Basis and congestion component ─────────────────────────────────────────
    basis_by_node = {
        nid: dr.lmp.get(nid, 0.0) - hub_price
        for nid in [n.id for n in scenario.nodes]
    }
    congestion_component_by_node = basis_by_node  # same thing for MVP (no losses)

    # ── Line loading ───────────────────────────────────────────────────────────
    line_loading_pct: dict[str, float] = {}
    binding_lines: list[str] = []

    # A line is "economically binding" when the LP has a non-zero congestion dual
    # (i.e. nodal prices diverge across it). We detect this via LMP differences
    # across the line and flow >= threshold.
    for line in active_lines:
        flow = dr.line_flow.get(line.id, 0.0)
        loading = abs(flow) / line.capacity_mw if line.capacity_mw > 0 else 0.0
        line_loading_pct[line.id] = loading
        # True economic binding: loading at threshold AND price diverges across the line
        from_lmp = dr.lmp.get(line.from_node_id, 0.0)
        to_lmp = dr.lmp.get(line.to_node_id, 0.0)
        price_spread = abs(from_lmp - to_lmp)
        if loading >= CONGESTION_THRESHOLD_LOADING and price_spread > 1.0:
            binding_lines.append(line.id)

    # ── Dispatch, available, curtailment ───────────────────────────────────────
    available_by_asset = {g.id: g.available_mw(hour) for g in scenario.generators}
    # Curtailment = renewable output that could have been produced but wasn't.
    # Thermal generators being partly dispatched is economic dispatch, not curtailment.
    curtailment_by_asset = {
        g.id: max(0.0, available_by_asset[g.id] - dr.dispatch.get(g.id, 0.0))
        if g.variable_cost == 0 else 0.0
        for g in scenario.generators
    }

    # ── Demand by node ─────────────────────────────────────────────────────────
    demand_by_node = {
        n.id: scenario.demand_at_node(n.id, hour) for n in scenario.nodes
    }

    return HourResult(
        hour=hour,
        lmp_by_node=dict(dr.lmp),
        hub_price=hub_price,
        energy_component=hub_price,
        congestion_component_by_node=congestion_component_by_node,
        basis_by_node=basis_by_node,
        line_flow_mw=dict(dr.line_flow),
        line_loading_pct=line_loading_pct,
        binding_lines=binding_lines,
        dispatch_by_asset=dict(dr.dispatch),
        available_by_asset=available_by_asset,
        curtailment_by_asset=curtailment_by_asset,
        marginal_asset_id=dr.marginal_asset_id,
        demand_by_node=demand_by_node,
        events=[],  # populated separately by explain/events.py
    )


def compute_asset_daily_pnl(scenario: Scenario, hours: list[HourResult]) -> dict:
    """
    Compute daily energy revenue per generator asset across all hours.

    Returns:
        dict mapping asset_id → {
            "total_revenue_usd": float,
            "total_dispatch_mwh": float,
            "total_curtailment_mwh": float,
            "avg_capture_price": float,   (revenue / dispatch if dispatch > 0)
            "avg_lmp": float,             (avg hub price for reference)
        }
    """
    results = {}
    for gen in scenario.generators:
        total_rev = 0.0
        total_mwh = 0.0
        total_curtail = 0.0
        total_hub = 0.0

        for hr in hours:
            dispatch = hr.dispatch_by_asset.get(gen.id, 0.0)
            lmp = hr.lmp_by_node.get(gen.node_id, 0.0)
            curtailment = hr.curtailment_by_asset.get(gen.id, 0.0)

            total_rev += dispatch * lmp
            total_mwh += dispatch
            total_curtail += curtailment
            total_hub += hr.hub_price

        avg_hub = total_hub / len(hours) if hours else 0.0
        avg_capture = total_rev / total_mwh if total_mwh > 0 else 0.0

        results[gen.id] = {
            "asset_id": gen.id,
            "asset_name": gen.name,
            "node_id": gen.node_id,
            "total_revenue_usd": round(total_rev, 2),
            "total_dispatch_mwh": round(total_mwh, 1),
            "total_curtailment_mwh": round(total_curtail, 1),
            "avg_capture_price": round(avg_capture, 2),
            "avg_hub_price": round(avg_hub, 2),
            "avg_basis": round(avg_capture - avg_hub, 2) if total_mwh > 0 else 0.0,
        }

    return results
