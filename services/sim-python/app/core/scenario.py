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

# Prefab names derived from generator/load type
_GEN_PREFAB = {
    "solar":       "SolarPrefab",
    "wind":        "WindPrefab",
    "gas_cc":      "GasCCPrefab",
    "gas_peaker":  "GasPeakerPrefab",
    "hydro":       "SolarPrefab",    # fallback
    "battery":     "SolarPrefab",    # fallback
}
_LOAD_PREFAB = {
    "city":        "CityLoadPrefab",
    "factory":     "CityLoadPrefab",
    "town":        "CityLoadPrefab",
    "data_center": "CityLoadPrefab",
}


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


def _derive_line_connectivity(line_id: str, node_ids: set[str]) -> tuple[str, str]:
    """
    Derive from/to node IDs from the naming convention "L_<from>_<to>".

    Raises ValueError if the ID doesn't follow the convention or the extracted
    node IDs are not in the scenario's node set.
    """
    parts = line_id.split("_")
    if len(parts) == 3 and parts[0] == "L" and parts[1] in node_ids and parts[2] in node_ids:
        return parts[1], parts[2]
    raise ValueError(
        f"Cannot derive connectivity for line '{line_id}'. "
        f"Either add 'from_node_id'/'to_node_id' to the line definition, "
        f"or use naming convention 'L_<from>_<to>' (e.g. 'L_N1_N3')."
    )


def _parse_map(
    map_data: dict,
    node_ids: set[str],
    line_ids: set[str],
    generators: list,
    loads: list,
) -> tuple[list[dict], list[dict]]:
    """
    Convert a 'map' object to flat tile lists.

    Grid cells hold entity/topology IDs directly as strings:
      - Node ID  (e.g. "N1")          → prefab="substation", node_id=<id>
      - Line ID  (e.g. "L_N1_N3")     → prefab="line",        line_id=<id>
      - Generator ID (e.g. "G1")       → prefab from generator type, asset_id=<id>
      - Load ID  (e.g. "D1")           → prefab from load type,      asset_id=<id>
      - "substation"                   → prefab="substation", no ids (visual waypoint)
      - 0 / null                       → empty cell, skipped

    Returns:
        grid_tiles: spawnable objects (prefab, node_id, line_id, asset_id)
        zone_tiles: background region cells (zone_id only)
    """
    if not map_data:
        return [], []

    origin_col = map_data["origin"]["col"]
    origin_row = map_data["origin"]["row"]

    gen_by_id  = {g.id: g for g in generators}
    load_by_id = {l.id: l for l in loads}

    grid_tiles = []
    zone_tiles = []

    for row_idx, row in enumerate(map_data.get("grid", [])):
        for col_idx, cell in enumerate(row):
            if not cell or cell == 0:
                continue
            key       = str(cell)
            col       = origin_col + col_idx
            row_coord = origin_row + row_idx

            if key in node_ids:
                grid_tiles.append({
                    "col": col, "row": row_coord,
                    "prefab": "substation",
                    "node_id": key, "line_id": None, "asset_id": None,
                })
            elif key in line_ids:
                grid_tiles.append({
                    "col": col, "row": row_coord,
                    "prefab": "line",
                    "node_id": None, "line_id": key, "asset_id": None,
                })
            elif key == "substation":
                # Visual-only waypoint substation (no node_id)
                grid_tiles.append({
                    "col": col, "row": row_coord,
                    "prefab": "substation",
                    "node_id": None, "line_id": None, "asset_id": None,
                })
            elif key in gen_by_id:
                g = gen_by_id[key]
                prefab = _GEN_PREFAB.get(g.type, "SolarPrefab")
                grid_tiles.append({
                    "col": col, "row": row_coord,
                    "prefab": prefab,
                    "node_id": None, "line_id": None, "asset_id": key,
                })
            elif key in load_by_id:
                l = load_by_id[key]
                prefab = _LOAD_PREFAB.get(l.type, "CityLoadPrefab")
                grid_tiles.append({
                    "col": col, "row": row_coord,
                    "prefab": prefab,
                    "node_id": None, "line_id": None, "asset_id": key,
                })
            # else: unknown key — skip silently

    # Zone background layer.
    zone_defs = map_data.get("zone_defs", {})
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

    node_id_set = {n.id for n in nodes}

    lines = []
    for l in data["lines"]:
        from_id = l.get("from_node_id")
        to_id   = l.get("to_node_id")
        if from_id is None or to_id is None:
            from_id, to_id = _derive_line_connectivity(l["id"], node_id_set)
        lines.append(Line(
            id=l["id"],
            name=l["name"],
            from_node_id=from_id,
            to_node_id=to_id,
            capacity_mw=l["capacity_mw"],
            reactance=l["reactance"],
            outage=l.get("outage", False),
        ))

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

    line_id_set = {l.id for l in lines}
    scenario.grid_tiles, scenario.zone_tiles = _parse_map(
        data.get("map", {}),
        node_id_set,
        line_id_set,
        generators,
        loads,
    )
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
