"""Small directed road network and preference-weighted Dijkstra routing."""
import heapq
import math

NODES = {
    "A": {"x": 90, "y": 260, "name": "校园起点"},
    "B": {"x": 300, "y": 260, "name": "西侧路口"},
    "C": {"x": 620, "y": 260, "name": "东侧路口"},
    "D": {"x": 830, "y": 260, "name": "科技园终点"},
    "E": {"x": 300, "y": 90, "name": "快速路西"},
    "F": {"x": 620, "y": 90, "name": "快速路东"},
    "G": {"x": 300, "y": 430, "name": "绿荫路西"},
    "H": {"x": 620, "y": 430, "name": "绿荫路东"},
}
SPECS = [
    ("AB", "A", "B", "校园大道", 14, .12),
    ("BC", "B", "C", "中央商业街", 9, 1.0),
    ("CD", "C", "D", "科技园大道", 14, .12),
    ("BE", "B", "E", "北连接线", 25, .8),
    ("EF", "E", "F", "城市快速路", 25, .8),
    ("FC", "F", "C", "东连接线", 25, .8),
    ("BG", "B", "G", "公园西路", 13, .02),
    ("GH", "G", "H", "绿荫大道", 13, .02),
    ("HC", "H", "C", "公园东路", 13, .02),
]
PROFILES = {
    "balanced": {"name": "距离优先", "time": .2, "distance": .7, "comfort": .1},
    "fast": {"name": "时间优先", "time": .9, "distance": .05, "comfort": .05},
    "comfort": {"name": "舒适优先", "time": .05, "distance": .05, "comfort": .9},
}


def fresh_edges():
    return {eid: {"id": eid, "source": a, "target": b, "name": name,
                  "length": math.hypot(NODES[a]["x"] - NODES[b]["x"],
                                       NODES[a]["y"] - NODES[b]["y"]),
                  "limit": speed, "difficulty": difficulty, "congestion": 1.0,
                  "closed": False, "lanes": 2}
            for eid, a, b, name, speed, difficulty in SPECS}


def plan(edges, start="A", end="D", profile="balanced"):
    weights = PROFILES[profile]
    queue = [(0.0, start, [])]
    best = {start: 0.0}
    while queue:
        score, node, path = heapq.heappop(queue)
        if score > best[node]:
            continue
        if node == end:
            selected = [edges[e] for e in path]
            return {"edges": path, "distance": round(sum(e["length"] for e in selected), 1),
                    "eta": round(sum(e["length"] / e["limit"] * e["congestion"] for e in selected), 1),
                    "score": round(score, 4), "profile": profile,
                    "reason": f"{weights['name']}：综合时间、距离及舒适性代价，排除封闭路段"}
        for eid, e in edges.items():
            if e["source"] != node or e["closed"]:
                continue
            cost = (weights["time"] * e["length"] / e["limit"] * e["congestion"] / 100
                    + weights["distance"] * e["length"] / 1000
                    + weights["comfort"] * e["difficulty"] * e["length"] / 1000)
            new_score = score + cost
            if new_score < best.get(e["target"], float("inf")):
                best[e["target"]] = new_score
                heapq.heappush(queue, (new_score, e["target"], path + [eid]))
    return None
