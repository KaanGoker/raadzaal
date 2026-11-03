"""Dispatch of the pipeline steps. Each module exposes run(con, session) and the order is fixed."""
from raadzaal import db

ORDER = ["agenda", "fetch", "transcribe", "diarise", "regroup", "align", "speakers", "summarise", "names"]


# the status a session has once the step is done; steps without one (agenda, speakers) run on every eligible session
DONE = {"fetch": "downloaded", "transcribe": "transcribed", "diarise": "diarised", "align": "aligned", "summarise": "summarised"}


def _select(con, args, needs: str | None, step: str | None = None):
    """Sessions to process: filtered by the CLI, by the status they must have reached, and, unless --force,
    only those the step has not done yet. An explicit --session always runs."""
    rows = db.sessions(con, municipality=args.municipality, ids=args.session)
    if needs:
        rows = [r for r in rows if db.status_index(r["status"]) >= db.status_index(needs)]
    if step in DONE and not args.force and not args.session:
        rows = [r for r in rows if db.status_index(r["status"]) < db.status_index(DONE[step])]
    if args.limit:
        rows = rows[: args.limit]
    return rows


def run(step: str, con, args) -> int:
    from raadzaal import discover, agenda, fetch, transcribe, diarise, regroup, speakers, align, summarise, namecheck, build, report
    mods = {"agenda": agenda, "fetch": fetch, "transcribe": transcribe, "diarise": diarise, "regroup": regroup,
            "speakers": speakers, "align": align, "summarise": summarise, "names": namecheck}
    needs = {"agenda": "found", "fetch": "found", "transcribe": "downloaded", "diarise": "transcribed", "regroup": "diarised",
             "align": "diarised", "speakers": "aligned", "summarise": "aligned", "names": "summarised"}
    if step == "discover":
        return discover.run(con, args)
    if step == "councils":
        from raadzaal import councils
        return councils.run(con, args)
    if step == "build":
        return build.run(con, args)
    if step == "translate":
        from raadzaal import translate
        return translate.run(con, args)
    if step == "report":
        return report.run(con, args, align.eval_lines(con))
    if step == "all":
        discover.run(con, args)
        for s in ORDER:
            for row in _select(con, args, needs[s], s):
                mods[s].run(con, row, args)
        build.run(con, args)
        return report.run(con, args, align.eval_lines(con))
    if step == "align" and args.eval:
        return align.evaluate(con, args)
    rc = 0
    for row in _select(con, args, needs[step], step):
        rc |= int(bool(mods[step].run(con, row, args)))
    return rc
