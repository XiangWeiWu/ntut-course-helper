"""模擬「很多學生同時採用推薦課表」，並以擁擠扣分把推薦分散開。

問題：推薦的計分是固定的，同一班的學生會拿到同樣的推薦；若很多人照做，熱門的開課班會被擠爆。

模型（假設，報告中標示）：
- 每個本班（130 班）的學生向系統要推薦；班級人數取資料估計值，估不出者用全校中位數。
- 採用比例 α：α × 班級人數 照推薦選；其餘 (1−α) 依本學期實際選課人數佔用名額
  → 推薦者可用名額 cap_r = max(0, 推估名額 − (1−α) × 實際人數)。
- 「同班不同方案」：每班取前 3 名不同方案（k-best），照推薦的學生平均分到這 3 個方案。
- 只計選修（班級必修預排，名額另計）。
- 擁擠扣分（tâtonnement，類似以價格調節供需）：需求／可用名額 > 1 的開課班，每學分扣分
  price += η_t × min(超出比例, 3)；比例 < 0.7 時 price −= η_t/2（不低於 0）。
  η_t = η / (1 + t/4) 逐輪遞減，減少來回震盪。反覆到沒有超額或達到輪數上限。
- 大家同時對扣分反應會「從眾」（熱門選修被扣分後，所有人同一輪轉去名額小的博雅班），超額會來回震盪；
  因此公布的是過程中「超額人次最少的那一輪」的扣分與推薦。

python -m backend.recommend.crowd           # 寫出 reports/crowd.json（α = 0.25, 0.5, 1.0）
"""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter

from backend.ingest.load import ROOT, load_term
from backend.sim.population import all_home_classes
from .scoring import build
from .solver import solve

ETA = 0.5


def simulate(alpha: float, rounds: int = 16, variants: int = 3, year: int = 115, sem: int = 1) -> dict:
    courses = list(load_term(year, sem))
    t = {c.id: c for c in courses}
    classes = all_home_classes(courses)
    known = [g.size for g in classes if g.size > 0]
    default_size = int(statistics.median(known)) if known else 40
    size = {g.name: (g.size or default_size) for g in classes}
    cap_r = {c.id: max(0.0, c.capacity - (1 - alpha) * c.people) for c in courses}
    prices: dict[str, float] = {}
    history, first, best = [], None, None
    for it in range(rounds + 1):
        demand: Counter = Counter()
        recs = {}
        for g in classes:
            scores, must = build(t, classes, g.name, prices=prices)
            sols = solve(courses, scores, 16 if g.grade < 4 else 9, 25, must, variants, time_limit=2.0) \
                or solve(courses, scores, 0, 25, must, variants, time_limit=2.0)
            recs[g.name] = [[cid for cid in s["courses"] if cid not in must] for s in sols]
            for chosen in recs[g.name]:
                for cid in chosen:
                    demand[cid] += alpha * size[g.name] / len(sols)
        ratio = {cid: d / cap_r[cid] if cap_r[cid] > 0 else float("inf") for cid, d in demand.items()}
        over = {cid: r for cid, r in ratio.items() if r > 1 + 1e-9}
        excess = sum(max(0.0, demand[cid] - cap_r[cid]) for cid in demand)
        history.append({"round": it, "overloaded": len(over), "excess_seats": round(excess, 1),
                        "recommended_sections": len(demand), "priced": sum(1 for p in prices.values() if p > 0)})
        if first is None:
            first = {"ratio": ratio, "demand": dict(demand)}
        if best is None or excess < best["excess"]:
            best = {"excess": excess, "round": it, "prices": dict(prices), "ratio": ratio, "demand": dict(demand), "recs": recs}
        if it == rounds or not over:
            break
        eta = ETA / (1 + it / 4)
        for cid, r in ratio.items():
            if r > 1:
                prices[cid] = prices.get(cid, 0.0) + eta * min(r - 1, 3.0)
            elif r < 0.7 and prices.get(cid):
                prices[cid] = max(0.0, prices[cid] - eta / 2)
    fin = lambda r: round(r, 3) if r != float("inf") else 99.0
    return {
        "alpha": alpha, "rounds_run": len(history) - 1, "history": history, "best_round": best["round"],
        "prices": {k: round(v, 3) for k, v in best["prices"].items() if v > 0},
        "ratio": {k: fin(v) for k, v in best["ratio"].items()},
        "ratio_before": {k: fin(v) for k, v in first["ratio"].items()},
        "demand": {k: round(v, 1) for k, v in best["demand"].items()},
        "cap_available": {k: round(cap_r[k], 1) for k in best["demand"]},
        "classes": best["recs"], "default_size": default_size,
    }


def main():
    out = {"generated": time.strftime("%Y-%m-%d"), "eta": ETA,
           "assumptions": "見 backend/recommend/crowd.py 說明；名額為推估值，非採用者依本學期實際人數佔用名額。",
           "scenarios": []}
    for a in (0.25, 0.5, 1.0):
        t0 = time.time()
        r = simulate(a)
        h0, h1 = r["history"][0], r["history"][r["best_round"]]
        print(f"α={a}: 超額開課班 {h0['overloaded']} → {h1['overloaded']}，超額人次 {h0['excess_seats']} → {h1['excess_seats']}，"
              f"採用第 {r['best_round']} 輪（共 {r['rounds_run']} 輪），{time.time() - t0:.0f} 秒")
        out["scenarios"].append(r)
    p = ROOT / "reports" / "crowd.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(p, round(p.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
