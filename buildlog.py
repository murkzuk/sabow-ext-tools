# buildlog - the "one build, one look, one line" rule, as code. Part of SABoW Ext.
#
# BUILD_LOG.md is murkz's record: one table row per event. This module reads it
# to find the next build number and whether building is allowed, writes the
# BUILT row when a build finishes and murkz's GOOD / BAD row when he has looked,
# and backs a GOOD build up as proven. The window calls it; it has no window code
# of its own, so it can be tested on a copy of the log.
#
# The lock: after a BUILT row, nothing more can be built until a GOOD or BAD row
# for that same build exists. That is the rule v701-v703 and v680/v681 broke.

import datetime
import hashlib
import os
import re
import shutil

ROW = re.compile(r"^\|\s*(?P<when>[^|]*?)\s*\|\s*(?P<what>[^|]*?)\s*\|\s*(?P<version>[^|]*?)\s*\|\s*(?P<notes>.*?)\s*\|\s*$")


def rows(path):
    """Every event row of the log, oldest first."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = ROW.match(line.rstrip("\r\n"))
            if m and m.group("what") not in ("what", "---") and not m.group("what").startswith("-"):
                out.append(m.groupdict())
    return out


def number(version):
    m = re.match(r"^v(\d+)$", version.strip())
    return int(m.group(1)) if m else None


def next_version(events):
    built = [number(e["version"]) for e in events if e["what"] == "BUILT" and number(e["version"])]
    return (max(built) + 1) if built else 1


def lock(events):
    """(locked, reason). Locked while the newest build has no GOOD or BAD row."""
    built = [e for e in events if e["what"] == "BUILT" and number(e["version"])]
    if not built:
        return False, "no builds yet"
    last = built[-1]["version"]
    after = events[events.index(built[-1]) + 1:]
    if any(e["what"] in ("GOOD", "BAD") and e["version"] == last for e in after):
        return False, "%s has its result" % last
    return True, "%s has no GOOD or BAD line yet - install it, look, and record what you saw" % last


# Packs that have their OWN version series. Their rows must carry "<pack> vNNN" in the version
# column, never a bare "vNNN" - a bare one is THIS window's sabow_ext series and nothing else.
#
# Why this guard exists (2026-09-29): a row was hand-written as "| BUILT | v016 |" for the
# gtos_sokolovo_ob add-on. number() matched it, so it became the newest numbered build, the window
# asked murkz for a verdict on "v016", he gave one - correctly, on the information he had - and
# backup() then archived sabow_ext_v016.zip to <backups>016_PROVEN_UNKNOWN UNIT with his words
# attached. A build that was never play-tested acquired a PROVEN folder. The neighbouring rows for
# the same add-on were written "sokolovo_ob v014" and "sokolovo_ob v015", so the convention existed
# and was simply not followed.
# Packs with their OWN version series. Their rows must carry "<pack> vNNN" in the version column,
# never a bare "vNNN" - a bare one is THIS window's sabow_ext series and nothing else.
OTHER_SERIES = ("gtos_sokolovo_ob", "sokolovo_ob", "gtos_ww2", "sabow_ww2", "bow43")

# A pack's own row NAMES ITSELF AND ITS VERSION AT THE START of the notes; a genuine sabow_ext row
# only ever mentions another pack further in, as a cross-reference ("BoW43 v606's result holds",
# "BoW43 notes/76 v638"). Anchoring on the start is what separates them: measured over all 62
# numbered rows in the log, this flags exactly one - the hand-written gtos_sokolovo_ob row - and
# leaves the other 61 alone. An unanchored "does it mention another pack" test flagged three, two of
# them genuine builds, and a guard that refuses a legitimate verdict is worse than the bug.
FOREIGN = re.compile(r"^[\s*_`]*(" + "|".join(OTHER_SERIES) + r")\b[\s_]*v?\d", re.I)


def foreign_numbered(events):
    """Rows using this window's bare vNNN version while plainly belonging to another pack's series.

    Returns [(index, row)]. Why this guard exists (2026-09-29): a row was hand-written as
    "| BUILT | v016 |" for the gtos_sokolovo_ob add-on. number() matched it, so it became the newest
    numbered build; the window asked murkz for a verdict on "v016", he gave one - correctly, on the
    information he had - and backup() then archived sabow_ext_v016.zip to
    <backups>\v016_PROVEN_UNKNOWN UNIT with his words attached, so a build that was never
    play-tested acquired a PROVEN folder. The neighbouring rows for that add-on were written
    "sokolovo_ob v014" and "sokolovo_ob v015", so the convention existed and was not followed.
    """
    return [(i, e) for i, e in enumerate(events)
            if e["what"] in ("BUILT", "GOOD", "BAD") and number(e["version"])
            and FOREIGN.search(e["notes"])]


def newest_numbered_build(events):
    """(row, problem). `problem` is a sentence when the row must NOT be acted on."""
    built = [e for e in events if e["what"] == "BUILT" and number(e["version"])]
    if not built:
        return None, "there are no numbered builds in the log"
    last = built[-1]
    if any(e is last for _, e in foreign_numbered(events)):
        return last, ("the newest numbered build row, %s, is not one of this window's builds - its "
                      "notes name another pack. Correct that row's version column in BUILD_LOG.md to "
                      "\"<pack> %s\", then try again. Recording a result against it would attach "
                      "your words, and a PROVEN backup, to the wrong build."
                      % (last["version"], last["version"]))
    return last, None


def _clean(text):
    return " ".join(text.replace("|", "/").split())


def append(path, what, version, notes, when=None):
    when = when or datetime.date.today().isoformat()
    with open(path, "rb") as f:
        data = f.read()
    nl = b"\r\n" if b"\r\n" in data else b"\n"
    line = "| %s | %s | %s | %s |" % (when, what, version, _clean(notes))
    if data and not data.endswith(nl):
        data += nl
    with open(path, "wb") as f:
        f.write(data + line.encode("utf-8") + nl)
    return line


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def backup(zip_path, version, unit, verdict_line, recipe_report, backup_root):
    """Copy a GOOD build to <backup_root>/vNNN_PROVEN_<UNIT> with a README and md5s."""
    folder = os.path.join(backup_root, "v%03d_PROVEN_%s" % (number(version), unit.upper()))
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, os.path.basename(zip_path))
    shutil.copyfile(zip_path, dst)
    readme = os.path.join(folder, "README.md")
    with open(readme, "w", encoding="utf-8", newline="\n") as f:
        f.write("# %s - PROVEN: %s\n\n" % (version, unit))
        f.write("Built by SABoW Ext Control on %s.\n\n" % datetime.date.today().isoformat())
        f.write("## What murkz saw\n%s\n\n" % _clean(verdict_line))
        f.write("## The recipe it was built from\n```\n%s\n```\n" % recipe_report)
    with open(os.path.join(folder, "MANIFEST.md5"), "w", encoding="utf-8", newline="\n") as f:
        for name in (os.path.basename(dst), "README.md"):
            f.write("%s *%s\n" % (md5(os.path.join(folder, name)), name))
    if md5(dst) != md5(zip_path):
        raise RuntimeError("the backup copy does not match the build")
    return folder
