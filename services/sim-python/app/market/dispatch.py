"""
LP Economic Dispatch Solver — Corrected DC-OPF Formulation

For a lossless DC network, the correct LP is:

    minimize   Σ_g  c_g * p_g

    subject to:
        Σ_g p_g = total_demand                                [1 equality, dual = λ]
        -cap_l ≤ Σ_g PTDF[l, node_g] * p_g ≤ cap_l + PTDF[l,:] @ demand_non_slack
                                                              [2*n_lines inequalities]
        0 ≤ p_g ≤ p_g_max[hour]

LMP Extraction:
    LMP at slack bus       = λ
    LMP at non-slack node n = λ + Σ_l ρ_l * PTDF[l, n]

    where ρ_l = (dual of upper limit on line l) - (dual of lower limit on line l)
                 positive ρ_l: line l is importing (upper limit binding)
                 negative ρ_l: line l is exporting in reverse (lower limit binding)

    In scipy HiGHS minimization:
        result.eqlin.marginals[0]     = dual of system balance constraint
        result.ineqlin.marginals[:L]  = duals of upper flow limits (μ^+ ≥ 0)
        result.ineqlin.marginals[L:]  = duals of lower flow limits (μ^- ≥ 0)

    Sign convention (scipy minimization):
        For Ax ≤ b, dual μ ≥ 0 means "cost of relaxing constraint by 1 unit"
        For system balance Σg p_g = D, dual λ means "cost of increasing D by 1 MW"
        Therefore λ = LMP at slack.

    IMPORTANT: Validate with perturbation test before trusting.
"""

from __future__ import annotations
import numpy as np
from scipy.optimize import linprog, OptimizeResult
from typing import Optional
from ..core.entities import Scenario
from ..physics.dc_flow import build_ptdf

SLACK_NODE_ID = "N3"   # HubPoint is the reference bus


class DispatchResult:
    """Raw outputs from the LP solver for one hour."""

    def __init__(
        self,
        dispatch: dict[str, float],
        lmp: dict[str, float],
        line_flow: dict[str, float],
        injection: dict[str, float],
        marginal_asset_id: Optional[str],
        lp_result: OptimizeResult,
    ):
        self.dispatch = dispatch
        self.lmp = lmp
        self.line_flow = line_flow
        self.injection = injection
        self.marginal_asset_id = marginal_asset_id
        self.lp_result = lp_result


