"""Offline CLI. Network download and independent hash retention are external steps."""
import sys
import json
from pathlib import Path
from research_wp_r0.pinned_ema_research import run_pinned_ema_development


def main():
    options = ("--archive", "--plan-arguments", "--expected-plan-sha256", "--output")
    argv = sys.argv[1:]
    if len(argv) != 8 or set(argv[::2]) != set(options):
        raise SystemExit("Required: --archive ZIP --plan-arguments JSON --expected-plan-sha256 SHA --output NEW_JSON")
    args = dict(zip(argv[::2], argv[1::2]))
    plan = json.loads(Path(args["--plan-arguments"]).read_text(encoding='utf-8'))
    report = run_pinned_ema_development(args["--archive"],
        expected_plan_sha256=args["--expected-plan-sha256"], **plan)
    with Path(args["--output"]).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    print(report['replay_sha256'])


if __name__ == '__main__':
    main()
