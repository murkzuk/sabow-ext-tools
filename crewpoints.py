# Crew / camera points out of stock AZG2 vehicle meshes, READ-ONLY.
# Decode logic is read_mesh() from K:\DeepseekSABoW\stubify.py (notes/66-67),
# pointed at the clean L: install instead of G:.
import struct, sys, glob, os
sys.path.insert(0, r"K:\SABoW_Ext\tool")
import azcf
import settings

GAME = settings.get("live")


def find(name):
    for p in glob.glob(os.path.join(GAME, "data", "**", "*.flatdata"), recursive=True):
        try:
            recs = azcf.archive_records(p)
        except Exception:
            continue
        if name in recs and recs[name][2] == "mesh":
            return azcf.read_record(p, name)
    return None


def read_mesh(b):
    assert b[:4] == b"AZG2"
    tbl = struct.unpack_from("<I", b, 0x08)[0]
    cnt = struct.unpack_from("<I", b, 0x0c)[0]
    mbase = struct.unpack_from("<I", b, 0x18)[0]
    mcnt = struct.unpack_from("<I", b, 0x1c)[0]
    nodes = []
    for i in range(cnt):
        o = tbl + i * 0x140
        nm = b[o:o + 0x20].split(b"\0")[0].decode("latin1")
        f = struct.unpack_from("<8i", b, o + 0x20)
        # field[0] is the node's matrix index, -1 = none. The index comes in TWO
        # forms: high bit set (static nodes) and high bit clear (animated nodes -
        # hatches, turned-out and seated crew points). BoW43 notes/66-67 decoded
        # only the first, and reading the second as "no transform" made the
        # T-55's real s_loader_out, s_gunner and s_commander look like
        # placeholders on the turret pivot (corrected 2026-09-15).
        m = None
        if f[0] != -1:
            mi = f[0] & 0x7fffffff
            if mi < mcnt:
                m = list(struct.unpack_from("<16f", b, mbase + mi * 0x40))
        nodes.append({"name": nm, "parent": f[2], "matrix": m})
    return nodes


IDENT = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def mul(a, b):  # row-major 4x4, row vectors: world = local * parent
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def chain(nodes, i):
    out = []
    while 0 <= i < len(nodes):
        out.append(i)
        p = nodes[i]["parent"]
        if p == i or p < 0 or p >= len(nodes):
            break
        i = p
    return out


def world(nodes, i):
    m = IDENT
    for j in chain(nodes, i):
        m = mul(m, nodes[j]["matrix"] or IDENT)
    return m


def pos(m):
    return (m[12], m[13], m[14])