def solve_hour(scenario: Scenario, hour: int) -> DispatchResult:
    """
    Solve the economic dispatch LP for one hour.

    Uses a single system-wide power balance constraint (not per-node).
    LMPs are recovered from the energy dual + PTDF congestion duals.
    """
    generators = scenario.generators
    nodes = scenario.nodes
    active_lines = scenario.active_lines()

    node_ids = [n.id for n in nodes]
    gen_ids = [g.id for g in generators]
    node_idx = {nid: i for i, nid in enumerate(node_ids)}
    n_gen = len(generators)

    # ── Totals ─────────────────────────────────────────────────────────────────
    total_demand = sum(scenario.demand_at_node(nid, hour) for nid in node_ids)

    # ── Objective ──────────────────────────────────────────────────────────────
    c = np.array([g.variable_cost for g in generators], dtype=float)

    # ── Bounds ─────────────────────────────────────────────────────────────────
    bounds = [(0.0, g.available_mw(hour)) for g in generators]

    # ── PTDF + non-slack demand ────────────────────────────────────────────────
    ptdf, ptdf_line_ids, non_slack_ids = build_ptdf(scenario, SLACK_NODE_ID)
    non_slack_idx = {nid: i for i, nid in enumerate(non_slack_ids)}

    demand_non_slack = np.array(
        [scenario.demand_at_node(nid, hour) for nid in non_slack_ids], dtype=float
    )
    n_lines = len(ptdf_line_ids)

    # ── PTDF contribution matrix: ptdf_contrib[l, g_idx] ─────────────────────
    # = PTDF[l, node_of_g] if node_of_g is non-slack, else 0
    ptdf_contrib = np.zeros((n_lines, n_gen))
    for g_idx, gen in enumerate(generators):
        if gen.node_id in non_slack_idx:
            col = non_slack_idx[gen.node_id]
            ptdf_contrib[:, g_idx] = ptdf[:, col]

    # Net flow contribution of the fixed demand (demand withdrawals reduce injection)
    ptdf_demand_offset = ptdf @ demand_non_slack   # shape (n_lines,)

    # Actual line flow = ptdf_contrib @ p - ptdf_demand_offset
    # (negative because demand is a withdrawal, reducing net injection)
    # Wait: injection_n = gen_n - demand_n, so:
    # flow_l = PTDF[l,:] @ injection = PTDF[l,:] @ (gen - demand)
    #        = ptdf_contrib @ p - ptdf @ demand
    # This is correctly:  ptdf_contrib @ p - ptdf_demand_offset

    # ── Line capacity arrays ───────────────────────────────────────────────────
    line_cap_map = {l.id: l.capacity_mw for l in active_lines}
    line_cap = np.array([line_cap_map[lid] for lid in ptdf_line_ids], dtype=float)

    # ── Inequality constraints ─────────────────────────────────────────────────
    # flow_l = ptdf_contrib[l,:] @ p - ptdf_demand_offset[l]
    # Upper: ptdf_contrib[l,:] @ p ≤ cap_l + ptdf_demand_offset[l]
    # Lower: -ptdf_contrib[l,:] @ p ≤ cap_l - ptdf_demand_offset[l]

    A_ub_upper = ptdf_contrib
    b_ub_upper = line_cap + ptdf_demand_offset

    A_ub_lower = -ptdf_contrib
    b_ub_lower = line_cap - ptdf_demand_offset

    A_ub = np.vstack([A_ub_upper, A_ub_lower])
    b_ub = np.concatenate([b_ub_upper, b_ub_lower])

    # ── Equality: one system-wide power balance ────────────────────────────────
    # sum(p_g) = total_demand
    A_eq = np.ones((1, n_gen), dtype=float)
    b_eq = np.array([total_demand], dtype=float)

    # ── Solve ──────────────────────────────────────────────────────────────────
    result = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
        options={"presolve": True},
    )

    if not result.success:
        raise RuntimeError(
            f"Hour {hour} dispatch LP failed: {result.message}\n"
            f"Total demand: {total_demand:.1f} MW\n"
            f"Generator capacities: {[round(g.available_mw(hour), 1) for g in generators]}\n"
            f"Total available: {sum(g.available_mw(hour) for g in generators):.1f} MW"
        )

    p = result.x

    # ── LMP extraction ─────────────────────────────────────────────────────────
    # λ = dual of system-wide power balance (energy component)
    # In scipy minimize with equality Ax = b:
    #   Lagrangian: L = c^T x + λ^T (Ax - b) + μ^T (A_ub x - b_ub)
    #   dL/db = -λ, so increasing demand by 1 costs -λ per MW.
    #   result.eqlin.marginals stores λ (the multipliers).
    #   Since we minimize, the "cost to serve one more MW" = -lambda.

    # scipy HiGHS marginals convention for minimization:
    #   eqlin.marginals[i]  = d(obj*)/d(b_eq[i])  — direct sensitivity
    #   ineqlin.marginals[i] = d(obj*)/d(b_ub[i]) — direct sensitivity (≤ 0 for binding ≤ constraints)
    #
    # For the system balance equality (Σp = demand):
    #   d(obj*)/d(demand) = LMP at slack bus  → energy_lmp = eqlin.marginals[0]
    #
    # For the line flow inequality (ptdf_contrib @ p ≤ cap + offset):
    #   d(obj*)/d(b_ub_upper[l]) = ineqlin.marginals[l]  (≤ 0 when binding: relaxing saves cost)
    #
    # PTDF-based LMP formula:
    #   LMP[n] = energy_lmp + PTDF[:,n]^T @ rho
    # where rho[l] = -(μ_upper[l] - μ_lower[l]), μ are KKT multipliers (≥ 0)
    # scipy stores d(obj)/d(b_ub) = -μ  →  μ = -scipy_dual
    # so rho[l] = -((-scipy_upper[l]) - (-scipy_lower[l]))
    #           = -(−scipy_upper[l] + scipy_lower[l])
    #           = scipy_upper[l] - scipy_lower[l]

    energy_lmp = float(result.eqlin.marginals[0])  # LMP at slack bus = λ (direct)

    ineq_upper = result.ineqlin.marginals[:n_lines]   # d(obj)/d(b_ub_upper), ≤ 0 when binding
    ineq_lower = result.ineqlin.marginals[n_lines:]   # d(obj)/d(b_ub_lower), ≤ 0 when binding

    # rho[l]: congestion adder per unit PTDF; negative for lines exporting from cheap nodes
    rho = ineq_upper - ineq_lower    # shape (n_lines,)

    # Compute LMP per node:
    # LMP_slack = energy_lmp  (no congestion adder at reference bus by definition)
    # LMP_n = energy_lmp + PTDF^T[n, :] @ rho  for non-slack nodes
    lmp = {}
    for nid in node_ids:
        if nid == SLACK_NODE_ID:
            lmp[nid] = energy_lmp
        else:
            n_col = non_slack_idx[nid]
            congestion_adder = float(ptdf[:, n_col] @ rho)
            lmp[nid] = energy_lmp + congestion_adder

    # ── Line flows ─────────────────────────────────────────────────────────────
    injection_non_slack = np.array(
        [
            sum(p[i] for i, g in enumerate(generators) if g.node_id == nid)
            - scenario.demand_at_node(nid, hour)
            for nid in non_slack_ids
        ]
    )
    flows_arr = ptdf @ injection_non_slack
    line_flow = {ptdf_line_ids[l]: float(flows_arr[l]) for l in range(n_lines)}

    # ── Net injection per node ─────────────────────────────────────────────────
    injection = {}
    for nid in node_ids:
        gen_at_node = sum(p[i] for i, g in enumerate(generators) if g.node_id == nid)
        injection[nid] = gen_at_node - scenario.demand_at_node(nid, hour)

    # ── Marginal generator ─────────────────────────────────────────────────────
    marginal_asset_id = _find_marginal(generators, p, hour)

    return DispatchResult(
        dispatch={gen_ids[i]: float(p[i]) for i in range(n_gen)},
        lmp=lmp,
        line_flow=line_flow,
        injection=injection,
        marginal_asset_id=marginal_asset_id,
        lp_result=result,
    )


