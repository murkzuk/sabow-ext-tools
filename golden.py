# golden - the tool's own proof that it reaches a proven build. Part of SABoW Ext.
#
# Works out the T-55's recipe from the game (recipe.derive), ticks the choices murkz
# tested (recipe.V9_CHOICES), builds it, and compares every table in the result
# with the ones in the proven v9 zip. PASS only if all three are byte-identical.
#
# If a later build is proven and becomes the reference, change GOLDEN and the
# choices together - never loosen the comparison.
#
#   python golden.py

import hashlib
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402
import build  # noqa: E402
import recipe  # noqa: E402

GOLDEN = r"L:\sabow-ext-backups\v009_PROVEN_T55_ALL_CREW\sabow_ext_v009.zip"
UNIT = "sau_t55"
CHOICES = dict(recipe.V9_CHOICES, own_sight=False, drop_missing_hide=False)     # v9 used the borrowed TSh-2B-41
# drop_missing_hide=False everywhere below: every build proven before 2026-09-16 shipped the
# donor's d_hole_01/d_hole_02 hide rows (the cockpit-ceiling bug), so reproducing them
# byte for byte means keeping those rows.

# Further proven builds the tool must still reproduce: (unit, choices, zip, version).
# v12 is the first tool-made build proven with the vehicle table shipped (the
# Olifant, built with the window's default ticks). Added 2026-09-15, after the
# weapon rules changed for the Chieftain.
MORE = [
    ("saru_olifant", {"drop_missing_hide": False}, r"L:\sabow-ext-backups\v012_PROVEN_SARU_OLIFANT\sabow_ext_v012.zip", 12),
    # the Chieftain, proven GOOD with the own-mount weapon rule and the fallback shell.
    # v14 used the borrowed M105D, so its own sight is ticked off here.
    ("iru_chief_mk5", {"own_sight": False, "drop_missing_hide": False}, r"L:\sabow-ext-backups\v014_PROVEN_IRU_CHIEF_MK5\sabow_ext_v014.zip", 14),
    # the Chieftain with its own TLS No. 1 sight - the reticle mesh must rebuild too
    ("iru_chief_mk5", {"drop_missing_hide": False}, r"L:\sabow-ext-backups\v015_PROVEN_IRU_CHIEF_MK5\sabow_ext_v015.zip", 15),
    # the T-55 with its own TSh-2B-32P (no zoom record), on v9's ticks
    ("sau_t55", dict(recipe.V9_CHOICES, own_sight_zoom=False, ammo_text=False, drop_missing_hide=False),
     r"L:\sabow-ext-backups\v021_PROVEN_SAU_T55\sabow_ext_v021.zip", 21),
    # ... and with its own 7x zoom reticle (the recipe default)
    ("sau_t55", dict(recipe.V9_CHOICES, drop_missing_hide=False), r"L:\sabow-ext-backups\v024_PROVEN_SAU_T55\sabow_ext_v024.zip", 24),
    # the T-55 with the cockpit-ceiling fix (2026-09-16): v24 minus the donor hide rows
    # d_hole_01 / d_hole_02 that the t55 model lacks. Proven on 5-6 missions, no 001.
    ("sau_t55", dict(recipe.V9_CHOICES, ammo_text=False),
     r"L:\sabow-ext-backups\v027_PROVEN_SAU_T55\sabow_ext_v027.zip", 27),
    # the Chieftain with the cockpit-ceiling fix: v15 minus d_hole_01 / d_hole_02. Proven on
    # 13 player Chieftains, 3072 x 3072 m, Susangerd (2026-09-16) - both old failing setups.
    ("iru_chief_mk5", {}, r"L:\sabow-ext-backups\v029_PROVEN_IRU_CHIEF_MK5\sabow_ext_v029.zip", 29),
    # the Olifant with the cockpit-ceiling fix: v12 minus d_hole_01 / d_hole_02 (murkz, 2026-09-16)
    ("saru_olifant", {}, r"L:\sabow-ext-backups\v028_PROVEN_SARU_OLIFANT\sabow_ext_v028.zip", 28),
]


def tables_in(zpath):
    with zipfile.ZipFile(zpath) as z:
        blob = z.read("CORE/shared/packed_data/%s.flatdata" % build.ADDON)
    tmp = zpath + ".golden.flatdata"
    with open(tmp, "wb") as f:
        f.write(blob)
    try:
        return {n: azcf.read_record(tmp, n) for n in azcf.archive_records(tmp)}
    finally:
        os.remove(tmp)


def meaning_diff(name, a, b):
    """Where two tables differ, block by block, in decoded values."""
    da, db = build.decoded(azcf.Table(a)), build.decoded(azcf.Table(b))
    out = []
    if len(da) != len(db):
        out.append("%s: %d blocks vs %d" % (name, len(da), len(db)))
    for i, (x, y) in enumerate(zip(da, db)):
        if x == y:
            continue
        if isinstance(x[3], list) and isinstance(y[3], list) and len(x[3]) == len(y[3]):
            for r1, r2 in zip(x[3], y[3]):
                if r1 != r2:
                    out.append("%s block #%d %s: %r -> %r" % (name, i, x[0], r1, r2))
        else:
            out.append("%s block #%d %s differs" % (name, i, x[0]))
    return out


def run(log=print):
    if not os.path.isfile(GOLDEN):
        raise SystemExit("golden build missing: %s" % GOLDEN)
    plan = recipe.derive(build.INSTALL, UNIT, CHOICES)
    log(plan.report())
    zpath = build.build(plan, version=9, log=log, zip_name="%s_golden_test.zip" % build.ADDON)
    got, want = tables_in(zpath), tables_in(GOLDEN)
    ok = sorted(got) == sorted(want)
    if not ok:
        log("FAIL  tables: built %s, golden %s" % (sorted(got), sorted(want)))
    for name in sorted(want):
        if name not in got:
            continue
        same = got[name] == want[name]
        log("%s  %-15s md5 %s  golden %s" % ("SAME" if same else "DIFF", name,
                                             hashlib.md5(got[name]).hexdigest(),
                                             hashlib.md5(want[name]).hexdigest()))
        if not same:
            ok = False
            for line in meaning_diff(name, want[name], got[name])[:20]:
                log("      " + line)
    log("GOLDEN TEST %s: the tool %s proven v9 for the T-55" % (
        "PASS" if ok else "FAIL", "rebuilds" if ok else "does NOT rebuild"))
    for unit, choices, zpath_proven, version in MORE:
        plan = recipe.derive(build.INSTALL, unit, choices)
        z = build.build(plan, version, log=lambda s: None, zip_name="%s_golden_%s.zip" % (build.ADDON, unit))
        got2, want2 = tables_in(z), tables_in(zpath_proven)
        same = got2 == want2
        for name in sorted(want2):
            if got2.get(name) != want2[name]:
                for line in (meaning_diff(name, want2[name], got2[name]) if name in got2 else ["%s missing" % name])[:20]:
                    log("      " + line)
        log("GOLDEN TEST %s: the tool %s proven v%d for %s" % (
            "PASS" if same else "FAIL", "rebuilds" if same else "does NOT rebuild", version, unit))
        ok = ok and same
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
