"""Read-only Git overlay for the exact Scanner F dependency graph."""
import argparse
import io
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "work":"6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
    "core_c":"40ad0b4cf3b4b75b8ba55f524e79af3928b0673f",
    "core_d":"a86a590a5e2c32c18e03522f52896dbcf50c60ff",
    "core_f":"759507ea97548ae56e228b034dfb37a1d94f186f",
    "core_h":"99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
    "factory":"ef8d41b6ff273e4228e6b90210f4610dccf54251",
    "scanner_b":"30c37ae56851488b882998c7fa0085ec51dbfc92",
    "scanner227":"b9c9ff8602e79c534402f44bce83c56ec2fa6bb9",
    "raw":"7d97b09c0c6ee2650a61d523acb8d8c771a99c46",
}


def git(*args):
    return subprocess.check_output(["git","-c","core.autocrlf=false","-C",str(ROOT),*args])


def stage(output, fetch=False, working=False):
    output.mkdir()
    if fetch:
        for pin in PINS.values():
            git("fetch","--no-tags","origin",pin)
    def extract(pin,*paths):
        with tarfile.open(fileobj=io.BytesIO(git("archive",pin,*paths))) as archive:
            archive.extractall(output,filter="data")
    def modules(role,prefix):
        names = git("ls-tree","-r","--name-only",PINS[role],"research_wp_r0").decode().splitlines()
        chosen = [name for name in names if Path(name).name.startswith(prefix) and name.endswith(".py")]
        extract(PINS[role],*chosen)
    extract("HEAD","src","research_wp_r0","tools")
    for role,folder in (("work","strategy_service_offline"),("scanner_b","scanner_strategy_b"),
                        ("scanner227","scanner_engine_offline"),("raw","raw_vault_offline")):
        extract(PINS[role],"tools/"+folder)
    modules("core_c","aql_")
    modules("core_d","aql_core_d_")
    modules("core_f","aql_core_f_")
    extract(PINS["core_h"],"research_wp_r0/aql_core_backbone_local_v1.py")
    extract(PINS["factory"],*("research_wp_r0/"+name+".py" for name in (
        "aql_factory_historical_rule_projection","strategy_definition","indicator_library_v2",
        "aql_factory_authentic_research_admission","aql_p2_factory_real_development","aql_p2_factory_lab")))
    if working:
        for name in ("p0_slice.py","p0_delivery.py","test_p0_slice.py","p0_evidence.py"):
            relative = Path("tools/scanner_strategy_f")/name
            if (ROOT/relative).exists():
                (output/relative).write_bytes((ROOT/relative).read_bytes())


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--fetch",action="store_true")
    parser.add_argument("--working",action="store_true")
    args=parser.parse_args()
    stage(args.output.resolve(),args.fetch,args.working)
