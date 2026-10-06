# sabow_op_tool.py - author SABoW / Graviteam operations: one tab per stage of the pipeline.
#
# Written from the 2026-09-24 session that produced the first working user-created WW2 operation.
# Every check exists because its absence cost a build - see notes_104_first_ww2_operation.md.
#
# TABS
#   1 Project  - copy the stencil into a new project and rename/fix it (no LibreOffice needed)
#   2 Convert  - .ods -> binaries. WRITES the resconv script itself; campgen is just a dialog
#                around this, and its dialog is where the folder/name trap lives.
#   3 Editor   - launches campeditor (the one genuinely GUI, unscripptable stage).
#   4 Compile  - launches campcomp, which writes the loose operation files. It does NOT pack.
#   5 Pack     - merge + verify + pack the .campack2. The stage nobody documents.
#
# THE THREE SILENT KILLERS, all checked before packing
#   1. cfgp2pd output cannot be compiled as-is: cfgfix is mandatory.
#   2. CRLF must be preserved. pd2cfgp given LF text emits AN EMPTY TABLE, with no error.
#   3. "scripts" must be the COMPILED .script - a raw .engcfg makes the game 001 on clicking.
#
# Also remember: campcomp reports an ERROR for every unplaced platoon. That is normal.

import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import zipfile

# FINDING THE SABoW Ext TOOL FOLDER. This file does not live in it, so it has to look -
# it used to be the literal "K:/SABoW_Ext/tool", which meant the imports below raised
# ModuleNotFoundError on any machine without a K: drive, SILENTLY, because the shortcut
# starts this with pythonw. Release audit 2026-10-06, RELEASE_AUDIT_2026-10-06.md B1.
#
# Looked for in this order, so a user can override it without editing code:
#   1. the SABOW_EXT_TOOL environment variable
#   2. tool_path.txt sitting beside this script, holding the folder on one line
#   3. the SABoW_Ext/tool folder beside this repo (the layout the repos ship in)
#   4. this script's own folder, for when everything is unpacked together
HERE = os.path.dirname(os.path.abspath(__file__))


def _find_tool():
    """(folder, what was tried). A folder counts only if azcf.py is actually in it."""
    tried = []
    env = os.environ.get("SABOW_EXT_TOOL")
    if env:
        tried.append(("SABOW_EXT_TOOL", env))
    txt = os.path.join(HERE, "tool_path.txt")
    if os.path.isfile(txt):
        try:
            with open(txt, encoding="utf-8") as f:
                line = f.read().strip()
            if line:
                tried.append(("tool_path.txt", line))
        except OSError:
            pass
    tried.append(("beside this repo", os.path.join(os.path.dirname(HERE), "SABoW_Ext", "tool")))
    tried.append(("this folder", HERE))
    for _why, cand in tried:
        if cand and os.path.isfile(os.path.join(cand, "azcf.py")):
            return os.path.abspath(cand), tried
    return None, tried


TOOL, _TRIED = _find_tool()
if TOOL is None:
    _msg = ("The SABoW Ext tool folder could not be found, so this tool cannot start.\n\n"
            "It needs the folder that holds azcf.py, build.py and settings.py.\n\n"
            "Looked in:\n"
            + "\n".join("    %-18s %s" % (w, c) for w, c in _TRIED)
            + "\n\nFix it either way:\n"
              "  - put that folder's path on one line in tool_path.txt, next to this script\n"
              "  - or set the SABOW_EXT_TOOL environment variable to it")
    try:                               # a window, because pythonw gives no console to print to
        import tkinter
        from tkinter import messagebox
        _r = tkinter.Tk()
        _r.withdraw()
        messagebox.showerror("SABoW Operations Tool", _msg)
        _r.destroy()
    except Exception:
        pass
    print(_msg)
    sys.exit(1)