def _find_marginal(generators, p: np.ndarray, hour: int) -> Optional[str]:
    eps = 1e-3
    candidates = []
    for i, gen in enumerate(generators):
        avail = gen.available_mw(hour)
        if avail < eps:
            continue
        dispatched = float(p[i])
        if dispatched > eps:
            candidates.append((gen.variable_cost, gen.id))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ──────────────────────────────────────────────────────────────────────────────
# LMP validation (perturbation test)
# ──────────────────────────────────────────────────────────────────────────────

def validate_lmps(scenario: Scenario, hour: int, perturbation_mw: float = 1.0) -> dict:
    """
    Validate LMPs by perturbation test.
    For each node: add 1 MW of demand, re-solve, check delta_cost ≈ LMP.
    """
    from copy import deepcopy
    from ..core.entities import LoadEntity

    base_result = solve_hour(scenario, hour)
    base_cost = base_result.lp_result.fun
    results = {}

    for node in scenario.nodes:
        sc2 = deepcopy(scenario)
        perturbed = False
        for load in sc2.loads:
            if load.node_id == node.id:
                load.demand_mw = list(load.demand_mw)
                load.demand_mw[hour] += perturbation_mw
                perturbed = True
                break
        if not perturbed:
            sc2.loads.append(
                LoadEntity(
                    id=f"_perturb_{node.id}",
                    name="perturbation",
                    type="synthetic",
                    node_id=node.id,
                    demand_mw=[perturbation_mw if h == hour else 0.0 for h in range(24)],
                )
            )
        sc2.build_index()

        try:
            perturbed_result = solve_hour(sc2, hour)
            delta_cost = perturbed_result.lp_result.fun - base_cost
            lmp_predicted = base_result.lmp[node.id]
            error = abs(delta_cost - lmp_predicted * perturbation_mw)
            results[node.id] = {
                "lmp": round(lmp_predicted, 2),
                "delta_cost": round(delta_cost, 4),
                "expected": round(lmp_predicted * perturbation_mw, 4),
                "error": round(error, 4),
                "valid": error < 0.5,
            }
        except Exception as e:
            results[node.id] = {"error": str(e), "valid": False}

    all_valid = all(r.get("valid", False) for r in results.values())
    return {"all_valid": all_valid, "nodes": results}
