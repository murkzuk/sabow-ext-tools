# gtos_penmap.py - convert a GTOS map pack's movement maps from 56- to 60-byte nodes.
#
# Why (docs/gtos-zhal69-first-run.md, 2026-09-16): every GTOS map died a few seconds into the 3D
# battle in SABoW - BoW43 notes/56's wall. Caught under a debugger: adv_game FUN_1006f2c0 walks a
# tactical movement quadtree (the pen_tanks / pen_hums / pen_cars / pen_apcs layers of each map
# cell) at 60 bytes per node, and faults on a garbage child index. SABoW's own map cells store
# 60-byte nodes; GTOS cells store 56-byte nodes, so every node is read 4 bytes further out of step.
#
# Layout, measured field by field across ~40,000 nodes of each format:
#
#     field                       SABoW (60)   GTOS (56)
#     4 neighbours + 4 children   +0x00-0x1f   +0x00-0x1f   (-1 = none)
#     extra field                 +0x20        absent       same junk value in ~every node -> 0
#     link-like index             +0x24        +0x20
#     flags (0x80 = has children) +0x28        +0x24
#     tree depth (1-9)            +0x2c        +0x28
#     unknown pair                +0x30        +0x30
#     position shorts (x, z)      +0x34        +0x2c
#     movement class              +0x38        +0x34
#
# Map cells (*.polypack2) are AZP3 archives. Each record's directory carries a byte-sum checksum;
# the game's own mkflat rebuilds a cell with every record byte-identical and every checksum correct
# (proven on zgc2_zhalanashkol, 2026-09-16), so cells are repacked with mkflat, never patched in
# place. Everything happens in the SANDBOX; the result is a new .gt2extension installed through
# the updater, which re-signs it.

import os
import shutil
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf     # noqa: E402
import build    # noqa: E402

SANDBOX = r"K:\SABoW_sandbox"
PACK_IN = os.path.join(SANDBOX, "users", "modwork", "zhal_fix",
                       "gtos_zhal69_jul13_int_sabowseason.gt2extension")
LAYERS = ("pen_tanks", "pen_hums", "pen_cars", "pen_apcs")
ZERO4 = bytes(4)


def node_size(blob):
    """56 or 60, decided by the tree-depth field (1-16 in every node), not by record size -
    some cells are exact multiples of both."""
    votes = {}
    for size, depth_at in ((56, 0x28), (60, 0x2c)):
        if len(blob) % size:
            continue
        n = len(blob) // size
        good = sum(1 for i in range(n) if 1 <= struct.unpack_from("<I", blob, i * size + depth_at)[0] <= 16)
        votes[size] = good / float(n)
    ok = [s for s, v in votes.items() if v > 0.99]
    if len(ok) != 1:
        raise SystemExit("cannot tell the node size: %r" % votes)
    return ok[0], votes


def to60(blob):
    out = bytearray()
    for o in range(0, len(blob), 56):
        n = blob[o:o + 56]
        out += (n[0x00:0x20] + ZERO4 + n[0x20:0x24] + n[0x24:0x28] + n[0x28:0x2c]
                + n[0x30:0x34] + n[0x2c:0x30] + n[0x34:0x38])
    return bytes(out)


