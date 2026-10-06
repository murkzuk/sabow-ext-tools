# gtos_opstar.py - borrow what a GTOS map needs from an Operation Star install. READ-ONLY here;
# gtos_maps.convert() packs the result into the converted map pack.
#
# Why (BUILD_LOG 2026-09-16, Krasnaya Polyana): Operation Star's own maps ("apos_" packs) ship only
# map cells. They name tables that live in Operation Star's tabs.flatdata (builds, builds_cap,
# flora_win, season_ua_snow), and those tables name Operation Star's village and tree models,
# which SABoW does not have. murkz: take them from Operation Star itself, which is pristine - never
# from BoW43's copies.
#
# How it follows the chain, measured 2026-09-16:
#   table   props name  mesh = build01_s01_c0,  armor_map = arm_bush_dift,  shader = sh_flora,
#           and other tables as "tabs\<name>"
#   mesh    an AZG2 model; its [MATERIALS] name textures WITHOUT their prefix:
#           bush_dift -> trans_bush_dift,  bush_norsp -> bump_bush_norsp
#   season  its weather and daytime rows name sky textures the same way: cloudy_dift -> clouds_cloudy_dift.
#           The prefix list is read from Operation Star's own texture names, never typed in: a typed
#           list without "clouds" left 10 sky textures out and Krasnaya Polyana died in weather setup
#           (adv_render+0x5184 writing item -1 of an empty table, caught under cdb 2026-09-16).
#   armour, texture, sound - leaves, nothing further
#
# Only records SABoW lacks are borrowed, matched by name AND kind, so nothing in the base game is
# ever shadowed. Operation Star's dev_updates copy wins over its base copy, as it does in that game.
# BoW43 notes/18 proved the method: per-object records into a small archive inside the add-on.

import os
import re
import shutil
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OPSTAR = __import__("settings").get("opstar")      # chosen in the tab, remembered in settings.json
SCAN_KINDS = ("config", "mesh", "shader")       # kinds that name other records; the rest are leaves
TOKEN = re.compile(rb"[A-Za-z0-9_]{3,48}")
TABLE_REF = re.compile(rb"tabs[\\/]([A-Za-z0-9_]{3,40})")


def directory(path):
    """{(name lower, kind): (name, offset, size, kind, locale)} - reads only the header and
    the directory, not the whole archive (tex_main is 190 MB)."""
    with open(path, "rb") as f:
        head = f.read(0x14)
        if head[:4] != b"AZP3":
            raise ValueError("not an AZP3 archive: %s" % path)
        count = struct.unpack_from("<I", head, 4)[0]
        end = struct.unpack_from("<I", head, 0x10)[0]
        f.seek(end - count * 0x80)
        d = f.read(count * 0x80)
    out = {}
    for i in range(count):
        e = d[i * 0x80:(i + 1) * 0x80]
        off, size = struct.unpack_from("<I", e, 8)[0], struct.unpack_from("<I", e, 0x10)[0]
        name = e[0x20:0x40].split(b"\0")[0].decode("latin1")
        kind = e[0x40:0x60].split(b"\0")[0].decode("latin1")
        loc = e[0x60:0x80].split(b"\0")[0].decode("latin1")
        out[(name.lower(), kind)] = (name, off, size, kind, loc)
    return out


def read(path, entry):
    with open(path, "rb") as f:
        f.seek(entry[1])
        return f.read(entry[2])


def _archives(folders):
    out = []
    for folder in folders:
        if os.path.isdir(folder):
            out += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".flatdata"))
    return out


def sabow_archives(install):
    return _archives([os.path.join(install, "data", "mtc80", "dev_updates", "shared", "packed_data"),
                      os.path.join(install, "data", "mtc80", "shared", "packed_data")])


def opstar_archives(opstar=OPSTAR):
    """dev_updates first: its copy of a record is the one Operation Star itself uses."""
    return _archives([os.path.join(opstar, "data", "k43t", "dev_updates", "shared", "packed_data"),
                      os.path.join(opstar, "data", "k43t", "shared", "packed_data")])


def is_opstar(opstar):
    return os.path.isfile(os.path.join(opstar, "data", "k43t", "shared", "packed_data", "tabs.flatdata"))


class Index(object):
    """Every record of a set of archives; the first archive to hold a (name, kind) wins."""

    def __init__(self, archives):
        self.records, self.by_name = {}, {}
        for path in archives:
            for key, entry in directory(path).items():
                if key not in self.records:
                    self.records[key] = (path, entry)
                    self.by_name.setdefault(key[0], []).append(key)

    def has(self, key):
        return key in self.records


