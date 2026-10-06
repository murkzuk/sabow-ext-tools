# build - make the SABoW Ext addon from a recipe. Part of the tool; it becomes a
# button in Phase 3.
#
# WHAT to change comes from recipe.derive() - read from the game for the vehicle
# picked, never typed in. This file only knows HOW: edit the tables, check every
# change, pack, and read the result back out of the zip. The golden test
# (golden.py) proves the recipe for the T-55 rebuilds proven v9 exactly.
#
# WHAT IT CHANGES
#   1. Per vehicle, its row in div_units_misc/units gets the three values that
#      make a unit playable:
#          field 11  crewable     true
#          field 12  cockpit      its OWN cockpit (see 2)
#          field 13  crew anims   the donor's
#      (Text columns 14-16: the spec's one vector spreads over 4 columns.)
#
#   2. Per vehicle, its own cockpit in `cocpits`: a copy of the donor's with the
#      gunner station's gun and shells changed to the vehicle's own. A cockpit's
#      gunner block NAMES the gun and shells (BoW43 notes/26), so a borrowed
#      cockpit borrows its armament: v2's T-55 in coc_t62 asked for the T-62's
#      115 mm U5TS and had no main-gun ammunition.
#
#   3. Per quick-battle platoon: `user_in` in qbattle set to true. That flag
#      draws the crew icon and lets the player take the platoon (BoW43
#      notes/25). Graviteam ship the Iraqi T-55 platoons with it FALSE. One
#      byte per platoon, patched in the compiled table.
#
# HOW
#   qbattle is patched as compiled bytes - the flag already exists.
#   cocpits and div_units_misc need things that do not exist yet (a new block,
#   a new string), so they go through text with the game's own tools
#   (textable.py). That route is only used after a ROUND TRIP of the stock
#   table - stock -> text -> compiled - comes back md5-identical to stock
#   (both do, measured 2026-09-15). The old worry about commas in strings
#   (notes/15) is exactly what that check catches.
#
#   The addon ships WHOLE tables. An addon table replaces the base table of the
#   same name, so a partial table would delete everything else in it.
#
#   starter.exe is called one program at a time, each output checked before the
#   next step. Never chained (BoW43 notes/01), never through PowerShell, which
#   eats the commas.
#
# CHECKS
#   Every changed table is decoded and compared with stock block by block:
#   everything the build did not mean to change must read the same, and every
#   intended change must be there. Then all three tables are read back OUT OF
#   THE FINISHED ZIP.

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402
import crewpoints  # noqa: E402
import recipe  # noqa: E402
import settings  # noqa: E402
import textable  # noqa: E402

INSTALL = settings.get("live")        # SABoW Ext Control resets this when murkz picks another game
ADDON = "sabow_ext"
AUTHOR = "murkz"
DESCRIPTION = "SABoW Ext - stock vehicles made playable"

def drawable_chunks(model):
    """Names of the chunks in a cockpit model that carry geometry (node field[1])."""
    b = crewpoints.find(model)
    if b is None:
        raise SystemExit("mesh %s not found in the install" % model)
    tbl = struct.unpack_from("<I", b, 8)[0]
    nodes = crewpoints.read_mesh(b)
    return [x["name"] for i, x in enumerate(nodes)
            if struct.unpack_from("<8i", b, tbl + i * 0x140 + 0x20)[1] > 0]


def hide_rows_to_add(plan, existing):
    """[(chunk, mesh index)] for every drawable donor chunk not already hidden."""
    have = {(r[0], r[1]) for r in existing}
    out = []
    for idx, model in enumerate(plan.hide_models):
        for chunk in drawable_chunks(model):
            if (chunk, idx) not in have:
                out.append((chunk, idx))
    return out


CREWABLE, COCKPIT, ANIMS = 11, 12, 13

DESC_TEMPLATE = """i_updater:updater=()
{{
    path[s] = {path};
    desc[s] = {desc};
    authors[s] = {author};
    version[u] = {version};
    type[*] = RES;
    clear_prev[b] = true;
    eng_ver[u] = 1360;
    sys_path[s] = ;
    recover[s] = ;
}}
"""

CRLF = b"\r\n"


def tabs_path(install):
    return os.path.join(install, "data", "mtc80", "shared", "packed_data", "tabs.flatdata")


def work_dir(install):
    # starter.exe takes paths relative to the game root, so work inside it -
    # users\modwork is the game's own modding workspace.
    return os.path.join(install, "users", "modwork", ADDON)


# ---------------------------------------------------------------- decoding for checks

def _is_props(t, b):
    """A props block's second cell holds a key name inline (see azcf.props)."""
    if not b.rows or len(b.spec) != 1:
        return False
    c = t.data[b.data_ptr + 32:b.data_ptr + 64]
    return c[:1].isalpha() and c[16:20] == b"\0\0\0\0"


def block_values(t, b):
    return t.props(b) if _is_props(t, b) else t.rows(b)


def decoded(t):
    """Every block as (name, spec, rows, values) - strings resolved, so two
    tables compare by meaning, not by where their string pools put things."""
    return [(b.name, b.spec, b.rows, block_values(t, b)) for b in t.blocks]


# ---------------------------------------------------------------- qbattle (compiled patch)

def user_in_cell(table, block):
    """Offset of the value cell of a props block's `user_in`, or None."""
    for r in range(block.rows):
        base = block.data_ptr + r * 64
        key = table.data[base + 32:base + 64].split(b"\0")[0]
        if key == b"user_in":
            return base
    return None