def check60(old56, new60):
    """Every field of every node, read back at 60, must equal the 56-byte original."""
    if len(new60) % 60 or len(old56) // 56 != len(new60) // 60:
        raise SystemExit("node count changed")
    pairs = ((0x00, 0x00, 32), (0x20, 0x24, 4), (0x24, 0x28, 4), (0x28, 0x2c, 4),
             (0x30, 0x30, 4), (0x2c, 0x34, 4), (0x34, 0x38, 4))
    for i in range(len(old56) // 56):
        a, b = i * 56, i * 60
        if new60[b + 0x20:b + 0x24] != ZERO4:
            raise SystemExit("node %d: extra field not zero" % i)
        for src, dst, ln in pairs:
            if old56[a + src:a + src + ln] != new60[b + dst:b + dst + ln]:
                raise SystemExit("node %d: field 0x%02x -> 0x%02x wrong" % (i, src, dst))
    return len(old56) // 56


def dir_sums(path):
    """{record: (stored checksum, actual byte sum)} for an AZP3 archive."""
    d = open(path, "rb").read()
    count = struct.unpack_from("<I", d, 4)[0]
    end = struct.unpack_from("<I", d, 0x10)[0]
    base = end - count * 0x80
    out = {}
    for i in range(count):
        x = d[base + i * 0x80: base + (i + 1) * 0x80]
        name = x[0x20:0x40].split(b"\0")[0].decode("latin1")
        off, size = struct.unpack_from("<I", x, 8)[0], struct.unpack_from("<I", x, 0x10)[0]
        out[name] = (struct.unpack_from("<I", x, 4)[0], sum(d[off:off + size]) & 0xffffffff)
    return out


def convert_cell(cell_bytes, name, work, install=SANDBOX):
    """(new cell bytes, report lines). Returns the original bytes if no layer is 56."""
    cdir = os.path.join(work, name)
    shutil.rmtree(cdir, ignore_errors=True)
    pack = os.path.join(cdir, "pack")
    os.makedirs(pack)
    src = os.path.join(cdir, "original.polypack2")
    with open(src, "wb") as f:
        f.write(cell_bytes)
    recs = azcf.archive_records(src)
    new_blobs, report, converted = {}, [], False
    for rec in recs:
        blob = azcf.read_record(src, rec)
        if rec in LAYERS:
            size, _ = node_size(blob)
            if size == 56:
                conv = to60(blob)
                report.append("%s %d nodes 56->60" % (rec, check60(blob, conv)))
                blob, converted = conv, True
            else:
                report.append("%s already 60" % rec)
        new_blobs[rec] = blob
    if not converted:
        return cell_bytes, report
    flat = os.path.join(pack, "cell.!flatlist")
    with open(flat, "w", encoding="utf-8", newline="\n") as f:
        f.write("i_unflat:unflat()\n{\n")
        for rec, (off, size, kind, loc) in recs.items():
            with open(os.path.join(pack, "%s.%s.%s" % (rec, loc, kind)), "wb") as g:
                g.write(new_blobs[rec])
            f.write("\t%s, %s, %s ;\n" % (rec.ljust(16), kind.ljust(8), loc))
        f.write("}\n")
    out = os.path.join(cdir, "converted.polypack2")
    build.starter(install, "mkflat,", build.rel(out, install) + ",", build.rel(flat, install),
                  expect=out, timeout=900)
    got = azcf.archive_records(out)
    if [(k, v[2], v[3]) for k, v in got.items()] != [(k, v[2], v[3]) for k, v in recs.items()]:
        raise SystemExit("%s: record names/kinds/locales changed" % name)
    for rec in recs:
        if azcf.read_record(out, rec) != new_blobs[rec]:
            raise SystemExit("%s: %s inside the rebuilt cell is not what was written" % (name, rec))
    # A zero byte-sum is stored as 0xffffffff - the original GTOS cells and the game's own mkflat
    # both do this (zgd3_zhalanashkol's 4-byte all-zero obj_quads, 2026-09-16).
    bad = [k for k, (stored, actual) in dir_sums(out).items()
           if stored != actual and not (actual == 0 and stored == 0xffffffff)]
    if bad:
        raise SystemExit("%s: checksums wrong after mkflat: %s" % (name, bad))
    report.append("rebuilt: %d records exact, checksums correct" % len(recs))
    with open(out, "rb") as f:
        return f.read(), report


def rebuild(pack_in=PACK_IN, install=SANDBOX, log=print, work=None, keep_cells=True):
    """`work` defaults to the folder the proven Zhalanashkol pack was built in. With
    keep_cells=False the per-cell scratch folders (~100 MB each) are deleted once the
    pack has been written and checked - the GTOS maps tab does that."""
    work = work or os.path.join(install, "users", "modwork", "penmap")
    os.makedirs(work, exist_ok=True)
    pack_out = os.path.join(work, os.path.basename(pack_in).replace(".gt2extension", "_penmap60.gt2extension"))
    partial = pack_out + ".partial"     # renamed only when every cell has passed its checks
    for stale in (pack_out, partial):
        if os.path.exists(stale):
            os.remove(stale)
    changed = 0
    with zipfile.ZipFile(pack_in) as zin, zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.lower().endswith(".polypack2"):
                name = os.path.basename(item.filename).rsplit(".", 1)[0]
                data, report = convert_cell(data, name, work, install)
                log("  %-22s %s" % (name, "; ".join(report)))
                changed += any("56->60" in r for r in report)
            zout.writestr(item, data)
    with zipfile.ZipFile(pack_in) as a, zipfile.ZipFile(partial) as b:
        if a.namelist() != b.namelist():
            raise SystemExit("the new pack has a different file list")
    os.replace(partial, pack_out)
    if not keep_cells:
        for name in os.listdir(work):
            cdir = os.path.join(work, name)
            if os.path.isdir(cdir) and os.path.isfile(os.path.join(cdir, "original.polypack2")):
                shutil.rmtree(cdir, ignore_errors=True)
    log("OK  %d cells converted; wrote %s (%.0f MB)" % (changed, pack_out, os.path.getsize(pack_out) / 1e6))
    return pack_out


if __name__ == "__main__":
    rebuild()