def _names_in(blob, kind):
    """Record names a blob may refer to: every token, plus its prefixed texture names.
    Tables are followed only through explicit tabs\\<name> references."""
    tokens = {t.decode("latin1").lower() for t in TOKEN.findall(blob)}
    tables = {t.decode("latin1").lower() for t in TABLE_REF.findall(blob)}
    return tokens, tables


def _material_sets(src):
    """{set name lower: [texture names]} from the `materials` table: an UPPER-CASE set name, then its
    texture names until the next one (LAND_SNOW grass_frozen_dift snow2_dift ... GRASS_WINTER ...)."""
    key = ("materials", "config")
    if not src.has(key):
        return {}
    sets, current = {}, None
    for m in re.finditer(rb"[A-Za-z0-9_]{3,64}", read(*src.records[key])):
        s = m.group().decode("latin1")
        if s.isupper():
            current = sets.setdefault(s.lower(), [])
        elif current is not None and s.lower().endswith(("_dift", "_norsp")):
            current.append(s.lower())
    return sets


def _season_ambients(blob):
    """["amb_day_wint_", ...] - each daytime ambient base joined to the season's codes in `common`."""
    import azcf
    try:
        t = azcf.Table(blob)
    except ValueError:
        return []
    codes, bases = set(), set()
    for b in t.blocks:
        try:
            rows = t.rows(b)
        except Exception:
            continue
        for r in rows:
            for c in r:
                if not isinstance(c, str):
                    continue
                if b.name == "common" and c.isalpha() and c.islower() and len(c) <= 5:
                    codes.add(c)
                elif b.name == "daytime" and c.startswith("amb_"):
                    bases.add(c.rstrip("*"))
    return sorted("%s_%s_" % (b, c) for b in bases for c in codes)


# A texture's seasonal versions sit beside it with a suffix: reg_pz4g_dift -> reg_pz4g_dift_wint
# (BoW43 notes/52 key fact 5). The engine picks one by the map's season, so a vehicle needs them all.
# Off for maps: their proven packs were built without this rule and stay reproducible.
SEASON_SUFFIXES = ("wint", "des", "sum", "ostov")


def resolve(tables, install, opstar=OPSTAR, log=print, seed_tokens=(), season_variants=False):
    """Follow `tables` (names SABoW lacks) through Operation Star. `seed_tokens` starts from plain
    names instead - a vehicle's own block (gtos_vehicle.py). With `season_variants`, every borrowed
    texture brings its _wint/_des/_sum/_ostov versions too.
    Returns {"borrow": [(archive, entry)], "not_found": [table], "bytes": {kind: n}, "count": {kind: n}}."""
    have = Index(sabow_archives(install))
    src = Index(opstar_archives(opstar))
    prefixes = sorted({n.split("_")[0] for (n, k) in src.records if k == "texture" and "_" in n})
    log("Operation Star: %d records in %d archives; SABoW: %d records"
        % (len(src.records), len(opstar_archives(opstar)), len(have.records)))
    sets = _material_sets(src)
    borrow, seen, not_found = {}, set(), []
    queue, have_scanned = [], set()

    def want_texture(t):
        for name in [t] + ["%s_%s" % (p, t) for p in prefixes]:
            k = (name, "texture")
            if src.has(k) and not have.has(k):
                queue.append(k)
    for t in tables:
        key = (t.lower(), "config")
        if src.has(key):
            queue.append(key)
        else:
            not_found.append(t)
    pending_seeds = {t.lower() for t in seed_tokens}
    while queue or pending_seeds:
        if pending_seeds:
            # plain names to follow, as if they had been read out of a borrowed record
            key, blob, tokens, tables_named = None, b"", pending_seeds, set()
            pending_seeds = set()
        else:
            key = queue.pop()
            if key in seen:
                continue
            seen.add(key)
            if have.has(key):
                continue
            path, entry = src.records[key]
            borrow[key] = (path, entry)
            if season_variants and key[1] == "texture":
                for v in SEASON_SUFFIXES:
                    k = ("%s_%s" % (key[0], v), "texture")
                    if src.has(k) and not have.has(k):
                        queue.append(k)
            if key[1] not in SCAN_KINDS:
                continue
            blob = read(path, entry)
            tokens, tables_named = _names_in(blob, key[1])
        if key is not None and key[1] == "config":
            # A season names ground sets (LAND_SNOW, GRASS_WINTER, WATER_FROZEN); the materials table
            # lists each set's textures without prefix. GRASS_WINTER's two textures are Operation
            # Star's only - without them the grass rendered BLACK on Krasnaya Polyana (2026-09-16).
            for t in tokens:
                for tex in sets.get(t, ()):
                    want_texture(tex)
            if key[0].startswith("season_"):
                # Ambient sounds are asked for by BUILT names the data never spells out: the daytime
                # rows' base (amb_day) + the season code from `common` (wint) + "*", and amb_can*,
                # which no table names at all. Both were in the log as "Unable to find audio fragment".
                for pattern in _season_ambients(blob) + ["amb_can_"]:
                    for (n, k) in src.records:
                        if k == "sound" and n.startswith(pattern) and not have.has((n, k)):
                            queue.append((n, k))
        for t in tables_named:
            k = (t, "config")
            if src.has(k) and not have.has(k):
                queue.append(k)
        for t in tokens:
            candidates = [t] + ["%s_%s" % (p, t) for p in prefixes]
            for name in candidates:
                for k in src.by_name.get(name, []):
                    if k[1] == "config":
                        continue            # tables only through tabs\<name>
                    if name != t and k[1] != "texture":
                        continue            # prefixes are a texture rule
                    if not have.has(k):
                        queue.append(k)
            # A model SABoW already HAS is not borrowed, but its textures may not be: stock SABoW ships
            # the pine and fir models without their textures, and Sokolovo's conifers rendered BLACK
            # (fresh install, 2026-09-17). Follow SABoW's own copy to its textures.
            k = (t, "mesh")
            if have.has(k) and k not in have_scanned:
                have_scanned.add(k)
                for name in _names_in(read(*have.records[k]), "mesh")[0]:
                    want_texture(name)
    count, size = {}, {}
    for (name, kind), (path, entry) in borrow.items():
        count[kind] = count.get(kind, 0) + 1
        size[kind] = size.get(kind, 0) + entry[2]
    return {"borrow": sorted(borrow.values(), key=lambda pe: (pe[1][3], pe[1][0])),
            "not_found": not_found, "count": count, "bytes": size}


