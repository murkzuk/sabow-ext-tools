# player_tank_tool.py - report which platoons in an operation can be made drivable.
#
# PHASE 1: REPORT ONLY. This changes nothing on disk, ever. It reads an operation .campack2,
# lists the platoons that contain a vehicle, and badges each one:
#
#     DRIVABLE        we have a proven cockpit + techn for that vehicle model
#     NOT DRIVABLE    no cockpit exists for it, so it cannot be made drivable at all
#
# Plus an OOB audit: every squad the operation uses is resolved down to its units and checked for
# dangling references. One missing reference was what crashed the Sokolovo campaign (notes_105).
#
# WHAT PUTS A PLAYER IN THE BATTLE - notes/103, quoting the Operation Editor manual 1.2.4. Miss
# any ONE of these and the engine has nowhere to put the player, logs
# 'WARNING [i_gamespec:gamespec] Bad user desc!' and falls back to AUTOBATTLE: the battle plays
# itself with no tank in it. That is the failure this tool exists to prevent, so it checks all
# four - plus a fifth the manual does not list, and that is the one that was actually biting (5
# below) - and NAMES the one that is missing:
#   1. the platoon is on the operation's user_side   (desc block 0)   - not editable here
#   2. user_in = true on that platoon                (the operation)   - phase 2, make_drivable
#   3. ai = USER on that platoon                     (the operation)   - not editable here
#   4. EVERY vehicle the platoon can DRAW has a cockpit (the oob, GLOBAL) - phase 3
#   5. the operation's compiled records still carry the operation's OWN NAME  - NOT one of the
#      four the manual lists, and the one that was actually biting for days. pd2cfgp takes the
#      compiled record's name from the OUTPUT FILE NAME, so a round trip that names that file
#      after the PACK record renames the operation to 'desc'. The engine then cannot resolve the
#      name, logs the SAME 'Bad user desc!' warning, and plays a TACIMAGE - a stale saved battle
#      that is not the operation at all. Measured 2026-09-28; the guard is
#      tool/test_operation_name.py and the write-up is notes_127.
#
# 'Every vehicle it can DRAW' is meant literally, and it is not the same as 'every vehicle it
# LISTS': a platoon names squads, a squad may name a RANDOM pool, and the engine picks from that
# pool at runtime - so a platoon is only safe if the whole pool is crewable. That is what killed
# Sokolovo (notes_105): the pool held one cockpitless STZ.

# See SPEC_player_tank_tool.md. Phase 1 does not write. Phase 2 is written (make_drivable).
# Phase 3 (make a vehicle model crewable, a GLOBAL oob edit) is not written yet.
#
# ---------------------------------------------------------------------------------------------
# WHAT THIS TOOL GUARANTEES, and why each one is here rather than in a note
# ---------------------------------------------------------------------------------------------
# ALL FOUR must be true at once, and NOT ONE of them produces an error when it is false - the
# battle simply plays itself, with no warning and usually no log line at all:
#
#   1. the platoon is on the operation's user_side          read from desc block 0
#   2. ai = USER on that platoon                            read from the platoon block
#   3. EVERY units[] ROW it can draw is crewable AND its cockpit EXISTS
#                                                           the ROW, never the MODEL NAME
#   4. IT IS ON THE MAP WHEN YOU PLAY - its ARRIVAL TURN     read from plat_pos
#
# 3 and 4 are the two that cost evenings. 3 was the AI-only row: a MODEL can be drivable in
# div_units_misc while the ROW the platoon fields is AI-only in div_units_ussr, and matching on the
# model name made the tool say DRIVABLE on a platoon that could never be crewed. 4 is the arrival
# turn: the game LOCKS a platoon until the turn it arrives on, so it cannot be selected, moved or
# ordered, no battle can include it, and flagging it changes nothing - while its row is perfectly
# crewable and every other check passes.
#
# So: unit_verdict() for 3, arrival_turns() for 4, pick_playable() to CHOOSE correctly rather than
# describe, and make_playable() to do the whole job and read its own output back. If you add a fifth
# condition, put it in scan_one() where every caller sees it, and give it a test.
#
#   5. NO SOLDIER IN THE BATTLE IS OF A TYPE THAT CAN NEVER BE EQUIPPED    notes_128, 2026-09-28
#                                                           read from the add-on's human tables
#
# 5 is not about the player's tank at all and nothing this tool WRITES can fix it: a man whose
# soldier row lists no weapon gets an empty weapons list, the engine's startup walk dereferences it
# without a NULL check, and the battle dies with the generic "001: Program initialization error"
# before the deploy. It is here because it is the same class of fault as 3 and 4 - silent, fatal,
# and about content rather than the flag - and because the tool already resolves every platoon to
# its units[] rows, so the sentence costs nothing to say. The repair is an ADD-ON build; the audit
# is tool/soldier_rows.py.

import os
import re
import struct
import subprocess
import shutil
import sys
import glob

