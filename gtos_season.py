# gtos_season.py - rebuild a GTOS add-on pack's tabs.flatdata with a season SABoW can read.
#
# Why: the GTOS packs (Operation Star, 2013) carry a NEWER season schema than SABoW 2899
# reads - `micros` has an 8th field, `soils` field 12 is an array where SABoW has a number,
# `weather` has 8 rows not 7, and there are three blocks SABoW has none of (`ambients`,
# `cprops_ambients`, `cprops_water`). zhal69 loads its map and then dies inside weather
# setup, between "Time shift" and "Max game time" (docs/gtos-zhal69-first-run.md).
#
# BoW43 already solved this shape: it runs GTOS maps and ships its OWN seasons, which match
# SABoW's schema exactly, while its GTOS map add-ons ship no tables at all.
#
# This rebuilds the pack's own archive, so nothing depends on add-on ordering in
# paths.cfgpack - the pack answers for its own season, and the answer is now readable.
# The rebuilt .gt2extension goes back in through the updater, which re-signs it (notes/46:
# an unsigned add-on is silently ignored).
#
# Everything happens in the SANDBOX. The live install is never touched.

import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf     # noqa: E402
import build    # noqa: E402

SANDBOX = r"K:\SABoW_sandbox"
PACK = (r"G:\GTOS all addons gamersgate\gtos_zhal69_jul13_int"
        r"\gtos_zhal69_jul13_int.gt2extension")
TABS_IN_ZIP = "core/shared/packed_data/tabs.flatdata"

# the pack's season -> the SABoW season to stand in for it.
# af_summer is the dry, arid one: closest to the Kazakh steppe in August.
SWAP = {"season_kz_summer": "season_af_summer"}


def base_tabs(install):
    return os.path.join(install, "data", "mtc80", "shared", "packed_data", "tabs.flatdata")


