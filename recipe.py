# recipe - work out, from the game's own tables, everything needed to make one
# AI-only vehicle playable. READ-ONLY. Part of the SABoW Ext tool.
#
# Every answer here used to be typed into build.py by hand for the T-55. Each rule
# is the one a failed build taught (BUILD_LOG.md, PLAN.md "the recipe"):
#
#   donor        the closest already-playable vehicle; its cockpit is copied
#   cockpit      the vehicle's OWN cockpit, coc_<vehicle model>             (v3)
#   weapons      each cockpit weapon swapped for the vehicle's own of the
#                same class                                                (v3)
#   shells       each cockpit shell swapped for the vehicle's own of the same
#                type - from the rounds its ammo table LOADS, not lists     (v4)
#   crew         crew sync rows to mode 0 where the vehicle's model has that
#                point, so the crew use the AI's positions             (v6-v9)
#   hide         every drawable chunk of the donor cockpit's models        (v8)
#   platoons     quick-battle platoons fielding it whose crew flag is off  (v2)
#
# Two of those are CHOICES for murkz, not facts: which platoons to open, and which
# crewmen to move. derive() offers every candidate and ticks the safe default;
# `choices` overrides the ticks.

import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402
import crewpoints  # noqa: E402

CREWABLE, COCKPIT, ANIMS = 11, 12, 13
SQUAD_UNIT = 10

# donor pairings proven to fail in game - the similarity score cannot know these
KNOWN_BAD_DONORS = {
    ("saru_olifant", "iru_m60a1"): "BoW43: coc_m60a1 on the Olifant crashed (001) at battle start - it "
                                   "declares a rangefinder and fire control the Olifant lacks (notes/15)",
}

# shell types that can stand in for each other when the exact type is not loaded
SHELL_GROUPS = [{"AP", "APCR", "SH"}, {"HEAT", "HEAM"}, {"HE", "HEPT"}]


def fourcc(u):
    return struct.pack("<I", u).rstrip(b"\0").decode("latin1")


class Plan(object):
    """Everything build.py needs for one vehicle, plus why."""

    def __init__(self):
        self.unit = self.vehicle = self.donor_unit = self.donor_vehicle = None
        self.donor_cockpit = self.cockpit = self.anims = self.model = None
        self.station_edits = {}     # station -> {key: new value}
        self.crew_candidates = []   # [(chunk, has_real_point, position or None)]
        self.sync_modes = {}        # chunk -> 0, the ticked crew rows
        self.sync_retarget = {}     # chunk -> the VEHICLE chunk it should follow, when the vehicle has
                                    # no chunk of the same name (v22: a T-34 has no s_commander)
        self.sync_add = {}          # chunk -> target, rows the DONOR cockpit has not got at all
                                    # (v23: coc_t62 has no s_gunner_out, a T-62 gunner having no hatch)
        self.plc_add = []           # whole plc_states rows to append, as text (v28: the gunner has no
                                    # turned-out STATE in either stock cockpit - flag 0x1000)
        self.hide_models = []       # donor cockpit models, in mesh-index order
        self.hide_missing = []      # donor hide chunks on the vehicle's own model (-1) that model lacks
        self.hide_drop = []         # ... and the ones this build removes (the cockpit-ceiling fix)
        self.platoon_candidates = []  # [(block, text id, state)]
        self.platoons = []          # ticked platoon blocks
        self.platoon_state = {}     # ticked block -> "off" (flag to switch) or "no flag" (flag to add)
        self.platoon_labels = {}    # block -> "Side  -  battalion  -  platoon", the game's own words
        self.sight_heads = []       # [(row index in the vehicle's sights block, head)] to set
        self.techn_record = None    # the vehicle table those rows live in
        self.own_sight = None       # ownsight.OWN_SIGHTS entry: the vehicle's own gunner sight
        self.ammo_text = False      # ship the renamed ammunition text (ammotext.py)
        self.steps = []             # [(step, answer, reason)]
        self.warnings = []

    def step(self, name, answer, why):
        self.steps.append((name, answer, why))

    def report(self):
        out = ["Recipe for %s (%s)" % (self.unit, self.vehicle)]
        for name, answer, why in self.steps:
            out.append("  %-10s %s" % (name, answer))
            out.append("  %-10s   because %s" % ("", why))
        for w in self.warnings:
            out.append("  WARNING  " + w)
        return "\n".join(out)


