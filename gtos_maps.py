# gtos_maps.py - make a Graviteam Tactics (GTOS) map pack playable in SABoW. The engine
# behind the "GTOS maps" tab of SABoW Ext Control; nothing here touches Tk.
#
# A GTOS map pack needs up to three conversions before SABoW 2899 can play it
# (docs/gtos-zhal69-first-run.md, 2026-09-16):
#
#   1. seasons   - GTOS ships a newer season-table schema SABoW cannot read (the load stops in
#                  weather setup). Each incompatible season is replaced by SABoW's own nearest
#                  season (gtos_season.py).
#   2. movement  - each map cell's pen_* movement maps store 56-byte quadtree nodes; SABoW reads
#                  60 and crashes on the AI's first move search (gtos_penmap.py).
#   3. borrow    - Operation Star's own maps name tables, models and textures SABoW does not have;
#                  with an Operation Star install given, only those are copied into the pack
#                  (gtos_opstar.py).
#
# check() reads a pack and says what it needs, in plain words, without changing anything.
# convert() does only the steps the pack needs, in the SANDBOX install, and leaves one
# finished .gt2extension to install through the updater.
#
# Proven 2026-09-16: Zhalanashkol converted this way played ~28 minutes, enemy AI moving.

import hashlib
import os
import re
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf          # noqa: E402
import gtos_opstar   # noqa: E402
import gtos_penmap   # noqa: E402
import gtos_season   # noqa: E402

PACK_FOLDERS = [r"G:\GTOS all addons gamersgate"]
SANDBOX = __import__("settings").get("sandbox")      # chosen in the tab, remembered in settings.json

# A pack's season name -> the SABoW season that stands in for it. SABoW 2899 ships four:
# af_spring, af_summer, an_winter, ir_winter. Zhalanashkol's season_kz_summer used af_summer.
SEASON_WORDS = (("winter", "season_ir_winter"), ("snow", "season_ir_winter"),
                ("spring", "season_af_spring"), ("summer", "season_af_summer"))
DEFAULT_SEASON = "season_af_summer"

# A map names the tables it needs as "tabs\<name>" inside its files. Sokolovo (2026-09-16) needed four
# tables that exist neither in SABoW nor in the pack - a pack can be the right FORMAT and still not play.
TABLE_REF = re.compile(rb"tabs[\\/]([A-Za-z0-9_]{3,40})")
MAP_FILES = (".cfgpack", ".polypack2")          # the map itself: missing -> it cannot load
CAMPAIGN_FILES = (".campack2", ".mispack")      # campaigns and missions only
TOKEN = re.compile(rb"[A-Za-z0-9_]{3,48}")


