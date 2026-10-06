# vehicles - build the SABoW Ext vehicle list from the game's own files.
# READ-ONLY. Part of the SABoW Ext tool.
#
# This is Phase 1's data: every vehicle unit in the game, what kind of vehicle
# it is, whether it is already crewable, whether its cockpit exists, and where
# it comes from (base game, or the Basra 86 DLC).
#
# Everything here is read straight out of the installed game - nothing is
# assumed. What was learned building it, 2026-09-15:
#
#   WHERE THE FACTS LIVE
#     div_units_misc / units    one row per UNIT. field 3 = the vehicle,
#                               field 11 = crewable (BoW43's "field 15"),
#                               field 12 = cockpit name
#     cocpits                   one block per cockpit that exists
#     techn_base_mtc80          one entry per VEHICLE: a name block followed
#                               by its own props / heads / work_places /
#                               sights blocks
#     props["type"]             the vehicle class, a four-letter code:
#                               TANK FTAN APC ACAR GUN ATG MORT MGUN AAG ...
#     div_units_misc / squads   which units each squad fields
#
#   DLC
#     The Basra 86 DLC holds NO vehicle tables - only a map, a campaign and a
#     mission. Its campaign names squads, not units. So "DLC" is worked out by
#     following campaign -> squad -> unit, and a vehicle is:
#       base          fielded by base-game campaigns or quick battle
#       base + DLC    fielded by both
#       DLC only      fielded only by DLC content
#     Names are matched as WHOLE WORDS. Partial matching gave a false "DLC only"
#     on the first run.
#
#     Result on the clean Steam 2899 install: NO vehicle is DLC-only. The Iranian
#     vehicles are base game - the base game has its own 1981 Susengerd campaign.

import glob
import os
import re

import azcf

ARMOUR = ("TANK", "FTAN", "APC", "ACAR")

NAMES = {
    "TANK": "tank", "FTAN": "flamethrower tank", "APC": "armoured carrier",
    "ACAR": "armoured car", "GUN": "gun", "ATG": "anti-tank", "MORT": "mortar",
    "MGUN": "machine gun", "AAG": "anti-aircraft gun", "AASP": "self-propelled AA",
    "CAR": "truck", "UNK": "aircraft",
}


def paths(install):
    data = os.path.join(install, "data", "mtc80")
    return {
        "tabs": os.path.join(data, "shared", "packed_data", "tabs.flatdata"),
        "data": data,
        "dlc": [d for d in glob.glob(os.path.join(data, "dlc_*")) if os.path.isdir(d)],
    }


def four_cc(value):
    """The vehicle class code. Three-letter codes carry a padding byte, which
    made every APC read as "not armour" until it was stripped."""
    if not isinstance(value, int):
        return "?"
    return value.to_bytes(4, "little").decode("latin1").rstrip("\x00 ")


CONTENT = (".campack2", ".mispack", ".cfgpack", ".addpack")
WORD = re.compile(rb"[A-Za-z0-9_]+")


def _names_in(files, extra=()):
    """Every whole identifier in these files, as one set.

    Checking "is this squad name one of the identifiers" is the whole-word rule
    by construction, and a set lookup is instant. The first draft searched every
    file again for every squad name, and read the DLC's 300 MB of terrain too -
    it ran for over five minutes without finishing.
    """
    names = set()
    for f in files:
        try:
            with open(f, "rb") as fh:
                names.update(WORD.findall(fh.read()))
        except OSError:
            pass
    for blob in extra:
        names.update(WORD.findall(blob))
    return names


PASSENGER = "sig_pass"   # passenger seats; unresolved even on stock vehicles that play


