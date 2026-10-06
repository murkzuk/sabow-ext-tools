# ownsight - give a vehicle its OWN gunner's sight instead of the one it borrows.
# Part of the SABoW Ext tool. build.py calls it when the recipe has a "sight" step.
#
# Three pieces go into the addon (BoW43 notes/78, 82, 83, 85 and 86 are the source for
# every rule here):
#
#   1. the reticle mesh, made by the vehicle's own generator (chieftain_sight.py),
#      read back and checked before it is packed
#   2. common_res_mod holding ONE sights row - a copy of the sight the vehicle uses
#      now, renamed, with its two reticle fields pointed at the new mesh. Only our
#      own row ships: the whole table doubles the weapons reservation and a second
#      extra row stopped the load (notes/82)
#   3. the vehicle table: the gunner sight cell renamed to the new row. The table does
#      not survive the text route (cfgfix: pairing unsafe at block 102), so this is a
#      32-byte patch. A string cell is a length and a pointer into the table's own
#      string pool; the new name is the TAIL of a string already in that pool, so
#      its terminating NUL is already there and nothing moves.
#
# Everything except the mesh is a copy of stock the M105D row's values - the view,
# magnification and field 15 scale the Chieftain has today - so the only thing that
# changes in game is the drawing.

import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402

# sights row, flat value positions (azcf.flat - the text row spreads vectors the same
# way, so these are also its token positions): 0 name, 24 reticle mesh, 41 second
# reticle (the [G] key's), 55 zoom reticle (the higher magnification's).
FLAT_NAME, FLAT_MESH, FLAT_MESH2, FLAT_ZOOM = 0, 24, 41, 55
SIGHTS_FIELDS = 56

# vehicle unit -> its own sight
#   meshes   [(mesh name, generator module)]; the module's build_mesh(name) returns
#            (bytes, check report) - the first mesh is the sight's main reticle
#   fields   {sights-row position: new value}, every other value copied from donor_row
OWN_SIGHTS = {
    "iru_chief_mk5": dict(
        label="TLS No. 1 Mk 1 (Fig 35), marks from SABoW's L31 / L15A4 / 7.62 rows",
        donor_row="m105d",            # the sight row the vehicle's gunner uses now
        row="tn_chief_mk5",           # the new sights row: tail of txt_tn_chief_mk5
        pool_string="txt_tn_chief_mk5",
        meshes=[("tls1_chief", "chieftain_sight")],
        fields={FLAT_MESH: "tls1_chief", FLAT_MESH2: "tls1_chief"},
    ),
    # TSh-2B-32P in the stock TSh-2B-41 frame (docs/t55-sight-source.md): the scales
    # move with the range key like the T-62's.
    # The 7x view ([Tab], tank manual p.69-70) draws field 55's reticle: v21 without a
    # zoom record showed the T-62's scales at 7x (murkz's screenshot). So the zoom record
    # is added by recipe unless choices["own_sight_zoom"] is False - v21 was proven
    # without it. (v16-v17 shipped it on a battle proven v9 also fails: no evidence.)
    "sau_t55": dict(
        label="TSh-2B-32P, scales from SABoW's 3OF32 / BR-412D / 3BK17 / 7.62 / 3BM25 rows",
        donor_row="tsh2b",
        row="tn_t55",                 # tail of txt_tn_t55
        pool_string="txt_tn_t55",
        meshes=[("tsh2b32p_t55", "t55_sight")],
        fields={FLAT_MESH: "tsh2b32p_t55"},
        zoom=("tsh2b32p_t55_zoom", "t55_sight"),
        # the ammunition names the gunner picks from, renamed to their sight scales
        # (ammotext.py). choices["ammo_text"] = False builds without it.
        ammo_text=True,
    ),
}
for _s in OWN_SIGHTS.values():
    _s["mesh"] = _s["meshes"][0][0]   # the main reticle, for labels


def spec_for(unit):
    return OWN_SIGHTS.get(unit)


# ---------------------------------------------------------------- 1. the mesh

def make_meshes(spec, log=print):
    """[(mesh name, bytes)] for every reticle the sight ships, each checked."""
    out = []
    for name, generator in spec["meshes"]:
        blob, rep = __import__(generator).build_mesh(name)
        for line in rep:
            log("OK  " + line)
        out.append((name, blob))
    return out


# ---------------------------------------------------------------- 2. the sights row

SIGHTS_HEAD = r"(?m)^[ \t]*(sights\[[^\]\r\n]*\]\(\))[ \t]*\r?$"


def row_pattern(name):
    return r"(?m)^[ \t]*(" + re.escape(name) + r",[^\r\n]*;)[ \t]*\r?$"


def as_specs(spec):
    """One spec or several. A bare dict is still accepted, so build.py's own
    single-sight callers are untouched."""
    return [spec] if isinstance(spec, dict) else list(spec)


