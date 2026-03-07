"""
Explanation Engine — Structured Event Detection

Detects causal events from HourResult data and generates
deterministic, plain-language event cards.

Design principles:
  - Each detector checks a structured causal condition, not just a threshold.
  - Messages name the specific assets and lines involved.
  - The inspector panel should show the causal message BEFORE showing numbers.
  - Events are ordered by importance (congestion first, then curtailment, etc.)

All functions take a HourResult and the Scenario (for names/context)
and return a list of EventRecord objects.
"""

from __future__ import annotations
from ..core.entities import Scenario, HourResult, EventRecord

# Thresholds
CONGESTION_LOADING_THRESHOLD = 0.95       # line considered binding
CURTAILMENT_MW_THRESHOLD = 5.0            # MW below which we ignore curtailment noise
NEGATIVE_BASIS_THRESHOLD = -8.0           # $/MWh — clearly weak basis
PRICE_SPIKE_THRESHOLD = 70.0              # $/MWh — high price event
PEAKER_DISPATCH_THRESHOLD = 10.0          # MW — peaker is considered dispatched


def detect_events(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Run all event detectors and return a list of EventRecord objects,
    ordered from most important to least important.
    """
    events: list[EventRecord] = []

    events.extend(_detect_congestion(scenario, hr))
    events.extend(_detect_curtailment(scenario, hr))
    events.extend(_detect_peaker_dispatch(scenario, hr))
    events.extend(_detect_negative_basis(scenario, hr))
    events.extend(_detect_price_spike(scenario, hr))

    return events


# ──────────────────────────────────────────────────────────────────────────────
# Individual detectors
# ──────────────────────────────────────────────────────────────────────────────

def _detect_congestion(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Congestion event: a line is at or near its flow limit.
    The explanation names:
      - which line is binding
      - which cheap generation is blocked
      - which node is paying the premium
    """
    events = []
    line_map = {l.id: l for l in scenario.active_lines()}

    for line_id in hr.binding_lines:
        line = line_map.get(line_id)
        if not line:
            continue

        from_node = scenario.get_node(line.from_node_id)
        to_node = scenario.get_node(line.to_node_id)

        flow_mw = hr.line_flow_mw.get(line_id, 0.0)
        loading_pct = hr.line_loading_pct.get(line_id, 0.0)

        from_lmp = hr.lmp_by_node.get(from_node.id, 0.0)
        to_lmp = hr.lmp_by_node.get(to_node.id, 0.0)

        # Determine which side is cheap (export side) and which is expensive
        if flow_mw >= 0:
            cheap_side = from_node
            expensive_side = to_node
            price_diff = to_lmp - from_lmp
        else:
            cheap_side = to_node
            expensive_side = from_node
            price_diff = from_lmp - to_lmp

        # Identify cheap generation on the export side
        cheap_gens = [
            g for g in scenario.generators
            if g.node_id == cheap_side.id and g.variable_cost < 15
        ]
        cheap_gen_names = [g.name for g in cheap_gens]

        if cheap_gen_names:
            gen_str = " and ".join(cheap_gen_names)
            message = (
                f"The {line.name} line is at {loading_pct:.0%} capacity. "
                f"Cheap {gen_str} cannot fully reach {expensive_side.name}. "
                f"Price separation: {cheap_side.name} at ${from_lmp if flow_mw >= 0 else to_lmp:.0f}/MWh "
                f"vs {expensive_side.name} at ${to_lmp if flow_mw >= 0 else from_lmp:.0f}/MWh "
                f"(${price_diff:.0f} spread)."
            )
        else:
            message = (
                f"The {line.name} line is at {loading_pct:.0%} capacity, "
                f"creating a ${price_diff:.0f}/MWh price spread between "
                f"{cheap_side.name} and {expensive_side.name}."
            )

        events.append(EventRecord(
            type="congestion",
            asset_ids=[g.id for g in cheap_gens],
            line_ids=[line_id],
            message=message,
        ))

    return events


def _detect_curtailment(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Curtailment event: a renewable asset is producing less than available.
    Usually caused by congestion on its export path.
    """
    events = []

    for gen in scenario.generators:
        curtailment = hr.curtailment_by_asset.get(gen.id, 0.0)
        if curtailment < CURTAILMENT_MW_THRESHOLD:
            continue
        if gen.variable_cost > 10:
            continue  # Thermal curtailment is economic, not physical — skip for now

        available = hr.available_by_asset.get(gen.id, 0.0)
        dispatched = hr.dispatch_by_asset.get(gen.id, 0.0)
        curtail_pct = curtailment / available if available > 0 else 0

        # Check if there's a binding line on the export path from this node
        binding_export_lines = []
        for line in scenario.active_lines():
            if line.from_node_id == gen.node_id and line.id in hr.binding_lines:
                binding_export_lines.append(line)

        if binding_export_lines:
            line_names = " and ".join(l.name for l in binding_export_lines)
            message = (
                f"{gen.name} could produce {available:.0f} MW but only {dispatched:.0f} MW "
                f"is dispatched — {curtailment:.0f} MW ({curtail_pct:.0%}) curtailed "
                f"because the {line_names} export line is full."
            )
        else:
            message = (
                f"{gen.name} is curtailed by {curtailment:.0f} MW ({curtail_pct:.0%}). "
                f"Local supply exceeds what the grid can absorb or transport."
            )

        events.append(EventRecord(
            type="curtailment",
            asset_ids=[gen.id],
            line_ids=[l.id for l in binding_export_lines],
            message=message,
        ))

    return events


def _detect_peaker_dispatch(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Peaker dispatch event: an expensive gas peaker is running.
    This usually means cheaper imports cannot reach the load.
    """
    events = []

    for gen in scenario.generators:
        if gen.type != "gas_peaker":
            continue
        dispatch = hr.dispatch_by_asset.get(gen.id, 0.0)
        if dispatch < PEAKER_DISPATCH_THRESHOLD:
            continue

        node = scenario.get_node(gen.node_id)
        lmp = hr.lmp_by_node.get(gen.node_id, 0.0)
        hub_price = hr.hub_price

        # Check if there are binding import lines to this area
        binding_import_lines = []
        for line in scenario.active_lines():
            if line.to_node_id == gen.node_id and line.id in hr.binding_lines:
                binding_import_lines.append(line)

        if binding_import_lines or lmp > hub_price + 10:
            if binding_import_lines:
                reason = (
                    f"cheaper imports via {binding_import_lines[0].name} are constrained"
                )
            else:
                reason = f"local demand cannot be fully served by cheaper sources"

            message = (
                f"{gen.name} is dispatching {dispatch:.0f} MW at ${gen.variable_cost}/MWh "
                f"because {reason}. "
                f"{node.name} price is ${lmp:.0f}/MWh vs hub ${hub_price:.0f}/MWh."
            )
        else:
            message = (
                f"{gen.name} is running {dispatch:.0f} MW to help meet system demand. "
                f"Local price: ${lmp:.0f}/MWh."
            )

        events.append(EventRecord(
            type="peaker_dispatch",
            asset_ids=[gen.id],
            line_ids=[l.id for l in binding_import_lines],
            message=message,
        ))

    return events


def _detect_negative_basis(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Negative basis event: a node's LMP is significantly below hub price.
    Typical cause: renewable generation saturating the local/export capacity.
    """
    events = []

    for node in scenario.nodes:
        basis = hr.basis_by_node.get(node.id, 0.0)
        if basis > NEGATIVE_BASIS_THRESHOLD:
            continue

        lmp = hr.lmp_by_node.get(node.id, 0.0)
        hub = hr.hub_price

        # Find renewable generators at this node
        renewables = [
            g for g in scenario.generators
            if g.node_id == node.id and g.variable_cost < 10
        ]

        # Find binding export lines from this node
        binding_exports = [
            l for l in scenario.active_lines()
            if l.from_node_id == node.id and l.id in hr.binding_lines
        ]

        if renewables and binding_exports:
            ren_names = " and ".join(g.name for g in renewables)
            line_names = " and ".join(l.name for l in binding_exports)
            message = (
                f"{node.name} price is ${lmp:.0f}/MWh — ${abs(basis):.0f} below hub (${hub:.0f}/MWh). "
                f"{ren_names} production is saturating the {line_names} export line, "
                f"pushing local prices down. If you sell power at this node and hedge at hub, "
                f"you carry this ${abs(basis):.0f}/MWh basis loss."
            )
        elif renewables:
            ren_names = " and ".join(g.name for g in renewables)
            message = (
                f"{node.name} price is ${lmp:.0f}/MWh — ${abs(basis):.0f} below hub. "
                f"High output from {ren_names} is weighing on local prices."
            )
        else:
            message = (
                f"{node.name} price is ${lmp:.0f}/MWh — ${abs(basis):.0f} below hub (${hub:.0f}/MWh). "
                f"This node is in a low-price area."
            )

        events.append(EventRecord(
            type="negative_basis",
            asset_ids=[g.id for g in renewables],
            line_ids=[l.id for l in binding_exports],
            message=message,
        ))

    return events


def _detect_price_spike(scenario: Scenario, hr: HourResult) -> list[EventRecord]:
    """
    Price spike event: system prices are elevated above the threshold.
    Generates ONE system-wide event (not one per node) to avoid noise.
    Skips if congestion events already explain the hour.
    """
    spiked_nodes = [
        nid for nid, lmp in hr.lmp_by_node.items()
        if lmp >= PRICE_SPIKE_THRESHOLD
    ]

    if not spiked_nodes:
        return []

    # Congestion events already cover this hour — skip generic spike
    if hr.binding_lines:
        return []

    system_lmp = hr.hub_price
    marginal_gen = None
    if hr.marginal_asset_id:
        for g in scenario.generators:
            if g.id == hr.marginal_asset_id:
                marginal_gen = g
                break

    if marginal_gen and marginal_gen.type == "gas_peaker":
        message = (
            f"System prices at ${system_lmp:.0f}/MWh — {marginal_gen.name} "
            f"is the last unit dispatched. All cheaper generation is fully committed."
        )
    elif hr.hour in range(17, 23):
        message = (
            f"Evening demand peak: ${system_lmp:.0f}/MWh system-wide. "
            f"Solar has wound down and gas generation is filling the gap."
        )
    else:
        message = (
            f"Elevated system prices: ${system_lmp:.0f}/MWh. "
            f"Peak demand has absorbed all low-cost generation."
        )

    return [EventRecord(
        type="price_spike",
        asset_ids=[hr.marginal_asset_id] if hr.marginal_asset_id else [],
        line_ids=[],
        message=message,
    )]


# ──────────────────────────────────────────────────────────────────────────────
# Node inspector — causal explanation for a specific node
# ──────────────────────────────────────────────────────────────────────────────

def explain_node(scenario: Scenario, hr: HourResult, node_id: str) -> dict:
    """
    Generate the inspector panel content for a clicked node.
    Returns a dict with:
      - headline: causal one-liner (shown BEFORE numbers)
      - detail:   supporting explanation
      - lmp, hub_price, basis, energy_component, congestion_component
    """
    node = scenario.get_node(node_id)
    lmp = hr.lmp_by_node.get(node_id, 0.0)
    hub = hr.hub_price
    basis = hr.basis_by_node.get(node_id, 0.0)
    congestion = hr.congestion_component_by_node.get(node_id, 0.0)

    headline = _node_headline(scenario, hr, node_id, lmp, hub, basis)

    return {
        "node_id": node_id,
        "node_name": node.name,
        "headline": headline,
        "lmp": round(lmp, 2),
        "hub_price": round(hub, 2),
        "basis": round(basis, 2),
        "energy_component": round(hr.energy_component, 2),
        "congestion_component": round(congestion, 2),
        "demand_mw": round(hr.demand_by_node.get(node_id, 0.0), 1),
        "local_generation_mw": round(
            sum(
                hr.dispatch_by_asset.get(g.id, 0.0)
                for g in scenario.generators
                if g.node_id == node_id
            ), 1
        ),
        "binding_export_lines": [
            l.id for l in scenario.active_lines()
            if l.from_node_id == node_id and l.id in hr.binding_lines
        ],
        "binding_import_lines": [
            l.id for l in scenario.active_lines()
            if l.to_node_id == node_id and l.id in hr.binding_lines
        ],
    }


def _node_headline(
    scenario: Scenario,
    hr: HourResult,
    node_id: str,
    lmp: float,
    hub: float,
    basis: float,
) -> str:
    """One-line causal explanation for a node's price. Shown first in inspector."""
    node = scenario.get_node(node_id)

    binding_exports = [
        l for l in scenario.active_lines()
        if l.from_node_id == node_id and l.id in hr.binding_lines
    ]
    binding_imports = [
        l for l in scenario.active_lines()
        if l.to_node_id == node_id and l.id in hr.binding_lines
    ]

    renewables_here = [
        g for g in scenario.generators
        if g.node_id == node_id and g.variable_cost < 10
        and hr.dispatch_by_asset.get(g.id, 0.0) > 5
    ]

    if binding_exports and basis < -5:
        line = binding_exports[0]
        return (
            f"{node.name} is cheap because its export line ({line.name}) is full — "
            f"${abs(basis):.0f}/MWh below hub."
        )
    elif binding_imports and basis > 5:
        line = binding_imports[0]
        return (
            f"{node.name} is expensive because the import line ({line.name}) is congested — "
            f"${basis:.0f}/MWh above hub. Local generation must fill the gap."
        )
    elif renewables_here and basis < -2:
        names = ", ".join(g.name for g in renewables_here)
        return (
            f"High output from {names} is keeping {node.name} prices below hub."
        )
    elif lmp >= PRICE_SPIKE_THRESHOLD:
        return (
            f"{node.name} prices are elevated at ${lmp:.0f}/MWh — "
            f"expensive local generation is setting the price."
        )
    elif abs(basis) < 3:
        return (
            f"{node.name} is in balance with hub — no significant congestion. "
            f"Price: ${lmp:.0f}/MWh."
        )
    else:
        return f"{node.name} price: ${lmp:.0f}/MWh (hub: ${hub:.0f}/MWh, basis: ${basis:+.0f}/MWh)."


def explain_asset(scenario: Scenario, hr: HourResult, asset_id: str) -> dict:
    """
    Generate the inspector panel content for a clicked generator asset.
    Returns a dict with causal headline + economics breakdown.
    """
    gen = next((g for g in scenario.generators if g.id == asset_id), None)
    if not gen:
        return {"error": f"Asset {asset_id} not found"}

    dispatch = hr.dispatch_by_asset.get(asset_id, 0.0)
    available = hr.available_by_asset.get(asset_id, 0.0)
    curtailment = hr.curtailment_by_asset.get(asset_id, 0.0)
    lmp = hr.lmp_by_node.get(gen.node_id, 0.0)
    hub = hr.hub_price
    basis = hr.basis_by_node.get(gen.node_id, 0.0)
    revenue = dispatch * lmp

    headline = _asset_headline(scenario, hr, gen, dispatch, available, lmp, hub, basis)

    return {
        "asset_id": asset_id,
        "asset_name": gen.name,
        "asset_type": gen.type,
        "node_id": gen.node_id,
        "headline": headline,
        "dispatch_mw": round(dispatch, 1),
        "available_mw": round(available, 1),
        "curtailment_mw": round(curtailment, 1),
        "utilization_pct": round(dispatch / available * 100 if available > 0 else 0, 1),
        "node_lmp": round(lmp, 2),
        "hub_price": round(hub, 2),
        "basis": round(basis, 2),
        "revenue_usd": round(revenue, 2),
        "variable_cost": gen.variable_cost,
        "margin_usd_per_mwh": round(lmp - gen.variable_cost, 2),
    }


def _asset_headline(scenario, hr, gen, dispatch, available, lmp, hub, basis) -> str:
    """One-line causal headline for an asset inspector."""
    node = scenario.get_node(gen.node_id)

    if available < 1.0:
        return f"{gen.name} is not producing this hour (no {gen.type} available)."

    curtailment = available - dispatch
    curtail_pct = curtailment / available if available > 0 else 0

    binding_exports = [
        l for l in scenario.active_lines()
        if l.from_node_id == gen.node_id and l.id in hr.binding_lines
    ]

    if curtailment > CURTAILMENT_MW_THRESHOLD and binding_exports:
        line = binding_exports[0]
        return (
            f"{gen.name} is curtailed {curtailment:.0f} MW ({curtail_pct:.0%}) — "
            f"the {line.name} export line is full. Only {dispatch:.0f} MW can reach the market."
        )
    elif gen.variable_cost == 0 and dispatch > 1:
        if basis < -5:
            return (
                f"{gen.name} is producing {dispatch:.0f} MW but earning only ${lmp:.0f}/MWh — "
                f"${abs(basis):.0f}/MWh below hub due to export congestion."
            )
        else:
            return (
                f"{gen.name} is fully dispatched at {dispatch:.0f} MW, earning ${lmp:.0f}/MWh."
            )
    elif dispatch < 1:
        return f"{gen.name} is not dispatched this hour — cheaper generation is available."
    else:
        margin = lmp - gen.variable_cost
        return (
            f"{gen.name} dispatching {dispatch:.0f} MW at ${lmp:.0f}/MWh "
            f"(cost ${gen.variable_cost}/MWh, margin ${margin:.0f}/MWh)."
        )
