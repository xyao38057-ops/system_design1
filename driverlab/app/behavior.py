"""Explicitly synthetic manual-driving samples; never infer users from autopilot."""
import random


def analyze(style="steady"):
    if style not in ("steady", "active", "cautious"):
        raise ValueError("未知行为样本")
    rng = random.Random({"steady": 7, "active": 13, "cautious": 21}[style])
    rows = []
    for i in range(120):
        amplitude = {"steady": 1.8, "active": 4.0, "cautious": 1.0}[style]
        rows.append({"second": i, "acceleration": round(rng.uniform(-amplitude, amplitude), 2),
                     "headway": round(rng.uniform(*{"steady": (1.5, 3.2),
                                                     "active": (.6, 2.4),
                                                     "cautious": (2.2, 4.0)}[style]), 2)})
    rapid_accel = sum(r["acceleration"] > 2.5 for r in rows)
    hard_brake = sum(r["acceleration"] < -2.5 for r in rows)
    short_gap = sum(r["headway"] < 1.2 for r in rows)
    score = max(0, 100 - rapid_accel - hard_brake - short_gap)
    return {"source": "固定随机种子生成的模拟人工驾驶样本（非真实用户数据）",
            "style": style, "samples": len(rows), "window_seconds": 120,
            "rapid_accel": rapid_accel, "hard_brake": hard_brake,
            "short_gap_ratio": round(short_gap / len(rows), 3), "score": score,
            "label": "平稳倾向" if score >= 80 else "需关注急加减速及跟车间距",
            "rule": "急加速 > 2.5 m/s²；急刹车 < -2.5 m/s²；短时距 < 1.2 s。仅为课程规则。",
            "rows": rows}
