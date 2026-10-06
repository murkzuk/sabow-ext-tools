# names - the game's own English names for the codes the tables use. READ-ONLY.
# Part of SABoW Ext.
#
# The tables name things by id (platoon `sa_tank_plat_03`, text id
# `txt_qb_pl_sa_tank_to55`, side code USSR). The words murkz sees in the game live
# in packed text records under data\mtc80\loc_eng. The game's own `text2pd`
# unpacks one into lines like
#
#     txt_qb_pl_sa_tank_to55[s]() { Tank batallion$nFlamethrower platoon (TO-55); }
#
# where $n is a line break. Unpacked records are cached by md5 in the build work
# folder. text2pd is always called with an explicit output: with one argument it
# OVERWRITES its input (memory: project_sabow_quick_battle_chain).

import hashlib
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402

RECORDS = ["loc_qbattle_mtc80", "loc_qbattle_common", "loc_kit_units_mtc80", "loc_kit_units"]
LINE = re.compile(rb"^\s*(\w+)\[s\]\(\)\s*\{\s*(.*?);\s*\}\s*$")


def _starter():
    import build          # late: build imports recipe, which imports this
    return build


def texts(install, log=None):
    """{text id: text} from the English text records, unpacked with text2pd."""
    b = _starter()
    arch = os.path.join(install, "data", "mtc80", "loc_eng", "packed_data", "text_loc.flatdata")
    folder = os.path.join(b.work_dir(install), "text", "names")
    os.makedirs(folder, exist_ok=True)
    recs = azcf.archive_records(arch)
    out = {}
    for name in RECORDS:
        if name not in recs:
            continue
        data = azcf.read_record(arch, name)
        tag = hashlib.md5(data).hexdigest()[:12]
        unpacked = os.path.join(folder, "%s.%s.engcfg2" % (name, tag))
        if not os.path.isfile(unpacked):
            src = os.path.join(folder, "%s.loc_eng.text" % name)
            with open(src, "wb") as f:
                f.write(data)
            b.starter(install, "text2pd,", b.rel(src, install) + ",", b.rel(unpacked, install),
                      expect=unpacked, timeout=60)
        with open(unpacked, "rb") as f:
            for raw in f.read().splitlines():
                m = LINE.match(raw)
                if m:
                    text = m.group(2).decode("cp1251", "replace")
                    parts = [p for p in (re.sub(r"[\x00-\x1f]", "", s).strip() for s in text.split("$n")) if p]
                    out[m.group(1).decode("latin1")] = parts
    return out


def fourcc(u):
    return struct.pack("<I", u).rstrip(b"\0").decode("latin1")


def platoon_labels(install, qbattle, common_res, blocks):
    """{platoon block: "Side - battalion - platoon"} in the game's own words.
    Anything not found falls back to the id, never to a guess."""
    t = texts(install)
    sides = {}
    sb = common_res.find("sides")
    if sb:
        for r in common_res.rows(sb[0]):
            words = t.get(r[1])
            sides[fourcc(r[0])] = words[0] if words else fourcc(r[0])
    out = {}
    for name in blocks:
        blk = qbattle.find(name)
        if not blk:
            out[name] = name
            continue
        p = qbattle.props(blk[0])
        words = t.get(p.get("name", ""), [])
        platoon = words[-1] if words else name
        group = words[0] if len(words) > 1 else ""
        side = ""
        bat = qbattle.find(p.get("pool", ""))
        if bat:
            bp = qbattle.props(bat[0])
            code = bp.get("side")
            side = sides.get(fourcc(code), fourcc(code)) if isinstance(code, int) else ""
            bwords = t.get(bp.get("name", ""), [])
            group = group or (bwords[0] if bwords else "")
        out[name] = "  -  ".join(x for x in (side, group, platoon) if x)
    return out