def object_models(install, opstar, tables, tokens, log=print):
    """Objects the map places from tables SABoW OWNS, whose models or textures SABoW lacks and Operation Star
    has. The borrow step follows only tables SABoW lacks, so these were never looked at: Sokolovo's and
    Krasnaya Polyana's well0 (structs) names mesh well01_s01, which stock SABoW does not ship. Every battle
    logged "Unable to find object ... well0", and on 2026-09-17 (gtos_ww2 v10) the game read uninitialised
    memory for it and died with 001 - caught under cdb in basic_render, 'well0' on the stack.

    An object's DAMAGED STATES are their own blocks in the same table, chained by destr_desc, and the map never
    names them: well0 -> well0_s2 (mesh well01_s02) -> well0_s3 (same mesh). The first version of this function
    tried to follow that chain with t.rows(), but a state block is a PROPS block, so it silently found nothing and
    only the whole well's model was borrowed. The well then crashed the same way once it had been shot and its
    damaged model was drawn - caught under cdb again on 2026-09-17 with 'well0_s2' and 'well0_s3' on the stack,
    this time reading FREED memory (feeefeee). States are now followed by their props, as far as the chain goes.
    Returns (names to borrow, [(table, object, [names])])."""
    have = gtos_opstar.Index(gtos_opstar.sabow_archives(install))
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    # A mesh names its textures WITHOUT their prefix (bush_dift -> trans_bush_dift). The
    # prefix list is read from Operation Star's own texture names, never typed in - the same
    # rule gtos_opstar.resolve uses, and a typed list has burned this project before.
    prefixes = sorted({n.split("_")[0] for (n, k) in src.records if k == "texture" and "_" in n})
    base_tabs = gtos_season.base_tabs(install)
    seeds, found = set(), []
    for tname in sorted(tables):
        t = azcf.Table(azcf.read_record(base_tabs, tname))
        names = {b.name.lower(): b for b in t.blocks}

        def props_of(block):
            try:
                return t.props(block)
            except Exception:
                return None
        # A map names most objects it places, so the token filter keeps this cheap. FLORA IS
        # DIFFERENT: a map indexes the global flora table BY NUMBER, not by name (BoW43 notes/53),
        # so not one of Shilovo 1942's crops, bushes or garden trees appeared in 861,445 map
        # tokens - measured 2026-09-23 - while well0 and gazmm_ostov_plc both did. That is why the
        # map loaded with thousands of BLACK rectangles: every flora row was invisible to this
        # function, so its armour maps were never borrowed. An index-addressed table has to be read
        # WHOLE. flora_sum is 78 blocks, so this is bounded, and nothing SABoW already has is taken.
        # ostovs added 2026-09-23 for the same reason: a WRECK is not placed by the map, it is
        # created when a vehicle dies, so it is never a map token either. Shilovo 1942 was short
        # six of them - 52k, marder, opel, pz1f, stuart and t26 - and they would have appeared as
        # missing models the moment anything was knocked out. Kr Pol's own open item, "3 objects
        # still missing in ostovs/structs", is the same gap seen from the other side.
        whole = tname.lower().startswith("flora") or tname.lower() == "ostovs"
        for b in t.blocks:
            # The isalpha guard exists to stop junk tokens matching block names. Reading a table
            # WHOLE does no token matching, so it does not need the guard - and the guard was
            # silently dropping 52k_ostov0, the 52-K anti-tank gun's wreck, purely because its
            # name starts with a digit (2026-09-23: five of six wrecks came through, that one did not).
            if not whole and not b.name[:1].isalpha():
                continue
            if not whole and b.name.lower() not in tokens:
                continue
            values = props_of(b)
            if values is None:
                continue
            words, chain, seen = set(), [(b.name, values)], {b.name.lower()}
            while chain:
                who, vals = chain.pop()
                words |= set(TOKEN.findall(" ".join(str(v) for v in vals.values()).encode("latin1")))
                dd = str(vals.get("destr_desc", "")).lower()
                if dd and dd in names and dd not in seen:
                    seen.add(dd)
                    nxt = props_of(names[dd])
                    if nxt is not None:
                        chain.append((names[dd].name, nxt))
                # AN OBJECT WHOSE MESH SABoW ALREADY OWNS WAS NEVER OPENED, so that mesh's own
                # TEXTURES were never checked. Measured 2026-09-23: SABoW ships the pine, cherry
                # and corn meshes AND their armour maps, but not trans_pine_big_col_dift,
                # trans_cherry_dift or trans_tr_corn_sum_dift. A flora quad with an alpha cutout
                # and no diffuse draws BLACK with the right silhouette - which is exactly what
                # Shilovo 1942 showed once the armour maps were fixed.
                mname = str(vals.get("mesh", "")).lower()
                mk = [k for k in have.by_name.get(mname, []) if k[1] == "mesh"] if mname else []
                if mk:
                    mpath, ment = have.records[mk[0]]
                    for tok in TOKEN.findall(gtos_opstar.read(mpath, ment)):
                        tok = tok.decode("latin1").lower()
                        if tok.endswith(("_dift", "_norsp", "_spec")):
                            words |= {("%s_%s" % (p, tok)).encode("latin1") for p in prefixes}
            lacks = sorted({w.decode("latin1").lower() for w in words
                            # "armor" added 2026-09-23: Shilovo 1942 loaded with thousands of BLACK
                            # rectangles where its crops, bushes and garden trees should be. An armour
                            # map is a flora object's alpha cutout, and without it the billboard draws
                            # solid. i_orender named three - arm_tr_corn_sum_dift (corn, trostnik1/2),
                            # arm_cultbush_dift (cultbush1/2, verba_bush) and arm_cherry_dift
                            # (tree_gard +2 states) - all kind "armor" in Operation Star's
                            # phys_maps.flatdata, none in SABoW. They were found by the token scan and
                            # then dropped here, because this filter only looked at mesh and texture.
                            if any(k[1] in ("mesh", "texture", "armor") and not have.has(k)
                                   for k in src.by_name.get(w.decode("latin1").lower(), []))})
            if lacks:
                seeds.update(lacks)
                found.append((tname, "%s (+%d damaged states)" % (b.name, len(seen) - 1) if len(seen) > 1 else b.name,
                              lacks))
    for tname, obj, lacks in found:
        log("  %s %s: SABoW lacks %s - Operation Star has it" % (tname, obj, ", ".join(lacks)))
    return seeds, found