def summary(res):
    parts = ["%d %s" % (res["count"][k], k) for k in sorted(res["count"])]
    return "%s (%.0f MB)" % (", ".join(parts), sum(res["bytes"].values()) / 1e6)


# ---------------------------------------------------------------- packing

def _mkflat(records, out, install, work, log):
    """records: [(name, kind, loc, bytes)] -> AZP3 archive `out`, built by the game's own mkflat
    and read back: every record byte-identical, every checksum right."""
    import build
    import gtos_penmap
    pack = os.path.join(work, os.path.splitext(os.path.basename(out))[0])
    shutil.rmtree(pack, ignore_errors=True)
    os.makedirs(pack)
    flat = os.path.join(pack, "archive.!flatlist")
    with open(flat, "w", encoding="utf-8", newline="\n") as f:
        f.write("i_unflat:unflat()\n{\n")
        for name, kind, loc, blob in records:
            with open(os.path.join(pack, "%s.%s.%s" % (name, loc, kind)), "wb") as g:
                g.write(blob)
            # NO PADDING, AND THAT IS LOAD-BEARING. mkflat reads this list through a 19,456-byte
            # (0x4C00) buffer and SILENTLY IGNORES every line past it - measured 2026-09-28 on the crew
            # build: 498 records were written, 340 were packed and the 158 after byte 19456 were dropped
            # without a word. Padded to 32 and 10 (the old style here, 57 bytes a line) that is a cap of
            # 341 records; with single spaces it is 564, and the same 498 come to 17,151 bytes. The
            # add-on was at 312 records and one build away from losing records, and the build's own
            # read-back is what caught it.
            f.write("\t%s, %s, %s;\n" % (name, kind, loc))
        f.write("}\n")
    if os.path.exists(out):
        os.remove(out)
    build.starter(install, "mkflat,", build.rel(out, install) + ",", build.rel(flat, install),
                  expect=out, timeout=1800)
    got = directory(out)
    want = {(n.lower(), k): (n, k, l, b) for n, k, l, b in records}
    if sorted(got) != sorted(want):
        raise SystemExit("%s holds %d records, expected %d" % (os.path.basename(out), len(got), len(want)))
    for key, (n, k, l, b) in want.items():
        if got[key][4] != l or read(out, got[key]) != b:
            raise SystemExit("%s: %s is not what was written" % (os.path.basename(out), n))
    bad = [k for k, (stored, actual) in gtos_penmap.dir_sums(out).items()
           if stored != actual and not (actual == 0 and stored == 0xffffffff)]
    if bad:
        raise SystemExit("%s: checksums wrong after mkflat: %s" % (os.path.basename(out), bad))
    shutil.rmtree(pack, ignore_errors=True)
    log("OK  %s: %d records, each byte-identical to its source, checksums correct (%.0f MB)"
        % (os.path.basename(out), len(records), os.path.getsize(out) / 1e6))


