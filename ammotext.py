# ammotext - rewrite the ammunition names the gunner sees when picking a round, so each
# one names its SIGHT SCALE as well as the type (murkz, 2026-09-16):
#     БР 412Д - AP    БК - HEAT    ОФ ПОЛН - HE    ГТ Т - 7.62    ПОДК-APDS
#
# The strings live in the AZTX record `loc_kit_units_mtc80`
# (data\mtc80\loc_eng\packed_data\text_loc.flatdata). Format, measured 2026-09-16:
#
#     entry, 48 bytes   id[32] then u32 line count, u32 pointer to the line table,
#                       u32 (unknown, kept), u32 0
#     line table        16 bytes per line: u32 length, u32 offset of the text, 0, 0
#     text              raw bytes at that offset, CP1251, no terminator needed
#
# So a line's text is found by length, not by a NUL - which means an entry's lines can be
# REPACKED inside the bytes they already occupy: write the new text contiguously from the
# first line's offset and update each line's length and offset. Nothing else in the record
# moves, and the record keeps its size.
#
# The game's own text2pd/pd2text round trip is LOSSY (measured: blank lines dropped,
# trailing spaces trimmed - the rank list came back one short and every rank shifted), so
# it is never used to write.

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402

ENTRY = 48
LINE = 16

# The record we take the stock text from -> the record name we SHIP it under.
# v25 shipped these under their stock names (loc_kit_units, loc_kit_units_mtc80) and the
# engine ignored them entirely - the artefact was verified correct on disk and the names
# in game did not change (BUILD_LOG 2026-09-16). Two explanations were left: a record
# whose name already exists in data\mtc80\loc_eng cannot replace it, or a string id that
# already exists cannot be redefined whatever record it sits in. Shipping the same bytes
# under our own name separates them, and costs nothing if it fails.
SHIP_AS = {
    "loc_kit_units_mtc80": "sabow_ext_units_mtc80",
    "loc_kit_units":       "sabow_ext_units",
}

# record -> {text id: the lines we want (full name, short name, type)}
# Each entry's new text must fit the bytes its old text occupied; the coax one has only
# 17, hence no spaces round its dash.
WANTED = {
    "loc_kit_units_mtc80": {
        "txt_sh_d10t_br412d": ("БР 412Д - AP", "БР 412Д", "AP"),
        "txt_sh_d10t_3bk17":  ("БК - HEAT", "БК", "HEAT"),
        "txt_sh_d10t_3of32":  ("ОФ ПОЛН - HE", "ОФ ПОЛН", "HE"),
        "txt_sh_d10t_3bm25":  ("ПОДК - APDS", "ПОДК", "APDS"),
    },
    "loc_kit_units": {
        "txt_sh_762_ap":      ("ГТ Т-7.62", "ГТ Т", "7.62"),
    },
}


def archive(install):
    return os.path.join(install, "data", "mtc80", "loc_eng", "packed_data", "text_loc.flatdata")


def entries(blob):
    """[(entry offset, id, line count, line-table pointer)]."""
    start = blob.find(b"txt_")
    out, o = [], start
    while o + ENTRY <= len(blob):
        name = blob[o:o + 32].split(b"\0")[0].decode("latin1")
        cnt, ptr, _spare, pad = struct.unpack_from("<4I", blob, o + 32)
        if not name.startswith("txt") or cnt > 64 or pad != 0 or ptr >= len(blob):
            break
        out.append((o, name, cnt, ptr))
        o += ENTRY
    return out


def lines_of(blob, ptr, cnt):
    """[(length, offset, text)] for one entry."""
    out = []
    for i in range(cnt):
        ln, at, _a, _b = struct.unpack_from("<4I", blob, ptr + i * LINE)
        out.append((ln, at, blob[at:at + ln]))
    return out


def patch(blob, wanted):
    """Return (new bytes, report). Same length; only the named entries' text and line
    tables change."""
    data = bytearray(blob)
    report, done = [], set()
    for _o, name, cnt, ptr in entries(blob):
        if name not in wanted:
            continue
        lines = lines_of(blob, ptr, cnt)
        first = lines[0][1]
        room = lines[-1][1] + lines[-1][0] - first          # bytes this entry's text owns
        new = [s.encode("cp1251") for s in wanted[name]][:cnt]
        while len(new) < cnt:                                # keep every line the game expects
            new.append(lines[len(new)][2])
        need = sum(len(s) for s in new)
        if need > room:
            raise SystemExit("%s: new text needs %d bytes, only %d available - shorten it"
                             % (name, need, room))
        at = first
        for i, s in enumerate(new):
            data[at:at + len(s)] = s
            struct.pack_into("<2I", data, ptr + i * LINE, len(s), at)
            at += len(s)
        if at < first + room:                                 # blank whatever is left over
            data[at:first + room] = b" " * (first + room - at)
        report.append("%-22s %s -> %s  (%d of %d bytes)"
                      % (name, [x[2].decode("cp1251") for x in lines],
                         [s.decode("cp1251") for s in new], need, room))
        done.add(name)
    missing = set(wanted) - done
    if missing:
        raise SystemExit("not in this record: %s" % ", ".join(sorted(missing)))
    if len(data) != len(blob):
        raise SystemExit("the record changed length")
    return bytes(data), report


def check(original, patched, wanted):
    """Read the patched record back with the same reader: our entries say what we asked,
    every other entry reads exactly as before."""
    a, b = entries(original), entries(patched)
    if [(x[1], x[2], x[3]) for x in a] != [(y[1], y[2], y[3]) for y in b]:
        raise SystemExit("the entry table changed")
    for (_o, name, cnt, ptr) in a:
        old = [x[2] for x in lines_of(original, ptr, cnt)]
        new = [x[2] for x in lines_of(patched, ptr, cnt)]
        if name in wanted:
            want = [s.encode("cp1251") for s in wanted[name]][:cnt]
            if new[:len(want)] != want:
                raise SystemExit("%s reads %r, expected %r" % (name, new, want))
        elif old != new:
            raise SystemExit("%s changed but should not have: %r -> %r" % (name, old, new))
    return ["all %d text entries read back correctly; %d changed, %d untouched"
            % (len(a), len(wanted), len(a) - len(wanted))]


def patched_records(install, log=print):
    """[(record name, new bytes)] - every record whose ammunition text we change."""
    out = []
    for record, wanted in WANTED.items():
        blob = azcf.read_record(archive(install), record)
        new, rep = patch(blob, wanted)
        log("   %s:" % record)
        for line in rep:
            log("     " + line)
        for line in check(blob, new, wanted):
            log("OK   " + line)
        out.append((SHIP_AS[record], new))
    return out


def wanted_for(ship_name):
    """The ids we changed, looked up by the name the record is SHIPPED under."""
    for source, ship in SHIP_AS.items():
        if ship == ship_name:
            return WANTED[source]
    raise KeyError(ship_name)


if __name__ == "__main__":
    import build
    patched_records(build.INSTALL)
