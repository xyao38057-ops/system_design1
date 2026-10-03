import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.network import fresh_edges, plan
from app.simulation import Simulation
from app.behavior import analyze
from app.storage import Storage
from server import Application, handler_for
from tools.export_sumo import export


def advance(sim, seconds):
    sim.running = True
    for _ in range(round(seconds * 10)):
        sim.tick(.1)


class RoutingTests(unittest.TestCase):
    def test_preferences_choose_three_distinct_routes(self):
        routes = [plan(fresh_edges(), profile=p)["edges"] for p in ("balanced", "fast", "comfort")]
        self.assertIn("BC", routes[0])
        self.assertIn("EF", routes[1])
        self.assertIn("GH", routes[2])

    def test_closed_edge_never_selected(self):
        edges = fresh_edges()
        edges["BC"]["closed"] = True
        self.assertNotIn("BC", plan(edges)["edges"])

    def test_no_route_is_explicit(self):
        edges = fresh_edges()
        for eid in ("BC", "BE", "BG"):
            edges[eid]["closed"] = True
        self.assertIsNone(plan(edges))

    def test_congestion_updates_fastest_route(self):
        edges = fresh_edges()
        edges["EF"]["congestion"] = 10
        self.assertIn("BC", plan(edges, profile="fast")["edges"])

    def test_mid_edge_replan_preserves_location(self):
        sim = Simulation()
        advance(sim, 3)
        before = sim.snapshot()["vehicle"]
        sim.set_road("BC", "close")
        after = sim.snapshot()["vehicle"]
        self.assertEqual((before["x"], before["y"]), (after["x"], after["y"]))
        self.assertNotIn("BC", sim.route["edges"])

    def test_congestion_demo_changes_default_route(self):
        sim = Simulation()
        self.assertIn("BC", sim.route["edges"])
        sim.set_road("BC", "congestion")
        self.assertNotIn("BC", sim.route["edges"])

    def test_mid_edge_no_route_and_recovery(self):
        sim = Simulation()
        advance(sim, 3)
        for eid in ("BC", "BE", "BG"):
            sim.set_road(eid, "close")
        advance(sim, 10)
        self.assertEqual(sim.status, "NO_ROUTE")
        self.assertFalse(sim.completed)
        self.assertEqual(sim.speed, 0)
        sim.set_road("BC", "restore")
        advance(sim, 200)
        self.assertTrue(sim.completed)

    def test_dead_end_is_not_reported_as_destination(self):
        sim = Simulation()
        sim.position = sim.edges["AB"]["length"] - .1
        sim.speed = 14
        for eid in ("BC", "BE", "BG"):
            sim.set_road(eid, "close")
        advance(sim, 2)
        self.assertFalse(sim.completed)
        self.assertEqual(sim.status, "NO_ROUTE")
        self.assertFalse(sim.snapshot()["route_available"])
        self.assertEqual(sim.snapshot()["vehicle"]["x"], 300)
        sim.set_road("BC", "restore")
        advance(sim, 200)
        self.assertTrue(sim.completed)