sys.path.insert(0, TOOL)
TOOL_DIR = TOOL          # the tool folder, not HERE: this script lives elsewhere
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
    _startup_error('SABoW Operations Tool',
                   "SABoW Operations Tool could not load its own modules (azcf.py, build.py, gtos_opstar.py, settings.py).\n\n"
                   "It needs them in: " + TOOL_DIR)

# The Graviteam operation stencil ships INSIDE the game, at the path below, so it is derived
# from whichever install the user picked. It used to be the literal
# "G:/SABoW_2899/docs/modwork/editors/op_stencil" (release audit B3) - a folder on a drive
# nobody else has, when the tool was already being told where the game is.
STENCIL_REL = os.path.join("docs", "modwork", "editors", "op_stencil")


def stencil_for(install):
    """The stencil inside `install`, or a plain-English refusal naming where it looked."""
    p = os.path.join(install, STENCIL_REL)
    if os.path.isdir(p):
        return p
    raise RuntimeError(
        "The Graviteam operation stencil is not in this install.\n\n"
        "Looked for:\n  %s\n\n"
        "It ships with Graviteam Tactics: Operation Star and with some Steel Armor builds. "
        "Point the Game install box at one that has it." % p)
BANNER = b"//Cfgp2Pd auto converter\r\n\r\n"
CRLF = b"\r\n"


def parts_of(proj, name):
    return [
        ("campgen",  os.path.join(proj, name + ".camproj2"),          1),
        ("div_pool", os.path.join(proj, name + "_div_pool.cfgpack"), 60),
        ("frames",   os.path.join(proj, name + "_frames.cfgpack"),    8),
    ]


def strip_banner(text):
    """Drop cfgp2pd's banner. CRLF IS PRESERVED on split AND join: normalising to LF makes
    pd2cfgp emit an empty table with no error at all. That was the merge killer."""
    ls = text.split(CRLF)
    while ls and (ls[0].startswith(b"//") or not ls[0].strip()):
        ls.pop(0)
    while ls and not ls[-1].strip():
        ls.pop()
    return CRLF.join(ls) + CRLF


# ------------------------------------------------------------------ stage 1: project

def create_from_stencil(dst, name, install, log):
    """Copy the Graviteam stencil into a new project, renaming everything to <name> and
    fixing the file-reference cells inside the .ods. zipped XML - LibreOffice not needed."""
    src = stencil_for(install)
    if os.path.isdir(dst) and os.listdir(dst):
        raise RuntimeError("%s already exists and is not empty" % dst)
    os.makedirs(os.path.join(dst, "SRC"), exist_ok=True)
    os.makedirs(os.path.join(dst, "BRIEFS"), exist_ok=True)

    ren = {"stencil.ods": name + ".ods",
           "stencil_div_pool.ods": name + "_div_pool.ods",
           "stencil_text.ods": name + "_text.ods"}
    for a, b in ren.items():
        shutil.copy2(os.path.join(src, "SRC", a), os.path.join(dst, "SRC", b))
    for a, b in (("stencil_scripts.engcfg", name + "_scripts.engcfg"),
                 ("stencil_op_image.tga", name + "_op_image.tga")):
        shutil.copy2(os.path.join(src, a), os.path.join(dst, b))
    for a in ("op_brief.engcfg", "op_brief.odg"):
        shutil.copy2(os.path.join(src, "BRIEFS", a), os.path.join(dst, "BRIEFS", a))

    def rewrite(path, fn):
        with zipfile.ZipFile(path) as z:
            items = [(i, z.read(i.filename)) for i in z.infolist()]
        out = []
        for info, data in items:
            if info.filename == "content.xml":
                data = fn(data.decode("utf-8")).encode("utf-8")
            out.append((info, data))
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info, data in out:
                if info.filename == "mimetype":
                    zi = zipfile.ZipInfo("mimetype")
                    zi.compress_type = zipfile.ZIP_STORED
                    z.writestr(zi, data)
                else:
                    z.writestr(info.filename, data)
        os.replace(tmp, path)

    rewrite(os.path.join(dst, "SRC", name + "_div_pool.ods"),
            lambda x: x.replace("stencil_div_pool.cfgpack", name + "_div_pool.cfgpack"))
    rewrite(os.path.join(dst, "SRC", name + ".ods"),
            lambda x: x.replace("stencil.camproj2", name + ".camproj2"))
    log("   project created at %s" % dst)
    log("   NOTE the stencil ships for the Taranovka map, which a SABoW install does not have.")
    log("        Set polygon + camp_area in SRC\\%s.ods first, or the editor shows a black map." % name)
    log("        Installed districts: 7a_abualhasib, 3o_oskol, k_kr_polana, 5s_shilovo, m_sokolovo")