def qbattle_renames_only(stock, back):
    """Round-trip gate for qbattle: every block reads the same as stock, except the
    SECOND copy of a duplicated block name, renamed <name>_2 by cfgfix and
    otherwise identical (BoW43 notes/43 - pd2cfgp would overwrite the first copy
    otherwise). Anything else fails."""
    a, b = decoded(azcf.Table(stock)), decoded(azcf.Table(back))
    if len(a) != len(b):
        raise SystemExit("qbattle round trip: %d blocks came back as %d" % (len(a), len(b)))
    counts = {}
    for x in a:
        counts[x[0]] = counts.get(x[0], 0) + 1
    renamed = []
    for x, y in zip(a, b):
        if x == y:
            continue
        if y[0] == x[0] + "_2" and counts[x[0]] > 1 and x[1:] == y[1:]:
            renamed.append(x[0])
            continue
        raise SystemExit("qbattle round trip changed block %s beyond a duplicate rename - do not build" % x[0])
    return "every block reads the same as stock except duplicate copies renamed: %s" % ", ".join(renamed)


def edit_qbattle_text(src, plan):
    """Switch on, or add, user_in = true in each ticked platoon block."""
    lines = src.split(CRLF)
    for name in plan.platoons:
        st = [i for i, l in enumerate(lines) if l == b"\t" + name.encode() + b"=()"]
        en = [i for i, l in enumerate(lines) if l == b"\t} //endof " + name.encode()]
        if len(st) != 1 or len(en) != 1:
            raise SystemExit("qbattle: platoon %s not found exactly once in the text" % name)
        flag = [i for i in range(st[0], en[0]) if lines[i].startswith(b"\t\tuser_in[b]\t= ")]
        if len(flag) > 1:
            raise SystemExit("qbattle: platoon %s has %d crew flags" % (name, len(flag)))
        if flag:
            lines[flag[0]] = b"\t\tuser_in[b]\t= true;"
            continue
        props = [i for i in range(st[0] + 2, en[0])
                 if lines[i].startswith(b"\t\t") and not lines[i].startswith(b"\t\t\t")
                 and b"]\t= " in lines[i]]
        if not props:
            raise SystemExit("qbattle: platoon %s has no properties to add the flag after" % name)
        # stock writes the flag straight after the last property (sa_tank_plat_01: camo, then user_in)
        lines.insert(props[-1] + 1, b"\t\tuser_in[b]\t= true;")
    return CRLF.join(lines)


def check_qbattle(stock, built, plan):
    """Every block as stock, except duplicate renames and the ticked platoons,
    whose properties must equal stock's plus user_in = true."""
    a, b = decoded(azcf.Table(stock)), decoded(azcf.Table(built))
    if len(a) != len(b):
        raise SystemExit("qbattle: %d blocks became %d" % (len(a), len(b)))
    counts = {}
    for x in a:
        counts[x[0]] = counts.get(x[0], 0) + 1
    seen, renamed, report = set(), [], []
    for x, y in zip(a, b):
        if x[0] in plan.platoons and y[0] == x[0]:
            want = dict(x[3], user_in=True)
            if y[3] != want:
                raise SystemExit("qbattle: platoon %s reads %r, expected %r" % (x[0], y[3], want))
            seen.add(x[0])
            report.append("  %s: user_in %s -> true" % (x[0], x[3].get("user_in", "(none, added)")))
            continue
        if x == y:
            continue
        if y[0] == x[0] + "_2" and counts[x[0]] > 1 and x[1:] == y[1:]:
            renamed.append(x[0])
            continue
        raise SystemExit("qbattle: block %s changed and should not have" % x[0])
    missing = set(plan.platoons) - seen
    if missing:
        raise SystemExit("qbattle: platoons not found: %s" % ", ".join(sorted(missing)))
    report.append("  every other block reads the same as stock; duplicate copies renamed: %s" % ", ".join(renamed))
    return report


def string_cell(t, blocks, text, prefer):
    """Offset of a string cell holding `text` in one of this vehicle's blocks.
    A string cell is a length and a pointer into the table's own string pool, so
    a cell from any block of the same table names the same string. The Olifant's
    sights block had a head1 cell of its own; the Chieftain's has none, but its
    weapons and heads blocks do (v13)."""
    order = [n for n in prefer if n in blocks] + [n for n in blocks if n not in prefer]
    for name in order:
        blk = blocks[name]
        if not blk.spec or not blk.rows:
            continue
        stride = len(blk.spec) * 32
        for r in range(blk.rows):
            for f, letter in enumerate(blk.spec):
                if letter != "s":
                    continue
                off = blk.data_ptr + r * stride + f * 32
                if t.string(t.data[off:off + 32]) == text:
                    return off
    return None