class SimulationTests(unittest.TestCase):
    def test_normal_journey_completes(self):
        sim = Simulation()
        advance(sim, 200)
        self.assertTrue(sim.completed)
        self.assertEqual(sim.status, "ARRIVED")
        self.assertAlmostEqual(sim.snapshot()["vehicle"]["x"], 830)
        self.assertFalse(sim.collision)

    def test_blocked_side_lane_brakes_without_collision(self):
        sim = Simulation()
        sim.reset("brake")
        advance(sim, 15)
        self.assertEqual(sim.lane, 0)
        self.assertEqual(sim.speed, 0)
        self.assertGreater(sim.gap(), 0)
        self.assertFalse(sim.collision)
        self.assertIn("拒绝换道", sim.reason)

    def test_available_side_lane_allows_avoidance(self):
        sim = Simulation()
        sim.reset("avoid")
        advance(sim, 6)
        self.assertEqual(sim.lane, 1)
        self.assertFalse(sim.collision)
        self.assertIn("换道完成", [e["title"] for e in sim.events])

    def test_sensor_failure_stops_and_recovers(self):
        sim = Simulation()
        sim.reset("sensor")
        advance(sim, 6)
        self.assertEqual(sim.status, "DEGRADED")
        self.assertEqual(sim.speed, 0)
        self.assertIsNone(sim.snapshot()["vehicle"]["gap"])
        sim.set_sensor(True)
        advance(sim, 2)
        self.assertEqual(sim.status, "CRUISE")
        self.assertGreater(sim.speed, 0)

    def test_pause_does_not_advance_clock(self):
        sim = Simulation()
        sim.tick()
        self.assertEqual(sim.time, 0)

    def test_reset_clears_faults_and_metrics(self):
        sim = Simulation()
        sim.reset("brake")
        advance(sim, 10)
        sim.reset()
        self.assertIsNone(sim.obstacle)
        self.assertFalse(sim.side_blocked)
        self.assertEqual(sim.max_decel, 0)
        self.assertEqual(sim.status, "READY")

    def test_no_route_never_moves(self):
        sim = Simulation()
        sim.reset("no_route")
        advance(sim, 10)
        self.assertEqual(sim.speed, 0)
        self.assertEqual(sim.distance, 0)
        self.assertEqual(sim.status, "NO_ROUTE")

    def test_snapshots_have_no_nan_or_infinity(self):
        for scenario in ("normal", "brake", "avoid", "sensor", "no_route", "closure", "congestion"):
            sim = Simulation()
            sim.reset(scenario)
            advance(sim, 8)
            json.dumps(sim.snapshot(), allow_nan=False)


class DataTests(unittest.TestCase):
    def test_behavior_samples_are_reproducible_and_distinct(self):
        self.assertEqual(analyze("active"), analyze("active"))
        self.assertGreater(analyze("active")["hard_brake"], analyze("steady")["hard_brake"])
        self.assertIn("模拟", analyze()["source"])

    def test_events_persist_across_database_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sqlite3"
            sim = Simulation()
            store = Storage(path)
            store.save(sim)
            store.save(sim)
            again = Storage(path)
            self.assertEqual(len(again.runs()), 1)
            csv = again.export_csv().decode("utf-8-sig")
            self.assertEqual(csv.count("场景已重置"), 1)

    def test_sumo_xml_references_valid_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            export(Path(tmp))
            edges = {e.attrib["id"] for e in ET.parse(Path(tmp) / "campus.edg.xml").getroot()}
            routes = ET.parse(Path(tmp) / "campus.rou.xml").getroot()
            for route in routes.findall("route"):
                self.assertTrue(set(route.attrib["edges"].split()) <= edges)
            self.assertEqual(len(routes.findall("vehicle")), 25)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.app = Application(Path(cls.temp.name) / "http.sqlite3")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(cls.app))
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def call(self, data):
        return urlopen(Request(self.base + "/api/action", data=json.dumps(data).encode(),
                               headers={"Content-Type": "application/json"}), timeout=5)

    def test_home_and_assets(self):
        for path in ("/", "/app.js", "/style.css"):
            with urlopen(self.base + path) as result:
                self.assertEqual(result.status, 200)
                self.assertGreater(len(result.read()), 100)

    def test_state_and_action(self):
        with self.call({"action": "scenario", "scenario": "brake"}) as result:
            body = json.load(result)
            self.assertTrue(body["running"])
            self.assertTrue(body["side_blocked"])

    def test_invalid_action_returns_400(self):
        with self.assertRaises(HTTPError) as result:
            self.call({"action": "road", "edge": "fake", "operation": "close"})
        self.assertEqual(result.exception.code, 400)

    def test_database_not_public(self):
        with self.assertRaises(HTTPError) as result:
            urlopen(self.base + "/data/driverlab.sqlite3")
        self.assertEqual(result.exception.code, 404)

    def test_export_is_downloadable_csv(self):
        with urlopen(self.base + "/api/export") as result:
            self.assertIn("attachment", result.headers["Content-Disposition"])
            self.assertIn("run_id", result.read().decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
