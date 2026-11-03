"""python -m raadzaal <step> [options]"""
import argparse
import sys

from raadzaal import config, db

STEPS = ["discover", "councils", "agenda", "fetch", "transcribe", "diarise", "regroup", "speakers", "align", "summarise", "names", "build", "topics", "translate", "report", "all", "status"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="raadzaal", description="Flemish council meetings, transcribed and searchable.")
    p.add_argument("step", choices=STEPS)
    p.add_argument("--municipality", "-m", help="slug from municipalities.yaml")
    p.add_argument("--session", "-s", action="append", help="session id (YouTube video id); repeatable")
    p.add_argument("--limit", type=int, default=0, help="stop after N sessions")
    p.add_argument("--force", action="store_true", help="redo the step even when done")
    p.add_argument("--eval", action="store_true", help="align: print the evaluation against the gold spans")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config.ensure_dirs()
    con = db.connect()
    for m in config.municipalities():
        db.upsert_municipality(con, m)
    con.commit()
    if args.step == "status":
        return cmd_status(con)
    from raadzaal import steps
    return steps.run(args.step, con, args)


def cmd_status(con) -> int:
    rows = con.execute(
        "SELECT municipality, status, COUNT(*) n, ROUND(SUM(duration_s)/3600.0,1) hours FROM sessions "
        "GROUP BY municipality, status ORDER BY municipality, status").fetchall()
    if not rows:
        print("no sessions yet; run discover")
        return 0
    for r in rows:
        print(f"{r['municipality']:<12} {r['status']:<12} {r['n']:>3}  {r['hours'] or 0:>5} h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