def patch_techn(stock, plan):
    """Return (patched bytes, report). Sets the head of the gunner sight rows in
    plan.sight_heads by copying a cell that already holds that head's name from
    the same sights block - a string cell is a length and a pointer into the same
    table's string pool, so nothing else has to move (like the v1 unit patch)."""
    t = azcf.Table(stock)
    blocks = dict(azcf.vehicles(t)).get(plan.vehicle, {})
    if "sights" not in blocks:
        raise SystemExit("%s: no sights block for %s" % (plan.techn_record, plan.vehicle))
    blk = blocks["sights"]
    rows = t.rows(blk)
    stride = len(blk.spec) * 32
    data = bytearray(stock)
    report = []
    renamed = {}
    own = getattr(plan, "own_sight", None)
    if own:
        # the gunner's sight renamed to the vehicle's own row (ownsight.py)
        import ownsight
        i = ownsight.gunner_row(t, blocks, own)
        dst, cell = ownsight.name_cell(stock, t, blocks, own, i)
        data[dst:dst + 32] = cell
        renamed[i] = own["row"]
        report.append("%s sight %s: %r -> %r (tail of the pool string %s)"
                      % (plan.vehicle, rows[i][0], rows[i][2], own["row"], own["pool_string"]))
    for i, head in plan.sight_heads:
        dst = blk.data_ptr + i * stride + 8 * 32
        src = string_cell(t, blocks, head, prefer=("sights", "weapons", "heads"))
        if src is None:
            raise SystemExit("%s's table has no cell naming %s to copy from" % (plan.vehicle, head))
        if stock[src + 8:src + 32] != stock[dst + 8:dst + 32]:
            raise SystemExit("the %s cell found is not the same kind of cell as the sight's head" % head)
        data[dst:dst + 32] = stock[src:src + 32]
        report.append("%s sight %s (%s): head %r -> %r" % (plan.vehicle, rows[i][0], rows[i][2], rows[i][8], head))
    # check: only those cells changed, and they now read the head
    after = azcf.Table(bytes(data))
    arows = after.rows(dict(azcf.vehicles(after))[plan.vehicle]["sights"])
    heads = dict(plan.sight_heads)
    for i in set(heads) | set(renamed):
        want = list(rows[i])
        if i in heads:
            want[8] = heads[i]
        if i in renamed:
            want[2] = renamed[i]
        if list(arows[i]) != want:
            raise SystemExit("sight patch failed: row %d reads %r" % (i, arows[i]))
    for j, (x, y) in enumerate(zip(rows, arows)):
        if j not in heads and j not in renamed and list(x) != list(y):
            raise SystemExit("sight patch changed row %d as well" % j)
    changed = sum(1 for x, y in zip(stock, data) if x != y)
    if len(data) != len(stock) or changed > 32 * (len(plan.sight_heads) + len(renamed)):
        raise SystemExit("sight patch touched too much: %d bytes" % changed)
    report.append("  %d bytes differ from stock %s - only the sight cells" % (changed, plan.techn_record))
    return bytes(data), report


def patch_qbattle(stock, plan):
    """Return (patched bytes, report lines). Sets user_in = true on each platoon
    in plan.platoons by writing 1 into its existing bool cell."""
    t = azcf.Table(stock)
    data = bytearray(stock)
    report = []
    for name in plan.platoons:
        blk = t.find(name)
        if len(blk) != 1:
            raise SystemExit("qbattle has %d blocks named %s, expected 1" % (len(blk), name))
        off = user_in_cell(t, blk[0])
        if off is None:
            raise SystemExit("%s has no user_in to change" % name)
        if struct.unpack_from("<I", stock, off + 16)[0] != 5:
            raise SystemExit("%s user_in is not a bool cell" % name)
        struct.pack_into("<I", data, off, 1)
        report.append("%s: user_in %s -> true" % (name, t.props(blk[0])["user_in"]))

    # check: each platoon now reads the same as stock except user_in = true
    pt = azcf.Table(bytes(data))
    for name in plan.platoons:
        before, after = t.props(t.find(name)[0]), pt.props(pt.find(name)[0])
        if after != dict(before, user_in=True):
            raise SystemExit("qbattle patch failed: %s reads %r" % (name, after))
        report.append("  %s now reads user_in=%s, every other property unchanged" % (name, after["user_in"]))

    changed = sum(1 for a, b in zip(stock, data) if a != b)
    limit = len(plan.platoons)
    if len(data) != len(stock) or changed > limit:
        raise SystemExit("qbattle patch touched too much: %d bytes changed, limit %d" % (changed, limit))
    report.append("  %d bytes differ from stock qbattle (limit %d) - nothing else touched" % (changed, limit))
    return bytes(data), report


# ---------------------------------------------------------------- div_units_misc (text)

def edit_units_text(src, plan):
    """The unit's row: crewable, own cockpit, the recipe's anims. Returns new text."""
    lines = src.split(CRLF)
    for target, donor, cockpit in [(plan.unit, plan.donor_unit, plan.cockpit)]:
        idx = [i for i, l in enumerate(lines) if l.startswith(b"\t" + target.encode() + b",")]
        didx = [i for i, l in enumerate(lines) if l.startswith(b"\t" + donor.encode() + b",")]
        if len(idx) != 1 or len(didx) != 1:
            raise SystemExit("expected one units row each for %s and %s, found %d and %d"
                             % (target, donor, len(idx), len(didx)))
        row = lines[idx[0]].rstrip(b";").split(b", ")
        drow = lines[didx[0]].rstrip(b";").split(b", ")
        if len(row) != 17 or len(drow) != 17:
            raise SystemExit("units row for %s is not the 17-column shape this build knows" % target)
        row[14], row[15], row[16] = b"true", cockpit.encode(), plan.anims.encode()
        lines[idx[0]] = b", ".join(row) + b";"
    return CRLF.join(lines)


def check_units(stock, built, plan):
    t, n = azcf.Table(stock), azcf.Table(built)
    a, b = decoded(t), decoded(n)
    if [x[:3] for x in a] != [x[:3] for x in b]:
        raise SystemExit("div_units_misc: block layout changed")
    report = []
    for (name, spec, rows, va), (_, _, _, vb) in zip(a, b):
        if name != "units":
            if va != vb:
                raise SystemExit("div_units_misc: block %s changed and should not have" % name)
            continue
        want = [list(r) for r in va]
        names = [r[0] for r in want]
        for target, cockpit in [(plan.unit, plan.cockpit)]:
            r = want[names.index(target)]
            r[CREWABLE], r[COCKPIT], r[ANIMS] = True, cockpit, plan.anims
        if [list(r) for r in vb] != want:
            bad = [x[0] for x, y in zip(vb, want) if list(x) != y]
            raise SystemExit("div_units_misc: units differ from what was intended: %s" % bad)
        for target in [plan.unit]:
            r = vb[names.index(target)]
            report.append("  %s: crewable=%s cockpit=%s anims=%s"
                          % (target, r[CREWABLE], r[COCKPIT], r[ANIMS]))
    report.append("  every other unit, squad and block reads the same as stock")
    return report


