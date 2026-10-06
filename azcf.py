# azcf - read Steel Armor's compiled tables directly. READ-ONLY.
#
# Part of the SABoW Ext tool. It lets the tool (and murkz) look inside the
# game's own vehicle tables without an AI and without running starter.exe.
#
# Two layers:
#
#   AZP3  the archive (e.g. tabs.flatdata) - a directory of named records
#   AZCF  one compiled table inside it (e.g. techn_base_mtc80) - named blocks,
#         each a grid of 32-byte cells
#
# Why read the compiled form rather than decompile to text: Graviteam's own
# decompiler (cfgp2pd) has known defects, and common_res cannot round-trip
# through it at all because some strings contain commas (BoW43 notes/43,
# patchgate.py). Reading the compiled cells has neither problem.
#
# The layout, verified 2026-09-15 against the stock tsh2b sights row, all 56
# values matching its known text:
#
#   AZCF header   u32[4] = block count + 1
#   descriptors   start at byte 192, 128 bytes each:
#                   +0   name, 32 bytes, NUL padded
#                   +32  flag   +36 spec length   +40 row count
#                   +44  pointer to the spec letters
#                   +48  pointer to the row data
#   rows          spec length * 32 bytes each; one 32-byte cell per letter
#   cells         s  string: u32 length, u32 pointer into this table
#                 v  vector: 4 x float32
#                 a  array:  4 x u32
#                 f  float32     b  u32, 0 or 1     u  u32
#                 anything else is read as u32
#
# The self-test at the bottom re-checks all of this against the installed game,
# so a wrong decode fails loudly instead of quietly producing a wrong list.

import os
import struct

ARCHIVE_ENTRY = 0x80

# One directory read per archive, however many names get looked for in it. See archive_records.
_CACHE = {}


# ---------------------------------------------------------------- AZP3 archives


def archive_entries(path):
    """Every record in an AZP3 archive, in directory order, DUPLICATES AND ALL.

    [(name, offset, size, kind, locale)]. archive_records() collapses these into a dict keyed by
    name, so two records sharing a name become one. Measured on text_loc.flatdata: the game's own
    unflat reports 19 records and the dict held 16, so three were invisible to every count taken
    from it. Anything that COUNTS records must use this, not the dict.

    Reads the directory and nothing else, cached per file by size and mtime.
    """
    key = os.path.abspath(path)
    try:
        st = os.stat(key)
        stamp = (st.st_size, st.st_mtime_ns)
    except OSError:
        stamp = None
    hit = _CACHE.get(key)
    if hit is not None and stamp is not None and hit[0] == stamp:
        return hit[1]
    with open(key, "rb") as f:
        head = f.read(0x20)
        if head[:4] != b"AZP3":
            raise ValueError("not an AZP3 archive: %s" % path)
        count, = struct.unpack_from("<I", head, 0x04)
        end, = struct.unpack_from("<I", head, 0x10)
        base = end - count * ARCHIVE_ENTRY
        want = count * ARCHIVE_ENTRY
        if count < 0 or base < 0:
            raise ValueError("archive directory is not inside the file: %s" % path)
        f.seek(base)
        blob = f.read(want)
    if len(blob) < want:
        raise ValueError("archive directory runs past the end of the file: %s" % path)
    out = []
    for i in range(count):
        e = blob[i * ARCHIVE_ENTRY: (i + 1) * ARCHIVE_ENTRY]
        off, = struct.unpack_from("<I", e, 0x08)
        size, = struct.unpack_from("<I", e, 0x10)
        name = e[0x20:0x40].split(bytes([0]))[0].decode("latin1")
        kind = e[0x40:0x60].split(bytes([0]))[0].decode("latin1")
        loc = e[0x60:0x80].split(bytes([0]))[0].decode("latin1")
        out.append((name, off, size, kind, loc))
    if stamp is not None:
        _CACHE[key] = (stamp, out)
    return out


def archive_records(path):
    """{name: (offset, size, kind, locale)} - the LAST of any duplicate names wins.

    For looking a record up by name. Use archive_entries() when the question is how many there are.
    """
    out = {}
    for name, off, size, kind, loc in archive_entries(path):
        out[name] = (off, size, kind, loc)
    return out


def read_record(path, name):
    recs = archive_records(path)
    if name not in recs:
        raise KeyError("%s is not in %s" % (name, path))
    off, size, kind, loc = recs[name]
    with open(path, "rb") as f:
        f.seek(off)
        return f.read(size)


# ---------------------------------------------------------------- AZCF tables

class Block(object):
    __slots__ = ("name", "spec", "rows", "data_ptr", "index")

    def __init__(self, name, spec, rows, data_ptr, index):
        self.name, self.spec, self.rows = name, spec, rows
        self.data_ptr, self.index = data_ptr, index

    def __repr__(self):
        return "Block(%s, spec=%r, rows=%d)" % (self.name, self.spec, self.rows)