# ------------------------------------------------------------------ stage 2: convert

def write_resconv(proj, name, install, log):
    """campgen does exactly this: write a resconv script and run it. Doing it directly skips
    campgen's dialog, and with it the folder/name trap that silently looks for the wrong path."""
    # Built beside itself and renamed into place: an interrupted straight write (disk full,
    # antivirus, a crash) leaves a HALF-WRITTEN file where a valid one was. os.replace is
    # atomic on Windows. Release audit R1. The PACK stage is deliberately left alone - it
    # already reads every record back out of the finished archive and aborts if a check
    # fails, which is a stronger gate than this.
    src = os.path.join(proj, "SRC")
    up = os.path.join(src, "..")
    body = ["i_resconv:resconv()", "{"]
    for code, fn in ((5, name + ".ods"), (3, name + "_div_pool.ods"), (7, name + "_text.ods")):
        p = os.path.join(src, fn)
        if not os.path.isfile(p):
            raise RuntimeError("missing %s" % p)
        body.append("\t%d, %s%s, %s;" % (code, "*" if code != 7 else "", p, up))
    body += ["}", "_vars() {}", ""]
    eng = os.path.join(src, "make_%s_project.engcfg" % name)
    with open(eng + ".tmp", "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\r\n".join(body))
    os.replace(eng + ".tmp", eng)
    log("   wrote %s" % eng)

    cmd = os.path.join(src, "make_%s_project.cmd" % name)
    with open(cmd + ".tmp", "w", encoding="utf-8", newline="\r\n") as f:
        f.write("@echo off\r\n")
        f.write("cd /d \"%s\"\r\n" % install)
        f.write("\"%s\r\n" % os.path.join(install, "starter.exe").replace(chr(92), os.sep) +
                "\" root\\programs\\resconv.progpack, %s" % eng)
    os.replace(cmd + ".tmp", cmd)
    log("   wrote %s  (uses cd /d - campgen writes a bare cd, which cannot cross drives)" % cmd)

    before = {}
    for fn in (name + ".camproj2", name + "_div_pool.cfgpack",
               name + "_text.loc_eng.textpack"):
        p = os.path.join(proj, fn)
        before[fn] = os.path.getmtime(p) if os.path.isfile(p) else None

    r = subprocess.run([os.path.join(install, "starter.exe"),
                        "root" + os.sep + "programs" + os.sep + "resconv.progpack,", eng],
                       cwd=install, capture_output=True, text=True, timeout=900)
    log("   resconv returned %d" % r.returncode)
    for fn, t0 in before.items():
        p = os.path.join(proj, fn)
        now = os.path.getmtime(p) if os.path.isfile(p) else None
        if now is None:
            log("   *** %s was NOT produced ***" % fn)
        elif t0 is None or now > t0:
            log("   %-28s regenerated (%d bytes)" % (fn, os.path.getsize(p)))
        else:
            log("   *** %s was NOT regenerated - is the .ods valid? ***" % fn)


# ------------------------------------------------------------------ stages 3-4

def launch(install, prog, log):
    p = os.path.join(install, "starter.exe")
    if not os.path.isfile(p):
        raise RuntimeError("no starter.exe in %s" % install)
    arg = "root" + os.sep + "programs" + os.sep + prog + ".progpack"
    log("   launching %s" % arg)
    subprocess.Popen([p, arg], cwd=install)


