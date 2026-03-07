import sys
sys.path.insert(0, 'services/sim-python')
from app.core.scenario import load_scenario
from app.market.dispatch import solve_hour, validate_lmps
from app.finance.settlement import build_hour_result
from app.explain.events import detect_events

sc = load_scenario('sunny_valley', 'base')

def show_hour(h):
    dr = solve_hour(sc, h)
    hr = build_hour_result(sc, h, dr)
    lmps = " ".join(f"{k}=${v:.0f}" for k, v in dr.lmp.items())
    dispatch = " ".join(f"{k}={v:.0f}" for k, v in dr.dispatch.items())
    print(f"Hour {h:2d}: [{lmps}] hub=${hr.hub_price:.0f} binding={hr.binding_lines}")
    print(f"        dispatch: {dispatch}")
    return hr

print("--- 24-Hour LMP + Dispatch Summary ---")
for h in [6, 9, 11, 12, 13, 15, 18, 19, 20, 22]:
    show_hour(h)

print()
print("--- LMP Validation (hour 12) ---")
val = validate_lmps(sc, 12)
print(f"All valid: {val['all_valid']}")
for nid, r in val['nodes'].items():
    status = "OK" if r.get('valid') else "FAIL"
    print(f"  {nid}: LMP=${r.get('lmp')}, delta=${r.get('delta_cost')}, error=${r.get('error')} [{status}]")

print()
print("--- Events at hour 12 ---")
dr12 = solve_hour(sc, 12)
hr12 = build_hour_result(sc, 12, dr12)
events = detect_events(sc, hr12)
for ev in events:
    print(f"  [{ev.type}] {ev.message[:130]}")

print()
print("--- Events at hour 19 ---")
dr19 = solve_hour(sc, 19)
hr19 = build_hour_result(sc, 19, dr19)
events19 = detect_events(sc, hr19)
for ev in events19:
    print(f"  [{ev.type}] {ev.message[:130]}")
