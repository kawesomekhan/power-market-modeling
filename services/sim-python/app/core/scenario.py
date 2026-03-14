"""
Scenario loader.

Reads a scenario JSON file from the scenarios/ directory,
applies any variant overrides, and returns a fully populated Scenario object.

The scenarios directory is at the repo root: power-market-modeling/scenarios/
"""

from __future__ import annotations
import json
import copy
from pathlib import Path
from ..core.entities import (
    Scenario, Node, Line, GeneratorAsset, LoadEntity, Hub
)

# Path to the scenarios directory (two levels up from this file's package)
_SCENARIOS_DIR = Path(__file__).parents[4] / "scenarios"


def load_scenario(scenario_id: str, variant: str = "base") -> Scenario:
    """
    Load and instantiate a Scenario from JSON.

    Args:
        scenario_id: File stem under scenarios/ (e.g. "sunny_valley")
        variant:     Variant name (e.g. "base", "more_solar", "bigger_line")

    Returns:
        A fully constructed and indexed Scenario object.
    """
    path = _SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Apply variant overrides
    data = _apply_variant(data, variant)

    return _build_scenario(data)


def _apply_variant(data: dict, variant: str) -> dict:
    """
    Deep-copy the scenario data and apply variant overrides.

    Overrides are merged at the field level (not list level).
    e.g. overriding "capacity_mw" on a generator replaces only that field.
    """
    if variant == "base" or variant not in data.get("variants", {}):
        return copy.deepcopy(data)

    data = copy.deepcopy(data)
    overrides = data["variants"][variant].get("overrides", {})

    if "generators" in overrides:
        for gen_data in data["generators"]:
            gid = gen_data["id"]
            if gid in overrides["generators"]:
                gen_data.update(overrides["generators"][gid])

    if "lines" in overrides:
        for line_data in data["lines"]:
            lid = line_data["id"]
            if lid in overrides["lines"]:
                line_data.update(overrides["lines"][lid])

    if "loads" in overrides:
        for load_data in data["loads"]:
            did = load_data["id"]
            if did in overrides["loads"]:
                load_data.update(overrides["loads"][did])

    return data


def _parse_map(map_data: dict) -> tuple[list[dict], list[dict]]:
    """
    Convert a 'map' object to flat tile lists.

    Returns:
        grid_tiles: spawnable objects (prefabs, nodes, assets)
        zone_tiles: background region cells (zone_id only)
    """
    if not map_data:
        return [], []

    origin_col = map_data["origin"]["col"]
    origin_row = map_data["origin"]["row"]
    tile_defs  = map_data.get("tile_defs", {})
    entities   = map_data.get("entities", {})
    zone_defs  = map_data.get("zone_defs", {})

    grid_tiles = []
    zone_tiles = []

    # Single unified grid: tile_defs lookup first, entities fallback.
    for row_idx, row in enumerate(map_data.get("grid", [])):
        for col_idx, cell in enumerate(row):
            if cell == 0:
                continue
            key = str(cell)
            col = origin_col + col_idx
            row_coord = origin_row + row_idx
            if key in tile_defs:
                grid_tiles.append({
                    "col":      col,
                    "row":      row_coord,
                    "prefab":   tile_defs[key],
                    "node_id":  None,
                    "asset_id": None,
                })
            elif key in entities:
                entity = entities[key]
                grid_tiles.append({
                    "col":      col,
                    "row":      row_coord,
                    "prefab":   entity["prefab"],
                    "node_id":  entity.get("node_id"),
                    "asset_id": entity.get("asset_id"),
                })

    # Zone background layer.
    for row_idx, row in enumerate(map_data.get("zones", [])):
        for col_idx, cell in enumerate(row):
            if cell == 0:
                continue
            zone_id = zone_defs.get(str(cell))
            if zone_id:
                zone_tiles.append({
                    "col":     origin_col + col_idx,
                    "row":     origin_row + row_idx,
                    "zone_id": zone_id,
                })

    return grid_tiles, zone_tiles


def _build_scenario(data: dict) -> Scenario:
    nodes = [
        Node(
            id=n["id"],
            name=n["name"],
            x=n["x"],
            y=n["y"],
            zone_id=n.get("zone_id"),
        )
        for n in data["nodes"]
    ]

    lines = [
        Line(
            id=l["id"],
            name=l["name"],
            from_node_id=l["from_node_id"],
            to_node_id=l["to_node_id"],
            capacity_mw=l["capacity_mw"],
            reactance=l["reactance"],
            outage=l.get("outage", False),
        )
        for l in data["lines"]
    ]

    generators = [
        GeneratorAsset(
            id=g["id"],
            name=g["name"],
            type=g["type"],
            node_id=g["node_id"],
            capacity_mw=g["capacity_mw"],
            variable_cost=g["variable_cost"],
            profile=g.get("profile", [1.0] * 24),
        )
        for g in data["generators"]
    ]

    loads = [
        LoadEntity(
            id=d["id"],
            name=d["name"],
            type=d["type"],
            node_id=d["node_id"],
            demand_mw=d["demand_mw"],
        )
        for d in data["loads"]
    ]

    hub_data = data["hub"]
    hub = Hub(
        id=hub_data["id"],
        name=hub_data["name"],
        constituent_node_ids=hub_data["constituent_node_ids"],
        weights=hub_data.get("weights"),
    )

    scenario = Scenario(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        nodes=nodes,
        lines=lines,
        generators=generators,
        loads=loads,
        hub=hub,
    )
    scenario.build_index()
    scenario.grid_tiles, scenario.zone_tiles = _parse_map(data.get("map", {}))
    return scenario


def list_scenarios() -> list[dict]:
    """Return metadata for all available scenarios."""
    results = []
    for path in sorted(_SCENARIOS_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        variants = list(data.get("variants", {}).keys())
        results.append({
            "id": data["id"],
            "name": data["name"],
            "description": data["description"],
            "variants": variants,
        })
    return results