class Game(object):
    """The install's tables, read once."""

    def __init__(self, install):
        self.install = install
        self.tabs = os.path.join(install, "data", "mtc80", "shared", "packed_data", "tabs.flatdata")
        self._t = {}
        self._mesh = {}

    def table(self, name):
        if name not in self._t:
            self._t[name] = azcf.Table(azcf.read_record(self.tabs, name))
        return self._t[name]

    def mesh(self, name):
        if name not in self._mesh:
            b = crewpoints.find(name)
            self._mesh[name] = (b, crewpoints.read_mesh(b)) if b is not None else (None, None)
        return self._mesh[name]

    def units(self):
        t = self.table("div_units_misc")
        return {r[0]: r for r in t.rows(t.find("units")[0])}

    def squads(self):
        t = self.table("div_units_misc")
        return {r[0]: r for r in t.rows(t.find("squads")[0])}

    def techn(self, unit_row):
        rec = os.path.splitext(os.path.basename(unit_row[2].replace("\\", "/")))[0]
        t = self.table(rec)
        return t, dict(azcf.vehicles(t)).get(unit_row[3], {})

    def cockpit_blocks(self, name):
        """The blocks of one cockpit in cocpits: its top block to the next cockpit."""
        c = self.table("cocpits")
        tops = [b.index for b in c.blocks if b.name.startswith("coc_")] + [len(c.blocks)]
        start = next((b.index for b in c.blocks if b.name == name), None)
        if start is None:
            return c, []
        return c, c.blocks[start:next(i for i in tops if i > start)]


def _model(game, unit_row):
    """The vehicle's 3D model name: its techn props `mesh`, which is NOT always
    the unit row's vehicle name (the Olifant is `olifant` in the table and
    `olifant_mk1a` as a model)."""
    t, blocks = game.techn(unit_row)
    props = t.props(blocks["props"]) if "props" in blocks else {}
    return props.get("mesh") or unit_row[3]


def _weapons(game, unit_row):
    t, blocks = game.techn(unit_row)
    return [r[0] for r in t.rows(blocks["weapons"])] if "weapons" in blocks else []


def _shells(game, unit_row):
    t, blocks = game.techn(unit_row)
    return [r[0] for r in t.rows(blocks["shells"])] if "shells" in blocks else []


def _loaded(game, vehicle):
    """{shell: count} from the ammo table's quick-battle load for this vehicle."""
    a = game.table("ammo")
    names = [b.name for b in a.blocks]
    if vehicle not in names:
        return {}
    out, default = {}, {}
    for b in a.blocks[names.index(vehicle) + 1:]:
        if b.spec == "" and b.rows == 0:
            break
        rows = {r[0]: azcf.flat(r)[1] for r in a.rows(b)}
        if b.name == "qbat":
            out = rows
        elif b.name == "default":
            default = rows
    return out or default


def first_gunner_sight(c, blocks):
    """The sight number the cockpit's first gunner view picks (plc_states:
    place 1 = gunner, field 2 = index in the vehicle's gunner sight list)."""
    plc = next((b for b in blocks if b.name == "plc_states"), None)
    if not plc:
        return None
    return next((r[2] & 0x7fffffff for r in c.rows(plc) if r[0][0] == 1 and r[2] != 0xffffffff), None)


def props_weap0(c, blocks):
    """The gunner's main weapon as the donor cockpit names it."""
    g = next((b for b in blocks[1:] if b.name == "gunner" and len(b.spec) == 1), None)
    return c.props(g).get("weap0") if g else None


# ---- the crewman a cockpit row belongs to, and the point HIS OWN vehicle puts him at (v98).

CREW_ROLES = ("driver", "mgunner", "gunner", "loader", "commander")
# mgunner before gunner: "mgunner" contains "gunner", and reading them in the wrong order turned the
# T-34's hull gunner into its turret gunner in the first draft of this table.


def crew_role(chunk):
    """The crewman a cockpit sync chunk belongs to: s_commander_out -> "commander"."""
    name = chunk[2:] if chunk.startswith("s_") else chunk
    for role in CREW_ROLES:
        if role in name:
            return role
    return None


def own_crew_points(techn_t, blocks, tidx, tnodes):
    """{role -> the point the vehicle's OWN work_places puts that crewman at}.

    work_places: [10] the sight group (sig_driver...), [12] the camera point, [13] the body point -
    the one a turned-out crewman uses, the Panzer IV's s_driver_out and the T-34's s_mgunner_out.
    Take the body point where this vehicle's model has it, and the camera point otherwise: a KV-1's
    driver has no body point at all, and his camera point is his own seat. A point is only usable
    when the model has it AND it carries a transform of its own (docs/sync-modes.md: a point parked
    on its parent's origin is not a position).
    """
    out = {}
    for r in techn_t.rows(blocks["work_places"]) if "work_places" in blocks else []:
        group = r[10] if len(r) > 10 else None
        if not isinstance(group, str) or not group.startswith("sig_"):
            continue
        role = group[4:]
        if role not in CREW_ROLES:
            continue                     # sig_pass and its like are seats no cockpit can open
        for field in (13, 12):
            p = r[field] if len(r) > field else None
            if isinstance(p, str) and p and p in tidx and tnodes[tidx[p]]["matrix"] is not None:
                out.setdefault(role, p)
                break
    return out