def recipe(techn_t, blocks, crewable, cockpit, cockpit_exists, sight_rows):
    """The five recipe checks for one vehicle, from its own data.

    Field positions are the ones BoW43's vehaudit.py uses, not counted afresh:
    a seat's sight group is work_places field 10 (0-based), and the group a
    sights row belongs to is sights field 4 - reading field 0 instead was a real
    mistake once (BoW43 notes/38). A sights row: 0 name, 1 camera, 2 the sight
    it uses, 4 its group, 8 its head (vertical aim).

    Check 4 is NOT "a _sight_hole row". That name came from the Steel Fury
    Panzer IV rows (BoW43 notes/73) and appears in none of the stock tables. For
    stock vehicles the rule behind the 99% load error is: every crew seat's
    group must have at least one sight.

    Returns [(label, ok, detail)] and a list of smaller warnings.
    """
    checks, warnings = [], []
    checks.append(("1  Cockpit", bool(cockpit) and cockpit_exists,
                   ("%s" % cockpit) if cockpit_exists else
                   ("%s is named but missing" % cockpit if cockpit else "none")))
    checks.append(("2  Crewable", crewable, "yes" if crewable else "no - AI only"))

    wp = techn_t.rows(blocks["work_places"]) if "work_places" in blocks else []
    si = techn_t.rows(blocks["sights"]) if "sights" in blocks else []
    # A seat with NO group is a seat without its own view - passenger seats on
    # the Olifant, BTR-60 and M113 are like this, and the Olifant PLAYED with
    # exactly that data (BoW43 notes/15). The first draft counted such seats as
    # broken and called the Olifant "not possible", which that note disproves.
    seats = [r for r in wp if str(r[0]).startswith("wp_") and r[10] and r[10] != PASSENGER]
    checks.append(("3  Crew seats name a sight group", bool(seats),
                   ("%d seats with a view: %s" % (len(seats), ", ".join(r[0].replace("wp_", "") for r in seats)))
                   if seats else "no seat has a view - nowhere to put a crew"))

    groups = {}
    for r in si:
        groups.setdefault(r[4], []).append(r)
    # The real load-error risk (vehaudit's rule): a seat naming a group that has
    # no sights at all.
    blind = sorted({r[10] for r in seats if r[10] not in groups})
    checks.append(("4  Every crew seat has a sight to look through", bool(seats) and not blind,
                   ", ".join("%s %d" % (g.replace("sig_", ""), len(groups.get(g, [])))
                             for g in sorted({r[10] for r in seats}))
                   if seats and not blind else
                   ("no crew seats" if not seats else "nothing to look through: " + ", ".join(blind))))

    gunner = [r for r in groups.get("sig_gunner", [])]
    aimed = [r for r in gunner if r[8] and r[2] in sight_rows]
    checks.append(("5  Gunner can aim up and down", bool(aimed),
                   ("%s with %s" % (aimed[0][2], aimed[0][8])) if aimed else
                   ("no gunner sight" if not gunner else "gunner sights have no head")))

    missing = sorted({r[2] for r in si if r[2] and r[2] not in sight_rows})
    if missing:
        warnings.append("names sights that do not exist: " + ", ".join(missing))
    for g in ("sig_gunner", "sig_commander"):
        no_head = [r[2] for r in groups.get(g, []) if not r[8]]
        if g == "sig_commander" and groups.get(g) and len(no_head) == len(groups[g]):
            warnings.append("the commander has no sight with vertical aim")
        elif g == "sig_gunner" and aimed and no_head:
            warnings.append("gunner sights without vertical aim: " + ", ".join(sorted(set(no_head))))
    return checks, warnings


# Answers known from real play-tests, not from this code. If the checks ever
# disagree with these, the checks are wrong - the play-test is the evidence.
KNOWN = {
    "t62": ("playable", "stock, crewable in the shipped game"),
    "m60a1": ("playable", "stock, crewable in the shipped game"),
    "olifant": ("easy", "BoW43 notes/15: played with only crewable + coc_t62 added"),
}


def known_answers(vs):
    """[problem] - every place the checks disagree with a real play-test."""
    problems = []
    for v in vs:
        if v["vehicle"] in KNOWN:
            want, why = KNOWN[v["vehicle"]]
            if v["verdict"] != want:
                problems.append("%s came out '%s' but should be '%s' (%s)"
                                % (v["vehicle"], v["verdict"], want, why))
    return problems


def verdict(checks):
    ok = {label[0]: passed for label, passed, detail in checks}
    if all(ok.values()):
        return "playable"
    if ok.get("3") and ok.get("4") and ok.get("5"):
        return "easy"               # only the unit-level switches are missing
    if not ok.get("3"):
        return "not possible"       # no crew seats to put anyone in
    return "needs work"


