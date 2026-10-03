"""Deterministic 2-D teaching simulator, not SUMO or a real driving controller."""
import math
import uuid
from .network import NODES, PROFILES, fresh_edges, plan
from .behavior import analyze

SCENARIOS = {"normal": "正常导航", "congestion": "中央街拥堵", "closure": "道路封闭",
             "brake": "前车急停 · 侧方占用", "avoid": "前方障碍 · 可换道",
             "sensor": "测距传感器中断", "no_route": "全部出口封闭"}


class Simulation:
    def __init__(self):
        self.event_seq = 0
        self.reset()

    def reset(self, scenario="normal", profile="balanced"):
        if scenario not in SCENARIOS or profile not in PROFILES:
            raise ValueError("未知场景或偏好")
        self.run_id = uuid.uuid4().hex[:12]
        self.scenario, self.profile = scenario, profile
        self.edges = fresh_edges()
        self.time, self.speed, self.acceleration = 0.0, 0.0, 0.0
        self.position, self.edge_index, self.distance = 0.0, 0, 0.0
        self.lane, self.lane_progress = 0, 0.0
        self.changing = False
        self.running, self.completed, self.collision = False, False, False
        self.status, self.reason = "READY", "选择场景后点击开始，或运行预设场景"
        self.route = plan(self.edges, profile=profile)
        self.history, self.events = [], []
        self.pending_events = []
        self.obstacle = None
        self.side_blocked = False
        self.sensor_online, self.sensor_timestamp = True, 0.0
        self.replans, self.min_gap, self.max_decel = 0, None, 0.0
        self.behavior = analyze()
        self.log("system", "场景已重置", SCENARIOS[scenario])
        if scenario == "congestion":
            self.set_road("BC", "congestion")
        elif scenario == "closure":
            self.set_road("BC", "close")
        elif scenario == "no_route":
            for eid in ("BC", "BE", "BG"):
                self.edges[eid]["closed"] = True
            self.replan()
        elif scenario in ("brake", "avoid"):
            self.speed = 14.0
            self.position = 30.0
            self.distance = 30.0
            self.obstacle = {"edge": "AB", "position": 67.0, "lane": 0, "speed": 0.0}
            self.side_blocked = scenario == "brake"
            self.log("scenario", "前方车辆急停", "侧车道前后空间不足" if self.side_blocked else "侧车道可用")
        elif scenario == "sensor":
            self.speed = 12.0
            self.set_sensor(False)

    def log(self, kind, title, detail):
        self.event_seq += 1
        event = {"id": self.event_seq, "run_id": self.run_id, "time": round(self.time, 2),
                 "kind": kind, "title": title, "detail": detail}
        self.events.insert(0, event)
        self.events = self.events[:100]
        self.pending_events.append(event)

    def transition(self, status, reason):
        if status != self.status:
            self.log("decision", status, reason)
        self.status, self.reason = status, reason

    @property
    def current_edge(self):
        if not self.route or not self.route["edges"]:
            return None
        return self.edges[self.route["edges"][min(self.edge_index, len(self.route["edges"]) - 1)]]

    @property
    def route_available(self):
        return bool(self.route and self.route["edges"]
                    and self.edges[self.route["edges"][-1]]["target"] == "D")

    def replan(self):
        current = self.current_edge
        if current and self.position > 0:
            suffix = plan(self.edges, current["target"], "D", self.profile)
            if suffix:
                suffix["edges"] = [current["id"]] + suffix["edges"]
                self.route, self.edge_index = suffix, 0
                self.update_route_metrics()
            else:
                # Preserve physical location while stopping; route feasibility is separate.
                self.route = {"edges": [current["id"]], "profile": self.profile,
                              "distance": 0, "eta": 0, "score": 0, "reason": "无可行后续路线"}
                self.edge_index = 0
                self.transition("NO_ROUTE", "后续路网无可行路线，停止并等待道路恢复")
        else:
            self.route = plan(self.edges, profile=self.profile)
            if not self.route:
                self.transition("NO_ROUTE", "起点至终点无可行路线")
        if self.route_available and self.status == "NO_ROUTE":
            self.transition("READY", "道路恢复，可继续行驶")
        self.replans += 1
        self.log("route", "重新计算路线", self.route["reason"] if self.route else "无可行路线")

    def update_route_metrics(self):
        if not self.route:
            return
        remaining = [self.edges[eid] for eid in self.route["edges"][self.edge_index:]]
        lengths = [max(0, e["length"] - self.position) if i == 0 else e["length"]
                   for i, e in enumerate(remaining)]
        self.route["distance"] = round(sum(lengths), 1)
        self.route["eta"] = round(sum(length / e["limit"] * e["congestion"]
                                      for length, e in zip(lengths, remaining)), 1)

    def set_road(self, eid, action):
        if eid not in self.edges or action not in ("close", "congestion", "restore"):
            raise ValueError("无效的路段操作")
        edge = self.edges[eid]
        edge["closed"] = action == "close"
        edge["congestion"] = 6.0 if action == "congestion" else 1.0
        self.log("road", edge["name"], {"close": "路段封闭", "congestion": "预计通行时间增至 6 倍", "restore": "恢复通行"}[action])
        self.replan()

    def set_sensor(self, online):
        self.sensor_online = online
        if online:
            self.sensor_timestamp = self.time
        self.log("sensor", "测距传感器恢复" if online else "测距传感器断开", "过期阈值 0.5 仿真秒，故障时减速停车")

    def set_profile(self, profile):
        if profile not in PROFILES:
            raise ValueError("未知偏好")
        self.profile = profile
        self.replan()

    def gap(self):
        e = self.current_edge
        if not e or not self.obstacle or e["id"] != self.obstacle["edge"]:
            return None
        if self.lane != self.obstacle["lane"]:
            return None
        # Positions are centers; subtract the combined half-length (4.5 m).
        return self.obstacle["position"] - self.position - 4.5

    def tick(self, dt=.1):
        if not self.running or self.completed:
            return
        self.time = round(self.time + dt, 6)
        if self.sensor_online:
            self.sensor_timestamp = self.time
        stale = self.time - self.sensor_timestamp > .5
        e = self.current_edge
        gap = self.gap()
        decel, status, reason = 0.0, "CRUISE", "按路段目标速度行驶"
        if self.status == "NO_ROUTE" or not e:
            decel, status, reason = -4.0, "NO_ROUTE", "无可行路线，保持停车或减速停止"
        elif stale:
            decel, status, reason = -4.0, "DEGRADED", "测距观测超过 0.5 秒未更新，拒绝换道并减速停车"
        elif e["closed"]:
            decel, status, reason = -6.0, "BRAKE", "当前路段封闭，停车等待恢复"
        elif gap is not None and gap < max(50, self.speed * 4):
            if self.min_gap is None or gap < self.min_gap:
                self.min_gap = gap
            if not self.side_blocked and self.speed > 2 and gap > 8:
                self.changing = True
                decel, status, reason = -2.0, "AVOID", "侧方走廊在本简化场景内无车，减速并执行 2 秒换道"
            else:
                self.changing = False
                target = math.sqrt(max(0, 2 * 5.0 * (gap - 5.0)))
                decel = max(-7.0, min(0.0, (target - self.speed) / dt))
                # Brake early for the demo; stop with a visible residual clearance.
                if gap < self.speed * self.speed / 10 + 8:
                    decel = -6.0
                if self.speed < .1 and gap <= 8:
                    decel = 0
                status = "BRAKE" if gap < 25 or self.speed < 1 else "WARNING"
                reason = "侧方空间不足，拒绝换道；按制动距离减速" if self.side_blocked else "距离不足以换道，制动优先"
        else:
            target = e["limit"] / e["congestion"]
            decel = max(-3.0, min(2.0, (target - self.speed) / dt))
        if status != "AVOID":
            self.changing = False
            self.lane_progress = 0.0
        self.transition(status, reason)
        old_speed = self.speed
        self.speed = max(0.0, self.speed + decel * dt)
        self.acceleration = (self.speed - old_speed) / dt
        self.max_decel = max(self.max_decel, -self.acceleration)
        travel = (old_speed + self.speed) * .5 * dt
        self.position += travel
        self.distance += travel
        if self.changing:
            self.lane_progress = min(1.0, self.lane_progress + dt / 2)
            if self.lane_progress >= 1.0:
                self.lane, self.changing, self.lane_progress = 1, False, 0.0
                self.log("decision", "换道完成", "车辆转入相邻车道")
        new_gap = self.gap()
        if new_gap is not None and new_gap <= 0:
            self.collision, self.running, self.speed = True, False, 0.0
            self.transition("COLLISION", "简化模型检测到车辆重叠，场景已停止")
        if e and self.position >= e["length"]:
            self.position -= e["length"]
            self.edge_index += 1
            if self.edge_index >= len(self.route["edges"]):
                self.edge_index = len(self.route["edges"]) - 1
                self.distance -= self.position
                self.position = e["length"]
                self.speed = 0.0
                if e["target"] == "D":
                    self.completed, self.running = True, False
                    self.transition("ARRIVED", "已抵达科技园终点")
                else:
                    self.transition("NO_ROUTE", "已至当前路段边界，后续无可行路线；等待道路恢复")
        self.update_route_metrics()
        self.history.append({"time": round(self.time, 1), "speed": round(self.speed * 3.6, 1),
                             "acceleration": round(self.acceleration, 2)})
        self.history = self.history[-240:]

    def snapshot(self):
        e = self.current_edge
        a, b = (NODES[e["source"]], NODES[e["target"]]) if e else (NODES["A"], NODES["A"])
        ratio = min(1.0, self.position / e["length"]) if e else 0.0
        gap = self.gap()
        stale = self.time - self.sensor_timestamp > .5
        return {"engine": "builtin-2d", "run_id": self.run_id, "scenario": self.scenario,
                "scenario_name": SCENARIOS[self.scenario], "running": self.running,
                "completed": self.completed, "time": round(self.time, 1),
                "status": self.status, "reason": self.reason, "profile": self.profile,
                "nodes": NODES, "edges": list(self.edges.values()), "route": self.route,
                "route_available": self.route_available,
                "candidates": [plan(self.edges, profile=p) for p in PROFILES],
                "vehicle": {"x": a["x"] + (b["x"] - a["x"]) * ratio,
                            "y": a["y"] + (b["y"] - a["y"]) * ratio,
                            "angle": math.atan2(b["y"] - a["y"], b["x"] - a["x"]),
                            "edge": e["id"] if e else None, "lane": self.lane,
                            "lane_progress": self.lane_progress,
                            "speed": round(self.speed * 3.6, 1), "acceleration": round(self.acceleration, 2),
                            "distance": round(self.distance, 1), "gap": None if stale else gap,
                            "ttc": round(gap / self.speed, 2) if gap is not None and self.speed > .1 and not stale else None},
                "obstacle": self.obstacle, "side_blocked": self.side_blocked,
                "sensor": {"online": self.sensor_online, "stale": stale,
                           "last_update": round(self.sensor_timestamp, 1),
                           "age": round(self.time - self.sensor_timestamp, 1)},
                "metrics": {"replans": self.replans, "collision": self.collision,
                            "min_gap": round(self.min_gap, 2) if self.min_gap is not None else None,
                            "max_decel": round(self.max_decel, 2)},
                "history": self.history, "events": self.events,
                "behavior": {k: v for k, v in self.behavior.items() if k != "rows"}}
