"""Prepare full-day activity and rate runs in separate Phase 1B databases."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys,io,json,xml.etree.ElementTree as ET
import pandas as pd
from paths import MOVES_HOME
sys.path.insert(0,str(locate("phase1a")))  # needs Phase 1A MOVES helpers (not included)
from moves_db import query
SOURCE="phase1a_nyc2025_input_20261002"
def main():
    names=pd.read_csv(io.StringIO(query(f"SHOW TABLES FROM {SOURCE}")),sep="\t").iloc[:,0]
    configs={}
    for kind in ["activity","rates"]:
        inp=f"phase1b_nyc2025_full_{kind}_input_20261002"
        out=f"phase1b_nyc2025_full_{kind}_output_20261002"
        for db in [inp,out]:
            result=query(f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{db}'")
            if len(result.strip().splitlines())>1:raise RuntimeError("Database exists: "+db)
        query(f"CREATE DATABASE {inp}")
        for name in names:
            query(f"CREATE TABLE {inp}.`{name}` LIKE {SOURCE}.`{name}`; INSERT INTO {inp}.`{name}` SELECT * FROM {SOURCE}.`{name}`;")
        tree=ET.parse(locate("phase1a/phase1a_full.mrs"));root=tree.getroot()
        root.find("description").text=f"Phase 1B full-day {kind}; same EPA inputs as Phase 1A; national default activity normalization, not measured local inventory."
        root.find("scaleinputdatabase").set("databasename",inp)
        root.find("outputdatabase").set("databasename",out)
        root.find("timespan/beginhour").set("id","1");root.find("timespan/endhour").set("id","24")
        if kind=="activity":
            root.find("modelscale").set("value","Inventory")
            for elem in list(root.find("pollutantprocessassociations")):
                if elem.get("pollutantkey")!="3":root.find("pollutantprocessassociations").remove(elem)
        ET.indent(root)
        path=locate(f"phase1b/provenance/full_day_{kind}.mrs");tree.write(path,encoding="utf-8",xml_declaration=True)
        command='@echo off\ncd /d "'+MOVES_HOME+'"\ncall setenv.bat\ncall ant run -Drunspec="'+str(path)+'" > "'+str(locate(f"phase1b/provenance/full_day_{kind}_console.log"))+'" 2>&1\nexit /b %errorlevel%\n'
        (locate(f"phase1b/code/run_full_day_{kind}.cmd")).write_text(command)
        configs[kind]=dict(input_database=inp,output_database=out,runspec=str(path),hours=list(range(1,25)),months=list(range(1,11)),year=2025)
    (locate("phase1b/provenance/supplemental_run_configuration.json")).write_text(json.dumps(configs,indent=2))
if __name__=="__main__":main()

