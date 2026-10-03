"""Export the course road network to SUMO. No SUMO installation needed to export XML."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.network import NODES, PROFILES, fresh_edges, plan


def write(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def export(output):
    output.mkdir(parents=True, exist_ok=True)
    nodes = ET.Element("nodes")
    for key, node in NODES.items():
        ET.SubElement(nodes, "node", id=key, x=str(node["x"]), y=str(530 - node["y"]), type="priority")
    edges = ET.Element("edges")
    network = fresh_edges()
    for eid, edge in network.items():
        ET.SubElement(edges, "edge", {"id": eid, "from": edge["source"], "to": edge["target"],
                                     "numLanes": "2", "speed": str(edge["limit"]), "priority": "2"})
    routes = ET.Element("routes")
    ET.SubElement(routes, "vType", id="passenger", accel="2.0", decel="4.5", sigma="0", length="4.5", minGap="2.5", maxSpeed="25")
    for profile in PROFILES:
        ET.SubElement(routes, "route", id=profile, edges=" ".join(plan(network, profile=profile)["edges"]))
    ET.SubElement(routes, "vehicle", id="ego", type="passenger", route="balanced", depart="0", color="0,1,0.8")
    for i in range(1, 25):
        ET.SubElement(routes, "vehicle", id=f"background_{i}", type="passenger",
                      route=list(PROFILES)[i % 3], depart=str(i * 2), departLane="best")
    config = ET.Element("configuration")
    inputs = ET.SubElement(config, "input")
    ET.SubElement(inputs, "net-file", value="campus.net.xml")
    ET.SubElement(inputs, "route-files", value="campus.rou.xml")
    time = ET.SubElement(config, "time")
    ET.SubElement(time, "step-length", value="0.1")
    ET.SubElement(time, "end", value="300")
    for tree, name in [(nodes, "campus.nod.xml"), (edges, "campus.edg.xml"),
                       (routes, "campus.rou.xml"), (config, "campus.sumocfg")]:
        write(tree, output / name)


def main():
    parser = argparse.ArgumentParser(description="Generate an independent SUMO scenario (not connected to the web dashboard)")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "sumo")
    parser.add_argument("--build", action="store_true", help="Run installed netconvert to build the SUMO network")
    parser.add_argument("--netconvert", default="netconvert", help="Executable name or absolute path")
    args = parser.parse_args()
    output = args.output.resolve()
    export(output)
    print(f"XML scenario exported: {output}")
    if args.build:
        executable = shutil.which(args.netconvert)
        if not executable:
            parser.exit(1, "netconvert was not found. Install SUMO binaries, then use --netconvert with its full path.\n")
        subprocess.run([executable, "--node-files", str(output / "campus.nod.xml"),
                        "--edge-files", str(output / "campus.edg.xml"),
                        "--output-file", str(output / "campus.net.xml")], check=True)
        print(f'SUMO GUI command: sumo-gui -c "{output / "campus.sumocfg"}"')
    else:
        print("After installing SUMO, run this script with --build to generate campus.net.xml.")
    print("This SUMO scenario is independent. The dashboard still uses the built-in 2-D engine.")


if __name__ == "__main__":
    main()
