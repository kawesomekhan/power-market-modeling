"""
Core data entities for the power market simulation engine.

Separation of concerns:
- These are pure data containers (dataclasses / Pydantic models).
- No simulation logic lives here.
- All layers (physics, market, finance, explain, api) import from this module.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Grid topology
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """A pricing location / bus on the network."""
    id: str
    name: str
    x: Optional[int] = None   # Isometric grid column — derived from map grid if absent
    y: Optional[int] = None   # Isometric grid row    — derived from map grid if absent
    zone_id: Optional[str] = None  # Derived from map zones if absent


@dataclass
class Line:
    """A transmission path between two nodes."""
    id: str
    name: str
    from_node_id: str
    to_node_id: str
    capacity_mw: float
    reactance: float      # Per-unit reactance (higher = more resistive)
    outage: bool = False  # If True, line is out of service


# ---------------------------------------------------------------------------
# Assets and loads
# ---------------------------------------------------------------------------

@dataclass
class GeneratorAsset:
    """
    A dispatchable or renewable generation asset.

    For renewable assets, variable_cost is effectively 0 and
    availability is driven by profile[hour] (0–1 fraction of capacity_mw).
    For thermal assets, availability defaults to 1.0 per hour.
    """
    id: str
    name: str
    type: str              # "solar" | "wind" | "gas_cc" | "gas_peaker" | "hydro" | "battery"
    node_id: str
    capacity_mw: float
    variable_cost: float   # $/MWh
    profile: list[float] = field(default_factory=lambda: [1.0] * 24)
    # profile[hour] ∈ [0, 1]: fraction of capacity available that hour

    def available_mw(self, hour: int) -> float:
        return self.capacity_mw * self.profile[hour]


@dataclass
class LoadEntity:
    """
    An exogenous demand entity attached to a node.

    Loads are NOT dispatchable in Phase 1 — they represent fixed
    hourly demand that the dispatch must serve.
    Multiple loads can exist at the same node (e.g. city + factory).
    The node's total demand = sum of all its LoadEntity.demand[hour].
    """
    id: str
    name: str
    type: str              # "city" | "town" | "factory" | "data_center"
    node_id: str
    demand_mw: list[float] = field(default_factory=lambda: [0.0] * 24)
    # demand_mw[hour]: MW demanded in that hour


# ---------------------------------------------------------------------------
# Hub
# ---------------------------------------------------------------------------

@dataclass
class Hub:
    """
    A commercial settlement / trading point derived from multiple nodes.

    Hub price = weighted average of constituent node LMPs.
    For MVP, weights are equal (1/N per node).
    """
    id: str
    name: str
    constituent_node_ids: list[str]
    weights: Optional[list[float]] = None  # If None, equal weights are applied

    def effective_weights(self) -> list[float]:
        n = len(self.constituent_node_ids)
        if self.weights:
            assert len(self.weights) == n
            return self.weights
        return [1.0 / n] * n


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """
    A complete world state: topology + assets + loads + hub + profiles.
    Variant overrides (e.g. more solar, bigger line) are applied before
    passing the scenario to the simulation engine.
    """
    id: str
    name: str
    description: str
    nodes: list[Node]
    lines: list[Line]
    generators: list[GeneratorAsset]
    loads: list[LoadEntity]
    hub: Hub

    # Flat tile lists produced by _parse_map(); consumed by the /simulate API response.
    grid_tiles: list = field(default_factory=list)
    zone_tiles: list = field(default_factory=list)

    # Convenience lookups (populated by scenario.py after construction)
    _node_index: dict[str, Node] = field(default_factory=dict, repr=False)
    _line_index: dict[str, Line] = field(default_factory=dict, repr=False)
    _gen_index: dict[str, GeneratorAsset] = field(default_factory=dict, repr=False)

    def build_index(self) -> None:
        self._node_index = {n.id: n for n in self.nodes}
        self._line_index = {l.id: l for l in self.lines}
        self._gen_index = {g.id: g for g in self.generators}

    def get_node(self, node_id: str) -> Node:
        return self._node_index[node_id]

    def get_line(self, line_id: str) -> Line:
        return self._line_index[line_id]

    def demand_at_node(self, node_id: str, hour: int) -> float:
        """Total MW demanded at a node in a given hour."""
        return sum(
            load.demand_mw[hour]
            for load in self.loads
            if load.node_id == node_id
        )

    def generators_at_node(self, node_id: str) -> list[GeneratorAsset]:
        return [g for g in self.generators if g.node_id == node_id]

    def active_lines(self) -> list[Line]:
        return [l for l in self.lines if not l.outage]


# ---------------------------------------------------------------------------
# Simulation results
# ---------------------------------------------------------------------------

@dataclass
class EventRecord:
    """A plain-language event detected by the explanation engine."""
    type: str            # "congestion" | "curtailment" | "price_spike" | "negative_basis" | "peaker_dispatch"
    asset_ids: list[str]
    line_ids: list[str]
    message: str         # Human-readable explanation


@dataclass
class HourResult:
    """All simulation outputs for a single hour."""
    hour: int

    # Prices
    lmp_by_node: dict[str, float]          # node_id → $/MWh
    hub_price: float                        # $/MWh
    energy_component: float                 # = hub_price (simplified, no losses)
    congestion_component_by_node: dict[str, float]   # node_id → $/MWh (LMP - hub)
    basis_by_node: dict[str, float]        # node_id → $/MWh (same as congestion_component for MVP)

    # Physical
    line_flow_mw: dict[str, float]         # line_id → MW (positive = from→to direction)
    line_loading_pct: dict[str, float]     # line_id → 0.0–1.0
    binding_lines: list[str]               # line_ids where |flow| ≥ 0.95 * capacity

    # Dispatch
    dispatch_by_asset: dict[str, float]    # asset_id → MW
    available_by_asset: dict[str, float]   # asset_id → MW
    curtailment_by_asset: dict[str, float] # asset_id → MW (available - dispatch)
    marginal_asset_id: Optional[str]       # asset_id of the price-setting generator
    demand_by_node: dict[str, float]       # node_id → MW

    # Explanations
    events: list[EventRecord] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Full 24-hour simulation output for one scenario variant."""
    scenario_id: str
    variant: str
    hours: list[HourResult]   # hours[0] = hour 0, hours[23] = hour 23

    def get_hour(self, hour: int) -> HourResult:
        return self.hours[hour]