# ---------------------------------------------------------------- cocpits (text)

def edit_cocpits_text(src, plan):
    """Append the new cockpit: a copy of the donor with the recipe's station edits,
    crew sync modes and hide rows."""
    lines = src.split(CRLF)
    end = [i for i, l in enumerate(lines) if l.startswith(b"} //endof i_cocpits:cocpits")]
    if len(end) != 1:
        raise SystemExit("cocpits text has no single closing line")
    added = []
    for new, donor in [(plan.cockpit, plan.donor_cockpit)]:
        if any(l == b"\t" + new.encode() + b"=()" for l in lines):
            raise SystemExit("cocpits already has a %s" % new)
        st = [i for i, l in enumerate(lines) if l == b"\t" + donor.encode() + b"=()"]
        en = [i for i, l in enumerate(lines) if l == b"\t} //endof " + donor.encode()]
        if len(st) != 1 or len(en) != 1:
            raise SystemExit("cocpits: donor %s not found exactly once" % donor)
        copy = lines[st[0]:en[0] + 1]
        copy[0] = b"\t" + new.encode() + b"=()"
        copy[-1] = b"\t} //endof " + new.encode()
        for station, fields in plan.station_edits.items():
            gs = [i for i, l in enumerate(copy) if l == b"\t\t" + station.encode() + b"=()"]
            ge = [i for i, l in enumerate(copy) if l == b"\t\t} //endof " + station.encode()]
            if len(gs) != 1 or len(ge) != 1:
                raise SystemExit("cocpits: %s has no single %s block" % (donor, station))
            for key, value in fields.items():
                hits = [i for i in range(gs[0], ge[0]) if copy[i].startswith(b"\t\t\t" + key.encode() + b"[s]\t= ")]
                if len(hits) != 1:
                    raise SystemExit("cocpits: %s %s has %d %s lines, expected 1" % (donor, station, len(hits), key))
                copy[hits[0]] = b"\t\t\t" + key.encode() + b"[s]\t= " + value.encode() + b";"
        modes = plan.sync_modes
        if modes:
            ss = [i for i, l in enumerate(copy) if l == b"\t\tsync[ssa]()"]
            se = [i for i, l in enumerate(copy) if l == b"\t\t} //endof sync"]
            if len(ss) != 1 or len(se) != 1:
                raise SystemExit("cocpits: %s has no single sync block" % donor)
            for chunk, mode in modes.items():
                hits = [i for i in range(ss[0], se[0]) if copy[i].startswith(b"\t\t\t" + chunk.encode() + b",")]
                if len(hits) != 1:
                    raise SystemExit("cocpits: %s sync has %d %s rows, expected 1" % (donor, len(hits), chunk))
                f = copy[hits[0]].strip().rstrip(b";").split(b", ")
                if len(f) != 6 or f[3] != b"1":
                    raise SystemExit("cocpits: %s sync row %s is not a mode-1 crew row: %r" % (donor, chunk, copy[hits[0]]))
                f[3] = str(mode).encode()
                if chunk in plan.sync_retarget:
                    # follow a DIFFERENT chunk of the vehicle's: mode 0 alone follows the one with the
                    # same name, and some vehicles have no such chunk at all
                    f[1] = plan.sync_retarget[chunk].encode()
                copy[hits[0]] = b"\t\t\t" + b", ".join(f) + b";"
        if plan.plc_add:
            # whole states rows the donor cockpit has not got. A crewman can only turn out when his
            # PLACE has a state to enter - flag 0x1000, a view with no sight and wide angles. Places
            # 0, 2 and 3 have one in both stock cockpits; place 1, the gunner, has none in either.
            pe = [i for i, l in enumerate(copy) if l == b"\t\t} //endof plc_states"]
            if len(pe) != 1:
                raise SystemExit("cocpits: %s has no single plc_states block" % donor)
            for row in plan.plc_add:
                copy.insert(pe[0], b"\t\t\t" + row.encode() + b";")
                pe = [i for i, l in enumerate(copy) if l == b"\t\t} //endof plc_states"]
        if plan.sync_add:
            # rows the donor has not got at all. A crewman can only turn out when the cockpit HAS an
            # s_<place>_out row to bind, and coc_t62 has none for the gunner - so an imported vehicle
            # whose gunner does have a hatch can never use it, and asking for the view 001s.
            se = [i for i, l in enumerate(copy) if l == b"\t\t} //endof sync"]
            if len(se) != 1:
                raise SystemExit("cocpits: %s has no single sync block to add to" % donor)
            ss = [i for i, l in enumerate(copy) if l == b"\t\tsync[ssa]()"]
            for chunk, target in sorted(plan.sync_add.items()):
                if any(copy[i].startswith(b"\t\t\t" + chunk.encode() + b",") for i in range(ss[0], se[0])):
                    raise SystemExit("cocpits: %s sync already has a %s row" % (donor, chunk))
                copy.insert(se[0], b"\t\t\t" + chunk.encode() + b", " + target.encode() + b", 0, 0, 0, 0;")
                se = [i for i, l in enumerate(copy) if l == b"\t\t} //endof sync"]
        if plan.hide_models:
            hs = [i for i, l in enumerate(copy) if l == b"\t\thide[suu]()"]
            he = [i for i, l in enumerate(copy) if l == b"\t\t} //endof hide"]
            if len(hs) != 1 or len(he) != 1:
                raise SystemExit("cocpits: %s has no single hide block" % donor)
            drop = set(plan.hide_drop)
            if drop:
                keep, gone = [], []
                for l in copy[hs[0] + 2:he[0]]:
                    t = l.strip().rstrip(b";")
                    if t:
                        name, idx, flag = [x.strip() for x in t.split(b",")]
                        if idx == b"0xffffffff" and name.decode() in drop:
                            gone.append(name.decode())
                            continue
                    keep.append(l)
                if sorted(gone) != sorted(drop):
                    raise SystemExit("cocpits: %s hide should lose %s but lost %s" % (donor, sorted(drop), gone))
                copy[hs[0] + 2:he[0]] = keep
                he = [i for i, l in enumerate(copy) if l == b"\t\t} //endof hide"]
            existing = []
            for l in copy[hs[0] + 2:he[0]]:
                t = l.strip().rstrip(b";")
                if t:
                    name, idx, flag = [x.strip() for x in t.split(b",")]
                    existing.append((name.decode(), -1 if idx == b"0xffffffff" else int(idx)))
            rows = [b"\t\t\t%s, %d, 0;" % (c.encode(), i) for c, i in hide_rows_to_add(plan, existing)]
            last = he[0] - 1 if copy[he[0] - 1] == b"" else he[0]
            copy[last:last] = rows
        added += copy + [b""]
    lines[end[0]:end[0]] = added
    return CRLF.join(lines)