class Table(object):

    def __init__(self, data):
        if data[:4] != b"AZCF":
            raise ValueError("not a compiled AZCF table")
        self.data = data
        count = struct.unpack_from("<I", data, 4)[0] - 1
        self.blocks = []
        for i in range(count):
            o = 192 + i * 128
            name = data[o:o + 32].split(b"\0")[0].decode("latin1")
            flag, speclen, rows = struct.unpack_from("<III", data, o + 32)
            spec_ptr, data_ptr = struct.unpack_from("<II", data, o + 44)
            spec = data[spec_ptr:spec_ptr + speclen].decode("latin1") if speclen else ""
            self.blocks.append(Block(name, spec, rows, data_ptr, i))

    def string(self, cell):
        ln, ptr = struct.unpack_from("<II", cell, 0)
        if not ln:
            return ""
        # A cell that is not really a string can hold a huge "length". Refuse it
        # rather than read megabytes of the file - that froze the first draft.
        if ln > 65536 or ptr + ln > len(self.data):
            return "<not a string>"
        return self.data[ptr:ptr + ln].decode("cp1251", "replace")

    def props(self, block):
        """A `props` block as {key: value}.

        Despite its spec letter `s`, a props block is not a list of strings. Its
        rows come in PAIRS: a typed value cell, then a cell holding the key name
        inline. The value cell's type marker is the u32 at byte 16:

            0 float    1 vector (4 floats)    2 string    4 int    5 bool

        Worked out on the T-62, 2026-09-15: name = txt_tn_t62, mesh = t62,
        type = TANK (a four-letter code stored as a u32), and so on.

        The block's row count is the number of PAIRS, not cells: 2 x rows
        cells. Reading it as cells lost the second half of every block - the
        T-62 has 70 properties, and `user_in` on the quick-battle platoons was
        never seen, which sent a whole diagnosis the wrong way. Checked on all
        144 props blocks in qbattle and all 36 in techn_base_mtc80.
        """
        out = {}
        for r in range(block.rows):
            base = block.data_ptr + r * 64
            vc = self.data[base:base + 32]
            key = self.data[base + 32:base + 64].split(b"\0")[0].decode("latin1")
            tag = struct.unpack_from("<I", vc, 16)[0]
            if tag == 0:
                val = struct.unpack_from("<f", vc)[0]
            elif tag == 1:
                val = struct.unpack_from("<4f", vc)
            elif tag == 2:
                val = self.string(vc)
            elif tag == 4:
                val = struct.unpack_from("<i", vc)[0]
            elif tag == 5:
                val = bool(struct.unpack_from("<I", vc)[0])
            else:
                val = ("<type %d>" % tag, vc[:16].hex())
            out[key] = val
        return out

    def cell(self, letter, cell):
        if letter == "s":
            return self.string(cell)
        if letter == "v":
            return struct.unpack_from("<4f", cell)
        if letter == "a":
            return struct.unpack_from("<4I", cell)
        if letter == "f":
            return struct.unpack_from("<f", cell)[0]
        if letter == "b":
            return bool(struct.unpack_from("<I", cell)[0])
        return struct.unpack_from("<I", cell)[0]

    def rows(self, block):
        """Every row of a block as a list of values, one per spec letter."""
        stride = len(block.spec) * 32
        out = []
        for r in range(block.rows):
            base = block.data_ptr + r * stride
            out.append([self.cell(t, self.data[base + i * 32: base + (i + 1) * 32])
                        for i, t in enumerate(block.spec)])
        return out

    def find(self, name):
        return [b for b in self.blocks if b.name == name]


def flat(values):
    """A row flattened the way the text table writes it - vectors and arrays
    spread into their 4 values. Used to compare against known text."""
    out = []
    for v in values:
        out.extend(v if isinstance(v, tuple) else [v])
    return out


# ---------------------------------------------------------------- techn tables

def vehicles(table):
    """Group a techn table into vehicles.

    A vehicle is a name block with no spec and no rows (e.g. `t62`), followed by
    its own sub-blocks (props, heads, work_places, sights, ...) up to the next
    such name block. Returns [(name, {subblock_name: Block})].

    DO NOT "IMPROVE" THIS TEST. It was changed on 2026-09-27 to group on "the next block is props",
    which reads a PACKED add-on correctly - and it silently altered what the BUILDER produced: the
    same specs rebuilt to a package differing from the proven one in four tables, cocpits by 120 KB.
    A shared helper's behaviour is part of every proven build. Callers that need the packed-add-on
    reading ask for vehicles_any() below, by name.
    """
    out, current = [], None
    for b in table.blocks:
        if b.spec == "" and b.rows == 0:
            current = (b.name, {})
            out.append(current)
        elif current is not None:
            current[1].setdefault(b.name, b)
    return out