def find_packs(folders=PACK_FOLDERS):
    """Every .gt2extension up to two folders deep, not counting our own converted ones."""
    out = []
    for top in folders:
        if not os.path.isdir(top):
            continue
        for root, dirs, files in os.walk(top):
            if root[len(top):].count(os.sep) >= 2:
                dirs[:] = []
            for f in files:
                if f.lower().endswith(".gt2extension") and "_sabow" not in f.lower():
                    out.append(os.path.join(root, f))
    return sorted(out)


def _tabs_member(z):
    hits = [n for n in z.namelist() if n.lower().replace("\\", "/").endswith("shared/packed_data/tabs.flatdata")]
    return hits[0] if len(hits) == 1 else None


def _schema(blob):
    return [(b.name, b.spec) for b in azcf.Table(blob).blocks]


def substitute_for(season):
    for word, sabow in SEASON_WORDS:
        if word in season.lower():
            return sabow, "its name says %s" % word
    return DEFAULT_SEASON, "no season word in its name - the summer one is the default"


def check(pack, install=SANDBOX, log=print, opstar=None, objects=True):
    """Read the pack; change nothing. Returns a dict the tab and convert() both use.
    With `opstar` (an Operation Star install), tables the map needs that SABoW lacks are looked
    for there, with every model and texture they name (gtos_opstar.py) - and, with `objects`
    (2026-09-17), the models of objects SABoW's OWN tables place that SABoW lacks (object_models).
    objects=False reproduces the packs proven before that."""
    info = {"pack": pack, "name": os.path.splitext(os.path.basename(pack))[0], "readme": [],
            "tabs": None, "seasons": [], "in_front_of_sabow": [], "in_front_of_ext": [],
            "cells": [], "problems": [], "missing_map_tables": [], "missing_campaign_tables": [],
            "opstar": None, "borrow": None, "object_models": [], "convert_seasons": []}
    map_refs, campaign_refs, pack_tables, map_tokens = set(), set(), set(), set()

    def refs(data, name):
        found = {m.group(1).decode("latin1").lower() for m in TABLE_REF.finditer(data)}
        (map_refs if name.lower().endswith(MAP_FILES) else campaign_refs).update(found)
        if name.lower().endswith(MAP_FILES):
            map_tokens.update(t.decode("latin1").lower() for t in TOKEN.findall(data))
    base_tabs = gtos_season.base_tabs(install)
    base = azcf.archive_records(base_tabs)
    ref = _schema(azcf.read_record(base_tabs, DEFAULT_SEASON))
    ext_path = os.path.join(install, "data", "mtc80", "sabow_ext", "shared", "packed_data", "sabow_ext.flatdata")
    ext = azcf.archive_records(ext_path) if os.path.isfile(ext_path) else {}
    tmp = tempfile.mkdtemp(prefix="gtosmaps_")
    try:
        with zipfile.ZipFile(pack) as z:
            names = z.namelist()
            readme = [n for n in names if n.lower().endswith("readme_eng.txt")]
            if readme:
                text = z.read(readme[0]).decode("cp1251", "replace").splitlines()
                title = []
                for l in (x.strip() for x in text):
                    if not l or set(l) <= set("-=*_ "):
                        continue
                    if l[0].isdigit() and "." in l[:3]:      # "1. INSTALL" - the title is over
                        break
                    title.append(l)
                info["readme"] = title[:4]
            member = _tabs_member(z)
            info["tabs"] = member
            if member:
                tp = os.path.join(tmp, "tabs.flatdata")
                with open(tp, "wb") as f:
                    f.write(z.read(member))
                recs = azcf.archive_records(tp)
                pack_tables = set(recs)
                for rec in recs:
                    if rec.startswith("season_"):
                        ok = _schema(azcf.read_record(tp, rec)) == ref
                        sub, why = (None, "") if ok else substitute_for(rec)
                        info["seasons"].append((rec, ok, sub, why))
                info["in_front_of_sabow"] = sorted(r for r in recs if r in base)
                info["in_front_of_ext"] = sorted(r for r in recs if r in ext)
            for n in names:
                low = n.lower()
                if low.endswith(MAP_FILES + CAMPAIGN_FILES) and not low.endswith(".polypack2"):
                    refs(z.read(n), n)
            cells = [n for n in names if n.lower().endswith(".polypack2")]
            log("Reading %d map cells ..." % len(cells))
            for n in cells:
                cp = os.path.join(tmp, "cell.polypack2")
                data = z.read(n)
                refs(data, n)
                with open(cp, "wb") as f:
                    f.write(data)
                del data
                recs = azcf.archive_records(cp)
                sizes = {}
                for layer in gtos_penmap.LAYERS:
                    if layer in recs:
                        try:
                            sizes[layer] = gtos_penmap.node_size(azcf.read_record(cp, layer))[0]
                        except SystemExit as e:
                            sizes[layer] = None
                            info["problems"].append("%s %s: %s" % (os.path.basename(n), layer, e))
                info["cells"].append((os.path.basename(n), sizes))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    exists = lambda t: t in base or t in pack_tables
    info["missing_map_tables"] = sorted(t for t in map_refs if not exists(t))
    info["missing_campaign_tables"] = sorted(t for t in campaign_refs if not exists(t) and t not in map_refs)
    info["needs_seasons"] = {s: sub for s, ok, sub, why in info["seasons"] if not ok}
    info["needs_movement"] = [c for c, sizes in info["cells"] if 56 in sizes.values()]
    seeds = set()
    if objects and opstar and gtos_opstar.is_opstar(opstar):
        owned = sorted(t for t in map_refs if t in base and t not in pack_tables)
        log("Checking the objects the map places from SABoW's own tables (%s) ..." % ", ".join(owned))
        seeds, info["object_models"] = object_models(install, opstar, owned, map_tokens, log)
    if (info["missing_map_tables"] or seeds) and opstar and gtos_opstar.is_opstar(opstar):
        log("Looking in Operation Star for %s ..." % ", ".join(info["missing_map_tables"] + sorted(seeds)))
        res = gtos_opstar.resolve(info["missing_map_tables"], install, opstar, log, seed_tokens=seeds)
        info["opstar"] = opstar
        if res["borrow"]:
            info["borrow"] = res
        info["missing_map_tables"] = sorted(res["not_found"])
        # A borrowed season has to be one SABoW can read - it is not swapped like a pack's own.
        for path, entry in res["borrow"]:
            if entry[3] == "config" and entry[0].lower().startswith("season_"):
                if _schema(gtos_opstar.read(path, entry)) != ref:
                    # NOT a wall. Same engine, a few versions apart - the differences are version
                    # drift and gtos_season.convert_season_blob reshapes them (2026-09-23).
                    info["convert_seasons"].append(entry[0])
    return info