def derive(install, unit, choices=None, game=None):
    # game: a Game whose tables may be overlaid - gtos_vehicle.py passes one holding its add-on's own
    # vehicle, which the stock tables do not have
    choices = choices or {}
    game = game or Game(install)
    plan = Plan()
    units = game.units()
    if unit not in units:
        raise SystemExit("%s is not a unit in div_units_misc" % unit)
    row = units[unit]
    plan.unit, plan.vehicle = unit, row[3]
    if row[CREWABLE]:
        plan.warnings.append("%s is already crewable in the stock game" % unit)

    # ---- donor: the playable vehicle whose model shares the most chunk names
    cockpits = {b.name for b in game.table("cocpits").blocks if b.name.startswith("coc_")}
    plan.model = _model(game, row)
    _, mine = game.mesh(plan.model)
    if not mine:
        plan.warnings.append("the %s model (%s) was not found - crew positions cannot be read" % (plan.vehicle, plan.model))
    mine_names = {x["name"] for x in mine} if mine else set()
    mt, mb = game.techn(row)
    mine_gunner_sights = sum(1 for r in mt.rows(mb["sights"]) if r[4] == "sig_gunner") if "sights" in mb else 0
    scored = []
    for name, r in units.items():
        if name == unit or not r[CREWABLE] or r[COCKPIT] not in cockpits:
            continue
        if (unit, name) in KNOWN_BAD_DONORS:
            plan.warnings.append("not using %s as the donor: %s" % (name, KNOWN_BAD_DONORS[(unit, name)]))
            continue
        dc, dblocks = game.cockpit_blocks(r[COCKPIT])
        opens = first_gunner_sight(dc, dblocks)
        if opens is not None and opens >= mine_gunner_sights:
            plan.warnings.append("not using %s as the donor: its cockpit opens the gunner on sight %d, and %s has "
                                 "only %d gunner sights - the gunner would have nothing to look through"
                                 % (name, opens, plan.vehicle, mine_gunner_sights))
            continue
        _, theirs = game.mesh(_model(game, r))
        if not theirs:
            continue
        theirs_names = {x["name"] for x in theirs}
        score = len(mine_names & theirs_names) / float(len(mine_names | theirs_names) or 1)
        scored.append((score, name))
    scored.sort(reverse=True)
    if not scored:
        # SAY WHY. Until 2026-10-06 this raised the bare first line, while the loop above had
        # already written a sentence per rejected donor into plan.warnings - and then threw them
        # away, because the exit happens before the plan is ever returned. Balrog hit it on his
        # own install (Chieftain Mk5) and the window could tell him nothing at all.
        #
        # Three ways a candidate disappears, and only two of them leave a warning:
        #   - the skip at the top of the loop (not crewable, or its cockpit is not in cocpits):
        #     silent, and it is the one that empties the list completely
        #   - KNOWN_BAD_DONORS, or the gunner-sight guard: these DO append a warning
        #   - its model could not be read: silent
        # So report the counts as well as the warnings; the counts are what distinguish "there was
        # nothing to consider" from "everything was considered and rejected".
        considered = sorted(n for n, r in units.items()
                            if n != unit and r[CREWABLE] and r[COCKPIT] in cockpits)
        why = [w for w in plan.warnings if w.startswith("not using ")]
        out = ["no playable vehicle with a cockpit to copy from",
               "",
               "%d of %d units in this install are crewable AND have a cockpit the game defines."
               % (len(considered), len(units))]
        if considered:
            out.append("Candidates: " + ", ".join(considered))
        if why:
            out.append("")
            out.append("Every candidate was rejected:")
            out.extend("  - " + w[len("not using "):] for w in why)
        elif considered:
            out.append("")
            out.append("None of them was rejected for a stated reason, so their models could not be "
                       "read - the model files the cockpits belong to are missing from this install.")
        else:
            out.append("")
            out.append("There is nothing here to copy from. Either no vehicle in this install is "
                       "playable yet, or the add-on that makes them playable is not actually in "
                       "force - on the retail/GamersGate build it is ignored silently.")
        raise SystemExit(chr(10).join(out))
    donor = choices.get("donor") or scored[0][1]
    drow = units[donor]
    plan.donor_unit, plan.donor_vehicle, plan.donor_cockpit = donor, drow[3], drow[COCKPIT]
    plan.step("donor", "%s (cockpit %s)" % (donor, plan.donor_cockpit),
              "its model shares the most parts with %s's: %s" % (plan.vehicle, ", ".join(
                  "%s %.0f%%" % (n, s * 100) for s, n in scored)))

    plan.cockpit = "coc_" + plan.vehicle
    if plan.cockpit in cockpits:
        raise SystemExit("the game already has a cockpit called %s" % plan.cockpit)
    plan.step("cockpit", plan.cockpit, "a borrowed cockpit borrows its gun and crew positions (v2-v4)")
    # ---- WHOSE CREW ANIMATIONS (v103). The donor's by default - what every PROVEN SABoW Ext build
    # ships, and v5's "swapping them changed nothing" was measured on a cockpit whose interior was still
    # drawn, so the crew were behind it. An imported Operation Star vehicle tells a different story: its
    # OWN unit row usually leaves this field EMPTY, and that is what its crews animate with - while ours
    # were given the donor's anims_t62, i.e. a T-62 tanker sitting in a T-34 hull. murkz, after three
    # builds of moving that seat: "worse now the driver is poking out as well as the mgunner" - because
    # moving a man posed by the wrong animation set only changes WHICH head comes through the roof.
    # choices["anims_from"] = "vehicle" asks for the vehicle's own field instead.
    if choices.get("anims_from") == "vehicle":
        plan.anims = row[ANIMS]
        plan.step("anims", plan.anims or "(none - the vehicle's own)",
                  "the animation set the vehicle's OWN unit row carries, not the donor's (v103)")
    elif choices.get("anims_from"):
        # v104: a set named LITERALLY. v103 asked for the vehicle's own and got EMPTY - which is what
        # a crewman's row carries in SABoW's own div_units_misc, not what a playable tank's does: the
        # game's two playable vehicles name anims_t62 and anims_m60a1. The stock anims record lists the
        # human states a man in a vehicle uses - sit_in_tech, sit_in_tech_nw, techn_out, driving_left,
        # loading - and every set that can carry them exists as a record: anims_regular,
        # anims_in_techn, anims_t62, anims_m60a1. anims_in_techn is the generic IN-VEHICLE set and the
        # engine loads it as a BASE on every run, so it matches the crew's own skeleton rather than the
        # T-62 tanker's.
        plan.anims = choices["anims_from"]
        plan.step("anims", plan.anims,
                  "a NAMED set: the generic in-vehicle one, matching the crew's own skeleton (v104)")
    else:
        plan.anims = drow[ANIMS]
        plan.step("anims", plan.anims, "the donor's crew animations; swapping them changed nothing (v5)")

    # ---- weapons and shells in every crew station of the donor cockpit
    crm = game.table("common_res_mod")
    # A shell is tied to its gun by a shared number: the weapon row's flat field 8
    # equals the shell row's flat field 8 (U5TS and its rounds 52.6, D10T2S and
    # the 100L56 rounds 56.0; machine-gun rounds carry 0 and are matched by name).
    wrows = {r[0]: azcf.flat(r) for r in crm.rows(crm.find("weapons")[0])}
    srows = {r[0]: azcf.flat(r) for r in crm.rows(crm.find("shells")[0])}
    wclass = {k: (v[1], fourcc(v[3])) for k, v in wrows.items()}
    sinfo = {k: (v[3], fourcc(v[2])) for k, v in srows.items()}      # family, type
    link = lambda table, name: table[name][8] if name in table else 0

    def family(weapon):
        """The ammunition family a weapon fires: weapons flat field 41 names it
        (PKT B_762, MG4 B_762N, GT7 105L51); some rows leave it blank."""
        row = wrows.get(weapon)
        f = row[41] if row and len(row) > 41 and isinstance(row[41], str) else ""
        return f or None

    def fires(weapon, shell):
        """Does this weapon fire this shell? Family name first; for rows without
        one, the shared field-8 number (U5TS 52.6, M85 and P50_BALL 15.0)."""
        fam = family(weapon)
        if fam:
            return sinfo.get(shell, (None,))[0] == fam
        return bool(link(srows, shell)) and link(wrows, weapon) == link(srows, shell)
    dweap, tweap = _weapons(game, drow), _weapons(game, row)
    tshell = _shells(game, row)
    loaded = _loaded(game, plan.vehicle)
    word = "loaded"
    if not loaded:
        # The ammo table covers 56 vehicles; the TO-55 is not one. Its own shells
        # list is then the only load the game has for it. NOT proven: where both
        # exist they can differ (T-55 3BM25: listed 3, loaded 0).
        t_, b_ = game.techn(row)
        loaded = {r[0]: r[1] for r in t_.rows(b_["shells"])} if "shells" in b_ else {}
        word = "listed"
        plan.warnings.append("the ammo table has no load for %s, so its shells are chosen from the counts in "
                             "its own vehicle entry instead - NOT proven in game, check the ammo panel"
                             % plan.vehicle)
    # each donor weapon -> the vehicle's weapon standing in for it
    wmap, taken = {}, set()
    for w in dweap:
        if w in tweap:
            wmap[w] = w
            taken.add(w)
    # pairings given by hand: WW2 guns carry extra flag bits in the class field (KWK40 256 vs U5TS 0,
    # MG34 65537 vs PKT 1), so the class match below cannot pair them (gtos_vehicle.py, 2026-09-17)
    for w, x in (choices.get("weapons") or {}).items():
        if w in dweap and w not in wmap and x in tweap and x not in taken:
            wmap[w] = x
            taken.add(x)
    for w in dweap:
        if w not in wmap:
            cands = [x for x in tweap if x not in taken and wclass.get(x) == wclass.get(w)]
            if cands:
                wmap[w] = cands[0]
                taken.add(cands[0])

    # which mount (head) each crewman sits on, and which mount each weapon is on
    tt_, tb2 = game.techn(row)
    station_head = {r[0][3:]: r[9] for r in tt_.rows(tb2["work_places"])} if "work_places" in tb2 else {}
    theads = {}              # weapon name -> every mount it sits on (MG4 is on the turret AND the cupola)
    for r in (tt_.rows(tb2["weapons"]) if "weapons" in tb2 else []):
        theads.setdefault(r[0], set()).add(r[5])

    c, blocks = game.cockpit_blocks(plan.donor_cockpit)
    for b in blocks[1:]:
        if b.name not in ("driver", "gunner", "commander", "loader", "mgunner") or len(b.spec) != 1:
            continue
        props = c.props(b)
        edits, used, unfilled = {}, set(), []
        allowed = {}         # this crewman's weapons -> the vehicle's weapon he really gets
        for key in sorted(k for k in props if re.match(r"^weap\d+$", k)):
            w = props[key]
            if w in tweap:
                allowed[w] = w
                continue
            # A crewman may only be given a weapon on his OWN mount (v13: the
            # Chieftain's loader has no head, and the M2HB that replaced the
            # T-62 loader's DShK sits on head1, the gunner's - the load stopped
            # after the cockpits were built). A weapon left pointing at nothing
            # is tolerated (T-55, TO-55, Olifant; BoW43 notes/65).
            own = station_head.get(b.name)
            if wmap.get(w) and own not in theads.get(wmap[w], set()):
                plan.warnings.append("%s %s names %s; %s's %s sits on %s but the %s's own mount is %s - "
                                     "left as it is" % (b.name, key, w, plan.vehicle, wmap[w],
                                                        "/".join(sorted(h or "no head" for h in theads.get(wmap[w], ()))),
                                                        b.name, own or "none"))
                continue
            if wmap.get(w):
                allowed[w] = wmap[w]
                edits[key] = wmap[w]
                plan.step("weapon", "%s %s: %s -> %s" % (b.name, key, w, wmap[w]),
                          ("paired by hand (the class field carries flag bits); %s has no %s" % (plan.vehicle, w))
                          if (choices.get("weapons") or {}).get(w) == wmap[w] else
                          "same weapon class %s/%s; %s has no %s" % (wclass[w][0], wclass[w][1], plan.vehicle, w))
            else:
                plan.warnings.append("%s %s names %s, which %s does not have and has no same-class "
                                     "replacement for - left as it is" % (b.name, key, w, plan.vehicle))
        for key in sorted(k for k in props if re.match(r"^shell\d+e?$", k)):
            s = props[key]
            if s in tshell:
                continue
            fam, typ = sinfo.get(s, (None, None))
            gun = next((w for w in dweap if fires(w, s)), None)
            tgun = allowed.get(gun)      # a round follows its weapon - never a swap refused above
            pool = [x for x in tshell if tgun and fires(tgun, x) and loaded.get(x, 0) > 0 and x not in used]
            exact = [x for x in pool if sinfo[x][1] == typ]
            group = next((g for g in SHELL_GROUPS if typ in g), {typ})
            near = [x for x in pool if sinfo[x][1] in group]
            pick = sorted(exact or near, key=lambda x: -loaded.get(x, 0))
            if pick:
                edits[key] = pick[0]
                used.add(pick[0])
                plan.step("shell", "%s %s: %s (%s) -> %s (%s, %d %s)" % (
                    b.name, key, s, typ, pick[0], sinfo[pick[0]][1], loaded[pick[0]], word),
                    "same type" if exact else "nearest type loaded - the exact type is not (v3)")
            else:
                unfilled.append((key, s, typ, gun, tgun))
        # second pass, after every slot had its own type: a slot whose round type
        # the vehicle does not carry at all (Chieftain: no HEAT) gets its most-
        # loaded round for that gun that no slot uses yet, smoke last - an empty
        # slot is the v2/v3 fault. Nothing left: the slot stays and says so.
        for key, s, typ, gun, tgun in unfilled:
            spare = [x for x in tshell if tgun and fires(tgun, x) and loaded.get(x, 0) > 0 and x not in used]
            spare.sort(key=lambda x: (sinfo[x][1] == "SMK", -loaded.get(x, 0)))
            if spare:
                edits[key] = spare[0]
                used.add(spare[0])
                plan.step("shell", "%s %s: %s (%s) -> %s (%s, %d %s)" % (
                    b.name, key, s, typ, spare[0], sinfo[spare[0]][1], loaded[spare[0]], word),
                    "%s carries no %s-type round, so this slot gets its most-loaded round nothing else uses"
                    % (plan.vehicle, typ))
                plan.warnings.append("%s %s: no %s round on %s - the slot holds %s instead"
                                     % (b.name, key, typ, plan.vehicle, spare[0]))
            else:
                plan.warnings.append("%s %s names %s (%s, for %s); %s loads no such round for %s - "
                                     "left as it is" % (b.name, key, s, typ, gun or "no gun found",
                                                        plan.vehicle, tgun or "any gun"))
        if edits:
            plan.station_edits[b.name] = edits

    # ---- the gunner's first sight must be tied to the gun's head, or the gun
    # cannot be aimed up and down from it (v11: Olifant, M105D had no head).
    # The donor cockpit's first gunner view picks a sight by its number in the
    # vehicle's gunner sight list (plc_states field 2); that sight row's head
    # field (sights field 8) must name the head the gunner's gun is mounted on.
    plc = next((b for b in blocks if b.name == "plc_states"), None)
    first = next((r[2] for r in c.rows(plc) if r[0][0] == 1 and r[2] != 0xffffffff), None) if plc else None
    tt, tb_ = game.techn(row)
    if first is not None and "sights" in tb_ and "weapons" in tb_:
        srow_all = tt.rows(tb_["sights"])
        gunner_rows = [i for i, r in enumerate(srow_all) if r[4] == "sig_gunner"]
        gun = plan.station_edits.get("gunner", {}).get("weap0") or props_weap0(c, blocks)
        heads = {r[0]: r[5] for r in tt.rows(tb_["weapons"])}
        want = heads.get(gun, "")
        if first < len(gunner_rows) and want:
            i = gunner_rows[first]
            r = srow_all[i]
            if r[8] != want:
                plan.sight_heads.append((i, want))
                plan.techn_record = os.path.splitext(os.path.basename(row[2].replace("\\", "/")))[0]
                plan.step("sight", "gunner's first sight %s (%s): head '%s' -> '%s'" % (r[2], r[1], r[8], want),
                          "the view the gunner starts in must move with the gun's %s, or the gun cannot be "
                          "aimed up and down from it (v11)" % want)
        elif first >= len(gunner_rows):
            plan.warnings.append("the donor cockpit opens the gunner on sight %d, but %s has only %d gunner sights"
                                 % (first, plan.vehicle, len(gunner_rows)))

    # ---- the vehicle's OWN gunner sight, where one has been made (ownsight.py).
    # On by default; choices["own_sight"] = False builds without it (the golden
    # test's v14 Chieftain was proven with the borrowed M105D).
    import ownsight
    own = ownsight.spec_for(unit)
    if own and own.get("zoom") and choices.get("own_sight_zoom", True) and choices.get("own_sight", True) is True:
        # the 7x view's own reticle, in field 55 (ownsight.py)
        zname, zgen = own["zoom"]
        own = dict(own, meshes=own["meshes"] + [(zname, zgen)],
                   fields={**own["fields"], ownsight.FLAT_ZOOM: zname})
    if own and choices.get("own_sight", True) == "row_only":
        # CONTROL BUILD (BoW43 notes/76 v638): the new sights row and the vehicle
        # pointed at it, but the donor's own stock reticle - no mesh of ours. Splits
        # "the renamed row breaks it" from "our mesh breaks it".
        own = dict(own, meshes=[], fields={}, mesh=own["donor_row"] + "'s stock reticle",
                   label="CONTROL - the row only, with %s's stock reticle" % own["donor_row"])
    if own and choices.get("own_sight", True):
        if "sights" not in tb_ or not any(r[2] == own["donor_row"] and r[4] == "sig_gunner"
                                          for r in tt.rows(tb_["sights"])):
            plan.warnings.append("%s's own sight is made to replace %s, but its gunner no longer uses %s - "
                                 "not used" % (plan.vehicle, own["donor_row"], own["donor_row"]))
        else:
            plan.own_sight = own
            plan.techn_record = os.path.splitext(os.path.basename(row[2].replace("\\", "/")))[0]
            plan.step("own sight", "%s -> %s: %s" % (own["donor_row"], own["row"], own["label"]),
                      "the same view and scale as %s with the vehicle's own reticle drawn in it; "
                      "ships one sights row and the mesh%s %s (BoW43 notes/82, 85)" % (
                          own["donor_row"], "es" if len(own["meshes"]) > 1 else "",
                          " + ".join(n for n, _ in own["meshes"])))
            # v15 gave 001 twice on a 2048 x 3072 m area, and this used to warn "keep the area
            # 2048 x 2048". That was the cockpit-ceiling bug, not the area: donor hide rows
            # naming chunks the vehicle model lacks (the "hide fix" step below). v29 - v15 plus
            # that fix - built all 13 cockpits of an Iran tank company on a 3072 x 3072 m area
            # (2026-09-16), so the warning is gone. If the fix is ticked off, the hide step warns.
    elif own:
        plan.step("own sight", "not used (ticked off)", "builds with the borrowed %s" % own["donor_row"])
    if plan.own_sight and plan.own_sight.get("ammo_text") and choices.get("ammo_text", True):
        import ammotext
        plan.ammo_text = True
        shown = ", ".join(v[0] for w in ammotext.WANTED.values() for v in w.values())
        plan.step("ammo names", shown,
                  "the round list the gunner picks from names its sight scale, so [1] [2] [3] "
                  "match the scales (murkz, 2026-09-16)")

    # ---- crew positions: mode-1 sync rows whose point the vehicle's model has
    tb, tnodes = game.mesh(plan.model)
    tidx = {x["name"]: i for i, x in enumerate(tnodes or [])}
    sync = next((b for b in blocks if b.name == "sync"), None)
    for r in c.rows(sync) if sync else []:
        if r[2][1] != 1:
            continue
        point = r[1] or r[0]
        i = tidx.get(point)
        real = i is not None and tnodes[i]["matrix"] is not None
        where = crewpoints.pos(crewpoints.world(tnodes, i)) if real else None
        plan.crew_candidates.append((r[0], real, where))
    ticked = choices.get("crew")
    for chunk, real, where in plan.crew_candidates:
        if (chunk in ticked) if ticked is not None else real:
            if not real:
                raise SystemExit("crew point %s cannot follow %s: its model has no such point" % (chunk, plan.vehicle))
            plan.sync_modes[chunk] = 0
    # ---- v98: A CREWMAN THE VEHICLE'S MODEL CANNOT PLACE STANDS AT HIS OWN STATION, NOT THE DONOR'S.
    # The sibling of the v29 hide fix. That one stopped a DONOR HIDE row naming a chunk the vehicle's
    # model has not, which reads garbage and dies with 001. A donor SYNC row naming one was left as it
    # was - and mode 1 on a crew row means the TANK's crewman is placed at the BORROWED COCKPIT's point
    # (docs/sync-modes.md; v6-v9 proved the lever on the T-55). So the Panzer IV's driver turned out
    # stood where a T-62's crewman would and the KV-1's where an M60A1's (murkz, 2026-09-28: "seating is
    # wrong for the crew"), and the tool had been saying so in a warning on every build and doing nothing
    # about it. Where the man SHOULD stand is in the vehicle's own work_places - the AI has been putting
    # him there all along - so the point comes from there. A hand-ticked build is left alone.
    seats = own_crew_points(tt, tb_, tidx, tnodes)
    moved = {}
    if ticked is None:
        for i, (chunk, real, where) in enumerate(plan.crew_candidates):
            if real:
                continue
            point = seats.get(crew_role(chunk) or "")
            if not point:
                continue
            plan.sync_retarget[chunk] = point
            plan.sync_modes[chunk] = 0
            moved[chunk] = point
            # the man HAS a position now, so the window must not go on offering him as one it cannot place
            plan.crew_candidates[i] = (chunk, True,
                                       crewpoints.pos(crewpoints.world(tnodes, tidx[point])))
    plan.step("crew", ", ".join(plan.sync_modes) or "none",
              "mode 0 = the crewman uses %s's own AI position (v6-v9)%s" % (
                  plan.vehicle, "" if ticked is None else "; ticked by hand"))
    if moved:
        plan.step("crew own", ", ".join("%s -> %s" % kv for kv in sorted(moved.items())),
                  "the %s model has no point of that name, so the man stands at the one the vehicle's "
                  "own work_places gives him instead of at the borrowed cockpit's (v98)" % plan.vehicle)
    missing = [ch for ch, real, _ in plan.crew_candidates if not real]
    if missing:
        plan.warnings.append("no position in the %s model for: %s - those crewmen keep the donor's"
                             % (plan.vehicle, ", ".join(missing)))

    # ---- hide the donor cockpit's geometry
    top = c.props(blocks[0])
    plan.hide_models = [top[k] for k in sorted(k for k in top if re.match(r"^mesh(_\d+)?$", k))]
    plan.step("hide", ", ".join(plan.hide_models),
              "every drawable piece of the donor cockpit, loaded but not drawn (v8)")

    # ---- donor hide rows aimed at the vehicle's OWN model must name a chunk it has.
    # A hide row with mesh index -1 is looked up in the vehicle's external model.
    # adv_tnksim FUN_10017c60 finds each hide chunk and copies its 4x4 matrix with NO
    # check that the find worked, so a chunk the model lacks reads garbage - and the load
    # dies with "001" whenever that garbage is unreadable. That is the intermittent
    # cockpit ceiling, caught under a debugger on 2026-09-16 (docs/cockpit-ceiling.md).
    # coc_t62's d_hole_01 / d_hole_02 exist in the t62 model, not in t55, olifant_mk1a
    # or chief_mk5. Removing a hide row only stops hiding a chunk the model never had.
    hide = next((b for b in blocks if b.name == "hide"), None)
    own = [r[0] for r in c.rows(hide) if r[1] == 0xffffffff] if hide else []
    if tnodes is None:
        if own:
            plan.warnings.append("the %s model was not found, so %d hide rows on it cannot be checked"
                                 % (plan.model, len(own)))
    else:
        plan.hide_missing = [ch for ch in own if ch not in tidx]
    if plan.hide_missing:
        if choices.get("drop_missing_hide", True):
            plan.hide_drop = list(plan.hide_missing)
            plan.step("hide fix", "drop " + ", ".join(plan.hide_drop),
                      "the donor hides these on its own model; %s has no such chunk, and the "
                      "unchecked lookup is the cockpit-ceiling 001 (2026-09-16)" % plan.model)
        else:
            plan.warnings.append("KEPT donor hide rows naming chunks %s lacks: %s - the cockpit-ceiling bug"
                                 % (plan.model, ", ".join(plan.hide_missing)))

    # ---- quick-battle platoons
    squads = [s for s, r in game.squads().items() if r[SQUAD_UNIT] == unit]
    q = game.table("qbattle")
    for i, b in enumerate(q.blocks):
        if b.name != "pool" or b.spec != "sus" or i == 0:
            continue
        if any(r[0] in squads for r in q.rows(b)):
            owner = q.blocks[i - 1]
            p = q.props(owner)
            state = "no flag" if "user_in" not in p else ("on" if p["user_in"] else "off")
            plan.platoon_candidates.append((owner.name, p.get("name", ""), state))
    ticked = choices.get("platoons")
    for name, text, state in plan.platoon_candidates:
        if (name in ticked) if ticked is not None else state in ("off", "no flag"):
            if state == "on":
                raise SystemExit("platoon %s is already crewable - nothing to open" % name)
            plan.platoons.append(name)
            plan.platoon_state[name] = state
    plan.step("platoons", ", ".join(plan.platoons) or "none",
              "the crew flag switched on, or added where the platoon has none (v2)%s"
              % ("" if ticked is None else "; ticked by hand"))
    try:
        import names
        plan.platoon_labels = names.platoon_labels(install, q, game.table("common_res"),
                                                   [n for n, _, _ in plan.platoon_candidates])
    except (Exception, SystemExit) as e:
        plan.platoon_labels = {}
        plan.warnings.append("could not read the game's platoon names (%s) - showing table ids" % e)
    added = [n for n in plan.platoons if plan.platoon_state[n] == "no flag"]
    if added:
        plan.warnings.append("the crew flag is ADDED (not just switched on) for: %s - the quick-battle table then "
                             "goes through the text route; not yet proven in a SABoW Ext build" % ", ".join(added))
    return plan


# The choices murkz tested in the proven v9 build - the golden test's ticks.
V9_CHOICES = {
    "platoons": ["iq_tank_plat2"],
    "crew": ["s_driver", "s_driver_out", "s_loader", "s_loader_out", "s_commander", "s_commander_out"],
}


if __name__ == "__main__":
    install = __import__("settings").get("live")
    unit = sys.argv[1] if len(sys.argv) > 1 else "sau_t55"
    print(derive(install, unit).report())
