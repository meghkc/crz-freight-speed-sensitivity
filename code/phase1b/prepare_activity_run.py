"""Clone the Phase 1A configuration for distance activity; preserve its databases."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys, io, json
import xml.etree.ElementTree as ET
import pandas as pd
sys.path.insert(0,str(locate("phase1a")))  # needs Phase 1A MOVES helpers (not included)
from moves_db import query
SOURCE="phase1a_nyc2025_input_20261002"
INPUT="phase1b_nyc2025_activity_input_20261002"
OUTPUT="phase1b_nyc2025_activity_output_20261002"
def main():
    names=pd.read_csv(io.StringIO(query(f"SHOW TABLES FROM {SOURCE}")),sep="\t").iloc[:,0]
    for db in (INPUT,OUTPUT):
        exists=query(f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{db}'")
        if len(exists.strip().splitlines())>1: raise RuntimeError("Refusing existing schema "+db)
    query(f"CREATE DATABASE {INPUT};")
    for name in names:
        query(f"CREATE TABLE {INPUT}.`{name}` LIKE {SOURCE}.`{name}`; INSERT INTO {INPUT}.`{name}` SELECT * FROM {SOURCE}.`{name}`;")
    tree=ET.parse(locate("phase1a/phase1a_full.mrs")); root=tree.getroot()
    root.find("description").text="Phase 1B activity diagnostic; EPA-default composition, not measured local VMT; emissions are not used."
    root.find("modelscale").set("value","Inventory")
    root.find("scaleinputdatabase").set("databasename",INPUT)
    root.find("outputdatabase").set("databasename",OUTPUT)
    for elem in list(root.find("pollutantprocessassociations")):
        if elem.get("pollutantkey")!="3": root.find("pollutantprocessassociations").remove(elem)
    root.find("outputvmtdata").set("value","true")
    ET.indent(root)
    tree.write(locate("phase1b/provenance/activity_run.mrs"),encoding="utf-8",xml_declaration=True)
    (locate("phase1b/provenance/activity_run_configuration.json")).write_text(json.dumps(dict(source_input=SOURCE,cloned_input=INPUT,output=OUTPUT,purpose="Distance activity only; diagnostic NOx outputs not used as rates"),indent=2))
if __name__=="__main__": main()