def build(install):
    """[dict] - one entry per vehicle unit in the game."""
    p = paths(install)
    units_t = azcf.Table(azcf.read_record(p["tabs"], "div_units_misc"))
    techn_t = azcf.Table(azcf.read_record(p["tabs"], "techn_base_mtc80"))
    cockpits = {b.name for b in azcf.Table(azcf.read_record(p["tabs"], "cocpits")).blocks}
    techn = dict(azcf.vehicles(techn_t))
    sight_rows = set()
    for tname in ("common_res", "common_res_mod"):
        st = azcf.Table(azcf.read_record(p["tabs"], tname))
        for b in st.find("sights"):
            sight_rows.update(r[0] for r in st.rows(b))

    units = [r for r in units_t.rows(units_t.find("units")[0]) if r[1] == "i_techn"]
    by_name = {r[0]: r for r in units}

    squads_of = {}
    for r in units_t.rows(units_t.find("squads")[0]):
        for x in r:
            if isinstance(x, str) and x in by_name:
                squads_of.setdefault(x, set()).add(r[0])

    dlc_files = [f for d in p["dlc"] for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                 if os.path.isfile(f) and f.lower().endswith(CONTENT)]
    base_files = [f for f in glob.glob(os.path.join(p["data"], "**", "*"), recursive=True)
                  if os.path.isfile(f) and not any(f.startswith(d) for d in p["dlc"])
                  and f.lower().endswith(CONTENT)]
    dlc_names = _names_in(dlc_files)
    base_names = _names_in(base_files, extra=[azcf.read_record(p["tabs"], "qbattle")])

    out = []
    for r in units:
        name, vehicle, crewable, cockpit = r[0], r[3], bool(r[11]), r[12]
        blocks = techn.get(vehicle, {})
        props = techn_t.props(blocks["props"]) if "props" in blocks else {}
        code = four_cc(props.get("type"))
        sq = [s.encode() for s in squads_of.get(name, ())]
        in_base = any(s in base_names for s in sq)
        in_dlc = any(s in dlc_names for s in sq)
        if in_dlc and not in_base:
            source = "DLC only"
        elif in_dlc:
            source = "base + DLC"
        elif in_base:
            source = "base"
        else:
            source = "not fielded in a campaign"
        cockpit_exists = bool(cockpit) and cockpit in cockpits
        checks, warnings = recipe(techn_t, blocks, crewable, cockpit, cockpit_exists, sight_rows)
        out.append({
            "unit": name,
            "vehicle": vehicle,
            "code": code,
            "kind": NAMES.get(code, code),
            "armour": code in ARMOUR,
            "crewable": crewable,
            "cockpit": cockpit,
            "cockpit_exists": cockpit_exists,
            "source": source,
            "dlc": in_dlc,
            "blocks": sorted(blocks),
            "checks": checks,
            "warnings": warnings,
            "verdict": verdict(checks),
        })
    out.sort(key=lambda v: (not v["armour"], not v["crewable"], v["code"], v["vehicle"]))
    return out


if __name__ == "__main__":
    import sys
    install = sys.argv[1] if len(sys.argv) > 1 else __import__("settings").get("live")
    ok, msg = azcf.self_test(paths(install)["tabs"])
    print(("OK  " if ok else "FAIL  ") + msg)
    if not ok:
        sys.exit(1)
    vs = build(install)
    armour = [v for v in vs if v["armour"]]
    print("\n%d vehicle units, %d of them armour\n" % (len(vs), len(armour)))
    print("%-16s %-18s %-9s %-11s %s" % ("vehicle", "kind", "crewable", "cockpit", "source"))
    for v in armour:
        coc = (v["cockpit"] + ("" if v["cockpit_exists"] else " MISSING")) if v["cockpit"] else "-"
        print("%-16s %-18s %-9s %-11s %s" % (v["vehicle"], v["kind"], "YES" if v["crewable"] else "no", coc, v["source"]))
    ai = [v for v in armour if not v["crewable"]]
    print("\nAI-only armour: %d    DLC-only vehicles of any kind: %d"
          % (len(ai), sum(1 for v in vs if v["source"] == "DLC only")))
    problems = known_answers(vs)
    print("\nknown answers: " + ("all agree with real play-tests" if not problems else
                                 "DISAGREE - the checks are wrong:\n  " + "\n  ".join(problems)))
    print("\nverdicts, armour:")
    for v in armour:
        print("  %-12s %s" % (v["vehicle"], v["verdict"]))
    for name in ("t62", "t55"):
        v = next(x for x in vs if x["vehicle"] == name)
        print("\n%s   verdict: %s" % (name.upper(), v["verdict"]))
        for label, passed, detail in v["checks"]:
            print("   %s  %-48s %s" % ("OK" if passed else "X ", label, detail))
        for w in v["warnings"]:
            print("   note: " + w)
