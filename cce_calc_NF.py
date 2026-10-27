#!/usr/bin/env python3
"""
5G NR PDCCH CCE index calculator (3GPP TS 38.213, Section 10.1)

CCE index for PDCCH candidate m, AL = L, CCE offset i:

  CCE = L * { ( Y_{p,n} + floor( m * N_CCE,p / (L * M_max^(L)) ) + n_CI )
              mod floor( N_CCE,p / L ) } + i

  Y_{p,n} = 0                                  for Common Search Space (CSS)
  Y_{p,n} = (A_p * Y_{p,n-1}) mod D            for UE-specific SS (USS)
            Y_{p,-1} = n_RNTI, D = 65537
            A_p = 39827 (p mod 3 = 0), 39829 (p mod 3 = 1), 39830 (p mod 3 = 2)

Usage:
  python cce_calc.py input_template.json
  python cce_calc.py            (runs with the built-in example)

Input JSON: each parameter may be either a plain value or an object
{"value": ..., "description": "..."} (as in input_template.json).
"""
import json
import sys

D = 65537
A_P = {0: 39827, 1: 39829, 2: 39830}

# (key, label, default, description) - drives the printed input table
PARAMS = [
    ("coreset_id",        "CORESET number (p)",           0,     "CORESET index"),
    ("search_space_id",   "Search space number (s)",      0,     "Search space index"),
    ("search_space_type", "Search space type",            "CSS", "CSS: Y=0 | USS: Y from RNTI"),
    ("aggregation_level", "Aggregation level (L)",        None,  "CCEs per candidate"),
    ("num_candidates",    "# PDCCH candidates (M_s,nCI)", None,  "candidates for this AL"),
    ("M_max_L",           "M_s,max^(L)",                  None,  "max candidates for this AL"),
    ("N_CCE_p",           "N_CCE,p",                      None,  "CCEs in CORESET p"),
    ("slot",              "Slot (n_s,f^mu)",              0,     "slot number, used for USS"),
    ("n_CI",              "Carrier indicator (n_CI)",     0,     "0 if no cross-carrier sched."),
    ("rnti",              "RNTI (n_RNTI)",                0,     "needed for USS only"),
]

EXAMPLE = {
    "coreset_id": 1, "search_space_id": 1, "search_space_type": "CSS",
    "aggregation_level": 4, "num_candidates": 2, "M_max_L": 2,
    "N_CCE_p": 10, "slot": 0, "n_CI": 0, "rnti": 0,
}


def load_config(path):
    """Read JSON; unwrap {"value": x, "description": ...} entries; skip _comments."""
    with open(path) as f:
        raw = json.load(f)
    cfg = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        cfg[k] = v["value"] if isinstance(v, dict) and "value" in v else v
    return cfg


def compute_Y(search_space_type, coreset_id, slot, rnti):
    """Hash value Y_{p,n}. CSS -> 0, USS -> recursion from slot 0 to `slot`."""
    if search_space_type.upper() == "CSS":
        return 0
    a_p = A_P[coreset_id % 3]
    y = rnti  # Y_{p,-1} = n_RNTI
    for _ in range(slot + 1):
        y = (a_p * y) % D
    return y


def normalize(cfg):
    """Fill defaults and return a complete parameter dict."""
    c = dict(cfg)
    for key, _, default, _ in PARAMS:
        if key not in c:
            if key == "num_candidates":
                c[key] = c.get("M_max_L")
            elif default is not None:
                c[key] = default
    for req in ("aggregation_level", "N_CCE_p", "M_max_L"):
        if c.get(req) is None:
            raise ValueError(f"missing required parameter '{req}'")
    if c.get("num_candidates") is None:
        c["num_candidates"] = c["M_max_L"]
    return c


def cce_indices(c):
    L = c["aggregation_level"]
    n_cce = c["N_CCE_p"]
    m_max = c["M_max_L"]
    n_ci = c["n_CI"]
    ss_type = c["search_space_type"]

    if L not in (1, 2, 4, 8, 16):
        raise ValueError("aggregation_level must be one of 1, 2, 4, 8, 16")
    if n_cce < L:
        raise ValueError(f"CORESET has only {n_cce} CCEs, cannot hold AL{L}")
    if ss_type.upper() not in ("CSS", "USS"):
        raise ValueError("search_space_type must be 'CSS' or 'USS'")
    if ss_type.upper() == "USS" and not c["rnti"]:
        raise ValueError("USS requires a non-zero 'rnti'")

    y = compute_Y(ss_type, c["coreset_id"], c["slot"], c["rnti"])
    blocks = n_cce // L

    results = []
    for m in range(c["num_candidates"]):
        offset = (m * n_cce) // (L * m_max)
        base = (y + offset + n_ci) % blocks
        start = L * base
        results.append({
            "m": m,
            "offset": offset,
            "base": base,
            "start_cce": start,
            "cce_indices": [start + i for i in range(L)],
        })
    return y, blocks, results


def print_report(c, y, blocks, results):
    L = c["aggregation_level"]
    line = "=" * 64

    print(line)
    print("INPUT PARAMETERS")
    print(line)
    for key, label, _, desc in PARAMS:
        print(f"  {label:<30} = {c[key]!s:<6}  ({desc})")
    print(f"  {'CCE offset (i)':<30} = {', '.join(str(i) for i in range(L)):<6}  (0 .. L-1)")

    print()
    print(line)
    print("INTERMEDIATE VALUES")
    print(line)
    if c["search_space_type"].upper() == "USS":
        print(f"  {'A_p (p mod 3 = ' + str(c['coreset_id'] % 3) + ')':<30} = {A_P[c['coreset_id'] % 3]}")
    print(f"  Y_p,n                          = {y}")
    print(f"  floor(N_CCE,p / L)             = {blocks}")

    print()
    print(line)
    print("RESULT")
    print(line)
    print(f"  {'m':>2} | {'floor(m*N/(L*M))':>16} | {'start CCE':>9} | CCE indices")
    print("  " + "-" * 60)
    for r in results:
        print(f"  {r['m']:>2} | {r['offset']:>16} | {r['start_cce']:>9} | {r['cce_indices']}")
    leftover = c["N_CCE_p"] - blocks * L
    if leftover:
        print(f"\n  Note: {leftover} CCE(s) at the end of the CORESET are never "
              f"used for AL{L} (N_CCE,p is not a multiple of L).")


def main():
    cfg = load_config(sys.argv[1]) if len(sys.argv) > 1 else EXAMPLE
    c = normalize(cfg)
    y, blocks, results = cce_indices(c)
    print_report(c, y, blocks, results)


if __name__ == "__main__":
    main()
