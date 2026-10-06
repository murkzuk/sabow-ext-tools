# textable - turn a stock compiled table into editable text, and prove the text
# compiles back to EXACTLY the stock bytes before anything is edited.
#
# Part of the SABoW Ext tool. Needed when a change is more than flipping bytes
# that already exist - e.g. a new cockpit, which adds blocks to `cocpits`.
#
# The chain, all with the game's own programs:
#   stock .config  --cfgp2pd-->  text  --cfgfix-->  repaired text  --pd2cfgp-->  .config
#
# cfgp2pd's text cannot be compiled as it comes out: indentation is written as
# NUL and spec-less blocks gain a stray "=" (BoW43 notes/21, notes/43).
# cfgfix.py (copied from L:\sabow-docs\Tools, commit 00b422d) repairs both,
# using the stock .config as the oracle. For `cocpits` it must run with
# --keep-dupes: the repeated names (gunner, controls, ...) are nested per
# cockpit and legitimate; renaming them would break the cockpit.
#
# round_trip() is the gate: if stock -> text -> compiled is not md5-identical
# to stock, nothing built from that text can be trusted.

import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402
import build  # noqa: E402

# cfgp2pd writes a spec-less block as "name=()", and that "=" recompiles as a ONE-CHARACTER SPEC.
# Measured 2026-09-27: a container that came out that way made every battle die entering the deploy
# with the generic "001: Program initialization error", with nothing in the log naming cockpits.
# See docs/2026-09-27-added-block-container-defect.md.
#
# A "=" in a spec is ALWAYS a defect - no field type is "=".
#
# A NUL spec is NOT always a defect, and saying it was would refuse tables that work: `techn_gtos`
# names all 13 of its vehicle blocks with spec 0x00 and battles run on it every day (measured
# 2026-09-27, the same hour). So the rule is RELATIVE to the stock record of the same table: a NUL
# spec is a defect only where the stock table has none - which is what a container that lost its spec
# looks like. `cocpits` has 0 such blocks in stock; the merged table had exactly 1, the added
# cockpit's `anims`.


def stock_record(install, table):
    """The shipped record for `table`, or None. Used to judge a compiled table against its own past."""
    try:
        return azcf.read_record(build.tabs_path(install), table)
    except Exception:
        return None


def spec_defects(stock, built):
    """[(index, name, spec, why)] for every block whose spec cannot be right.

    `stock` may be None, in which case only the absolute rule ("=" is never a field type) applies.
    """
    out = []
    stock_nul = 0
    if stock is not None:
        stock_nul = sum(1 for b in azcf.Table(stock).blocks if "\x00" in b.spec)
    for b in azcf.Table(built).blocks:
        if "=" in b.spec:
            out.append((b.index, b.name, b.spec,
                        "spec %r - cfgp2pd's stray '=' survived" % b.spec))
        elif "\x00" in b.spec and stock is not None and stock_nul == 0:
            out.append((b.index, b.name, b.spec,
                        "spec 0x00, and this record's stock table has no such block"))
    return out

# tables whose repeated block names are nested and must be kept (notes/43)
KEEP_DUPES = {"cocpits"}


def md5(b):
    return hashlib.md5(b).hexdigest()


def decompile(install, table, folder, log=print):
    """Write the stock table and its repaired text into `folder`.
    Returns (stock bytes, path of the repaired .engcfg2)."""
    os.makedirs(folder, exist_ok=True)
    stock = azcf.read_record(build.tabs_path(install), table)
    cfg = os.path.join(folder, table + ".stock.config")
    with open(cfg, "wb") as f:
        f.write(stock)
    raw = os.path.join(folder, table + ".cfgp2pd.engcfg2")
    if os.path.exists(raw):
        os.remove(raw)
    n = build.starter(install, "cfgp2pd,", build.rel(cfg, install) + ",", build.rel(raw, install),
                      expect=raw)
    log("OK  %s decompiled by cfgp2pd (%d bytes)" % (table, n))

    fixed = os.path.join(folder, table + ".loc_def.engcfg2")
    args = [sys.executable, os.path.join(HERE, "cfgfix.py"), cfg, raw, fixed]
    if table in KEEP_DUPES:
        args.append("--keep-dupes")
    r = subprocess.run(args, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        log("    cfgfix: " + line)
    if r.returncode != 0 or not os.path.isfile(fixed):
        raise SystemExit("cfgfix refused %s (exit %d)" % (table, r.returncode))
    return stock, fixed


def compile_text(install, src, out, log=print):
    """pd2cfgp one text table to `out`. Returns the compiled bytes.

    pd2cfgp writes the output file's name, minus its last extension, into the
    table header at byte 0x20. Stock tables say just "cocpits", so `out` must be
    named `<table>.config` - "cocpits.roundtrip.config" differed from stock in
    exactly those 10 header bytes and nothing else (measured 2026-09-15).
    """
    if os.path.basename(out).count(".") != 1:
        raise SystemExit("compile output must be named <table>.config, got %s" % out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    build.starter(install, "pd2cfgp,", build.rel(src, install) + ",", build.rel(out, install),
                  expect=out)
    with open(out, "rb") as f:
        built = f.read()
    # EVERY compiled table goes through here, so the check belongs here rather than at each call
    # site: it is the only place that cannot be fooled by how the text happened to be written. The
    # stock record for the same table is the reference - a NUL spec is normal in some tables and a
    # defect in others, so only the table itself can say which.
    table = os.path.basename(out)[:-len(".config")]
    bad = spec_defects(stock_record(install, table), built)
    if bad:
        for i, name, spec, why in bad[:10]:
            log("    block %d %r has %s" % (i, name, why))
        raise SystemExit(
            "the compiled table carries %d block(s) whose spec is not a field type - a stray '=' "
            "from cfgp2pd that cfgfix did not repair. MEASURED 2026-09-27: ONE such block in a "
            "cockpit table made every battle die entering the deploy with the generic '001: "
            "Program initialization error'. Do not ship it." % len(bad))
    return built


def round_trip(install, table, folder, log=print, accept=None):
    """The gate. Returns the path of repaired text proven to compile to stock.

    `accept(stock, back)` is for a table that cannot come back byte-identical for
    a known, harmless reason - qbattle's three duplicate block names, renamed by
    cfgfix (BoW43 notes/43). It must return a message, or raise SystemExit."""
    stock, fixed = decompile(install, table, folder, log)
    back = compile_text(install, fixed, os.path.join(folder, "roundtrip", table + ".config"), log)
    log("    stock      %8d bytes  md5 %s" % (len(stock), md5(stock)))
    log("    round trip %8d bytes  md5 %s" % (len(back), md5(back)))
    if back != stock:
        if accept is None:
            raise SystemExit("ROUND TRIP FAILED for %s - the text does not compile back to stock. "
                             "Do not build from it." % table)
        log("OK  %s round trip: %s" % (table, accept(stock, back)))
        return fixed
    log("OK  %s round trip is byte-identical to stock" % table)
    return fixed


if __name__ == "__main__":
    table = sys.argv[1] if len(sys.argv) > 1 else "cocpits"
    round_trip(build.INSTALL, table, os.path.join(build.work_dir(build.INSTALL), "text", table))