def common_res_mod_text(fixed_text, spec):
    """common_res_mod carrying OUR sight rows, from the round-trip-proven stock text.

    Grown from one row to N on 2026-09-22, because two crewable vehicles can each
    want their own reticle - the Panzer IV's TZF 5f and the T-34's TMFD-7 - and
    the build refused rather than silently shipping one of them. notes/82 settled
    that this is safe: ship only your own rows, and a sights row costs nothing.
    """
    specs = as_specs(spec)
    if not specs:
        raise SystemExit("common_res_mod_text called with no sights")
    raw = fixed_text.decode("cp1251")
    head = re.search(SIGHTS_HEAD, raw)
    if not head:
        raise SystemExit("common_res_mod text has no sights header")

    seen, out_rows = {}, []
    for sp in specs:
        # Two vehicles may legitimately share one sight. That is one row, not two -
        # but only if they really are the same row, so a name reused with different
        # fields is an error rather than a silent last-one-wins.
        key = (sp["donor_row"], tuple(sorted(sp["fields"].items())))
        if sp["row"] in seen:
            if seen[sp["row"]] != key:
                raise SystemExit("two different sights are both called %s" % sp["row"])
            continue
        seen[sp["row"]] = key
        rows = re.findall(row_pattern(sp["donor_row"]), raw)
        if len(rows) != 1:
            raise SystemExit("common_res_mod text has %d %s rows, expected 1" % (len(rows), sp["donor_row"]))
        tokens = [t.strip() for t in rows[0].rstrip(";").split(",")]
        if len(tokens) != SIGHTS_FIELDS:
            raise SystemExit("%s row has %d fields, expected %d" % (sp["donor_row"], len(tokens), SIGHTS_FIELDS))
        tokens[FLAT_NAME] = sp["row"]
        for pos, value in sorted(sp["fields"].items()):
            tokens[pos] = value
        out_rows.append(", ".join(tokens) + ";")
    nl = "\r\n"
    out = ("//Cfgp2Pd auto converter" + nl + nl + head.group(1) + nl + "{" + nl
           + "".join("\t" + r + nl for r in out_rows) + nl + "} //endof sights" + nl)
    return out.encode("cp1251")

def check_common_res_mod(stock, built, spec):
    """One sights block; our rows and nothing else, each the donor row's values
    except its name and the fields the recipe names.

    Grown with common_res_mod_text: the row count is now whatever the build asked
    for, and each row is matched BY NAME rather than by position, so the order the
    rows happen to be written in cannot make a wrong row pass.
    """
    specs = as_specs(spec)
    t = azcf.Table(built)
    if [b.name for b in t.blocks] != ["sights"]:
        raise SystemExit("common_res_mod holds %s, expected only sights" % [b.name for b in t.blocks])
    rows = t.rows(t.blocks[0])
    wanted = []
    for sp in specs:
        if sp["row"] not in [w["row"] for w in wanted]:
            wanted.append(sp)
    if len(rows) != len(wanted):
        raise SystemExit("common_res_mod sights has %d rows, expected %d" % (len(rows), len(wanted)))

    s = azcf.Table(stock)
    stock_rows = s.rows(s.find("sights")[0])
    names = {r[0] for r in stock_rows}
    by_name = {r[0]: r for r in rows}
    out = []
    for sp in wanted:
        if sp["row"] in names:
            raise SystemExit("stock already has a sights row called %s" % sp["row"])
        if sp["row"] not in by_name:
            raise SystemExit("common_res_mod has no %s row - built %s" % (sp["row"], sorted(by_name)))
        donor = next((r for r in stock_rows if r[0] == sp["donor_row"]), None)
        if donor is None:
            raise SystemExit("stock common_res_mod has no %s row" % sp["donor_row"])
        got, want = azcf.flat(by_name[sp["row"]]), azcf.flat(donor)
        want[FLAT_NAME] = sp["row"]
        for pos, value in sp["fields"].items():
            want[pos] = value
        if len(got) != len(want):
            raise SystemExit("%s decodes to %d values, expected %d" % (sp["row"], len(got), len(want)))
        for i, (g, w) in enumerate(zip(got, want)):
            same = abs(g - w) < 1e-5 if isinstance(w, float) and not isinstance(w, bool) else g == w
            if not same:
                raise SystemExit("%s value %d is %r, expected %r" % (sp["row"], i, g, w))
        out.append("common_res_mod: sights row %s = stock %s with %s, all %d other values identical"
                   % (sp["row"], sp["donor_row"],
                      ", ".join("[%d] %s" % kv for kv in sorted(sp["fields"].items())),
                      len(want) - 1 - len(sp["fields"])))
    out.append("common_res_mod: %d row(s), and nothing else in the table" % len(wanted))
    return out


# ---------------------------------------------------------------- 3. the vehicle table

def gunner_row(t, blocks, spec):
    rows = t.rows(blocks["sights"])
    hits = [i for i, r in enumerate(rows) if r[2] == spec["donor_row"] and r[4] == "sig_gunner"]
    if len(hits) != 1:
        raise SystemExit("%d gunner sight rows use %s, expected 1" % (len(hits), spec["donor_row"]))
    return hits[0]


def name_cell(stock, t, blocks, spec, row_index):
    """(offset of the row's sight-name cell, the new 32-byte cell)."""
    blk = blocks["sights"]
    dst = blk.data_ptr + row_index * len(blk.spec) * 32 + 2 * 32
    whole = spec["pool_string"].encode("latin1") + b"\0"
    at = stock.find(whole)
    if at < 0 or stock.find(whole, at + 1) >= 0:
        raise SystemExit("%s must appear exactly once in the vehicle table" % spec["pool_string"])
    tail = spec["row"].encode("latin1")
    if not spec["pool_string"].endswith(spec["row"]):
        raise SystemExit("%s is not the tail of %s" % (spec["row"], spec["pool_string"]))
    # prove it is the pool string a real cell points at, not a coincidence of bytes
    referenced = any(struct.unpack_from("<II", stock, o)[:2] == (len(whole) - 1, at)
                     for o in range(0, len(stock) - 8, 4))
    if not referenced:
        raise SystemExit("no string cell points at %s - not a pool string" % spec["pool_string"])
    cell = bytearray(stock[dst:dst + 32])
    struct.pack_into("<II", cell, 0, len(tail), at + len(whole) - 1 - len(tail))
    return dst, bytes(cell)