def check_cocpits(stock, built, plans):
    """Verify every cockpit appended past stock. `plans` is a list, in the order they were appended;
    a single plan is still accepted. Each is checked against its own donor, and the tail must be
    exactly accounted for - nothing may be appended that no plan asked for."""
    if not isinstance(plans, (list, tuple)):
        plans = [plans]
    t, n = azcf.Table(stock), azcf.Table(built)
    a, b = decoded(t), decoded(n)
    if b[:len(a)] != a:
        raise SystemExit("cocpits: a stock cockpit changed and should not have")
    report = ["  all %d stock blocks read the same as stock" % len(a)]
    names = [x[0] for x in a]
    tops = [i for i, x in enumerate(a) if x[0].startswith("coc_")] + [len(a)]
    extra = b[len(a):]
    pos = 0
    for plan in plans:
        new, donor = plan.cockpit, plan.donor_cockpit
        di = names.index(donor)
        dend = next(x for x in tops if x > di)
        want = [list(x) for x in deepcopy(a[di:dend])]
        got = extra[pos:pos + len(want)]
        pos += len(want)
        want[0][0] = new
        befores = {}
        for station, fields in plan.station_edits.items():
            gi = [i for i, x in enumerate(want) if x[0] == station]
            if len(gi) != 1:
                raise SystemExit("cocpits: %s has no single %s block" % (donor, station))
            befores[station] = (gi[0], dict(want[gi[0]][3]))
            want[gi[0]][3] = dict(befores[station][1], **fields)
        modes = plan.sync_modes
        si = [i for i, x in enumerate(want) if x[0] == "sync"]
        if modes and len(si) != 1:
            raise SystemExit("cocpits: %s has no single sync block" % donor)
        hidden_added = []
        if plan.hide_models:
            hi = [i for i, x in enumerate(want) if x[0] == "hide"]
            if len(hi) != 1:
                raise SystemExit("cocpits: %s has no single hide block" % donor)
            if plan.hide_drop:
                before = len(want[hi[0]][3])
                want[hi[0]][3] = [r for r in want[hi[0]][3]
                                  if not (r[1] == 0xffffffff and r[0] in plan.hide_drop)]
                if before - len(want[hi[0]][3]) != len(plan.hide_drop):
                    raise SystemExit("cocpits: %s hide rows to drop not all found" % donor)
                want[hi[0]][2] = len(want[hi[0]][3])
            existing = [(r[0], -1 if r[1] == 0xffffffff else r[1]) for r in want[hi[0]][3]]
            hidden_added = hide_rows_to_add(plan, existing)
            want[hi[0]][3] = want[hi[0]][3] + [[c, i, 0] for c, i in hidden_added]
            want[hi[0]][2] = len(want[hi[0]][3])
        for chunk, mode in modes.items():
            rows = [r for r in want[si[0]][3] if r[0] == chunk]
            if len(rows) != 1:
                raise SystemExit("cocpits: %s sync has %d %s rows" % (donor, len(rows), chunk))
            r = rows[0]
            r[2] = (r[2][0], mode, r[2][2], r[2][3])
            if chunk in plan.sync_retarget:
                r[1] = plan.sync_retarget[chunk]
        if plan.sync_add:
            for chunk, target in sorted(plan.sync_add.items()):
                want[si[0]][3] = want[si[0]][3] + [[chunk, target, (0, 0, 0, 0)]]
            want[si[0]][2] = len(want[si[0]][3])
        if plan.plc_add:
            # The added states rows are authored as TEXT, so they cannot be predicted field by field
            # here. Check what matters instead: the donor's own rows are untouched and come first, the
            # count grew by exactly what was added, and every added row is a turned-out state for the
            # place it claims - flag 0x1000 and no sight. Anything else is a real difference.
            pi = [i for i, x in enumerate(want) if x[0] == "plc_states"]
            if len(pi) != 1:
                raise SystemExit("cocpits: %s has no single plc_states block" % donor)
            base = want[pi[0]][3]
            gotp = got[pi[0]][3]
            if len(gotp) != len(base) + len(plan.plc_add):
                raise SystemExit("cocpits: %s plc_states has %d rows, expected %d + %d added"
                                 % (new, len(gotp), len(base), len(plan.plc_add)))
            if [list(r) for r in gotp[:len(base)]] != [list(r) for r in base]:
                raise SystemExit("cocpits: %s changed a plc_states row the donor already had" % new)
            for r in gotp[len(base):]:
                turnout = (r[0][2] & 0x1000) and r[2] == 0xffffffff
                # v42: a sight view that is deliberately NOT a device - slot -1, no flags, a real
                # sight index, and crucially NO button and NO device. Kept as strict as the turn-out
                # check it sits beside: anything carrying a device is still refused, so the guard
                # cannot rubber-stamp a row that merely claims to be a view.
                freelook = (r[0][1] == 0xffffffff and r[0][2] == 0
                            and r[2] != 0xffffffff and not r[3] and not r[6])
                if not turnout and not freelook:
                    raise SystemExit("cocpits: %s added a plc_states row that is neither a turned-out "
                                     "state nor a device-free sight view: %r" % (new, list(r)))
            want[pi[0]][3] = [list(r) for r in gotp]
            want[pi[0]][2] = len(gotp)
        if [list(x) for x in got] != want:
            bad = [w[0] for w, g in zip(want, got) if list(g) != w]
            raise SystemExit("cocpits: %s differs from %s in more than the recipe: %s" % (new, donor, bad))
        for station, fields in plan.station_edits.items():
            gi, before = befores[station]
            g = got[gi][3]
            report.append("  %s = %s + %s %s" % (new, donor, station, ", ".join(
                "%s %s->%s" % (k, before[k], g[k]) for k in fields)))
        if modes:
            gs = {r[0]: r[2][1] for r in got[si[0]][3] if r[0] in modes}
            report.append("    + sync modes %s" % ", ".join("%s 1->%s" % (c, gs[c]) for c in modes))
        if plan.hide_drop:
            report.append("    - hide rows dropped (chunks %s lacks): %s" % (plan.model, ", ".join(plan.hide_drop)))
        if hidden_added:
            per = {}
            for c, i in hidden_added:
                per[i] = per.get(i, 0) + 1
            report.append("    + hide rows added: %d (%s)" % (len(hidden_added), ", ".join(
                "%d from mesh %d" % (v, k) for k, v in sorted(per.items()))))
    if pos != len(extra):
        raise SystemExit("cocpits: %d unexpected extra blocks" % (len(extra) - pos))
    return report