# THE TOOL DIRECTORY IS THE ONE THIS FILE LIVES IN. It used to be the literal
# "K:/SABoW_Ext/tool", so on any machine without a K: drive the imports below raised
# ModuleNotFoundError before anything else ran - and because the shortcut starts this
# with pythonw, that crash was SILENT: no window, no message, nothing for the user to
# report. Release audit 2026-10-06, docs/RELEASE_AUDIT_2026-10-06.md B1.
TOOL = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOL)
TOOL_DIR = TOOL
def _startup_error(title, what):
    """Show a startup failure instead of dying invisibly.

    These tools are launched with pythonw, which has NO CONSOLE. Without this, any exception
    before the Tk window exists produces nothing at all - the icon flashes and the user has
    nothing to report. Release audit 2026-10-06, RELEASE_AUDIT_2026-10-06.md H4.

    Deliberately stdlib-only and deliberately repeated in each tool rather than shared: what it
    usually reports is "the local modules would not import", and a guard that is itself a local
    import cannot run to say so.
    """
    import traceback
    import tempfile
    detail = traceback.format_exc()
    written = ""
    for folder in (os.path.dirname(os.path.abspath(__file__)), tempfile.gettempdir()):
        try:
            path = os.path.join(folder, "sabow_tool_error.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(what + "\n\n" + detail)
            written = path
            break
        except OSError:
            continue
    last = detail.strip().splitlines()[-1] if detail.strip() else ""
    msg = what + "\n\n" + last
    if written:
        msg += "\n\nThe full details were written to:\n" + written
    shown = False
    try:
        import tkinter
        from tkinter import messagebox
        _r = tkinter.Tk()
        _r.withdraw()
        messagebox.showerror(title, msg)
        _r.destroy()
        shown = True
    except Exception:
        pass
    if not shown:
        # tkinter itself may be what is missing, and under pythonw a print goes nowhere.
        # ctypes is always there on Windows. 0x10 = MB_ICONERROR.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
        except Exception:
            pass
    print(what)
    print(detail)
    sys.exit(1)


try:
    import azcf
    import build
    import gtos_opstar
    import settings
except Exception:
    _startup_error('SABoW Player Tank Tool',
                   "SABoW Player Tank Tool could not load its own modules (azcf.py, build.py, gtos_opstar.py, settings.py).\n\n"
                   "It needs them in: " + TOOL_DIR)

# Which vehicle models SABoW Ext Control already knows, so a blocked platoon can say whether the
# model needs ADDING there first or is one press away. Guarded: the player tank tool must still run
# if the Ext tool is absent or unreadable, and an empty set only costs a vaguer sentence.
try:
    import gtos_vehicle as GV
    KNOWN_TO_GTOS = set(GV.VEHICLES)
    # A BUILT-IN's settings live in the tool's own code, and load_user_vehicles deliberately
    # never lets the settings file override one - so 'Make this one playable' REFUSES it. Saying
    # 'already there, one press' about a built-in is how the KV-1 read as ready when it was not.
    BUILT_IN_GTOS = set(GV.BUILT_IN)
except Exception:
    KNOWN_TO_GTOS = set()
    BUILT_IN_GTOS = set()

# A platoon can only take a player tank if it actually fields a VEHICLE. The oob classifies every
# squad with a type token in column 1, and most of what a WW2 operation holds is not a vehicle:
# sq_mortar (mt50, mt82), sq_mg (maxim), sq_atgun (pak38, 53k), sq_spam and sq_sup (trucks),
# sq_inf. Counting those as "tanks we cannot make drivable" is what made the first report
# alarming and useless - 336 blocked, mostly mortars. These are the types that ARE a fighting
# vehicle, so only these are worth offering to the player.
VEHICLE_SQUAD_TYPES = frozenset([
    "sq_tank",      # tanks
    "sq_spg",       # assault guns / self-propelled guns (stug3f8)
    "sq_atspg",     # self-propelled anti-tank (marder3h)
    "sq_apc",       # armoured personnel carriers
    "sq_spgapc",    # SPG on an APC chassis (sdkfz251c_2)
    "sq_atapc",     # AT gun on an APC chassis (sdkfz251c_10)
    "sq_acar",      # armoured cars (sdkfz232_8)
])

# A side is a four-character name packed into an int, so the operation header and every platoon
# block can be COMPARED rather than string-matched. The operation declares who the player is in
# its first desc block (i_campgen:campgen) as user_side, and each platoon states its own side in
# the same encoding - so 'is this platoon on the player's side?' is one equality.
#
# WHY THIS EXISTS AT ALL. notes/103, quoting the Operation Editor manual 1.2.4, lists user_side as
# one of four conditions. This tool checked three of them and never compared the two sides, and
# the omission was INVISIBLE because Sokolovo - the only operation anyone had made playable - is
# user_side = USSR and its DRIVABLE platoons are all USSR. The list was right by accident. Shilovo
# is the first operation with a DRIVABLE platoon on BOTH sides, and there the report offered two
# GERMAN platoons (wer_24tr_1lc_2p, wer_24tr_1lc_3p) in a SOVIET operation.
SIDES = {1381192533: "USSR", 5391687: "GER"}
AI_USER = 1380275029


def side_name(v):
    return SIDES.get(v, str(v))


# THE COCKPITS THAT ACTUALLY EXIST, filled by load_caps. A cockpit name in a units[] row is a
# DECLARATION, not a fact - notes_103: Operation Star declares cockpits that exist nowhere, and a
# declared-but-absent cockpit is the whole difference between a battle and an autobattle. Cached
# here rather than passed as a parameter because every caller holding `caps` has already been
# through load_caps, and a sixth argument on every signature would be churn for nothing.
EXISTING_COCKPITS = set()

# Cockpit tables found to carry the build defect of 2026-09-27, as (path, [(index, name, spec)]).
BROKEN_COCKPIT_TABLES = []


def bad_specs(table):
    """[(index, name, spec)] for every block whose spec is not a field type.

    WHY THIS IS HERE. cfgp2pd writes a spec-less block as "name=()", and that "=" recompiles as a
    ONE-CHARACTER SPEC. cfgfix repairs it against the stock .config, but a block the stock table does
    not have - a NEW COCKPIT, which is the whole point of this tool - has no entry there and used to
    be left alone. The table then LOADS PERFECTLY and the game dies entering the deploy with
    "001: Program initialization error": measured 2026-09-27, one day lost to it.

    A spec of '=' is always a defect: no field type is '='. A 0x00 spec is not - `techn_gtos` names
    all 13 of its vehicle blocks with 0x00 and runs battles every day - so the rule is only applied to
    COCKPIT tables, where the stock record uses an empty spec for every container and none of them is
    0x00. This function is only ever handed cockpit tables, which is why the absolute rule is right
    here. A tool whose job is to say whether a tank can be driven must not call such a table good.
    """
    return [(b.index, b.name, b.spec) for b in table.blocks
            if "\x00" in b.spec or "=" in b.spec]


def load_cockpits(install, log=None):
    """Every cockpit name THE GAME CAN LOAD - read from every installed add-on's cockpit table.

    IT USED TO READ ONE FILE: the gtos_ww2 build workspace's `cocpits` text. That is the OLDER
    cockpit line's working copy and only that, so the moment a cockpit arrived from a different
    add-on the tool called it "DECLARED but does not exist" and REFUSED A BUILD WHOSE COCKPIT WAS
    INSTALLED AND WORKING. Measured 2026-09-26: `coc_ww2_sov76` ships in sabow_ww2, the game's own
    table has it, and the tool said it did not exist.

    A declaration is not a fact - but neither is one add-on's workspace file a fact about what the
    game loads. So read all of them: every `cocpits` record under the installed add-ons'
    plus the workspace text as a fallback. Each archive's DIRECTORY is read, not the whole file
    (tex_main is 190 MB), and additions.flatdata holds no cocpits at all.
    """
    out = set()
    found_in = []
    for p in sorted(glob.glob(os.path.join(install, "data", "*", "*", "shared", "packed_data",
                                           "*.flatdata"))):
        try:
            d = gtos_opstar.directory(p)
        except Exception:
            continue
        if ("cocpits", "config") not in d:
            continue
        try:
            t = azcf.Table(gtos_opstar.read(p, d[("cocpits", "config")]))
        except Exception:
            continue
        bad = bad_specs(t)
        if bad:
            BROKEN_COCKPIT_TABLES.append((p, bad))
        here = set(b.name for b in t.blocks if b.name.startswith("coc_"))
        if here:
            found_in.append((os.path.basename(p), len(here)))
            out |= here
    # the Ext tool's working text, kept because a cockpit can exist there before it is packed
    for c in glob.glob(os.path.join(install, "users", "modwork", "gtos_ww2", "text", "cocpits",
                                    "edited", "cocpits.config")):
        try:
            raw = open(c, "rb").read()
        except Exception:
            continue
        out |= set(x.decode() for x in re.findall(rb"\bcoc_[a-z0-9_]+", raw))
    if log and found_in:
        log("      cockpits read from: %s"
            % ", ".join("%s (%d)" % (n, c) for n, c in found_in))
    if log:
        for path, bad in BROKEN_COCKPIT_TABLES:
            log("      *** %s carries %d block(s) whose spec is not a field type: %s"
                % (os.path.basename(path), len(bad),
                   ", ".join("%s (spec %r)" % (n, s) for _, n, s in bad[:4])))
            log("          MEASURED 2026-09-27: ONE such block in a cockpit table made every"
                " battle die entering the deploy with the generic '001: Program initialization"
                " error', and nothing in the log named cockpits. Do not ship this table.")
    return out


def unit_verdict(unit_name, units):
    """(crewable, cockpit, why_not) for ONE units[] row - the row the platoon ACTUALLY FIELDS.

    THIS IS THE CHECK THAT WAS MISSING, AND IT IS NOT THE SAME QUESTION AS 'IS THE MODEL
    DRIVABLE?'. The KV-1 proves it: the campaign table (div_units_ussr) holds

        rkkau_kv1_42_uztm   techn=tabs\techn_base.cfgpack   model=kv1_42_uztm   crewable=false

    while div_units_misc - a DIFFERENT table - holds a crewable row for the same model
    kv1_42_uztm. The tool built its 'drivable models' set from div_units_misc and then matched
    the platoon's model name against it, so a platoon fielding an AI-only row was reported
    DRIVABLE and READY. That single mismatch is why Shilovo autobattled across three evenings
    while this tool said everything was in order.

    A platoon can only put a player in a tank if the ROW IT FIELDS is crewable, names a cockpit,
    and that cockpit EXISTS.
    """
    r = units.get(unit_name)
    if r is None:
        return False, "", "no units[] row at all"
    if r[11] is not True:
        return False, r[12] or "", "crewable = false - an AI-only row in the campaign table"
    if not r[12]:
        return False, "", "crewable = true but it names no cockpit"
    if EXISTING_COCKPITS and r[12] not in EXISTING_COCKPITS:
        return False, r[12], "its cockpit %s is DECLARED but does not exist (notes_103)" % r[12]
    return True, r[12], ""


def load_caps(install, log=None):
    """{vehicle model: (techn_ref, cockpit, anims)} - the combinations gtos_ww2 already proves
    SOMEWHERE. This is the work-order view: it says a model COULD be driven, not that any given
    platoon can be. The verdict on a platoon comes from unit_verdict() and the row it fields."""
    caps = {}
    EXISTING_COCKPITS.clear()
    EXISTING_COCKPITS.update(load_cockpits(install))
    p = os.path.join(install, "data", "mtc80", "gtos_ww2", "shared", "packed_data", "gtos_ww2.flatdata")
    if not os.path.isfile(p):
        return caps
    d = gtos_opstar.directory(p)
    if ("div_units_misc", "config") not in d:
        return caps
    t = azcf.Table(gtos_opstar.read(p, d[("div_units_misc", "config")]))
    for r in t.rows(t.find("units")[0]):
        if r[11] is True and r[12]:
            caps[r[3]] = (r[2], r[12], r[13])
    return caps


def load_oob(install):
    """squad -> [units], random -> [squads], unit -> row, squad -> its type token, from our
    shipped div_units."""
    squads, randoms, units, stypes = {}, {}, {}, {}
    p = os.path.join(install, "data", "mtc80", "gtos_sokolovo_ob", "shared", "packed_data", "tabs.flatdata")
    if not os.path.isfile(p):
        return squads, randoms, units, stypes
    d = gtos_opstar.directory(p)
    for tab in ("div_units_ussr", "div_units_ger"):
        if (tab, "config") not in d:
            continue
        t = azcf.Table(gtos_opstar.read(p, d[(tab, "config")]))
        u = t.find("units")
        if u:
            for r in t.rows(u[0]):
                units[r[0]] = r
        s = t.find("squads")
        if s:
            for r in t.rows(s[0]):
                squads[r[0]] = [v for v in r[2:] if isinstance(v, str) and v.startswith(("rkkau_", "weru_", "czu_"))]
                stypes[r[0]] = r[1]
        rb = t.find("randoms")
        if rb:
            for r in t.rows(rb[0]):
                randoms[r[0]] = [v for v in r[1:] if isinstance(v, str) and v]
    return squads, randoms, units, stypes


# ---------------------------------------------------------------------------------------------
# A FIFTH WAY A BATTLE DIES BEFORE THE DEPLOY: a soldier type with no weapon   (notes_128)
# ---------------------------------------------------------------------------------------------
# A man's kit is built from his SOLDIER ROW in the add-on's human table: man+0x1AA0 is his
# AMMUNITION list and man+0x1AB0 his WEAPONS list, both built from that row's shells and weapons
# blocks. A row listing NEITHER builds a man with two empty lists - and the engine's own startup
# walk (basic_physic+0x97e64) reads the weapons list with no NULL check, so ONE such man kills the
# battle with "001: Program initialization error" before it ever reaches the deploy.
#
# MEASURED, not reasoned (notes_128): Shilovo built 310 men and only 302 got an equipment record;
# the 8 that did not were all the ATR type, all from rows that list no weapon and name an ammo
# pattern (ammo_pat = rus_ptr1) that is defined nowhere in the game data. The counts match the rows
# exactly - rus_inf_serg weapons 2 / shells 3 against containers of 2 and 3, and the number inside
# the first ammunition element is the exact round count (142 for his 762_TT, 21 for soldier4's
# 762_NAG) - so there is no doubt which field builds what.
#
# THIS TOOL CANNOT REPAIR IT. The rows live in
# gtos_sokolovo_ob\shared\packed_data\tabs.flatdata, not in the operation, and this tool writes
# operations. But it already resolves every platoon to its units[] rows, so it can SAY so before a
# battle is built on it - which is the whole difference between a note and another lost evening.
SOLDIER_TABLES = ("rus_hum_base", "ger_hum_base", "cz_hum_base")
_SOLDIER_CACHE = {}


def install_of(path):
    """The install an operation lives in, found by walking up to starter.exe."""
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(6):
        if os.path.isfile(os.path.join(d, "starter.exe")):
            return d
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return settings.get("sandbox")


def soldier_tag(cells):
    """The four-character type of a soldier row ('INF', 'HINF', 'ATR'): its first cell."""
    if not cells or not isinstance(cells[0][0], int):
        return None
    b = struct.pack("<I", cells[0][0])
    s = "".join(chr(c) for c in b if 32 <= c < 127)
    return s if len(s) >= 3 else None


def load_soldiers(install):
    """{human row: {table, type, weapons, shells}} from the add-on that runs these battles.

    Empty if the add-on is not there - the check is then simply silent, never wrong.
    """
    if install in _SOLDIER_CACHE:
        return _SOLDIER_CACHE[install]
    tabs = os.path.join(install, "data", "mtc80", "gtos_sokolovo_ob",
                        "shared", "packed_data", "tabs.flatdata")
    out = {}
    if tabs and os.path.isfile(tabs):
        for tab in SOLDIER_TABLES:
            try:
                t = azcf.Table(azcf.read_record(tabs, tab))
            except Exception:
                continue
            cur, rows = None, {}
            for b in t.blocks:
                if b.name in ("weapons", "shells", "addins"):
                    if cur is not None:
                        rows.setdefault(cur, {})[b.name] = t.rows(b)
                else:
                    cur = b.name
                    rows.setdefault(cur, {"_main": t.rows(b)})
            for row, d in rows.items():
                out[row] = {"table": tab, "type": soldier_tag(d.get("_main")),
                            "weapons": d.get("weapons") or [], "shells": d.get("shells") or []}
    _SOLDIER_CACHE[install] = out
    return out


def soldiers_without_weapons(soldiers):
    """The rows an engine can never equip - the ones a battle must not field."""
    return {r for r, d in soldiers.items() if not d["weapons"] and not d["shells"]}


def soldier_exposure(plats, squads, randoms, units, soldiers):
    """{platoon: [(units row, human row)]} for every platoon fielding an unequippable soldier.

    EVERY squad is walked, not only the ones carrying a vehicle: the men that kill a battle are
    infantry, and they sit in exactly the platoons a vehicle report skips two lines later.
    """
    bare = soldiers_without_weapons(soldiers)
    if not bare:
        return {}
    out = {}
    for pname, _props, sq in plats:
        found = []
        for s in sq:
            for squad_name in expand_squads(s, squads, randoms):
                for u in resolve(squad_name, squads, randoms):
                    r = units.get(u)
                    if r is not None and r[1] == "i_human" and r[3] in bare and (u, r[3]) not in found:
                        found.append((u, r[3]))
        if found:
            out[pname] = found
    return out


def soldier_note(expo):
    """The sentence the report owes the reader when a battle here cannot be built."""
    if not expo:
        return None
    rows = sorted({row for lst in expo.values() for _u, row in lst})
    who = ", ".join("%s [%s]" % (p, ",".join(sorted({r for _u, r in lst})))
                    for p, lst in sorted(expo.items())[:3])
    if len(expo) > 3:
        who += ", +%d more" % (len(expo) - 3)
    return ("SOLDIERS: %d soldier type(s) here have NO weapon (%s), fielded by %s. A battle that "
            "includes them dies at basic_physic+0x97e64 with the generic '001: Program "
            "initialization error' BEFORE the deploy, whatever the platoon rows below say - no flag "
            "and no cockpit changes that. The rows live in the ADD-ON, not in this operation: "
            "notes_128, tool/soldier_rows.py" % (len(rows), ", ".join(rows), who))


def resolve(name, squads, randoms, depth=0):
    """a squad or random-pool name -> the unit names it can produce."""
    if depth > 4:
        return []
    if name in squads:
        return squads[name]
    if name in randoms:
        out = []
        for x in randoms[name]:
            out += resolve(x, squads, randoms, depth + 1)
        return out
    return [name] if name.startswith(("rkkau_", "weru_", "czu_")) else []


def expand_squads(name, squads, randoms, depth=0):
    """a pool or squad name -> the SQUAD names it can produce (not units). A random pool such as
    rn_rkka_t34 holds squad names, so the type has to be looked up per squad, not per pool."""
    if depth > 4:
        return []
    if name in randoms:
        out = []
        for x in randoms[name]:
            out += expand_squads(x, squads, randoms, depth + 1)
        return out
    if name in squads:
        return [name]
    return []


def platoons_of(t):
    """[(platoon_name, props, [squad names])] from a div_pool or a merged desc."""
    bl = t.blocks
    out = []
    for i, b in enumerate(bl):
        if len(b.spec) != 1 or not b.rows:
            continue
        try:
            p = t.props(b)
        except Exception:
            continue
        if "pool" not in p or "ai" not in p:
            continue                      # not a platoon
        squads = []
        for j in range(i + 1, min(i + 3, len(bl))):
            if bl[j].name == "pool":
                try:
                    squads = [r[0] for r in t.rows(bl[j]) if r and isinstance(r[0], str) and r[0]]
                except Exception:
                    pass
                break
        out.append((b.name, p, squads))
    return out


def arrival_turns(t):
    """{platoon uid: arrival turn} from the operation's own plat_pos block.

    A plat_pos row is TWO arrays of four, not one of eight:

        (uid, cell_x, cell_y, node)    (TURN, 0, 0, 0)

    The second array's first value is the turn the platoon ARRIVES on, and THE GAME LOCKS A PLATOON
    UNTIL THEN - it cannot be selected, moved or ordered, so it cannot be in a battle before that
    turn, and flagging it changes nothing until the player plays that far.

    THIS IS THE FAULT THAT COST THE MOST TIME ON SHILOVO. p_rkka_110_tbr_1mc arrives on turn 8.
    Every test was played on turn 1, so the platoon could never be given an order, no battle ever
    included it, and every fight auto-resolved - correctly, silently, with no log line. The row
    edit, the flag, the side and the cockpit were ALL right; the platoon was simply not in play.

    Proved 121 for 121 against a save the engine itself wrote: every platoon's saved 'turn' equals
    this value, and nothing else in the operation carries it - not the platoon props, not the
    reserves blocks, not the frames.
    """
    out = {}
    blk = t.find("plat_pos")
    if not blk:
        return out
    for r in t.rows(blk[0]):
        a = r[0]
        b = r[1] if len(r) > 1 else None
        if isinstance(a, tuple) and len(a) == 4:
            out[a[0]] = b[0] if isinstance(b, tuple) and b else None
    return out


def scan_one(path, caps, squads, randoms, units, stypes, soldiers=None):
    """Read one operation ONCE and return its vehicle platoons as DATA. Writes nothing.

    report_one() prints as it walks, which is what turned a 15-operation run into a wall of text:
    every blocked platoon repeats the same three lines about cockpits that do not exist. The same
    walk, collected instead, lets the caller show a summary first and the detail only if asked.
    """
    name = os.path.basename(path)
    notes = []
    # The soldier check needs the ADD-ON's human table, which an operation path does not carry -
    # so it is found from the operation's own install, and if the add-on is not there at all the
    # check is silent rather than wrong.
    if soldiers is None:
        soldiers = load_soldiers(install_of(path))
    d = gtos_opstar.directory(path)
    if ("desc", "config") not in d:
        return name, [], 0, ["no desc record - not an operation"]
    t = azcf.Table(gtos_opstar.read(path, d[("desc", "config")]))
    names = [b.name for b in t.blocks]
    if not names or names[0] != "i_campgen:campgen":
        notes.append("desc does not start with i_campgen:campgen - the game would ignore it")
    # WHO THE PLAYER IS, read and never assumed. The same map ships as both a Soviet and a German
    # operation, and the two files differ in exactly this field.
    user_side = None
    try:
        user_side = t.props(t.blocks[0]).get("user_side")
    except Exception:
        pass
    usname = side_name(user_side) if user_side is not None else "?"
    # WHEN THIS PLATOON IS EVEN ON THE MAP. A platoon the game has locked until turn 8 cannot be
    # given an order on turn 1, so no battle can include it and everything autobattles regardless
    # of how right the flag is. Read here so every caller sees it.
    arrive = arrival_turns(t)
    out, no_tank = [], 0
    plats = platoons_of(t)
    # EVERY platoon, including the infantry ones this loop is about to skip - see the section at
    # the top of the file. A platoon holding no vehicle can still be the one that kills the battle.
    expo = soldier_exposure(plats, squads, randoms, units, soldiers)
    for pname, props, sq in plats:
        sqn = []
        for s in sq:
            sqn += expand_squads(s, squads, randoms)
        veh = [x for x in sqn if stypes.get(x) in VEHICLE_SQUAD_TYPES]
        if not veh:
            no_tank += 1
            continue
        # THE UNITS THIS PLATOON ACTUALLY FIELDS, each one tested on its OWN units[] row. Not on
        # the model name - see unit_verdict() for why that distinction cost three evenings.
        here, seen_u = [], set()
        for s in veh:
            for u in resolve(s, squads, randoms):
                r = units.get(u)
                if r is not None and r[1] == "i_techn" and u not in seen_u:
                    seen_u.add(u)
                    here.append((u, r))
        if not here:
            no_tank += 1
            continue
        models = []
        for u, r0 in here:
            if r0[3] not in models:
                models.append(r0[3])
        ok, bad, badwhy = [], [], []
        for u, r0 in here:
            good, ck, why = unit_verdict(u, units)
            if good:
                if u not in ok:
                    ok.append(u)
            else:
                bad.append(u)
                badwhy.append("%s - %s" % (u, why))
        side = side_name(props.get("side"))
        ai = "USER" if props.get("ai") == AI_USER else str(props.get("ai"))
        on_side = (user_side is not None and props.get("side") == user_side)
        user_in = props.get("user_in") is True
        # WHY THIS PLATOON WOULD AUTOBATTLE, in words. Every line is a condition notes/103 names,
        # and none of them can be repaired by setting user_in - which is the whole point: the tool
        # has to say so BEFORE the write, not after the player has sat through a battle with no
        # tank in it. This is the check that was asked for: is the tank we are spawning actually
        # in the battle?
        blockers = []
        if not on_side:
            blockers.append("it is a %s platoon but the player is %s" % (side, usname))
        if ai != "USER":
            blockers.append("ai = %s, not USER" % ai)
        blockers.extend(badwhy)
        can = not blockers
        # AI-ONLY ROW is its own state and deserves its own name: a table SOMEWHERE has a crewable
        # row for this model, but the row THIS PLATOON FIELDS is AI-only. That is Shilovo exactly,
        # and it is not fixed by user_in and not fixed by adding a cockpit - it needs the campaign
        # table edited, the way notes_103 did for the T-34.
        model_ok = [m for m in models if m in caps]
        if not can and not on_side:
            tag = "WRONG SIDE"
        elif not can and bad and model_ok:
            tag = "AI-ONLY ROW"
        elif not can:
            tag = "PARTLY" if ok else "NOT DRIVABLE"
        else:
            tag = "DRIVABLE"
        out.append({"platoon": pname, "side": side, "ai": ai, "user_in": user_in,
                    "op_side": usname, "on_side": on_side, "can": can,
                    "tag": tag, "ok": ok, "bad": bad, "models": models,
                    "blockers": blockers, "badwhy": badwhy,
                    "arrival": arrive.get(props.get("uid")),
                    # live = flagged AND nothing else in the way. The only state in which the
                    # player really gets a tank to drive.
                    "live": can and user_in, "user_in_div_pool": None,
                    # empty unless this platoon fields a soldier type that can never be equipped
                    "bad_soldiers": [row for _u, row in expo.get(pname, [])]})
    # THE FLAG MUST BE TRUE IN BOTH RECORDS. desc and div_pool both carry the platoon list and we
    # do not know which one the engine reads (SPEC V1), which is why make_drivable writes both - so
    # if they DISAGREE the tool has to say so rather than report whichever it happened to read.
    # Not hypothetical: the first build matched user_in against a single leading tab, missed the
    # two-tab row in desc, inserted a second row at the top and left the real 'false' at the
    # bottom. Files written by that build read user_in = true in div_pool and false in desc, and
    # would still autobattle while the report called them READY.
    dk = [k for k in d if k[0] == "div_pool"]
    if dk:
        divu = {}
        try:
            t2 = azcf.Table(gtos_opstar.read(path, d[dk[0]]))
            divu = {pn: (pr.get("user_in") is True) for pn, pr, sq in platoons_of(t2)}
        except Exception as ex:
            notes.append("div_pool could not be read: %s" % ex)
        for p in out:
            if p["platoon"] not in divu:
                continue
            p["user_in_div_pool"] = divu[p["platoon"]]
            # Only a fault if one of them actually claims the flag. Both false is just unflagged.
            if divu[p["platoon"]] != p["user_in"] and (p["user_in"] or divu[p["platoon"]]):
                p["blockers"].append(
                    "the two records DISAGREE - desc says user_in = %s, div_pool says %s"
                    % (p["user_in"], divu[p["platoon"]]))
                p["can"] = False
                p["live"] = False
                p["tag"] = "FLAG FAULTY"
    note = soldier_note(expo)
    if note:
        notes.append(note)
    return name, out, no_tank, notes, usname


def render_layers(rows, summaries, work, caps, log):
    """The readable view: state of the operations, what you can take, and what is in the way.

    Counted FOUR ways, because two of them can hold a player tank and calling a MIXED platoon
    "blocked" overstates the problem: a platoon holding a Panzer III and a Panzer III J is
    takeable, it just also contains one you cannot drive.
    """
    log("")
    log("=" * 92)
    log("WHERE YOU STAND")
    log("=" * 92)
    log("  %-22s %8s %6s %7s %6s %6s %8s %6s"
        % ("operation", "takeable", "mixed", "blocked", "no veh", "enemy", "AI-ONLY", "faulty"))
    td = tp = tb = tn = tw = tf = ta = 0
    for name, dr, pa, bl, nv, ws, ff, ao, note in summaries:
        td += dr; tp += pa; tb += bl; tn += nv; tw += ws; tf += ff; ta += ao
        flag = "" if not note else "   <-- " + note
        log("  %-22s %8d %6d %7d %6d %6d %8d %6d%s"
            % (name[:22], dr, pa, bl, nv, ws, ao, ff, flag))
    log("  " + "-" * 78)
    log("  %-22s %8d %6d %7d %6d %6d %8d %6d" % ("TOTAL", td, tp, tb, tn, tw, ta, tf))
    log("")
    log("  takeable - every model has a cockpit AND the platoon is on the PLAYER's side")
    log("  mixed    - some models have a cockpit, some do not; NOT safe (notes/103: autobattles)")
    log("  blocked  - no model in it has a cockpit")
    log("  enemy    - crewable, but on the OTHER side; the player is not in it, so it autobattles")
    log("  AI-ONLY  - a cockpit exists for the MODEL, but the ROW this platoon fields is AI-only.")
    log("             user_in CANNOT fix these; the campaign table must be edited (notes_103).")
    log("  faulty   - flagged in ONE record and not the other; it would STILL autobattle")
    log("  %d vehicle platoons across %d operations; %d can take one (%d outright)."
        % (td + tp + tb + tw, len(summaries), td + tp, td))

    takeable = [p for p in rows if p["tag"] in ("DRIVABLE", "PARTLY")]
    if takeable:
        log("")
        log("=" * 92)
        log("TAKE ONE OF THESE - %d platoon(s) that can hold a player tank" % len(takeable))
        log("=" * 92)
        log("  %-30s %-26s %-6s %-7s %-9s %-6s %s" % ("operation", "platoon", "side",
                                                         "user_in", "IN BATTLE", "turn",
                                                         "would drive"))
        for p in takeable:
            # 'IN BATTLE' is the answer to the question this column exists for. A platoon that is
            # DRIVABLE but not flagged is not in the battle yet and pressing the button is what
            # puts it there; one that is flagged AND DRIVABLE is the only state that actually
            # gives the player a tank.
            state = "READY" if p["live"] else ("flagged" if p["user_in"] else "-")
            # THE TURN COLUMN IS NOT DECORATION. A platoon that arrives on turn 8 is not in the
            # battle on turn 1 however crewable its row is, and 'READY' alone let that happen.
            ar = p.get("arrival")
            log("  %-30s %-26s %-6s %-7s %-9s %-6s %s"
                % (p["op"][:30], p["platoon"][:26], p["side"],
                   "YES" if p["user_in"] else "-", state,
                   ("turn %d" % ar) if ar else "-", ", ".join(p["ok"])))

    # THE PLATOONS THE OLD LIST GOT WRONG. Named, so that 'user_in is set but the battle still
    # played itself' has a visible cause instead of being a mystery.
    wrong = [p for p in rows if not p["on_side"] and p["can"] is False and p["ok"]]
    if wrong:
        log("")
        log("  %d platoon(s) hold a CREWABLE tank but sit on the OTHER side - the player is not"
            % len(wrong))
        log("  in them, so flagging one only autobattles (notes/103). This is the list that used")
        log("  to be offered by mistake:")
        for p in sorted(wrong, key=lambda q: (q["op"], q["platoon"]))[:10]:
            log("      %-30s %-26s %s, player is %s"
                % (p["op"][:30], p["platoon"][:26], p["side"], p["op_side"]))
        if len(wrong) > 10:
            log("      ... and %d more" % (len(wrong) - 10))

    # FILES THE OLD BUILD WROTE. Both records carry the platoon list, so when they disagree the
    # engine may read the one that still says false - and the player gets an autobattle while the
    # report said READY. Named here because, until this build, nothing could see it.
    faulty = [p for p in rows if p["tag"] == "FLAG FAULTY"]
    if faulty:
        log("")
        log("  *** %d platoon(s) are flagged in ONE record but not the other and WOULD STILL" % len(faulty))
        log("  *** AUTOBATTLE. Files written by an earlier build of this tool have this fault -")
        log("  *** press Make this platoon drivable again from the ORIGINAL operation to repair it:")
        for p in sorted(faulty, key=lambda q: (q["op"], q["platoon"]))[:10]:
            log("      %-26s %-24s desc=%-6s div_pool=%s"
                % (p["op"][:26], p["platoon"][:24], p["user_in"], p["user_in_div_pool"]))

    if work:
        log("")
        log("=" * 92)
        log("WHAT IS IN THE WAY - models with no cockpit, most wanted first")
        log("=" * 92)
        log("  %-18s %5s  %s" % ("model", "want", "operations"))
        for m in sorted(work, key=lambda k: (-len(work[k]), k)):
            ops = sorted(set(work[m]))
            log("  %-18s %5d  %s" % (m, len(work[m]),
                                     ", ".join(o[:26] for o in ops[:3])
                                     + (" ..." if len(ops) > 3 else "")))
        log("")
        ready = [m for m in work if m in KNOWN_TO_GTOS]
        fresh = [m for m in work if m not in KNOWN_TO_GTOS]
        log("  %d distinct models block %d platoons." % (len(work), sum(len(v) for v in work.values())))
        builtins = [m for m in ready if m in BUILT_IN_GTOS]
        presses = [m for m in ready if m not in BUILT_IN_GTOS]
        if presses:
            log("")
            log("  %d need ONE PRESS: %s" % (len(presses), ", ".join(sorted(presses))))
        if builtins:
            log("")
            log("  %d are BUILT INTO the tool - the button REFUSES them, and their settings live in its"
                % len(builtins))
            log("     code, so making them playable is a code change: %s" % ", ".join(sorted(builtins)))
        if ready:
            log("")
            log("  %d of them are ALREADY in SABoW Ext Control - but see the split below:" % len(ready))
            log("     press Make this one playable on each. The tool refuses with a reason, and "
                "never guesses, on any it cannot do.")
            log("     %s" % ", ".join(sorted(ready)))
        if fresh:
            log("")
            log("  %d need ADDING there first (Add an Operation Star vehicle), then make playable:"
                % len(fresh))
            log("     %s" % ", ".join(sorted(fresh)))
        log("")
        log("  Either way its platoons turn green here on the next report.")

    log("")
    log("  Tick Full detail, or read report_all_operations.txt, for every platoon in full.")
    log("  REPORT ONLY - nothing was written.")


def report_one(path, install, caps, squads, randoms, units, stypes, log):
    """Read one .campack2 and print its report. Writes nothing."""
    name = os.path.basename(path)
    d = gtos_opstar.directory(path)
    if ("desc", "config") not in d:
        log("  %s: no desc record - not an operation" % name)
        return 0, 0, 0
    t = azcf.Table(gtos_opstar.read(path, d[("desc", "config")]))
    names = [b.name for b in t.blocks]
    if not names or names[0] != "i_campgen:campgen":
        log("  %s: desc does not start with i_campgen:campgen - the game would ignore it" % name)
    user_side = None
    try:
        user_side = t.props(t.blocks[0]).get("user_side")
    except Exception:
        pass
    usname = side_name(user_side) if user_side is not None else "?"
    arrive = arrival_turns(t)
    plats = platoons_of(t)
    log("")
    log("=" * 78)
    log("%s   %d platoons   THE PLAYER IS %s" % (name, len(plats), usname))
    log("=" * 78)
    # BEFORE any platoon: a soldier type with no weapon kills the whole battle, whichever platoon
    # (or side, or AI) he belongs to. notes_128.
    _note = soldier_note(soldier_exposure(plats, squads, randoms, units, load_soldiers(install)))
    if _note:
        log("")
        log("  *** " + _note)
    drivable, blocked, no_tank, wrongside = 0, 0, 0, 0
    for pname, props, sq in plats:
        # which of this platoon's squads are actually a fighting vehicle?
        sqn = []
        for s in sq:
            sqn += expand_squads(s, squads, randoms)
        veh = [x for x in sqn if stypes.get(x) in VEHICLE_SQUAD_TYPES]
        if not veh:
            no_tank += 1          # infantry, guns, mortars, trucks - never a player tank
            continue
        vehicles = []
        for s in veh:
            for u in resolve(s, squads, randoms):
                r = units.get(u)
                if r is not None and r[1] == "i_techn":
                    vehicles.append((u, r[3], r[11], r[12]))
        if not vehicles:
            no_tank += 1
            continue
        side = side_name(props.get("side"))
        ai = "USER" if props.get("ai") == AI_USER else str(props.get("ai"))
        already = props.get("user_in") is True
        on_side = (user_side is not None and props.get("side") == user_side)
        # EACH ROW ON ITS OWN MERITS. ok/bad hold UNIT names, not models - a model name is not
        # what the platoon fields. See unit_verdict().
        must = sorted({v[1] for v in vehicles})
        ok, bad, badwhy = [], [], []
        for u, m, crw, ck in vehicles:
            good, ckname, why = unit_verdict(u, units)
            if good:
                if u not in ok:
                    ok.append(u)
            else:
                if u not in bad:
                    bad.append(u)
                    badwhy.append("%s - %s" % (u, why))
        model_ok = [m for m in must if m in caps]
        if not on_side:
            tag = "WRONG SIDE"
        elif bad and not ok and model_ok:
            tag = "AI-ONLY ROW"
        else:
            tag = "DRIVABLE" if (ok and not bad) else ("PARTLY" if ok else "NOT DRIVABLE")
        log("")
        log("  %-28s side=%-5s ai=%-6s user_in=%-5s   %s" % (pname, side, ai, already, tag))
        _ar = arrive.get(props.get("uid"))
        if _ar and _ar > 1:
            log("      *** LOCKED UNTIL TURN %d ***" % _ar)
            log("      The game locks a platoon until its arrival turn: it cannot be selected, moved")
            log("      or ordered, so it CANNOT be in a battle before turn %d. Flagging it does" % _ar)
            log("      nothing until you play that far - this is plat_pos, not a flag.")
        # THE VERDICT, in one sentence: will the tank we would spawn actually be in the battle?
        if tag == "DRIVABLE" and already:
            log("      THIS ONE FIGHTS. All four conditions in notes/103 are met.")
        elif tag == "DRIVABLE":
            log("      Can be made to fight: user_in is the only thing missing.")
        elif tag == "WRONG SIDE":
            log("      IT WOULD AUTOBATTLE - %s platoon, but the player is %s. user_in cannot fix"
                % (side, usname))
            log("      this. Pick a platoon on the %s side instead." % usname)
        elif tag == "PARTLY":
            log("      IT WOULD AUTOBATTLE - it mixes crewable with non-crewable models, which"
                " notes/103")
            log("      measured as 'Bad user desc!' even when the platoon is on the right side.")
        else:
            log("      IT WOULD AUTOBATTLE - no cockpit exists for any model in it yet.")
        log("      squads: %s" % ", ".join("%s [%s]" % (x, stypes.get(x, "?")) for x in veh))
        log("      THE ROWS IT FIELDS - this is the decision, not the model name:")
        for u, m, crw, ck in vehicles:
            good, ckname, why = unit_verdict(u, units)
            log("      %-24s %-14s crewable=%-6s cockpit=%-20s %s"
                % (u[:24], m[:14], crw, repr(ck)[:20], "OK" if good else "-> " + why))
        if tag == "AI-ONLY ROW":
            log("")
            log("      A cockpit for %s DOES exist elsewhere, which is why this used to be called"
                % ", ".join(model_ok))
            log("      DRIVABLE. But the row this platoon fields is AI-only, so the engine cannot")
            log("      crew it and the battle autobattles. THE FIX IS THE CAMPAIGN TABLE, exactly as")
            log("      notes_103 did for the T-34: make the row below crewable, give it its cockpit")
            log("      and its anims, then point the random pool at that row alone.")
            for u in bad:
                log("          %s" % u)
        for m in model_ok:
            if m in caps:
                log("      %-18s a cockpit for this model exists: %s (%s)"
                    % (m, caps[m][1], caps[m][0]))
            elif m in BUILT_IN_GTOS:
                log("      %-18s built into SABoW Ext Control - a CODE change there, not the button" % m)
            elif m in KNOWN_TO_GTOS:
                log("      %-18s no cockpit yet - press 'Make this one playable', then build" % m)
            else:
                log("      %-18s not in SABoW Ext Control yet - add it, then make it playable" % m)
        if tag == "DRIVABLE":
            drivable += 1
        elif tag == "WRONG SIDE":
            wrongside += 1
        elif tag == "NOT DRIVABLE":
            blocked += 1
    log("")
    log("  summary: %d drivable, %d not drivable, %d on the WRONG SIDE (the player is %s),"
        % (drivable, blocked, wrongside, usname))
    log("           %d platoons holding no fighting vehicle" % no_tank)
    return drivable, blocked, no_tank


def audit_oob(squads, randoms, units, log):
    """Every squad resolved to units; report names that resolve to nothing defined."""
    bad = []
    for s in sorted(squads):
        us = squads[s]
        if not us:
            continue
        for u in us:
            if u not in units and u.startswith(("rkkau_", "weru_")):
                bad.append((s, u))
    log("")
    log("=" * 78)
    log("OOB AUDIT - squads referencing a unit that is not defined")
    log("=" * 78)
    if not bad:
        log("  (none)")
    seen = set()
    for s, u in bad:
        if (s, u) in seen:
            continue
        seen.add((s, u))
        log("  %-28s -> %-24s NOT DEFINED" % (s, u))
    log("  %d dangling reference(s)" % len(bad))
    return bad




# ==================================================================== PHASE 2: WRITE

def _to_text(install, work, rec, blob):
    """record bytes -> cfgp2pd -> cfgfix -> repaired CRLF text."""
    cfg = os.path.join(work, rec + ".config")
    with open(cfg, "wb") as f:
        f.write(blob)
    raw = os.path.join(work, rec + ".cfgp2pd.engcfg2")
    if os.path.exists(raw):
        os.remove(raw)
    build.starter(install, "cfgp2pd,", build.rel(cfg, install) + ",", build.rel(raw, install),
                  expect=raw, timeout=900)
    fixed = os.path.join(work, rec + ".loc_def.engcfg2")
    r = subprocess.run([sys.executable, os.path.join(TOOL, "cfgfix.py"), cfg, raw, fixed],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(fixed):
        raise RuntimeError("cfgfix refused %s" % rec)
    with open(fixed, "rb") as f:
        return f.read()


def _record_name(blob):
    """The name a config record carries inside itself, at offset 0x20.

    MEASURED 2026-09-28 AND THIS IS THE 'Bad user desc!' BUG. pd2cfgp takes the compiled record's
    name from the OUTPUT FILE NAME, and the round trip here used to name that file after the PACK
    record - 'desc' and 'div_pool'. So every operation this tool wrote declared itself to be called
    'desc':
        stock  01_02_07_volokonovka_rus.campack2  desc header = 01_02_07_Volokonovka_RUS
        ours   01_02_07_volokonovka_rus_drive...  desc header = desc
    and the engine, handed a description whose name it cannot resolve, logs
    'WARNING [i_gamespec:gamespec] Bad user desc!' and falls back to the tacimage - a saved battle
    image that is not the battle the operation describes. Read the ORIGINAL record's own name out
    of its header and let the compiled file keep it."""
    return blob[0x20:0x60].split(b"\x00")[0].decode("latin1")


def _from_text(install, work, rec, text, inner):
    """edited text -> pd2cfgp -> record bytes. Output MUST be named <inner>.config, where inner is
    the ORIGINAL record's own name and NOT the pack record name: pd2cfgp writes the file name into
    the table header at 0x20, so naming it after the pack record RENAMES THE OPERATION.

    'inner' IS REQUIRED AND HAS NO DEFAULT, ON PURPOSE. It used to default to the pack record name,
    which is exactly how every operation this tool wrote came out named 'desc' - the engine could
    not resolve it, logged 'Bad user desc!', and played a tacimage instead of the operation. Two
    scripts in the scratch repo still called this with only four arguments, so the default was a
    loaded gun waiting for the next person. A caller that does not already know the operation's own
    name must read it out of the source record with _record_name(original_blob)."""
    if not inner:
        raise RuntimeError(
            "_from_text(%s) was given no record name. pd2cfgp writes the OUTPUT FILE NAME into the "
            "record header at 0x20, so compiling as the pack record RENAMES THE OPERATION to '%s' - "
            "the engine then logs 'Bad user desc!' and plays a tacimage that is not this battle "
            "(notes_127). Pass inner=_record_name(original_blob)." % (rec, rec))
    src = os.path.join(work, rec + ".edited.engcfg2")
    with open(src, "wb") as f:
        f.write(text)
    out = os.path.join(work, "out_" + rec, inner + ".config")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build.starter(install, "pd2cfgp,", build.rel(src, install) + ",", build.rel(out, install),
                  expect=out, timeout=900)
    with open(out, "rb") as f:
        return f.read()


def edit_user_in(text, platoon, log=None):
    """Set user_in = true on one platoon inside a config text. CRLF preserved throughout -
    pd2cfgp given LF emits an empty table and reports nothing at all.

    INDENTATION IS LOAD-BEARING AND GETTING IT WRONG IS SILENT. The existing row in the desc
    record is indented with TWO tabs:

            user_in[b]      = false;

    while div_pool's block for the same platoon carries no user_in row at all. The match used to
    require exactly ONE leading tab, so it MISSED the row in desc, inserted a second one at the top
    of the block, and left the original 'false' at the BOTTOM - where the parser takes the last
    value. The write therefore LOOKED successful in div_pool and did nothing at all in desc, which
    is the record whose own header declares who the player is. That is the standing candidate for
    the Shilovo autobattle, and it is why make_drivable now verifies what it wrote."""
    lines = text.split(b"\r\n")
    name = platoon.encode()
    starts = [i for i, l in enumerate(lines) if l.strip() in (name + b"=()", name + b"[s]()")]
    if len(starts) != 1:
        raise RuntimeError("platoon %s appears %d times as a props block" % (platoon, len(starts)))
    s = starts[0]
    ends = [i for i in range(s, len(lines)) if lines[i].strip() == b"} //endof " + name]
    if not ends:
        raise RuntimeError("no } //endof %s after its block start" % platoon)
    e = ends[0]
    # ANY INDENTATION. strip() first, so the TWO-tab row in desc is found as readily as a
    # one-tab row would be. This single line is the fix for the silent no-op described above.
    hits = [i for i in range(s, e) if lines[i].strip().startswith(b"user_in[")]
    if len(hits) > 1:
        raise RuntimeError("%s has %d user_in rows - refusing to guess which one wins"
                           % (platoon, len(hits)))
    if hits:
        # Keep the indentation the file already uses, so the block's shape does not change.
        old = lines[hits[0]]
        indent = old[:len(old) - len(old.lstrip())]
        lines[hits[0]] = indent + b"user_in[b]\t= true;"
        if log:
            log("      %s: user_in was present at line %d (%d leading tab(s)) - set to true"
                % (platoon, hits[0], indent.count(b"\t")))
    else:
        if lines[s + 1].strip() != b"{":
            raise RuntimeError("%s: expected { after the block name" % platoon)
        # Copy the indentation of the first real property line so the new row matches its
        # neighbours instead of being the odd one out.
        indent = b"\t\t"
        for j in range(s + 2, e):
            if lines[j].strip():
                j0 = lines[j]
                indent = j0[:len(j0) - len(j0.lstrip())]
                break
        lines.insert(s + 2, indent + b"user_in[b]\t= true;")
        if log:
            log("      %s: user_in added (no user_in row existed in this record)" % platoon)
    return b"\r\n".join(lines)


def pick_playable(rows, log=None):
    """THE PLATOON TO FLAG, chosen for you - the earliest-arriving crewable one on the player's side.

    WHY THIS IS A FUNCTION AND NOT ADVICE. The tool used to offer every DRIVABLE platoon as if they
    were equal, and the ONE property that decides whether the player ever gets a tank was invisible:
    the ARRIVAL TURN. A platoon the game has locked cannot be selected, moved or ordered, so it
    cannot be in a battle, so flagging it does nothing at all - while its row is perfectly crewable
    and the report says DRIVABLE. Choosing by hand cost three evenings on Shilovo, because the only
    platoon anybody thought to flag there arrives on turn 8.

    Ranked by arrival turn first - the player gets a tank soonest - then already-flagged, then name,
    so the same operation always yields the same answer.
    """
    cands = [p for p in rows if p.get("tag") == "DRIVABLE" and p.get("on_side")]
    if not cands:
        return None

    def turn(p):
        # AN UNREADABLE TURN IS THE WORST CASE, NOT THE BEST. Ranking it as turn 1 would put a
        # platoon we cannot vouch for at the top of the list - which is the exact shape of every
        # fault in this file: a plausible answer to a question nobody asked. 999 sorts it last.
        a = p.get("arrival")
        return a if isinstance(a, int) and a > 0 else 999

    ranked = sorted(cands, key=lambda p: (turn(p), 0 if p.get("user_in") else 1,
                                          p.get("op", ""), p.get("platoon", "")))
    best = ranked[0]
    if log:
        log("")
        log("PICKED FOR YOU: %s" % best["platoon"])
        log("  on the player's side and every row it fields is crewable.")
        if turn(best) == 999:
            log("  ITS ARRIVAL TURN COULD NOT BE READ from the operation's plat_pos, so nothing")
            log("  here can promise when it is on the map - check it before you trust this.")
        else:
            log("  It arrives on TURN %d - the earliest of the %d platoon(s) that qualify. That is"
                % (turn(best), len(cands)))
            log("  the whole reason: a platoon the game has locked cannot be ordered, so it cannot")
            log("  be in a battle, so flagging it does nothing until that turn arrives.")
        for p in ranked[1:4]:
            t = turn(p)
            log("  also possible: %-24s arrives %s" % (p["platoon"],
                                                       "turn %d" % t if t != 999 else "on an unreadable turn"))
    return best


def make_playable(campack2, out_path, install, log=print):
    """THE WHOLE JOB, ONE CALL: pick the best platoon, flag it, write a NEW operation, read the
    file back, and say in plain words when the player will actually get a tank.

    This exists so that none of the four things that have to be true at once has to be remembered:

        1. the platoon is on the operation's user_side          (notes/103)
        2. ai = USER on that platoon                            (notes/103)
        3. every units[] ROW it can draw is crewable and its cockpit EXISTS
        4. it is ON THE MAP when you play - the arrival turn in plat_pos

    Three of those the tool checked; the fourth is the one that cost the most time, because a
    locked platoon produces no error, no warning and no log line - just an autobattle.
    """
    caps = load_caps(install)
    squads, randoms, units, stypes = load_oob(install)
    base = os.path.basename(campack2)
    log("")
    log("=" * 78)
    log("MAKE %s PLAYABLE - all of it, automatically" % base)
    log("=" * 78)
    name, plats, no_tank, notes, uside = scan_one(campack2, caps, squads, randoms, units, stypes)
    log("  %d vehicle platoon(s); the player is %s; %d more hold no vehicle at all"
        % (len(plats), uside, no_tank))
    for n in notes:
        log("  note: %s" % n)
    if os.path.abspath(campack2) == os.path.abspath(out_path):
        raise RuntimeError("the output must not be the input - this writes a NEW operation")

    best = pick_playable(plats, log)
    if best is None:
        log("")
        log("NOTHING IN THIS OPERATION CAN TAKE A PLAYER TANK - nothing was written. The platoons")
        log("on the player's side, and what stops each one:")
        shown = 0
        for p in plats:
            if not p.get("on_side"):
                continue
            log("    %-24s %-13s %s" % (p["platoon"], p["tag"], "; ".join(p["blockers"])[:100]))
            shown += 1
        if not shown:
            log("    (there is no vehicle platoon on the player's side at all)")
        raise RuntimeError("no platoon in %s can be crewed" % base)

    make_drivable(campack2, best["platoon"], out_path, install, log=log)

    # READ THE FILE BACK and ask the same four questions of it. A write that reports success is not
    # a write that worked; that is how a stale user_in survived a whole evening.
    _, back, _, _, _ = scan_one(out_path, caps, squads, randoms, units, stypes)
    flagged = [p for p in back if p["user_in"] and p["user_in_div_pool"]]
    live = [p for p in back if p["live"]]
    names = [p["platoon"] for p in flagged]
    # THE CHOSEN PLATOON MUST BE FLAGGED AND READY. NOT 'the only one' - an operation may already
    # flag others, and Sokolovo flags THREE (rkkapl_179_otbr1/2/3); that is the operation working as
    # designed, not a fault. This writes an ADDITIONAL flag; it does not sweep.
    if best["platoon"] not in names:
        raise RuntimeError("the written operation does not carry user_in on %s - it carries %s."
                           " Do not ship it." % (best["platoon"], names))
    if best["platoon"] not in [p["platoon"] for p in live]:
        raise RuntimeError("%s is not READY in the written operation - do not ship it"
                           % best["platoon"])
    if len(names) > 1:
        log("  note: this operation already flags %d platoons (%s). That is fine - this added one"
            % (len(names), ", ".join(names)))
    me = [p for p in live if p["platoon"] == best["platoon"]][0]
    ar = me.get("arrival")
    log("")
    log("=" * 78)
    log("DONE - %s is READY in %s" % (best["platoon"], os.path.basename(out_path)))
    log("=" * 78)
    if ar and ar > 1:
        log("  THE PLAYER GETS A TANK FROM TURN %d." % ar)
        log("  The game locks a platoon until its arrival turn: before that it cannot be selected,")
        log("  moved or ordered, so no battle can include it and every fight autobattles. This is")
        log("  the operation's own plat_pos, not a flag.")
    else:
        log("  The player gets a tank from TURN 1.")
    log("  START A NEW OPERATION, not Continue - a save keeps the platoon table it was made with.")
    return out_path


def make_drivable(campack2, platoon, out_path, install, log=print):
    """Set user_in on one platoon and write a NEW operation. Never edits in place.

    The flag goes into BOTH records that carry the platoon list - desc and div_pool - because
    which one the engine reads at runtime is unmeasured (SPEC V1); setting both removes the
    question rather than answering it."""
    # REFUSE A PLATOON THE PLAYER IS NOT ON. user_in there is not a partial fix, it is the exact
    # recipe for autobattle (notes/103), and the report used to offer those platoons because
    # nothing compared the platoon's side with the operation's user_side. Checked HERE as well as
    # in the report, because this is the function that writes - and it checks that the platoon
    # EXISTS while it is at it, so a typo fails here rather than deep inside edit_user_in.
    d0 = gtos_opstar.directory(campack2)
    if ("desc", "config") not in d0:
        raise RuntimeError("%s has no desc record - not an operation" % campack2)
    t0 = azcf.Table(gtos_opstar.read(campack2, d0[("desc", "config")]))
    try:
        op_side = t0.props(t0.blocks[0]).get("user_side")
    except Exception:
        op_side = None
    pside, psq, puid = None, [], None
    for pname, props, sq in platoons_of(t0):
        if pname == platoon:
            pside = props.get("side")
            psq = sq
            puid = props.get("uid")
            break
    if pside is None:
        raise RuntimeError("%s is not a platoon of %s - nothing was written"
                           % (platoon, os.path.basename(campack2)))
    if op_side is None:
        raise RuntimeError("%s declares no user_side in its header, so there is no way to tell "
                           "whether %s is the player's platoon - refusing rather than guessing"
                           % (os.path.basename(campack2), platoon))
    if pside != op_side:
        raise RuntimeError(
            "%s is a %s platoon and the player is %s. user_in on it would AUTOBATTLE, not put the "
            "player in a tank (notes/103). Pick a platoon on the %s side. Nothing was written."
            % (platoon, side_name(pside), side_name(op_side), side_name(op_side)))

    # AND IT MUST FIELD A TANK THE PLAYER CAN ACTUALLY CREW. user_in on a platoon whose own unit
    # rows are AI-only changes nothing: the engine cannot put the player in it, and the battle
    # autobattles. THIS IS THE CHECK THAT WAS MISSING, and its absence is what let this tool
    # report READY and 'all four conditions met' on the Shilovo operation for three evenings.
    # The report used to answer 'is the MODEL drivable?' while the platoon fields a ROW that is
    # not - two different questions, and only the second one is the player's.
    squads_, randoms_, units_, stypes_ = load_oob(install)
    EXISTING_COCKPITS.clear()
    EXISTING_COCKPITS.update(load_cockpits(install))
    sqn = []
    for s in psq:
        sqn += expand_squads(s, squads_, randoms_)
    usable, unusable = [], []
    for s in sqn:
        if stypes_.get(s) not in VEHICLE_SQUAD_TYPES:
            continue
        for u in resolve(s, squads_, randoms_):
            r2 = units_.get(u)
            if r2 is None or r2[1] != "i_techn":
                continue
            g, ck, why = unit_verdict(u, units_)
            (usable if g else unusable).append((u, why))
    if not usable:
        raise RuntimeError(
            "%s fields no vehicle the player can crew, so user_in on it would AUTOBATTLE rather "
            "than put you in a tank. The rows it fields:\n%s\n"
            "Fix the CAMPAIGN table the way notes_103 did for the T-34 - make the row crewable, "
            "give it its cockpit and anims, and point its random pool at that row alone. "
            "Nothing was written."
            % (platoon, chr(10).join("    %-24s %s" % (u, w) for u, w in unusable)))

    # AND IT MUST BE ON THE MAP WHEN YOU PLAY. A platoon the game locks until its arrival turn
    # cannot be given an order before then, so no battle can include it and the write changes
    # nothing for however many turns you are short. Measured on Shilovo: the flagged platoon
    # arrived on turn 8, every test was played on turn 1, and three evenings went into a flag that
    # was already correct. This is a warning, not a refusal - flagging a turn-3 platoon is a real
    # thing to want - but it is impossible to miss.
    _ar = arrival_turns(t0).get(puid)
    if _ar and _ar > 1:
        log("")
        log("  " + "*" * 74)
        log("  ***  %s ARRIVES ON TURN %d - THE GAME LOCKS IT UNTIL THEN  ***" % (platoon, _ar))
        log("  " + "*" * 74)
        log("  A locked platoon cannot be selected, moved or ordered, so it cannot be in a battle")
        log("  before turn %d and THIS FLAG DOES NOTHING until you play that far. That is not a" % _ar)
        log("  guess: it is the operation's own plat_pos, and it was proved 121 for 121 against a")
        log("  save the engine wrote. Carry on if that is what you want.")
        log("")

    work = os.path.join(os.path.dirname(out_path), "_drivefix")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    d = gtos_opstar.directory(campack2)
    recs = {}
    for rec in ("desc", "div_pool", "op_image", "scripts", "text"):
        if (rec, "config") in d or (rec, "image") in d or (rec, "script") in d or (rec, "text") in d:
            for k in d:
                if k[0] == rec:
                    recs[rec] = (d[k][3], d[k][4], gtos_opstar.read(campack2, d[k]))
                    break
    if not recs:
        raise RuntimeError("%s holds no operation records" % campack2)
    log("  read %d records from %s" % (len(recs), os.path.basename(campack2)))

    out_records = []
    for rec, (kind, loc, blob) in recs.items():
        if rec in ("desc", "div_pool"):
            log("  %s: decompiling" % rec)
            text = _to_text(install, work, rec, blob)
            text2 = edit_user_in(text, platoon, log)
            blob2 = _from_text(install, work, rec, text2, _record_name(blob))
            if len(blob2) < 64:
                raise RuntimeError("%s compiled to %d bytes - the edit broke it" % (rec, len(blob2)))
            log("      %s: %d -> %d bytes" % (rec, len(blob), len(blob2)))
            blob = blob2
        out_records.append((rec, kind, loc, blob))

    # VERIFY, DO NOT ASSUME. Each record is PARSED BACK the same way the report parses an
    # operation, and the platoon's user_in must read true. The engine reads one of desc and
    # div_pool and we do not know which (SPEC V1), so BOTH are checked: a record that merely looks
    # edited is not enough. Before this check existed, desc ended up holding two user_in rows with
    # the real one last and false, the write silently did nothing there, and the tool reported
    # success - which is exactly the shape of 'the flag is set but the battle still autobattled'.
    for rec, kind, loc, blob in out_records:
        if rec not in ("desc", "div_pool"):
            continue
        try:
            tv = azcf.Table(blob)
        except Exception as ex:
            raise RuntimeError("%s did not parse back after the edit (%s) - nothing was written"
                               % (rec, ex))
        got = None
        for b in tv.blocks:
            if b.name == platoon:
                got = tv.props(b).get("user_in")
                break
        if got is None:
            raise RuntimeError("%s: %s is not in the recompiled record - nothing was written"
                               % (rec, platoon))
        if got is not True:
            raise RuntimeError(
                "%s: %s reads user_in = %r after the write, not true. This record would not put "
                "the player in the battle (notes/103) - nothing was written."
                % (rec, platoon, got))
        log("      %s: VERIFIED - %s reads user_in = true" % (rec, platoon))

    # AND THE OPERATION'S OWN NAME MUST SURVIVE THE ROUND TRIP. pd2cfgp takes it from the output
    # file name, so a record compiled as <pack record>.config silently RENAMES the operation - and
    # an operation whose name the engine cannot resolve is what logs 'Bad user desc!' and sends it
    # to the tacimage instead (measured 2026-09-28). A build that renamed the operation used to
    # report success and produce a file that plays a different battle.
    for rec, kind, loc, blob in out_records:
        if rec not in ("desc", "div_pool"):
            continue
        want = _record_name(recs[rec][2])
        got = _record_name(blob)
        if got != want:
            raise RuntimeError(
                "%s: the record now calls the operation %r, not %r - the engine would log "
                "'Bad user desc!' and fall back to a tacimage that is not this battle. "
                "Nothing was written." % (rec, got, want))
        if got in ("desc", "div_pool") or not got:
            raise RuntimeError(
                "%s: the record calls the operation %r - that is the PACK RECORD'S OWN NAME, or "
                "nothing at all, not an operation name. The SOURCE operation is already misnamed, "
                "so preserving it would preserve the fault the check exists to catch (notes_127). "
                "Nothing was written." % (rec, got))
        log("      %s: VERIFIED - the operation is still called %s" % (rec, want))

    log("  packing %s" % out_path)
    gtos_opstar._mkflat(out_records, out_path, install, os.path.join(work, "mkflat"), log)
    return out_path


def main():
    import tkinter as tk
    from tkinter import ttk, filedialog
    install = settings.get("sandbox")
    caps = load_caps(install)
    squads, randoms, units, stypes = load_oob(install)

    root = tk.Tk()
    root.title("SABoW player tank tool")
    root.geometry("1080x720")
    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Operation (.campack2), or a folder of them:").pack(side="left")
    ent = ttk.Entry(top, width=78)
    ent.pack(side="left", padx=6, fill="x", expand=True)
    # PRE-FILLED, because an empty box used to answer "no .campack2 found at ''" - which reads
    # like the tool cannot find operations at all. It ships able to find every one of them.
    ent.insert(0, os.path.join(install, "data"))

    out = tk.Text(root, wrap="none", font=("Consolas", 9))
    out.pack(fill="both", expand=True, padx=8, pady=6)

    def log(m):
        out.insert("end", str(m) + "\n")
        out.see("end")
        out.update()

    def pick_file():
        f = filedialog.askopenfilename(filetypes=[("operations", "*.campack2"), ("all", "*.*")])
        if f:
            ent.delete(0, "end")
            ent.insert(0, os.path.normpath(f))

    def pick_dir():
        d = filedialog.askdirectory()
        if d:
            ent.delete(0, "end")
            ent.insert(0, os.path.normpath(d))

    # filled by the report below: label -> (operation file, platoon). Nothing here writes.
    pchoice = {}

    def go():
        out.delete("1.0", "end")
        target = ent.get().strip()
        log("install : %s" % install)
        log("drivable vehicle models known (%d): %s" % (len(caps), ", ".join(sorted(caps))))
        log("oob     : %d squads, %d randoms, %d units" % (len(squads), len(randoms), len(units)))
        log("vehicle squad types: %s" % ", ".join(sorted(VEHICLE_SQUAD_TYPES)))
        detailed = full.get()
        files, looked = [], []
        if not target:
            # NOTHING TYPED = every operation on the install. This is what almost every run wants,
            # and it is the difference between a tool that finds your operations and one that looks
            # like it cannot see them.
            log("no path given - reporting every operation on this install")
            for sub in ("data", "users"):
                p = os.path.join(install, sub)
                if os.path.isdir(p):
                    looked.append(p)
                    files += glob.glob(os.path.join(p, "**", "*.campack2"), recursive=True)
        elif os.path.isdir(target):
            looked = [target]
            files = glob.glob(os.path.join(target, "**", "*.campack2"), recursive=True)
        elif os.path.isfile(target):
            files = [target]
        else:
            looked = [target]
        files = sorted(set(os.path.normpath(f) for f in files))
        if not files:
            log("no .campack2 found. Looked in:")
            for p in looked or [repr(target)]:
                log("   %s%s" % (p, "" if os.path.isdir(p) else "   (does not exist)"))
            log("")
            log("Pick an operation with Operation file..., a folder with Folder..., or leave the box")
            log("empty to report every operation on the install.")
            return
        log("found %d operation(s)" % len(files))
        if detailed:
            tot = [0, 0, 0]
            for f in files:
                try:
                    a, b, c = report_one(f, install, caps, squads, randoms, units, stypes, log)
                    tot[0] += a; tot[1] += b; tot[2] += c
                except Exception as e:
                    log("  %s: FAILED - %s" % (os.path.basename(f), e))
            log("")
            log("TOTAL across %d operation(s): %d drivable, %d not drivable"
                % (len(files), tot[0], tot[1]))
            audit_oob(squads, randoms, units, log)
            log("")
            log("REPORT ONLY - nothing was written.")
            return
        rows, summaries, work = [], [], {}
        for f in files:
            try:
                name, plats, no_tank, notes, op_side = scan_one(f, caps, squads, randoms, units, stypes)
            except Exception as e:
                log("  %s: FAILED - %s" % (os.path.basename(f), e))
                continue
            for p in plats:
                p["op"] = name
                p["path"] = f
                rows.append(p)
                for m in p["bad"]:
                    work.setdefault(m, []).append(name)
            dr = len([p for p in plats if p["tag"] == "DRIVABLE"])
            pa = len([p for p in plats if p["tag"] == "PARTLY"])
            bl = len([p for p in plats if p["tag"] == "NOT DRIVABLE"])
            ws = len([p for p in plats if p["tag"] == "WRONG SIDE"])
            ff = len([p for p in plats if p["tag"] == "FLAG FAULTY"])
            ao = len([p for p in plats if p["tag"] == "AI-ONLY ROW"])
            summaries.append((name, dr, pa, bl, no_tank, ws, ff, ao, "; ".join(notes)))
        summaries.sort(key=lambda s: (-(s[1] + s[2]), s[0]))
        render_layers(rows, summaries, work, caps, log)
        audit_oob(squads, randoms, units, log)

        # FILL THE PLATOON BOX from what this report just found, so nobody has to copy a
        # name out of a wall of text. Only platoons that can hold a player tank, and
        # choosing one also fills in which operation it lives in.
        # ONLY DRIVABLE. A PARTLY platoon holds a mix - some models have a cockpit, some do
        # not - and notes/103 measured what that does to the PLAYER's own platoon:
        #   'a user platoon that mixed crewable and non-crewable tanks' logged
        #   'WARNING [i_gamespec:gamespec] Bad user desc!' and the engine, having nowhere to
        #   put the player, fell back to Autobattle.
        # Which is exactly what happened on 2026-09-27 when wer_24tr_1lc_1p (pz3jlg + pz3jkz)
        # was given user_in: the battle played all seven turns with no player in it.
        takeable = [p for p in rows if p["tag"] == "DRIVABLE"]
        pchoice.clear()
        for p in sorted(takeable, key=lambda q: (q["op"], q["platoon"])):
            # the turn is in the label, because a platoon that arrives on turn 8 is not usable
            # on turn 1 and choosing it wastes an evening - see arrival_turns()
            _ar = p.get("arrival")
            label = "%-28s %-22s %-5s %-8s %s" % (p["op"][:28], p["platoon"], p["side"],
                                                  ("turn %d" % _ar) if _ar else "-",
                                                  ",".join(p["ok"]))
            pchoice[label] = (p["path"], p["platoon"])
        pent["values"] = list(pchoice)
        log("")
        log("%d platoon(s) can hold a player - DRIVABLE only, never PARTLY - pick one above."
            % len(pchoice))
        # AND THE BOX ALREADY HOLDS THE RIGHT ONE. Leaving that choice to the reader is what let a
        # platoon locked until turn 8 be selected three times in a row: it was DRIVABLE, it was at
        # the top of the list, and nothing on screen said it could not be ordered.
        _best = pick_playable(rows, None)
        if _best:
            for _label, _v in sorted(pchoice.items()):
                if _v[1] == _best["platoon"]:
                    pent.set(_label)
                    chose()
                    log("The box is already set to %s - the earliest-arriving one, so press the"
                        % _best["platoon"])
                    log("button and it is done. To choose a different one, pick it from the list.")
                    break

    bar = ttk.Frame(root, padding=(8, 0))
    bar.pack(fill="x")
    ttk.Button(bar, text="Operation file...", command=pick_file).pack(side="left")
    ttk.Button(bar, text="Folder...", command=pick_dir).pack(side="left", padx=4)
    ttk.Button(bar, text="Report", command=go).pack(side="left", padx=4)
    full = tk.BooleanVar(value=False)
    ttk.Checkbutton(bar, text="Full detail", variable=full).pack(side="left", padx=10)
    ttk.Button(bar, text="Clear", command=lambda: out.delete("1.0", "end")).pack(side="left", padx=4)

    # ---- PHASE 2. The function below this window has existed since the player-tank work and was
    # reachable from NOTHING - no button, no command. That made "make a platoon drivable" something
    # only a command line could do, in a tool whose whole point is that a person runs it.
    bar2 = ttk.Frame(root, padding=(8, 4))
    bar2.pack(fill="x")
    ttk.Label(bar2, text="Make drivable - platoon:").pack(side="left")
    pent = ttk.Combobox(bar2, width=62, state="readonly")

    def chose(_e=None):
        """Picking a platoon also says which operation it is in."""
        v = pchoice.get(pent.get())
        if v:
            ent.delete(0, "end")
            ent.insert(0, os.path.normpath(v[0]))

    pent.bind("<<ComboboxSelected>>", chose)
    pent.pack(side="left", padx=6)

    def make_it():
        from tkinter import messagebox
        src = ent.get().strip()
        platoon = (pchoice.get(pent.get()) or (None, None))[1]
        if not platoon:
            log("")
            log("Pick a platoon from the list. Press Report first - the list is filled from"
                " what it finds, and every one of them can hold a player tank.")
            return
        if not os.path.isfile(src):
            log("")
            log("PHASE 2 needs ONE operation file, not a folder. Use Operation file... first, and")
            log("copy a platoon name out of the TAKE ONE OF THESE list above.")
            return
        if not platoon:
            log("")
            log("PHASE 2 needs a platoon name. Press Report, then copy one out of")
            log("TAKE ONE OF THESE - the names look like rkkapl_179_otbr1 or wer_24tr_1lc_1p.")
            return
        base = os.path.basename(src)
        stem = base[:-len(".campack2")] if base.lower().endswith(".campack2") else base
        dst = filedialog.asksaveasfilename(
            title="Write a NEW operation as...",
            defaultextension=".campack2",
            initialfile=stem + "_drive.campack2",
            initialdir=os.path.dirname(src),
            filetypes=[("operations", "*.campack2")])
        if not dst:
            log("")
            log("PHASE 2 cancelled - nothing written.")
            return
        if os.path.normpath(dst).lower() == os.path.normpath(src).lower():
            log("")
            log("PHASE 2 REFUSED - the output must not be the input.")
            log("This writes a NEW operation and never edits one in place, so that the operation")
            log("you started from is still there whatever happens next.")
            return
        ask = ("Write a new operation" + chr(10) + chr(10) + "  " + dst + chr(10) + chr(10) +
               "with " + platoon + " drivable?" + chr(10) + chr(10) +
               "The operation you started from is not touched.")
        if not messagebox.askyesno("Write a new operation?", ask):
            log("")
            log("PHASE 2 cancelled - nothing written.")
            return
        log("")
        log("PHASE 2 - writing a new operation. The original is not touched.")
        try:
            make_drivable(src, platoon, dst, install, log=log)
        except Exception as e:
            log("PHASE 2 FAILED: %s" % e)
            log("Nothing was written to the operation you started from.")
            return
        log("")
        log("PHASE 2 DONE - wrote %s" % dst)
        log("")
        log("TO SHIP IT - the real route, and the one that survives a reinstall:")
        log("  every map add-on carries its own operation file, so the edited .campack2 goes")
        log("  back INTO the map pack and the pack is installed with the updater. Writing it")
        log("  straight into the installed game folder works for a quick look and is wiped the")
        log("  next time that map pack is installed over it.")
        log("")
        log("TO JUST TRY IT NOW: drop it in the operation camps folder and start the game.")
        log("If two operations then show the same name, HIDE the original - the display name")
        log("lives inside the file, so renaming the file does not change what the game lists.")

    ttk.Button(bar2, text="Make this platoon drivable...", command=make_it).pack(side="left", padx=4)
    ttk.Label(bar2, text="writes a NEW operation; never edits one in place",
              foreground="#666").pack(side="left", padx=8)

    # ---- THE WHOLE JOB, ONE BUTTON. Chooses the platoon, flags it, writes the operation, reads the
    # file back, and says in plain words WHEN the player gets a tank. Same four conditions the
    # sections above explain one at a time - so that none of them has to be remembered, and the
    # arrival turn in particular, which no error and no log line ever mentions.
    bar3 = ttk.Frame(root, padding=(8, 4))
    bar3.pack(fill="x")
    ttk.Label(bar3, text="Automatic:").pack(side="left")

    def auto_it():
        from tkinter import messagebox
        src = ent.get().strip()
        if not os.path.isfile(src):
            log("")
            log("AUTOMATIC needs ONE operation file, not a folder. Use Operation file... first.")
            return
        base = os.path.basename(src)
        stem = base[:-len(".campack2")] if base.lower().endswith(".campack2") else base
        dst = filedialog.asksaveasfilename(
            title="Write the playable operation as...",
            defaultextension=".campack2",
            initialfile=stem + "_playable.campack2",
            initialdir=os.path.dirname(src),
            filetypes=[("operations", "*.campack2")])
        if not dst:
            log("")
            log("Cancelled - nothing written.")
            return
        if os.path.normpath(dst).lower() == os.path.normpath(src).lower():
            log("")
            log("REFUSED - the output must not be the input. This never edits an operation in place.")
            return
        log("")
        log("Writing a NEW operation. The one you started from is not touched.")
        try:
            make_playable(src, dst, install, log=log)
        except Exception as e:
            log("")
            log("STOPPED: %s" % e)
            log("Nothing was written to the operation you started from.")
            return
        log("")
        log("TO TRY IT: copy the new file into the operation's camps folder and start a NEW")
        log("operation in the game - not Continue. If two operations then show the same name, hide")
        log("the original; the name the game lists lives INSIDE the file, so renaming it does"
            " nothing.")

    ttk.Button(bar3, text="Do it all automatically", command=auto_it).pack(side="left", padx=4)
    ttk.Label(bar3, text="chooses the platoon, flags it, writes it, reads it back, and tells you"
                         " which turn you get a tank",
              foreground="#666").pack(side="left", padx=8)



    log("PHASE 1 reports and writes nothing. PHASE 2 writes a NEW operation.")
    log("")
    log("Pick an operation .campack2 (or a folder of them) and press Report.")
    log("For each platoon holding a vehicle it says DRIVABLE if a proven cockpit exists for that")
    log("model, and NOT DRIVABLE with the reason if none does. It also lists any squad in the")
    log("oob that references a unit which is not defined - that was the Sokolovo crash.")
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _startup_error('SABoW Player Tank Tool', "SABoW Player Tank Tool hit an error while starting.")
