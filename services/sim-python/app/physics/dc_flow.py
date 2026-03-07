"""
DC Power Flow — PTDF Matrix Builder

The Power Transfer Distribution Factor (PTDF) matrix describes how
power flows respond to net injections at each node.

Given:
  net_injection[n] = generation[n] - demand[n]  for each node n

Line flow:
  flow[l] = sum_n( PTDF[l, n] * net_injection[n] )

This module:
  1. Builds the bus susceptance matrix B from line reactances.
  2. Computes the PTDF matrix using the standard DC approximation.
  3. Returns PTDF in a form usable by the LP dispatch solver.

Reference:
  B[i,j] = -1/x_ij   (off-diagonal, for line i-j)
  B[i,i] = sum_j(1/x_ij)  (diagonal)

  PTDF[l, :] = b_l * (e_from - e_to)^T @ B_reduced_inv

where b_l = 1/x_l (line susceptance), e_from/e_to are indicator vectors,
and B_reduced is B with the slack bus row/column removed.
"""

from __future__ import annotations
import numpy as np
from ..core.entities import Scenario, Line


def build_ptdf(scenario: Scenario, slack_node_id: str) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Build the PTDF matrix for the active (non-outaged) lines in the scenario.

    Returns:
        ptdf:          shape (n_lines, n_nodes), excluding the slack bus column
        line_ids:      ordered list of line IDs (row order)
        non_slack_ids: ordered list of non-slack node IDs (column order)

    Convention:
        ptdf[l, n] > 0: injecting 1 MW at node n increases flow on line l
                        in the from→to direction.
        ptdf[l, n] < 0: injecting 1 MW at node n decreases flow (or increases
                        in to→from direction).

    The LP dispatch solver uses:
        -capacity_l <= ptdf[l, :] @ injection_non_slack <= capacity_l
    where injection at the slack bus is implicitly determined by KCL.
    """
    nodes = scenario.nodes
    active_lines = scenario.active_lines()

    node_ids = [n.id for n in nodes]
    n = len(node_ids)
    node_idx = {nid: i for i, nid in enumerate(node_ids)}
    slack_idx = node_idx[slack_node_id]

    # Build full susceptance matrix B (n x n)
    B = np.zeros((n, n))
    for line in active_lines:
        fi = node_idx[line.from_node_id]
        ti = node_idx[line.to_node_id]
        b = 1.0 / line.reactance  # susceptance
        B[fi, fi] += b
        B[ti, ti] += b
        B[fi, ti] -= b
        B[ti, fi] -= b

    # Reduced B: remove slack bus row and column
    non_slack_indices = [i for i in range(n) if i != slack_idx]
    non_slack_ids = [node_ids[i] for i in non_slack_indices]
    B_red = B[np.ix_(non_slack_indices, non_slack_indices)]

    # Invert reduced B
    try:
        B_red_inv = np.linalg.inv(B_red)
    except np.linalg.LinAlgError as e:
        raise ValueError(
            f"Susceptance matrix is singular — network may be disconnected. Error: {e}"
        )

    # Build PTDF matrix: one row per line, one column per non-slack node
    n_lines = len(active_lines)
    n_non_slack = len(non_slack_indices)
    ptdf = np.zeros((n_lines, n_non_slack))

    non_slack_pos = {nid: i for i, nid in enumerate(non_slack_ids)}

    for l_idx, line in enumerate(active_lines):
        b_l = 1.0 / line.reactance
        from_nid = line.from_node_id
        to_nid = line.to_node_id

        # PTDF row = b_l * (e_from - e_to)^T @ B_red_inv
        # where e_from/e_to index into non-slack nodes only
        # If from_node or to_node is the slack, treat as zero vector for that side.
        row = np.zeros(n_non_slack)
        if from_nid != slack_node_id:
            row += B_red_inv[non_slack_pos[from_nid], :]
        if to_nid != slack_node_id:
            row -= B_red_inv[non_slack_pos[to_nid], :]
        ptdf[l_idx, :] = b_l * row

    return ptdf, [l.id for l in active_lines], non_slack_ids


def compute_line_flows(
    ptdf: np.ndarray,
    injection_non_slack: np.ndarray,
    line_ids: list[str],
    non_slack_ids: list[str],
) -> dict[str, float]:
    """
    Compute line flows from net injections at non-slack nodes.

    Args:
        ptdf:                 (n_lines, n_non_slack) PTDF matrix
        injection_non_slack:  (n_non_slack,) net injection at each non-slack node
        line_ids:             ordered line IDs matching ptdf rows
        non_slack_ids:        ordered node IDs matching ptdf columns

    Returns:
        dict mapping line_id → flow_mw (positive = from→to)
    """
    flows = ptdf @ injection_non_slack
    return {line_ids[l]: float(flows[l]) for l in range(len(line_ids))}