def needs_converting(info):
    return bool(info["needs_seasons"] or info["needs_movement"] or info.get("borrow"))


def report(info):
    """Plain English, one fact per line."""
    L = ["%s" % info["name"]]
    if info["readme"]:
        L.append("  " + "  /  ".join(info["readme"][:4]))
    L.append("")
    cells = info["cells"]
    if not cells:
        L.append("No map cells in this pack - it adds no ground to fight on.")
    else:
        n56 = len(info["needs_movement"])
        n60 = sum(1 for c, s in cells if s and set(s.values()) == {60})
        L.append("Map cells: %d" % len(cells))
        if n56:
            L.append("  NEEDS FIXING: %d cells use GTOS movement maps (56-byte) - SABoW crashes a few seconds into the battle on these." % n56)
        if n60:
            L.append("  OK: %d cells already use SABoW's movement maps (60-byte)." % n60)
    L.append("")
    if not info["tabs"]:
        L.append("No game tables in this pack.")
    elif not info["seasons"]:
        L.append("Seasons: none in this pack - its maps use a season from elsewhere.")
    else:
        for s, ok, sub, why in info["seasons"]:
            if ok:
                L.append("Season %s: OK, SABoW can read it." % s)
            else:
                L.append("Season %s: NEEDS FIXING - newer format SABoW cannot read; will be replaced by SABoW's %s (%s)." % (s, sub, why))
    if info["in_front_of_ext"]:
        L.append("")
        L.append("Tables that sit in front of SABoW Ext's own: %s. Keep this pack in the sandbox." % ", ".join(info["in_front_of_ext"]))
    if info["in_front_of_sabow"]:
        L.append("Tables that sit in front of the base game's: %s." % ", ".join(info["in_front_of_sabow"]))
    borrow = info.get("borrow")
    if borrow:
        tables = [e[0] for p, e in borrow["borrow"] if e[3] == "config"]
        L.append("")
        L.append("FROM OPERATION STAR - the map needs tables SABoW does not have; Operation Star has them: %s. "
                 "Converting copies them into the pack, with only the models and textures SABoW lacks: %s. "
                 "Nothing in SABoW is replaced. This map will only work for someone who owns Operation Star."
                 % (", ".join(tables), gtos_opstar.summary(borrow)))
    if info.get("object_models"):
        L.append("")
        L.append("OBJECT MODELS - the map places objects from SABoW's own tables whose models SABoW does not ship "
                 "(a missing model can crash the load with 001). Converting copies them from Operation Star: %s."
                 % "; ".join("%s (%s): %s" % (obj, t, ", ".join(n)) for t, obj, n in info["object_models"]))
    if info["missing_map_tables"]:
        L.append("")
        where ="SABoW, Operation Star nor this pack has" if info.get("opstar") else "neither SABoW nor this pack has"
        L.append("MISSING - the map needs tables that %s: %s. "
                 "The map will not load, converted or not." % (where, ", ".join(info["missing_map_tables"])))
        if not info.get("opstar"):
            L.append("(No Operation Star install was given to look in.)")
    if info["missing_campaign_tables"]:
        L.append("Missing for its campaigns only (quick battles are unaffected): %s."
                 % ", ".join(info["missing_campaign_tables"]))
    if info.get("convert_seasons"):
        L.append("")
        L.append("SEASON - %s is a NEWER VERSION of SABoW's own season table, not a foreign "
                 "format. Converting reshapes it to SABoW's schema and keeps Operation Star's "
                 "own values, so the map still looks like itself."
                 % ", ".join(info["convert_seasons"]))
    if info["problems"]:
        L.append("")
        L.append("COULD NOT READ: " + "; ".join(info["problems"]))
    L.append("")
    if info["problems"]:
        L.append("Verdict: the tool cannot convert this pack safely.")
    elif info["missing_map_tables"]:
        L.append("Verdict: cannot play yet - it depends on game data SABoW does not have. Converting will not fix that.")
    elif not needs_converting(info):
        L.append("Verdict: nothing to convert - install it as it is.")
    else:
        steps = []
        if info["needs_seasons"]:
            steps.append("replace %d season(s)" % len(info["needs_seasons"]))
        if info["needs_movement"]:
            steps.append("convert movement maps in %d cells" % len(info["needs_movement"]))
        if borrow:
            steps.append("copy in what it needs from Operation Star")
        L.append("Verdict: convert it - " + " and ".join(steps) + ".")
    return "\n".join(L)


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def out_folder(pack, install=SANDBOX):
    return os.path.join(install, "users", "modwork", "gtos", os.path.splitext(os.path.basename(pack))[0])