# ---------------------------------------------------------------- packing

def check_spec_bytes(built, label, log=print, stock=None):
    """Refuse a compiled table that carries a spec which is not a field type.

    MEASURED 2026-09-27, and it is the reason a whole day went on the wrong suspects. cfgp2pd writes
    a spec-less block as "name=()", and that "=" recompiles as a ONE-CHARACTER SPEC. cfgfix repairs
    it against the stock .config - but an ADDED block has no entry there, so it used to be left
    alone. The result is a table that loads perfectly and then dies entering the deploy with the
    generic "001: Program initialization error", which names nothing and points nowhere:

        stock coc_t62       anims   speclen 0   a container
        an added cockpit    anims   speclen 1   spec 0x00

No field type is 0x00 and none is '=', so a spec holding either is always a build defect. This is
    checked on the COMPILED bytes, because that is the only place that cannot be fooled by how the
    text happened to be written.
    """
    bad = textable.spec_defects(stock, built)   # one implementation, in the funnel every compile uses
    if bad:
        for i, name, spec, why in bad[:10]:
            log("    block %d %r has %s" % (i, name, why))
        raise SystemExit(
            "%s: %d block(s) carry a spec that is not a field type - a stray '=' from cfgp2pd "
            "that cfgfix did not repair. MEASURED 2026-09-27: ONE such block in the cockpit table "
            "made every battle die entering the deploy with the generic \"001: Program "
            "initialization error\", with nothing in the log naming cockpits. Do not ship it."
            % (label, len(bad)))
    n = len(azcf.Table(built).blocks)
    log("OK  %s: all %d block specs are field types (no NUL, no '=')" % (label, n))
    return n


def starter(install, *args, expect=None, timeout=180):
    """One starter.exe call, waited for, its output checked. Never chained."""
    exe = os.path.join(install, "starter.exe")
    subprocess.run([exe] + list(args), cwd=install, timeout=timeout, check=False)
    if expect:
        # The programs can return before their file is complete. Wait for the
        # file to exist and stop growing.
        last, stable = -1, 0
        end = time.time() + timeout
        while time.time() < end:
            size = os.path.getsize(expect) if os.path.isfile(expect) else -1
            if size > 0 and size == last:
                stable += 1
                if stable >= 3:
                    return size
            else:
                stable = 0
            last = size
            time.sleep(0.5)
        raise SystemExit("%s produced no complete %s" % (args[0], expect))


def rel(path, install):
    return os.path.relpath(path, install)


def text_table(install, name, edit, check, plan, log, accept=None):
    """Round-trip gate, edit the text, compile, check. Returns compiled bytes."""
    folder = os.path.join(work_dir(install), "text", name)
    fixed = textable.round_trip(install, name, folder, log, accept)
    with open(fixed, "rb") as f:
        src = f.read()
    stock = azcf.read_record(tabs_path(install), name)
    edited = os.path.join(folder, "edited", name + ".loc_def.engcfg2")
    os.makedirs(os.path.dirname(edited), exist_ok=True)
    with open(edited, "wb") as f:
        f.write(edit(src, plan))
    built = textable.compile_text(install, edited, os.path.join(folder, "edited", name + ".config"), log)
    log("OK  %s edited and compiled (%d bytes, stock %d)" % (name, len(built), len(stock)))
    check_spec_bytes(built, name, log, stock)
    for line in check(stock, built, plan):
        log(line)
    return built


