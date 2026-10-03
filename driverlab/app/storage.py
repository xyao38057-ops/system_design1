import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with database(self.path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    scenario TEXT, profile TEXT, elapsed REAL, status TEXT, metrics TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, sim_time REAL,
                    kind TEXT, title TEXT, detail TEXT);
            ''')

    def save(self, sim):
        snap = sim.snapshot()
        with database(self.path) as db:
            db.execute('''INSERT INTO runs(id,scenario,profile,elapsed,status,metrics)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                profile=excluded.profile,elapsed=excluded.elapsed,status=excluded.status,metrics=excluded.metrics''',
                       (sim.run_id, sim.scenario, sim.profile, sim.time, sim.status,
                        json.dumps(snap["metrics"], ensure_ascii=False)))
            db.executemany("INSERT INTO events(run_id,sim_time,kind,title,detail) VALUES(?,?,?,?,?)",
                           [(e["run_id"], e["time"], e["kind"], e["title"], e["detail"])
                            for e in sim.pending_events])
        sim.pending_events.clear()

    def runs(self):
        with database(self.path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 50")]

    def export_csv(self):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["run_id", "simulation_seconds", "kind", "title", "detail"])
        with database(self.path) as db:
            writer.writerows(db.execute("SELECT run_id,sim_time,kind,title,detail FROM events ORDER BY id"))
        return output.getvalue().encode("utf-8-sig")