def convert(pack, install=SANDBOX, log=print, info=None):
    """Do only what the pack needs. Returns the finished .gt2extension, or None if nothing to do."""
    info = info or check(pack, install, log)
    if info["problems"]:
        raise SystemExit("cannot convert: " + "; ".join(info["problems"]))
    if info["missing_map_tables"]:
        raise SystemExit("cannot play even if converted - the map needs tables SABoW does not have: "
                         + ", ".join(info["missing_map_tables"]))
    if not needs_converting(info):
        log("Nothing to convert - this pack can be installed as it is.")
        return None
    root = out_folder(pack, install)
    os.makedirs(root, exist_ok=True)
    final = os.path.join(root, info["name"] + "_sabow.gt2extension")
    for stale in (final, final + ".report.txt"):
        if os.path.exists(stale):
            os.remove(stale)
    current, made = pack, []
    if info["needs_seasons"]:
        log("")
        log("STEP 1 - seasons: %s" % ", ".join("%s <- %s" % kv for kv in info["needs_seasons"].items()))
        current = gtos_season.rebuild(install, current, dict(info["needs_seasons"]), log,
                                      work=os.path.join(root, "season"), tabs_in_zip=info["tabs"])
        made.append(current)
    else:
        log("STEP 1 - seasons: nothing to do")
    if info["needs_movement"]:
        log("")
        log("STEP 2 - movement maps in %d cells" % len(info["needs_movement"]))
        current = gtos_penmap.rebuild(current, install, log, work=os.path.join(root, "penmap"), keep_cells=False)
        made.append(current)
    else:
        log("STEP 2 - movement maps: nothing to do")
    if info.get("borrow"):
        log("")
        log("STEP 3 - from Operation Star: %s" % gtos_opstar.summary(info["borrow"]))
        want = {n.lower() for n in info.get("convert_seasons") or ()}

        def reshape(name, kind, blob, lg):
            """A borrowed season in the newer schema is converted, not refused."""
            if kind == "config" and name.lower() in want:
                return gtos_season.convert_season_blob(install, blob, name, lg,
                                                       work=os.path.join(root, "season_convert", name))
            return blob

        current = gtos_opstar.pack_into(current, info, install, log,
                                        work=os.path.join(root, "opstar"), transform=reshape)
        made.append(current)
    else:
        log("STEP 3 - from Operation Star: nothing to do")
    os.replace(current, final)
    for p in made[:-1]:                     # intermediate packs are rebuilt on demand, not kept
        if os.path.isfile(p) and os.path.dirname(os.path.dirname(p)) == root:
            os.remove(p)
    digest = md5(final)
    with open(final + ".report.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(report(info) + "\n\nConverted pack: %s\nmd5 %s\n" % (final, digest))
    log("")
    log("DONE  %s  (%.0f MB, md5 %s)" % (final, os.path.getsize(final) / 1e6, digest))
    return final