def vehicles_any(table):
    """vehicles(), but it also reads a PACKED add-on - a SEPARATE FUNCTION ON PURPOSE (see above).

    A vehicle's header in a packed add-on carries a ONE-NUL spec ('\x00') where the base game's
    tables carry an empty one, so vehicles() returns the zero-row SUB-tables instead - shell_places,
    marks, carets and 17 more on gtos_ww2's techn_gtos, and none of its 13 vehicles. Measured
    2026-09-27: three checks built on vehicles() examined the wrong blocks and still printed OK.
    The header here is "the block whose next block is props", which is true of both.
    """
    blocks = table.blocks
    header = set(i for i, b in enumerate(blocks)
                 if b.rows == 0 and i + 1 < len(blocks) and blocks[i + 1].name == "props")
    if not header:
        return vehicles(table)          # nothing to go on - the old rule is all there is
    out, current = [], None
    for i, b in enumerate(blocks):
        if i in header:
            current = (b.name, {})
            out.append(current)
        elif current is not None:
            current[1].setdefault(b.name, b)
    return out


# ---------------------------------------------------------------- self-test

TSH2B_KNOWN = [
    "tsh2b", 9, 63, 0, 0, 3.5, 7, 0, 0, 2, 0.3, 0.2, 0.05, 2, True, 0, 0, 0, 0,
    1, 0.2, 0, 0, False, "tnsh2b_41", "cross", 3221225472, 4293318077,
    4294967295, 4289571728, 3, 0, -0.5, 0.2, 3, False, 0.791183, 1.43, 0.2, 0,
    False, "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, "txt_sig_tnsh2b_41",
    "tnk_sig_tele", "tnsh2b_41_zoom"]

# Stock qbattle, read from raw cells 2026-09-15. mobility and type are
# four-letter codes stored as a u32 ("PIL", "STR").
_PIL, _STR = 0x4C4950, 0x525453
PLATOONS_KNOWN = {
    "iq_tank_plat1": {"code": 33, "name": "txt_qb_pl_iq_tank1", "str_sprite": "pl_tank_t62",
                      "max_squads": 6, "mobility": _PIL, "pool": "p_iq_tank_bat", "type": _STR,
                      "uid": 53505, "user_in": True, "camo": "pat1"},
    "iq_tank_plat2": {"code": 49, "name": "txt_qb_pl_iq_tank2", "str_sprite": "pl_tank_t62",
                      "max_squads": 6, "mobility": _PIL, "pool": "p_iq_tank_bat", "type": _STR,
                      "uid": 53553, "camo": "pat1", "user_in": False},
}


def self_test(tabs_flatdata):
    """Decode the stock tsh2b sights row and compare every value with its known
    text. Returns (ok, message). If this fails, nothing else the tool reads from
    these tables can be trusted."""
    t = Table(read_record(tabs_flatdata, "common_res_mod"))
    blk = t.find("sights")
    if not blk:
        return False, "no sights block in common_res_mod"
    row = next((r for r in t.rows(blk[0]) if r[0] == "tsh2b"), None)
    if row is None:
        return False, "no tsh2b row in common_res_mod sights"
    got = flat(row)
    if len(got) != len(TSH2B_KNOWN):
        return False, "tsh2b decoded to %d values, expected %d" % (len(got), len(TSH2B_KNOWN))
    for i, (g, k) in enumerate(zip(got, TSH2B_KNOWN)):
        same = (abs(g - k) < 1e-4) if isinstance(k, float) and not isinstance(k, bool) else (g == k)
        if not same:
            return False, "tsh2b value %d decoded as %r, expected %r" % (i, g, k)

    # Property blocks: the stock Iraqi tank platoons. Their LAST key is
    # user_in or camo, so a reader that only gets half of a block fails here.
    q = Table(read_record(tabs_flatdata, "qbattle"))
    for name, known in PLATOONS_KNOWN.items():
        blk = q.find(name)
        if not blk:
            return False, "no %s block in qbattle" % name
        got = q.props(blk[0])
        if got != known:
            return False, "%s decoded as %r, expected %r" % (name, got, known)
    return True, ("table reader verified: all %d tsh2b values and %d platoon "
                  "property blocks match" % (len(TSH2B_KNOWN), len(PLATOONS_KNOWN)))


if __name__ == "__main__":
    import sys
    import os
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        __import__("settings").get("live"), "data", "mtc80", "shared", "packed_data", "tabs.flatdata")
    ok, msg = self_test(path)
    print(("OK  " if ok else "FAIL  ") + msg)
    sys.exit(0 if ok else 1)
