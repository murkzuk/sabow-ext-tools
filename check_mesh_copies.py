#!/usr/bin/env python3
"""A model that exists in more than one archive must agree with itself. Check that, everywhere.

WHY THIS EXISTS - and it is the third time this fault has cost a day.

`gtos_vehicle.model_copies()` and `patch_shadowing_models()` already know a model can sit in several
archives, and already patch the ones outside our own add-on. But those patches are written INTO AN
INSTALLED FILE, and its own docstring says what that means: "an add-on reinstall can wipe them, and
that backup is the only way back". Measured 2026-09-25 and 2026-09-27:

  * pz3jlg    - the anchor name moved the driver while mesh_points never did, because the edit went
                to the copy nothing reads. Four builds went into that.
  * t34_42_utz - gtos_ww2 (the copy we build) held s_mgunner z=1.300 with the v26 seat fix;
                gtos_sokolovo_ob (the copy Shilovo READS) still held 1.658. The hull MG man stood
                0.358 m too far forward, and Jeff had to report it twice.

Both times the two copies were allowed to diverge quietly. This checks for exactly that: for every
mesh name held by more than one archive, compare the world position of every crew/shape node and
report any node whose position differs between copies.

RUN:  python check_mesh_copies.py            # every install, every duplicated mesh
      python check_mesh_copies.py <install>  # one install

Exit status is 1 when any copy disagrees, so a build or a release script can gate on it.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf  # noqa: E402
import crewpoints as CP  # noqa: E402

# nodes worth comparing: the crew anchors and the named shape points. A render-only node is not worth
# failing a check over, and comparing whole meshes would drown the answer in harmless art differences.
PREFIXES = ("s_", "p_", "d_", "head")


def meshes(install):
    """{mesh name: [(path, blob)]} for every mesh record in the install."""
    out = {}
    for p in sorted(glob.glob(os.path.join(install, "data", "**", "*.flatdata"), recursive=True)):
        try:
            recs = azcf.archive_records(p)
        except Exception:
            continue
        for name, (off, size, kind, loc) in recs.items():
            if kind != "mesh":
                continue
            try:
                blob = azcf.read_record(p, name)
            except Exception:
                continue
            out.setdefault(name, []).append((p, blob))
    return out


def node_positions(blob):
    """{node name: (x, y, z)} for the nodes worth comparing, world positions."""
    nodes = CP.read_mesh(blob)
    out = {}
    for i, n in enumerate(nodes):
        nm = n["name"]
        if not nm or not nm.startswith(PREFIXES):
            continue
        out[nm] = CP.pos(CP.world(nodes, i))
    return out


def main(argv):
    if len(argv) > 1:
        installs = [argv[1]]
    else:
        sys.path.insert(0, HERE)
        import settings
        installs = [settings.get("sandbox"), settings.get("live")]
    problems = 0
    cam_only = 0
    for install in installs:
        if not os.path.isdir(install):
            continue
        print("=== %s" % install)
        seen = meshes(install)
        dupes = {n: v for n, v in seen.items() if len(v) > 1}
        print("    %d mesh records, %d of them held by more than one archive" % (len(seen), len(dupes)))
        for name, copies in sorted(dupes.items()):
            try:
                ref = node_positions(copies[0][1])
            except Exception as e:
                print("    %-18s cannot read the mesh (%s)" % (name, str(e)[:40]))
                continue
            for path, blob in copies[1:]:
                try:
                    other = node_positions(blob)
                except Exception:
                    continue
                # A CREW node is where a man is drawn; a CAMERA node (s_camera_*) is where a
                # PLAYER's view sits. Both matter, but not equally, and the exit status follows the
                # crew ones. Measured 2026-09-29 on pz3jlg: its s_driver and s_mgunner are IDENTICAL
                # in both copies and only the two s_camera_* differ - so no crewman is misplaced, and
                # pz3jlg is AI-only, so nothing reads those cameras today. The recipe asks for z
                # 1.4431 on both cameras and NEITHER copy carries that, so there is no justified
                # value to patch toward either. Failing the whole check on it would train everyone to
                # ignore a red FAIL, which is how the T-34 seat got through twice.
                crew, cams = [], []
                for node, pos in sorted(ref.items()):
                    q = other.get(node)
                    if q is None:
                        continue
                    if max(abs(pos[k] - q[k]) for k in range(3)) > 0.002:
                        line = "%s %s vs %s" % (node, tuple(round(x, 3) for x in pos),
                                                tuple(round(x, 3) for x in q))
                        (cams if node.startswith("s_camera") else crew).append(line)
                if crew or cams:
                    if crew:
                        problems += 1
                    else:
                        cam_only += 1
                    print("    %s%s" % (name, "" if crew else "   (camera points only)"))
                    print("        %s" % os.path.relpath(copies[0][0], install))
                    print("        differs from %s" % os.path.relpath(path, install))
                    for line in (crew + cams)[:6]:
                        print("            %s" % line)
                    if len(crew + cams) > 6:
                        print("            ... and %d more" % (len(crew + cams) - 6))
    print()
    if cam_only:
        print("NOTE  %d duplicated mesh(es) disagree on CAMERA points only - no crewman is misplaced"
              % cam_only)
        print("      by these. They would matter if such a vehicle became playable, so they are")
        print("      reported, but they do not fail the check. See BUILD_LOG 2026-09-29 on pz3jlg.")
    if problems:
        print("FAIL  %d duplicated mesh(es) disagree on a CREW point. The engine reads whichever copy"
              % problems)
        print("      wins, so a fix applied to one copy can be invisible. Patch EVERY copy -")
        print("      gtos_vehicle.py has model_copies() and patch_mesh_point() for it.")
        return 1
    print("PASS  every duplicated mesh agrees with itself about where its CREW sit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