# ------------------------------------------------------------------ stage 5: pack

class Packer(object):
    def __init__(self, install, log):
        self.install = install
        self.log = log

    def run(self, rel):
        return build.rel(rel, self.install)

    def decompile(self, work, tag, src, expect_blocks):
        if not os.path.isfile(src):
            raise RuntimeError("missing %s" % src)
        cfg = os.path.join(work, tag + ".config")
        shutil.copy2(src, cfg)
        raw = os.path.join(work, tag + ".cfgp2pd.engcfg2")
        if os.path.exists(raw):
            os.remove(raw)
        build.starter(self.install, "cfgp2pd,", self.run(cfg) + ",", self.run(raw),
                      expect=raw, timeout=900)
        fixed = os.path.join(work, tag + ".loc_def.engcfg2")
        r = subprocess.run([sys.executable, os.path.join(TOOL, "cfgfix.py"), cfg, raw, fixed],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(fixed):
            raise RuntimeError("cfgfix refused %s (exit %d)" % (tag, r.returncode))
        nul = 0
        for line in r.stdout.splitlines():
            if "NULs" in line:
                try:
                    nul = int(line.split(":")[1].strip())
                except Exception:
                    pass
        with open(fixed, "rb") as f:
            body = f.read()
        rt = os.path.join(work, "rt_" + tag, "part.config")
        os.makedirs(os.path.dirname(rt), exist_ok=True)
        build.starter(self.install, "pd2cfgp,", self.run(fixed) + ",", self.run(rt),
                      expect=rt, timeout=900)
        with open(rt, "rb") as f:
            blob = f.read()
        try:
            nb = len(azcf.Table(blob).blocks)
        except Exception as e:
            nb = -1
            self.log("      unreadable result: %s" % e)
        ok = (nb == expect_blocks)
        self.log("   %-9s %7d bytes text (%d NUL repairs) -> %s"
                 % (tag, len(body), nul, ("OK, %d blocks" % nb) if ok
                    else "*** %d blocks, expected %d ***" % (nb, expect_blocks)))
        if not ok:
            raise RuntimeError("%s compiles to %d blocks, expected %d - not packing"
                               % (tag, nb, expect_blocks))
        return body

    def merge_and_pack(self, proj, name, chapter, addon):
        work = os.path.join(proj, "_pack")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        self.log("STEP 1  decompile + repair + compile-check each part")
        texts = [strip_banner(self.decompile(work, tag, src, n))
                 for tag, src, n in parts_of(proj, name)]
        self.log("")
        self.log("STEP 2  merge into desc (campgen -> div_pool -> frames)")
        merged = BANNER + CRLF.join(texts)
        mtxt = os.path.join(work, "desc_merged.config")
        with open(mtxt, "wb") as f:
            f.write(merged)
        self.log("   merged text: %d bytes" % len(merged))
        out = os.path.join(work, "merged", "desc.config")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        build.starter(self.install, "pd2cfgp,", self.run(mtxt) + ",", self.run(out),
                      expect=out, timeout=900)
        with open(out, "rb") as f:
            desc = f.read()
        self.log("")
        self.log("STEP 3  verify the merged desc")
        t = azcf.Table(desc)
        names = [b.name for b in t.blocks]
        if not names or names[0] != "i_campgen:campgen":
            raise RuntimeError("desc does not start with i_campgen:campgen (%s) - the game would"
                               " ignore the operation" % (names[:1] or "no blocks"))
        fam = ["frames", "frames_raw", "ai_orders", "tac_markers", "plat_pos", "mg_nodes",
               "mg_links"]
        miss = [n for n in fam if n not in names]
        if miss:
            raise RuntimeError("desc is missing the frames family: %s" % miss)
        self.log("   %d blocks, %d bytes;  first %s, last %s"
                 % (len(t.blocks), len(desc), names[0], names[-1]))
        def nrows(nm):
            b = [x for x in t.blocks if x.name == nm]
            return len(t.rows(b[0])) if b else 0
        self.log("   campgen %d, frames_raw %d, plat_pos %d, ai_orders %d"
                 % (nrows("i_campgen:campgen"), nrows("frames_raw"), nrows("plat_pos"),
                    nrows("ai_orders")))
        if nrows("plat_pos") == 0:
            self.log("   WARNING plat_pos is empty - no platoon placed on the map.")
        def blob(fn):
            p = os.path.join(proj, fn)
            if not os.path.isfile(p):
                raise RuntimeError("missing %s" % p)
            with open(p, "rb") as f:
                return f.read()
        self.log("")
        self.log("STEP 4  the other four records")
        script = name + "_scripts.script"
        if os.path.isfile(os.path.join(proj, script)):
            self.log("   scripts: %s (COMPILED - correct)" % script)
        else:
            script = name + "_scripts.engcfg"
            self.log("   scripts: *** only %s, NOT compiled ***" % script)
            self.log("            Ctrl+G then Ctrl+H in campeditor produces the .script.")
            self.log("            A raw .engcfg made the game 001 on clicking the operation.")
        recs = [("desc", "config", "loc_def", desc),
                ("div_pool", "config", "loc_def", blob(name + "_div_pool.cfgpack")),
                ("op_image", "image", "loc_def", blob(name + "_op_image.tga")),
                ("scripts", "script", "loc_def", blob(script)),
                ("text", "text", "loc_eng", blob(name + "_text.loc_eng.textpack"))]
        for n, k, l, b in recs:
            self.log("   %-9s %-7s %-8s %9d bytes" % (n, k, l, len(b)))
        self.log("")
        self.log("STEP 5  pack")
        dst = os.path.join(self.install, "data", "mtc80", addon, "shared", "camps", chapter,
                           name + ".campack2")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        gtos_opstar._mkflat(recs, dst, self.install, os.path.join(work, "mkflat"), self.log)
        shutil.copy2(dst, os.path.join(proj, name + ".campack2"))
        self.log("")
        self.log("DONE  %s" % dst)
        return dst


# ------------------------------------------------------------------ GUI

def main():
    import tkinter as tk
    from tkinter import ttk, filedialog

    try:
        install0 = settings.get("sandbox")
    except Exception:
        install0 = ""

    root = tk.Tk()
    root.title("SABoW operation tool")
    root.geometry("1000x720")

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    vals = {}
    def field(r, label, key, default, browse=False):
        ttk.Label(top, text=label).grid(row=r, column=0, sticky="w", pady=2)
        e = ttk.Entry(top, width=80)
        e.insert(0, default)
        e.grid(row=r, column=1, sticky="we", pady=2)
        vals[key] = e
        if browse:
            def pick():
                d = filedialog.askdirectory(
                    initialdir=e.get() or os.path.expanduser("~"))
                if d:
                    e.delete(0, "end")
                    e.insert(0, os.path.normpath(d))
            ttk.Button(top, text="Browse...", command=pick).grid(row=r, column=2, padx=4)
    field(0, "Game install", "install", install0)
    field(1, "Operation project folder", "proj", "", True)   # empty: the user picks
    field(2, "Operation name", "name", "soko_test")
    field(3, "Chapter folder", "chapter", "1943_03_Kharkov")
    field(4, "Add-on to install into", "addon", "gtos_sokolovo_ob")
    top.columnconfigure(1, weight=1)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8)
    tabs = {}
    for t in ("1 Project", "2 Convert", "3 Editor", "4 Compile", "5 Pack"):
        fr = ttk.Frame(nb, padding=10)
        nb.add(fr, text=t)
        tabs[t] = fr

    def note(parent, text):
        w = tk.Text(parent, height=14, wrap="word", font=("Consolas", 9))
        w.insert("1.0", text)
        w.configure(state="disabled")
        w.pack(fill="both", expand=True)
        return w

    note(tabs["1 Project"],
         "HOW TO SET UP A NEW OPERATION\n"
         "\n"
         "1.  Click [Create project from stencil] below.\n"
         "    That makes the folder and copies Graviteam's template into it, renaming every file to\n"
         "    <name>. Nothing after this step works until it exists.\n"
         "\n"
         "2.  Open  SRC\\<name>.ods  in LibreOffice Calc.\n"
         "    One sheet called 'local'. Columns are:  A=description  B=format  C=key name  D=value.\n"
         "    You only ever edit column D. Change these rows:\n"
         "\n"
         "        key name        new value in column D\n"
         "        ------------------------------------------------------------------\n"
         "        chap_id         User_Ops                     (chapter shown in the menu)\n"
         "        polygon         polygons\\M_Sokolovo\\M_Sokolovo.cfgpack\n"
         "        camp_area       2, 2, 6, 6\n"
         "        date_beg        0x19430308                   (YYYY MM DD as hex)\n"
         "        turns           5\n"
         "\n"
         "    polygon MUST name a district this install has. Ours has exactly five:\n"
         "        7a_abualhasib   3o_oskol   k_kr_polana   5s_shilovo   m_sokolovo\n"
         "    The template ships set to 2T_Taranovka, which is not installed - the editor then shows a\n"
         "    black empty map and says nothing about why.\n"
         "\n"
         "3.  Save it: Ctrl+S. LibreOffice will ask about the format - choose [Use ODF Format!].\n"
         "\n"
         "4.  Open  SRC\\<name>_div_pool.ods  in Calc.     <- this is the one that makes a tank drivable\n"
         "    The sheet name is the operation's name. Scrolling down you will find a line reading\n"
         "    '{act_platoons'. Everything below it is a platoon, each starting with a line like\n"
         "    '1 tnk coy, 1 plat | {rkkapl_201_tbr_1c_1p | = |'.\n"
         "\n"
         "    Find the platoon that has a TANK in its list (look for rkka_t34, rkka_mk2, wer_pz4 ...).\n"
         "    Inside that platoon's block, on a fresh empty row, type four cells:\n"
         "\n"
         "        column A   column B   column C    column D\n"
         "        player     b          user_in     true\n"
         "\n"
         "    (A is just a note to yourself. B is the format, lowercase b for true/false.)\n"
         "    Without this row the operation loads and plays, but there is NO tank you can take - the\n"
         "    player never gets into the 3D world. The stencil has no user_in row anywhere, so it must\n"
         "    be added by hand.\n"
         "\n"
         "5.  Open  SRC\\<name>_text.ods  and change what the menu shows.\n"
         "    Columns:  D=marker name   E=Russian   F=English.  Edit E and F only.\n"
         "        txt_op_name     the operation's title in the list\n"
         "        txt_op_chap     the chapter heading\n"
         "    Leave the marker names in column D alone - they are the links.\n"
         "\n"
         "6.  Save all three, then go to the [2 Convert] tab.\n"
         "\n"
         "TIP  All three .ods files are ordinary spreadsheets. If a row you expect is missing, it is\n"
         "     safe to add it - the converter reads by key name, not by row position.")
    note(tabs["2 Convert"],
         "HOW TO CONVERT\n"
         "\n"
         "1.  Click [Convert .ods (resconv)] below.\n"
         "    It writes the conversion script and runs it in one go. You do not need to open a cmd\n"
         "    window, and you do not need to know where anything is.\n"
         "\n"
         "2.  Read the four lines it prints. For each of\n"
         "        <name>.camproj2\n"
         "        <name>_div_pool.cfgpack\n"
         "        <name>_text.loc_eng.textpack\n"
         "    you want to see 'regenerated (NNNN bytes)'.\n"
         "\n"
         "    'was NOT produced' or 'was NOT regenerated' means the .ods it came from is not valid.\n"
         "    Usually a cell you typed into the wrong column, or a save that kept a different format.\n"
         "    Fix the .ods, come back, click again. This is safe to repeat as often as you like.\n"
         "\n"
         "3.  When all three say regenerated, go to the [3 Editor] tab.\n"
         "\n"
         "WHY THIS TAB EXISTS\n"
         "    Graviteam's own tool for this (campgen) does the same job but asks you for a project\n"
         "    folder AND a name, and fails with 'Some project files not found' unless the two match\n"
         "    exactly. This tab skips that question entirely.")
    note(tabs["3 Editor"],
         "HOW TO PLACE THINGS (this one is a normal Windows program)\n"
         "\n"
         "1.  Click [Open editor], then open your project's .camproj2 when it asks.\n"
         "    You should see the map. If it is BLACK, your polygon in the .ods names a map this install\n"
         "    does not have - go back to tab 1.\n"
         "\n"
         "2.  Units tab.\n"
         "    On the right is a list of platoons. Click one, then click a square on the map. It appears\n"
         "    there. Right-click a square to remove one.\n"
         "    PLACE THE PLATOON THAT HAS YOUR TANK IN IT. Use the Side filter on the right to switch\n"
         "    between Germany and USSR. Place at least one enemy platoon too, or there is nothing to\n"
         "    fight.\n"
         "\n"
         "3.  Markers tab - optional for a first test.\n"
         "    F3 and F5 only SHOW or HIDE a layer of markers. They do not create anything, and on an\n"
         "    empty map they correctly show nothing. To add marks: pick a mode in the Group drop-down,\n"
         "    press F3 or F5, then left-click squares.\n"
         "\n"
         "4.  Press Ctrl+G, then Ctrl+H.\n"
         "    Ctrl+G converts the briefing picture. Ctrl+H compiles the script, and creates\n"
         "    <name>_scripts.script. THIS IS NOT OPTIONAL - without it the game crashes the moment you\n"
         "    click the operation in the menu. It cost us an hour to find.\n"
         "\n"
         "5.  Ctrl+S to save, then go to the [4 Compile] tab.\n"
         "\n"
         "IF IT CRASHES ON OPENING with 'Zero raw frame cnt in ext camp desc!':\n"
         "    delete <name>_frames.cfgpack in the project folder and open it again. The editor rebuilds\n"
         "    that file itself. This happens on the first ever open of a new project.")
    note(tabs["4 Compile"],
         "STAGE 4 - campcomp (Graviteam GUI)\n"
         "\n"
         "Writes the loose operation files. It does NOT make a .campack2 - stage 5 does that.\n"
         "\n"
         "It reports an ERROR for EVERY platoon you did not place:\n"
         "    ERROR! Platoon is out of area! rkkapl_xxx  4294967295, 4294967295\n"
         "That position is -1,-1, meaning 'not on the map'. It is not a fault - placing the platoon\n"
         "clears its error. The report is at out\\campcomp.report.\n"
         "\n"
         "This is also where the frames file becomes real: it may be a few KB before this and tens of KB\n"
         "after, because this is what writes the placement.")
    note(tabs["5 Pack"],
         "STAGE 5 - merge, verify and pack\n"
         "\n"
         "The campaign menu reads ONE archive, <name>.campack2, holding five records, and the record it\n"
         "opens, 'desc', is a MERGE of three loose files in a fixed order:\n"
         "\n"
         "    i_campgen:campgen            <- <name>.camproj2\n"
         "    reserves / pools / platoons  <- <name>_div_pool.cfgpack\n"
         "    frames, frames_raw, ai_orders, tac_markers, plat_pos, mg_nodes, mg_links\n"
         "                                 <- <name>_frames.cfgpack\n"
         "\n"
         "Pack only the frames as desc and the operation is simply ABSENT from the menu, with no error\n"
         "anywhere. That cost an entire evening to find.\n"
         "\n"
         "The merge runs cfgp2pd -> cfgfix -> concatenate -> pd2cfgp, preserving CRLF throughout:\n"
         "pd2cfgp given LF text emits an empty table and reports nothing at all.\n"
         "\n"
         "Every record is read back out of the finished archive and compared before this reports DONE,\n"
         "and it aborts before packing if any part or the merge fails its check.")

    logbox = tk.Text(root, height=18, wrap="none", font=("Consolas", 9))
    logbox.pack(fill="both", expand=False, padx=8, pady=(0, 8))

    busy = {"on": False}
    def log(msg):
        def do():
            logbox.insert("end", str(msg) + "\n")
            logbox.see("end")
        root.after(0, do)

    def check_inputs(need_proj):
        """Refuse before anything runs, in plain English. Release audit: the install used to be
        checked only inside launch(), so project and pack steps ran against an unchecked path -
        and a blank project folder would have made rmtree(join("", "_pack")) relative to wherever
        this happened to be running."""
        install = g("install")
        if not install:
            return "Fill in the Game install box first."
        if not os.path.isdir(install):
            return "That Game install folder does not exist:\n  %s" % install
        if not settings.is_sabow(install) and not settings.is_opstar(install):
            return ("That folder is not a Steel Armor or Operation Star install - there is no "
                    "starter.exe and data folder in it:\n  %s" % install)
        if need_proj:
            proj = g("proj")
            if not proj:
                return "Fill in the Operation project folder box first."
            if os.path.splitdrive(proj)[0] == "" and not os.path.isabs(proj):
                return ("Give the Operation project folder as a full path, not a relative one:\n"
                        "  %s" % proj)
            if not g("name"):
                return "Fill in the Operation name box first."
        return ""

    def guard(fn, need_proj=True):
        if busy["on"]:
            return
        problem = check_inputs(need_proj)
        if problem:
            log("")
            for line in problem.split("\n"):
                log(line)
            return
        busy["on"] = True
        def runner():
            try:
                fn()
            except Exception as e:
                # One sentence for the user; the traceback goes in a file they can send.
                log("")
                log("STOPPED: %s" % e)
                try:
                    where = os.path.join(HERE, "sabow_op_tool_error.txt")
                    with open(where, "w", encoding="utf-8") as fh:
                        fh.write(traceback.format_exc())
                    log("Full details: %s" % where)
                except OSError:
                    log(traceback.format_exc())
            finally:
                busy["on"] = False
        threading.Thread(target=runner, daemon=True).start()

    def g(k):
        return vals[k].get().strip()

    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=8)
    def btn(text, cmd):
        b = ttk.Button(bar, text=text, command=cmd)
        b.pack(side="left", padx=3)
        return b

    btn("Create project from stencil", lambda: guard(
        lambda: create_from_stencil(os.path.normpath(g("proj")), g("name"), g("install"), log)))
    btn("Convert .ods  (resconv)", lambda: guard(
        lambda: write_resconv(os.path.normpath(g("proj")), g("name"), g("install"), log)))
    btn("Open editor", lambda: guard(lambda: launch(g("install"), "campeditor", log), False))
    btn("Compile  (campcomp)", lambda: guard(lambda: launch(g("install"), "campcomp", log), False))
    btn("Check and pack", lambda: guard(lambda: Packer(g("install"), log).merge_and_pack(
        os.path.normpath(g("proj")), g("name"), g("chapter"), g("addon"))))
    btn("Clear log", lambda: logbox.delete("1.0", "end"))

    log("Stages 1, 2 and 5 are fully driven by this tool. 3 and 4 are Graviteam GUIs.")
    log("")
    log("Typical run: 1 Project (once) -> edit SRC\\*.ods -> 2 Convert -> 3 Editor")
    log("           (place platoons, Ctrl+G, Ctrl+H, Ctrl+S) -> 4 Compile -> 5 Pack")
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _startup_error('SABoW Operations Tool', "SABoW Operations Tool hit an error while starting.")