def pack_into(pack_in, info, install, log=print, work=None, transform=None):
    """Put info["borrow"] into a copy of the pack: borrowed tables join the pack's tabs.flatdata
    (or become one), everything else goes into <source archive>_opstar.flatdata beside it.
    Returns the new .gt2extension."""
    res = info["borrow"]
    work = work or os.path.join(install, "users", "modwork", "gtos", info["name"], "opstar")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    with zipfile.ZipFile(pack_in) as z:
        names = z.namelist()
        desc = [n for n in names if n.lower().endswith("desc.addpack")]
        if len(desc) != 1:
            raise SystemExit("cannot find the pack's desc.addpack to know where its files live")
        prefix = desc[0][:-len("desc.addpack")] + "shared/packed_data/"
        tabs_member = info["tabs"]
        pack_tabs = []
        if tabs_member:
            tp = os.path.join(work, "pack_tabs.flatdata")
            with open(tp, "wb") as f:
                f.write(z.read(tabs_member))
            d = directory(tp)
            pack_tabs = [(e[0], e[3], e[4], read(tp, e)) for e in d.values()]
            os.remove(tp)

    groups = {}
    for path, entry in res["borrow"]:
        name, off, size, kind, loc = entry
        if kind == "config":
            group = "tabs"
        else:
            group = os.path.splitext(os.path.basename(path))[0] + "_opstar"
        blob = read(path, entry)
        # transform: a borrowed record may need reshaping before it is written - a GTOS season
        # is a NEWER version of SABoW's own table, not a foreign format (2026-09-23).
        if transform is not None:
            blob = transform(name, kind, blob, log)
        groups.setdefault(group, []).append((name, kind, loc, blob))
    if "tabs" in groups:
        clash = {n.lower() for n, k, l, b in pack_tabs} & {n.lower() for n, k, l, b in groups["tabs"]}
        if clash:
            raise SystemExit("the pack already has tables named %s" % sorted(clash))
        groups["tabs"] = pack_tabs + groups["tabs"]

    built = {}
    for group in sorted(groups):
        out = os.path.join(work, group + ".flatdata")
        log("  packing %s ..." % os.path.basename(out))
        _mkflat(groups[group], out, install, work, log)
        member = tabs_member if (group == "tabs" and tabs_member) else prefix + group + ".flatdata"
        built[member] = out
    lower = {n.lower() for n in names}
    for member in built:
        if member.lower() in lower and member != tabs_member:
            raise SystemExit("the pack already has a file %s" % member)

    new = os.path.join(work, os.path.basename(pack_in).replace(".gt2extension", "_opstar.gt2extension"))
    partial = new + ".partial"
    with zipfile.ZipFile(pack_in) as zin, zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename in built:
                with open(built[item.filename], "rb") as f:
                    zout.writestr(item, f.read())
            else:
                zout.writestr(item, zin.read(item.filename))
        # Added archives take the pack's own desc.addpack date, not the build time, so the same
        # conversion gives the same md5 on any day (a fresh-install rebuild differed only by time).
        stamp = zin.getinfo(desc[0]).date_time
        for member, path in sorted(built.items()):
            if member not in names:
                info = zipfile.ZipInfo(member, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as f:
                    zout.writestr(info, f.read())
    with zipfile.ZipFile(partial) as z:
        got = z.namelist()
        expect = names + sorted(m for m in built if m not in names)
        if got != expect:
            raise SystemExit("the new pack has a different file list")
        for member, path in built.items():
            with open(path, "rb") as f:
                if z.read(member) != f.read():
                    raise SystemExit("%s inside the new pack is not the one that was built" % member)
    os.replace(partial, new)
    for path in built.values():
        os.remove(path)
    log("OK  wrote %s (%.0f MB) - added %s" % (new, os.path.getsize(new) / 1e6,
                                             ", ".join(sorted(built))))
    return new


if __name__ == "__main__":
    import sys
    install = sys.argv[1] if len(sys.argv) > 1 else r"K:\SABoW_sandbox"
    wanted = sys.argv[2:] or ["builds", "builds_cap", "flora_win", "season_ua_snow"]
    r = resolve(wanted, install)
    print(summary(r))
    for path, entry in r["borrow"]:
        print("  %-8s %-36s %9d  %s" % (entry[3], entry[0], entry[2], os.path.relpath(path, OPSTAR)))
    if r["not_found"]:
        print("NOT in Operation Star:", r["not_found"])