def rebuild(install=SANDBOX, pack=PACK, swap=None, log=print, work=None, tabs_in_zip=TABS_IN_ZIP):
    """Rebuild the pack's tabs.flatdata with the swapped season. Returns the new zip.
    `work` is emptied first; the default is the folder the proven Zhalanashkol pack was
    built in. The GTOS maps tab (gtos_maps.py) passes its own folder per pack."""
    swap = SWAP if swap is None else swap
    work = work or os.path.join(install, "users", "modwork", "zhal_fix")
    packdir = os.path.join(work, "pack")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(packdir)

    src_tabs = os.path.join(work, "tabs_original.flatdata")
    with zipfile.ZipFile(pack) as z:
        with open(src_tabs, "wb") as f:
            f.write(z.read(tabs_in_zip))
    recs = azcf.archive_records(src_tabs)
    log("OK  the pack's tabs.flatdata holds %d records" % len(recs))

    originals, written = {}, []
    for name, (off, size, kind, loc) in recs.items():
        blob = azcf.read_record(src_tabs, name)
        originals[name] = blob
        if name in swap:
            donor = swap[name]
            blob = azcf.read_record(base_tabs(install), donor)
            log("    %s <- SABoW's %s (%d b instead of %d b)"
                % (name, donor, len(blob), len(originals[name])))
        with open(os.path.join(packdir, "%s.%s.%s" % (name, loc, kind)), "wb") as f:
            f.write(blob)
        written.append((name, kind, loc))

    flatlist = os.path.join(packdir, "tabs.!flatlist")
    with open(flatlist, "w", encoding="utf-8", newline="\n") as f:
        f.write("i_unflat:unflat()\n{\n")
        for name, kind, loc in written:
            f.write("\t%s, %s, %s ;\n" % (name.ljust(24), kind.ljust(10), loc))
        f.write("}\n")

    out = os.path.join(work, "tabs.flatdata")
    n = build.starter(install, "mkflat,", build.rel(out, install) + ",",
                      build.rel(flatlist, install), expect=out)
    log("OK  rebuilt tabs.flatdata (%d bytes)" % n)

    # read the RESULT back, not the files we wrote
    new = azcf.archive_records(out)
    if sorted(new) != sorted(recs):
        raise SystemExit("rebuilt archive holds %s, expected %s" % (sorted(new), sorted(recs)))
    for name in sorted(new):
        got = azcf.read_record(out, name)
        if name in swap:
            want = azcf.read_record(base_tabs(install), swap[name])
            if got != want:
                raise SystemExit("%s is not SABoW's %s" % (name, swap[name]))
            log("OK  %s IS SABoW's %s, byte for byte" % (name, swap[name]))
        else:
            if got != originals[name]:
                raise SystemExit("%s changed and should not have" % name)
    log("OK  the other %d records are byte-identical to the pack's own"
        % (len(new) - len(swap)))

    newzip = os.path.join(work, os.path.basename(pack).replace(
        ".gt2extension", "_sabowseason.gt2extension"))
    with zipfile.ZipFile(pack) as zin, zipfile.ZipFile(newzip, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = open(out, "rb").read() if item.filename == tabs_in_zip else zin.read(item.filename)
            zout.writestr(item, data)
    log("OK  wrote %s (%.0f MB)" % (newzip, os.path.getsize(newzip) / 1e6))

    with zipfile.ZipFile(newzip) as z:
        names = z.namelist()
        if len(names) != len(zipfile.ZipFile(pack).namelist()):
            raise SystemExit("the new pack has a different file count")
        check = os.path.join(work, "check.flatdata")
        with open(check, "wb") as f:
            f.write(z.read(tabs_in_zip))
    if open(check, "rb").read() != open(out, "rb").read():
        raise SystemExit("the tabs inside the new pack is not the one that was built")
    os.remove(check)
    log("OK  inside the new pack: %d files, tabs.flatdata is the rebuilt one" % len(names))
    return newzip


if __name__ == "__main__":
    print(rebuild())


# ---------------------------------------------------------------- the season CONVERTER (2026-09-23)
#
# rebuild() SWAPS an unreadable season for one of SABoW's, which only reaches a season the PACK
# carries. Shilovo 1942 names season_ru_summer and carries no tables at all, so its season is
# BORROWED from Operation Star and the swap path never runs on it.
#
# It does not need swapping. SABoW and Operation Star are the SAME engine a few versions apart
# (murkz, 2026-09-23), so the differences are version drift - exactly like the 56 vs 60-byte
# movement maps gtos_penmap.py already converts. MEASURED against SABoW's season_af_summer:
#
#   micros   svfffvuu  vs svfffvu     one extra value on the end of every row
#   soils    ...uuaffuv vs ...uuuffuv field 21 is an ARRAY of 4 where SABoW has one number
#   weather  8 rows     vs 7 rows     LEFT ALONE - BoW43's own season_ua_summer ships 8 and runs
#   ambients, cprops_ambients, cprops_water  present vs absent   dropped
#
# ROW COUNTS ARE DATA, NOT SCHEMA, and are left alone. Operation Star has 17 soils to SABoW's 14;
# the extras are field_green, bumps and dry_grass - Eastern Front soils the map may index BY
# NUMBER. Trimming them is the one edit guaranteed to break the look.
#
# The soils array collapses to its FIRST element. Measured across all 17 rows: the first element
# equals SABoW's single value in 12 of the 14 rows both games share, and elements 2-4 are zero in
# 16 of 17. The exceptions are content, not structure - a Russian season against an Afghan one.
# Only `field` loses anything (4,7,0,0 -> 4).
#
# The spec string is otherwise copied through UNTOUCHED, including the `*` characters cfgp2pd
# emits, which are not understood. The compiled RESULT is checked against SABoW's own season
# rather than trusting the text.

SEASON_DROP_BLOCKS = ("ambients", "cprops_ambients", "cprops_water")
SEASON_REF = "season_af_summer"          # SABoW's own, the shape to match


def _block_span(txt, name):
    """(start, spec, body_start, body_end) for `name[spec]() { ... }`, or None."""
    i = txt.find("\n" + name + "[")
    if i < 0:
        return None
    i += 1
    spec = txt[i + len(name) + 1: txt.index("]", i)]
    s = txt.index("{", i) + 1
    e = txt.index("}", s)
    return i, spec, s, e


def _rows(txt, s, e):
    return [r for r in txt[s:e].split(";") if r.strip()]


def convert_season_text(txt, log=print):
    """GTOS season text -> SABoW-schema season text. Pure string work, no game tools."""
    sp = _block_span(txt, "micros")
    if sp and sp[1].endswith("uu"):
        i, spec, s, e = sp
        out = ["\n\t" + r.strip().rpartition(",")[0] for r in _rows(txt, s, e)]
        txt = txt[:s] + ";".join(out) + ";\n" + txt[e:]
        txt = txt.replace("micros[" + spec + "]", "micros[" + spec[:-1] + "]", 1)
        log("    micros  %s -> %s, dropped the last value of %d rows" % (spec, spec[:-1], len(out)))

    sp = _block_span(txt, "soils")
    if sp and "a" in sp[1]:
        i, spec, s, e = sp
        at = spec.index("a")
        before = sum(4 if c in "va" else 1 for c in spec[:at])
        out = []
        for r in _rows(txt, s, e):
            v = [x.strip() for x in r.strip().split(",")]
            v[before:before + 4] = [v[before]]
            out.append("\n\t" + ", ".join(v))
        txt = txt[:s] + ";".join(out) + ";\n" + txt[e:]
        txt = txt.replace("soils[" + spec + "]",
                          "soils[" + spec[:at] + "u" + spec[at + 1:] + "]", 1)
        log("    soils   array at value %d collapsed to its first element, %d rows kept"
            % (before + 1, len(out)))

    for name in SEASON_DROP_BLOCKS:
        sp = _block_span(txt, name)
        if sp:
            i, spec, s, e = sp
            j = txt.index("\n", e)
            txt = txt[:i] + txt[j + 1:]
            log("    dropped block %s" % name)
    return txt


def convert_season_blob(install, blob, name, log=print, work=None):
    """A GTOS season record -> the same season in SABoW's schema. Returns the new bytes.

    cfgp2pd -> cfgfix -> convert_season_text -> pd2cfgp, the same route the tool already uses
    for common_res_mod. The RESULT is checked against SABoW's own season, because the text's
    spec characters are not fully understood and the compiled header is what the engine reads.
    """
    import subprocess
    import textable
    work = work or os.path.join(install, "users", "modwork", "season_convert", name)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    cfg = os.path.join(work, name + ".stock.config")
    with open(cfg, "wb") as f:
        f.write(blob)
    raw = os.path.join(work, name + ".cfgp2pd.engcfg2")
    build.starter(install, "cfgp2pd,", build.rel(cfg, install) + ",",
                  build.rel(raw, install), expect=raw)

    fixed = os.path.join(work, name + ".loc_def.engcfg2")
    r = subprocess.run([sys.executable, os.path.join(HERE, "cfgfix.py"), cfg, raw, fixed],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(fixed):
        raise SystemExit("cfgfix refused %s (exit %d)" % (name, r.returncode))

    txt = open(fixed, "rb").read().decode("latin1")
    log("  converting %s to SABoW's season schema:" % name)
    out_txt = os.path.join(work, "converted", name + ".loc_def.engcfg2")
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)
    with open(out_txt, "wb") as f:
        f.write(convert_season_text(txt, log).encode("latin1"))

    out = os.path.join(work, "converted", name + ".config")
    new = textable.compile_text(install, out_txt, out, log=lambda s: None)

    # the gate: the compiled result must have SABoW's shape, read from the header
    ref = _season_schema(azcf.read_record(base_tabs(install), SEASON_REF))
    got = _season_schema(new)
    for block in ("micros", "soils"):
        if got.get(block, ("",))[0] != ref.get(block, ("",))[0]:
            raise SystemExit("%s: %s spec is %r, SABoW's is %r"
                             % (name, block, got.get(block), ref.get(block)))
    for block in SEASON_DROP_BLOCKS:
        if block in got:
            raise SystemExit("%s: block %s survived the conversion" % (name, block))
    log("  OK  %s now matches SABoW's schema (%d blocks, %d bytes)" % (name, len(got), len(new)))
    return new


def _season_schema(blob):
    t = azcf.Table(blob)
    return {b.name: (b.spec.replace(chr(0), ""), b.rows) for b in t.blocks}