def build(plan, version, install=INSTALL, log=print, zip_name=None):
    ok, msg = azcf.self_test(tabs_path(install))
    if not ok:
        raise SystemExit("table reader check failed: " + msg)
    log("OK  " + msg)

    # A MODEL HELD BY MORE THAN ONE ARCHIVE MUST AGREE WITH ITSELF. Measured three times (2026-09-25
    # pz3jlg, 2026-09-27 t34_42_utz): a mesh_points edit applied to one copy and not the other is
    # invisible, because the engine reads whichever archive wins. Refuse to build on a disagreement
    # rather than ship a fix that may never be read.
    import check_mesh_copies
    if check_mesh_copies.main(["check", install]) != 0:
        raise SystemExit(
            "two archives hold the same model with DIFFERENT node positions. The engine reads "
            "whichever loads last, so a fix in the other copy can be invisible. Patch every copy "
            "- gtos_vehicle.patch_shadowing_models() does it - then build again.")

    units = text_table(install, "div_units_misc", edit_units_text, check_units, plan, log)
    cocpits = text_table(install, "cocpits", edit_cocpits_text, check_cocpits, plan, log)
    if any(plan.platoon_state.get(p) == "no flag" for p in plan.platoons):
        # a flag has to be ADDED: bytes cannot grow a property, so the text route
        qb_patched = text_table(install, "qbattle", edit_qbattle_text, check_qbattle, plan, log,
                                accept=qbattle_renames_only)
    else:
        # every ticked platoon already has the flag: the proven one-byte patch (v2-v9)
        qb_patched, report = patch_qbattle(azcf.read_record(tabs_path(install), "qbattle"), plan)
        for line in report:
            log(line)
    tables = [("div_units_misc", units), ("qbattle", qb_patched), ("cocpits", cocpits)]
    assets = []                                    # (name, kind, bytes) - reticle meshes
    own = getattr(plan, "own_sight", None)
    if plan.sight_heads or own:
        # only when a gunner sight has to be tied to the gun (v11) or renamed to the
        # vehicle's own - otherwise the vehicle table is not shipped at all
        techn, report = patch_techn(azcf.read_record(tabs_path(install), plan.techn_record), plan)
        for line in report:
            log(line)
        tables.append((plan.techn_record, techn))
    if own:
        import ownsight
        folder = os.path.join(work_dir(install), "text", "common_res_mod")
        fixed = textable.round_trip(install, "common_res_mod", folder, log)
        with open(fixed, "rb") as f:
            text = ownsight.common_res_mod_text(f.read(), own)
        edited = os.path.join(folder, "edited", "common_res_mod.loc_def.engcfg2")
        os.makedirs(os.path.dirname(edited), exist_ok=True)
        with open(edited, "wb") as f:
            f.write(text)
        crm = textable.compile_text(install, edited, os.path.join(folder, "edited", "common_res_mod.config"), log)
        for line in ownsight.check_common_res_mod(azcf.read_record(tabs_path(install), "common_res_mod"), crm, own):
            log("OK  " + line)
        tables.append(("common_res_mod", crm))
        for name, blob in ownsight.make_meshes(own, log):
            assets.append((name, "mesh", blob))
    texts = []                                     # (record, bytes) for CORE/loc_eng
    if getattr(plan, "ammo_text", False):
        import ammotext
        texts = ammotext.patched_records(install, log)

    work = work_dir(install)
    pack = os.path.join(work, "pack")
    core = os.path.join(work, "CORE")
    shutil.rmtree(pack, ignore_errors=True)
    shutil.rmtree(core, ignore_errors=True)       # the zips beside them are kept
    os.makedirs(pack)
    os.makedirs(os.path.join(core, "shared", "packed_data"))

    for name, blob in tables:
        with open(os.path.join(pack, name + ".loc_def.config"), "wb") as f:
            f.write(blob)
    for name, kind, blob in assets:
        with open(os.path.join(pack, "%s.loc_def.%s" % (name, kind)), "wb") as f:
            f.write(blob)
    flatlist = os.path.join(pack, ADDON + ".!flatlist")
    with open(flatlist, "w", encoding="utf-8", newline="\n") as f:
        f.write("i_unflat:unflat()\n{\n")
        for name, _ in tables:
            f.write("\t%s, %s, loc_def ;\n" % (name.ljust(30), "config".ljust(16)))
        for name, kind, _ in assets:
            f.write("\t%s, %s, loc_def ;\n" % (name.ljust(30), kind.ljust(16)))
        f.write("}\n")
    for name, blob in texts:
        with open(os.path.join(pack, name + ".loc_eng.text"), "wb") as f:
            f.write(blob)
    if texts:
        tlist = os.path.join(pack, ADDON + "_text.!flatlist")
        with open(tlist, 'w', encoding='utf-8', newline='\n') as f:
            f.write('i_unflat:unflat()\n{\n')
            for name, _ in texts:
                f.write('\t%s, %s, loc_eng ;\n' % (name.ljust(30), 'text'.ljust(16)))
            f.write('}\n')
    desc_src = os.path.join(work, "desc.addpack.engcfg2")
    with open(desc_src, "w", encoding="utf-8", newline="\n") as f:
        f.write(DESC_TEMPLATE.format(path=ADDON, desc=DESCRIPTION, author=AUTHOR, version=version))

    desc_out = os.path.join(core, "desc.addpack")
    n = starter(install, "pd2cfgp,", rel(desc_src, install) + ",", rel(desc_out, install), expect=desc_out)
    log("OK  addon description compiled (%d bytes)" % n)

    flat = os.path.join(core, "shared", "packed_data", ADDON + ".flatdata")
    n = starter(install, "mkflat,", rel(flat, install) + ",", rel(flatlist, install), expect=flat)
    log("OK  addon archive packed (%d bytes)" % n)

    tflat = None
    if texts:
        os.makedirs(os.path.join(core, "loc_eng", "packed_data"), exist_ok=True)
        tflat = os.path.join(core, "loc_eng", "packed_data", ADDON + "_text.flatdata")
        n = starter(install, "mkflat,", rel(tflat, install) + ",", rel(tlist, install), expect=tflat)
        log("OK  addon text archive packed (%d bytes)" % n)

    zpath = os.path.join(work, zip_name or "%s_v%03d.zip" % (ADDON, version))
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(desc_out, "CORE/desc.addpack")
        z.write(flat, "CORE/shared/packed_data/%s.flatdata" % ADDON)
        if tflat:
            z.write(tflat, "CORE/loc_eng/packed_data/%s_text.flatdata" % ADDON)

    # read the result back out of the finished zip, not from the files we wrote
    with zipfile.ZipFile(zpath) as z:
        blob = z.read("CORE/shared/packed_data/%s.flatdata" % ADDON)
    tmp = zpath + ".check.flatdata"
    with open(tmp, "wb") as f:
        f.write(blob)
    try:
        recs = azcf.archive_records(tmp)
        insides = {name: azcf.read_record(tmp, name) for name, _ in tables}
        inside_assets = {name: azcf.read_record(tmp, name) for name, _, _ in assets}
    finally:
        os.remove(tmp)
    expected = [name for name, _ in tables] + [name for name, _, _ in assets]
    if sorted(recs) != sorted(expected):
        raise SystemExit("the zip holds %s, expected exactly %s" % (sorted(recs), expected))
    for name, kind, blob in assets:
        if hashlib.md5(inside_assets[name]).hexdigest() != hashlib.md5(blob).hexdigest():
            raise SystemExit("the %s %s inside the zip is not the one that was made" % (kind, name))
        log("OK  inside the zip: %s %s, %d bytes, md5 %s" % (kind, name, len(blob), hashlib.md5(blob).hexdigest()))
    if own:
        tt = azcf.Table(insides[plan.techn_record])
        srows = tt.rows(dict(azcf.vehicles(tt))[plan.vehicle]["sights"])
        log("OK  inside the zip: %s gunner sights %s" % (plan.vehicle, ", ".join(
            "%s=%s(head %s)" % (r[0], r[2], r[8] or "none") for r in srows if r[4] == "sig_gunner")))
        cr = azcf.Table(insides["common_res_mod"])
        r0 = azcf.flat(cr.rows(cr.blocks[0])[0])
        log("OK  inside the zip: common_res_mod sights row %s, %s" % (r0[0], ", ".join(
            "[%d] %s" % (pos, r0[pos]) for pos in sorted(own["fields"]))))
    for name, blob in tables:
        if hashlib.md5(insides[name]).hexdigest() != hashlib.md5(blob).hexdigest():
            raise SystemExit("the %s inside the zip is not the one that was built" % name)
        head = insides[name][0x20:0x40].split(b"\0")[0].decode("latin1")
        if head != name:
            raise SystemExit("the %s inside the zip names itself %r in its header" % (name, head))
    if texts:
        import ammotext
        with zipfile.ZipFile(zpath) as z:
            tblob = z.read("CORE/loc_eng/packed_data/%s_text.flatdata" % ADDON)
        ttmp = zpath + ".text.flatdata"
        with open(ttmp, "wb") as f:
            f.write(tblob)
        try:
            for name, blob in texts:
                if azcf.read_record(ttmp, name) != blob:
                    raise SystemExit("the %s text inside the zip is not the one that was made" % name)
                ents = {e[1]: e for e in ammotext.entries(blob)}
                for tid in ammotext.wanted_for(name):
                    e = ents[tid]
                    shown = ammotext.lines_of(blob, e[3], e[2])[0][2].decode("cp1251")
                    log("OK  inside the zip: %s %s reads %r" % (name, tid, shown))
        finally:
            os.remove(ttmp)
    q = azcf.Table(insides["qbattle"])
    for name in plan.platoons:
        log("OK  inside the zip: qbattle %s user_in=%s" % (name, q.props(q.find(name)[0])["user_in"]))
    t = azcf.Table(insides["div_units_misc"])
    rows = {r[0]: r for r in t.rows(t.find("units")[0])}
    for target in [plan.unit]:
        r = rows[target]
        log("OK  inside the zip: %s crewable=%s cockpit=%s anims=%s"
            % (target, r[CREWABLE], r[COCKPIT], r[ANIMS]))
    c = azcf.Table(insides["cocpits"])
    for new in [plan.cockpit]:
        i = [b.index for b in c.blocks if b.name == new]
        for station, fields in plan.station_edits.items():
            g = next(b for b in c.blocks[i[0]:] if b.name == station)
            p = c.props(g)
            log("OK  inside the zip: %s %s %s" % (new, station, ", ".join(
                "%s=%s" % (k, p[k]) for k in sorted(fields))))
    log("OK  %d units in the shipped table" % len(rows))
    log("BUILT %s" % zpath)
    return zpath


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the SABoW Ext addon for one vehicle.")
    ap.add_argument("unit", help="unit name, e.g. sau_t55")
    ap.add_argument("version", type=int, help="build number for the zip name")
    a = ap.parse_args()
    p = recipe.derive(INSTALL, a.unit)
    print(p.report())
    build(p, a.version)
