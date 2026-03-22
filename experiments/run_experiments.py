from __future__ import annotations

import csv
from pathlib import Path

from simulator.engine import SimulationConfig, run_simulation


def run() -> None:
    rows = []

    for sigma in [0.6, 1.2, 2.0]:
        cfg = SimulationConfig(sigma=sigma, ticks=700, T=700)
        result = run_simulation(cfg)
        rows.append(
            {
                "experiment": "volatility_sweep",
                "sigma": sigma,
                "gamma": cfg.gamma,
                "delta": cfg.delta,
                **result["summary"],
            }
        )

    for gamma in [0.03, 0.08, 0.2]:
        cfg = SimulationConfig(gamma=gamma, ticks=700, T=700)
        result = run_simulation(cfg)
        rows.append(
            {
                "experiment": "gamma_sweep",
                "sigma": cfg.sigma,
                "gamma": gamma,
                "delta": cfg.delta,
                **result["summary"],
            }
        )

    fixed = SimulationConfig(delta=0.05, gamma=0.0, ticks=700, T=700)
    dynamic = SimulationConfig(delta=0.08, gamma=0.08, ticks=700, T=700)
    fixed_result = run_simulation(fixed)
    dynamic_result = run_simulation(dynamic)

    rows.append(
        {
            "experiment": "fixed_spread",
            "sigma": fixed.sigma,
            "gamma": fixed.gamma,
            "delta": fixed.delta,
            **fixed_result["summary"],
        }
    )
    rows.append(
        {
            "experiment": "dynamic_spread",
            "sigma": dynamic.sigma,
            "gamma": dynamic.gamma,
            "delta": dynamic.delta,
            **dynamic_result["summary"],
        }
    )

    out = Path(__file__).resolve().parent / "results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} experiment rows to {out}")


if __name__ == "__main__":
    run()
