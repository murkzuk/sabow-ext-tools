# SABoW Ext Control - see every vehicle in Steel Armor, what each needs to become
# playable, and make it playable. Double-click to open.
#
# Built the same way as BoW43 Control: big plain text, a tick or a cross, and
# every read done in the background so the window never freezes.
#
# Vehicles tab: reads only. Before it shows anything, it re-checks that it is
# reading the game's tables correctly (azcf.self_test). If that check fails, it
# says so in red and shows nothing - a wrong list is worse than no list.
#
# Make playable tab: pick a vehicle, the tool works out the recipe from the game
# (recipe.py), murkz ticks his choices and presses Build (build.py). The build
# goes into BUILD_LOG.md by itself; the next build stays locked until murkz has
# installed it, looked, and recorded one line (buildlog.py). A GOOD build is
# backed up as proven.

import os
import queue
import sys
import threading
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



# tkinter is imported AFTER _startup_error on purpose: it used to come first, so a Python
# built without tkinter died right here with nothing on screen - the exact failure the guard
# exists to prevent. Release audit 2026-10-06, the H4 residual.
try:
    import tkinter as tk
    from tkinter import ttk, filedialog
except Exception:
    _startup_error("SABoW Ext Control",
                   "This tool needs Python's tkinter, and this Python does not have it.\n\n"
                   "Install Python 3 from python.org, where tkinter is included, or on Linux "
                   "install the python3-tk package.")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL_DIR = HERE
try:
    import azcf        # noqa: E402
    import settings    # noqa: E402
    import vehicles    # noqa: E402
except Exception:
    _startup_error('SABoW Ext Control',
                   "SABoW Ext Control could not load its own modules (azcf.py, settings.py, vehicles.py).\n\n"
                   "It needs them in: " + TOOL_DIR)

REPO = os.path.dirname(HERE)
# The build record. In this project it is the repo's own BUILD_LOG.md, one level above the
# tool folder, and that stays the file used whenever it is there.
#
# On a RELEASED copy it is not there: the tools are unpacked into some folder and the parent
# is the user's Downloads. Until 2026-10-06 that was fatal - the window reads the log while
# it is still building its tabs, so the Control died at startup with FileNotFoundError on
# every machine but this one and showed the error box instead of a window. Found by
# double-clicking it, which no amount of import-checking had done.
# Two halves to the fix: buildlog.rows() now treats a missing log as "no builds yet", and the
# path falls back to the per-user settings folder, which is writable wherever the tools sit.
BUILD_LOG = os.path.join(REPO, "BUILD_LOG.md")
if not os.path.isfile(BUILD_LOG):
    BUILD_LOG = os.path.join(settings.config_dir(), "BUILD_LOG.md")
# Where frozen, proven packages are kept. It used to be the literal L:\sabow-ext-backups
# (release audit H3) - on a machine with no L: that made the SAFETY NET the thing that
# failed, and quietly. It is a setting now, defaulting to a folder beside the tools.
BACKUPS = settings.get("backups")


def _golden_available():
    """Whether this machine has the frozen proven archive the "Check the tool" button needs.

    Imported lazily and guarded: golden.py pulls in build and recipe, and a machine without the
    archive must not be stopped by any of that - it simply does not get the button.
    """
    try:
        import golden
        return golden.available()
    except Exception:
        return False

# Readable names for the vehicles we are confident about. Anything else shows
# the game's own internal name, rather than a guess.
READABLE = {
    "t62": "T-62", "t55": "T-55", "to55": "TO-55", "m60a1": "M60A1",
    "chief_mk5": "Chieftain Mk5", "olifant": "Olifant", "bmp1": "BMP-1",
    "btr60pb": "BTR-60PB", "m113a1": "M113A1", "ratel20": "Ratel 20",
    "ratel90": "Ratel 90", "ratel_cmd": "Ratel command", "brdm2": "BRDM-2",
}

BIG = ("Segoe UI", 16, "bold")
MID = ("Segoe UI", 12, "bold")
TXT = ("Segoe UI", 12)
GREEN, RED, AMBER = "#1b7a2b", "#b3261e", "#9a5b00"


class App(object):

    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()          # worker threads post here; poll() runs it
        self.install = settings.get("live")      # remembered between runs (settings.py)
        self.all = []
        root.title("SABoW Ext Control")
        root.geometry("1100x760")
        root.minsize(900, 600)
        style = ttk.Style()
        style.configure("Treeview", font=TXT, rowheight=30)
        style.configure("Treeview.Heading", font=MID)
        style.configure("TNotebook.Tab", font=MID, padding=(14, 6))

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.nb = nb
        self.tab = ttk.Frame(nb, padding=16)
        nb.add(self.tab, text="Vehicles")
        self.build_vehicles_tab()
        self.make = ttk.Frame(nb, padding=12)
        nb.add(self.make, text="Make playable")
        self.log_path, self.backup_root, self.zip_name = BUILD_LOG, BACKUPS, None
        self.plan = self.built = None
        self.busy = False
        self.build_make_tab()
        self.maps = ttk.Frame(nb, padding=12)
        nb.add(self.maps, text="GTOS maps")
        self.build_maps_tab()
        self.gv = ttk.Frame(nb, padding=12)
        nb.add(self.gv, text="GTOS vehicles")
        self.build_gv_tab()
        self.poll()
        self.refresh()

    def select_tab(self, name):
        """Open on a named tab, so a desktop shortcut can go straight to one tool.

        The tabs are Vehicles, Make playable, GTOS maps and GTOS vehicles. Without this the
        app always opens on the first one and a shortcut can only ever get you two clicks
        away from the tool you actually wanted.
        """
        for i in range(self.nb.index("end")):
            if str(self.nb.tab(i, "text")).strip().lower() == str(name).strip().lower():
                self.nb.select(i)
                return True
        return False

    # ---------- plumbing
    def poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def bg(self, work, done):
        def runner():
            try:
                result, err = work(), None
            except (Exception, SystemExit) as e:      # build.py stops with SystemExit
                result, err = None, e
            self.q.put(lambda: done(result, err))
        threading.Thread(target=runner, daemon=True).start()

    # ---------- the tab
    def build_vehicles_tab(self):
        t = self.tab
        top = ttk.Frame(t)
        top.pack(fill="x")
        ttk.Label(top, text="Game (Vehicles and Make playable):", font=MID).pack(side="left")
        self.l_install = ttk.Label(top, text="", font=TXT)
        self.l_install.pack(side="left", padx=8)
        ttk.Button(top, text="Choose a different install...", command=self.choose).pack(side="right")
        self.show_install()

        self.l_check = ttk.Label(t, text="", font=MID)
        self.l_check.pack(anchor="w", pady=(10, 2))
        self.l_summary = ttk.Label(t, text="Reading your game...", font=BIG, wraplength=1000, justify="left")
        self.l_summary.pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(t)
        row.pack(fill="x", pady=4)
        self.v_armour = tk.BooleanVar(value=True)
        self.v_ai = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Armoured vehicles only", variable=self.v_armour,
                        command=self.fill).pack(side="left")
        ttk.Checkbutton(row, text="AI-only only", variable=self.v_ai,
                        command=self.fill).pack(side="left", padx=18)
        ttk.Button(row, text="Check again", command=self.refresh).pack(side="right")

        cols = ("vehicle", "kind", "verdict", "cockpit", "source")
        self.tree = ttk.Treeview(t, columns=cols, show="headings", height=13)
        for c, w, h in (("vehicle", 170, "Vehicle"), ("kind", 170, "Kind"),
                        ("verdict", 300, "What it needs"), ("cockpit", 150, "Cockpit"),
                        ("source", 160, "Comes from")):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("playable", foreground=GREEN)
        self.tree.tag_configure("easy", foreground="#1f5fa8")
        self.tree.tag_configure("notpossible", foreground=RED)
        self.tree.pack(fill="x", pady=6)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.details())

        ttk.Label(t, text="About the selected vehicle:", font=MID).pack(anchor="w", pady=(10, 2))
        self.l_details = ttk.Label(t, text="Pick a vehicle in the list.", font=TXT,
                                   justify="left", wraplength=1000)
        self.l_details.pack(anchor="w")
        ttk.Button(t, text="Make the selected vehicle playable  >", command=self.to_make).pack(anchor="w", pady=8)

    def show_install(self):
        if settings.is_sabow(self.install):
            # THE RETAIL / GAMERSGATE BUILD IGNORES ADD-ONS, SILENTLY. It carries game update
            # 1.16 as a registered dev_updates add-on, and a user add-on cannot override that -
            # so every table this tool ships is dropped with no error and the game simply does
            # not change. Said here, loudly, because the alternative is a user believing the
            # tool is broken. See settings.channel().
            if settings.channel(self.install) == "retail":
                self.l_install.config(
                    text=self.install + "\n"
                    "!  RETAIL / GamersGate build. Update 1.16 ships here as a separate "
                    "dev_updates add-on, and a user add-on cannot override it.\n"
                    "   BLOCKED: the playable-vehicle add-on. It ships cocpits, common_res, "
                    "common_res_mod, div_units_misc and qbattle - all five are in dev_updates, "
                    "so all five are ignored, silently.\n"
                    "   WORKS: the GTOS maps, the order-of-battle pack, and everything that "
                    "reads. Their tables are new names and do not collide.",
                    foreground=RED)
            elif settings.channel(self.install) == "unknown":
                # SILENCE IS NOT AN ANSWER. Until 2026-10-06 anything that was not positively
                # identified as retail was shown as plain black text, i.e. exactly like a healthy
                # Steam install - so a machine we could not read was indistinguishable from a
                # machine that is fine. The failure being guarded against is INVISIBLE in game, so
                # "I could not tell" has to be said out loud.
                self.l_install.config(
                    text=self.install + "\n"
                    "?  Could not tell which build of the game this is. If it is the retail / "
                    "GamersGate one, the playable-vehicle add-on will be ignored silently and the "
                    "game will not change. The maps and the order of battle work either way.\n"
                    "   Check for a data\\<something>\\dev_updates folder: if one is there, this is "
                    "the retail build.",
                    foreground=RED)
            else:
                self.l_install.config(text=self.install, foreground="black")
        else:
            self.l_install.config(text=self.install + "   <- NOT FOUND: press Choose a different install...",
                                  foreground=RED)

    def choose(self):
        d = filedialog.askdirectory(title="Choose the Steel Armor install folder",
                                    initialdir=self.install if os.path.isdir(self.install) else "")
        if not d:
            return
        d = os.path.normpath(d)
        if not settings.is_sabow(d):
            self.l_install.config(text="%s is not a Steel Armor install (no starter.exe or tables) - nothing changed."
                                  % d, foreground=RED)
            return
        self.install = settings.put("live", d)
        import build                    # build.py and golden.py read build.INSTALL
        build.INSTALL = self.install
        self.show_install()
        if hasattr(self, "m_l_sandbox"):
            self.maps_show_sandbox()    # the maps tab warns if its sandbox IS this game
        self.refresh()

    # ---------- reading
    def refresh(self):
        self.l_check.config(text="Checking the table reader...", foreground=AMBER)
        self.l_summary.config(text="Reading your game...", foreground=AMBER)
        install = self.install

        def work():
            tabs = vehicles.paths(install)["tabs"]
            if not os.path.isfile(tabs):
                return (False, "No game found at that folder.", [])
            ok, msg = azcf.self_test(tabs)
            if not ok:
                return (False, msg, [])
            return (True, msg, vehicles.build(install))
        self.bg(work, self.show)

    def show(self, result, err):
        if err:
            self.l_check.config(text="X  Could not read the game: %s" % err, foreground=RED)
            self.l_summary.config(text="", foreground=RED)
            self.all = []
            self.fill()
            return
        ok, msg, vs = result
        if not ok:
            self.l_check.config(text="X  " + msg, foreground=RED)
            self.l_summary.config(text="Nothing is shown, because a wrong list would be worse than none.",
                                  foreground=RED)
            self.all = []
            self.fill()
            return
        problems = vehicles.known_answers(vs)
        self.trusted = not problems
        if problems:
            # The checks disagree with a real play-test, so the verdicts are wrong.
            self.l_check.config(text="X  The checks disagree with a real play-test, so verdicts are hidden: "
                                + "; ".join(problems), foreground=RED)
        else:
            self.l_check.config(text="OK  " + msg + ".  Checks agree with every known play-test.",
                                foreground=GREEN)
        self.all = vs
        choices = sorted("%s   (%s)" % (READABLE.get(v["vehicle"], v["vehicle"]), v["unit"])
                         for v in vs if v["armour"] and not v["crewable"])
        self.c_vehicle.config(values=choices)
        armour = [v for v in vs if v["armour"]]
        count = {k: sum(1 for v in armour if v["verdict"] == k)
                 for k in ("playable", "easy", "needs work", "not possible")}
        dlc_only = [v for v in vs if v["source"] == "DLC only"]
        if self.trusted:
            summary = ("%d armoured vehicles:  %d playable now,  %d easy,  %d need work,  %d not possible."
                       "   DLC-only: %d" % (len(armour), count["playable"], count["easy"],
                                            count["needs work"], count["not possible"], len(dlc_only)))
        else:
            summary = "%d armoured vehicles.  Verdicts hidden until the checks agree with the play-tests." % len(armour)
        self.l_summary.config(text=summary, foreground="black" if self.trusted else RED)
        self.fill()

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        self.shown = []
        for v in self.all:
            if self.v_armour.get() and not v["armour"]:
                continue
            if self.v_ai.get() and v["crewable"]:
                continue
            coc = v["cockpit"] or "-"
            if v["cockpit"] and not v["cockpit_exists"]:
                coc += "  (missing)"
            if getattr(self, "trusted", False):
                # Say what is MISSING. Printing the failed check's own label read
                # backwards - "needs work - gunner can aim up and down".
                missing = {"3": "no seat has a view", "4": "a crew seat has nothing to look through",
                           "5": "gunner can't aim up and down"}
                needs = [missing[label[0]] for label, ok, d in v["checks"] if not ok and label[0] in missing]
                words = {"playable": "Playable now",
                         "easy": "Easy - just the cockpit and crewable switch",
                         "needs work": "Needs work - " + "; ".join(needs),
                         "not possible": "Not possible - nowhere to put a crew"}[v["verdict"]]
                tags = ({"playable": "playable", "easy": "easy",
                         "not possible": "notpossible"}.get(v["verdict"], ""),)
            else:
                words, tags = "?", ()
            self.tree.insert("", "end", iid=str(len(self.shown)), tags=tags, values=(
                READABLE.get(v["vehicle"], v["vehicle"]), v["kind"], words, coc, v["source"]))
            self.shown.append(v)

    def details(self):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.shown[int(sel[0])]
        lines = [
            "%s   (game name: %s, unit %s)" % (READABLE.get(v["vehicle"], v["vehicle"]), v["vehicle"], v["unit"]),
            "Kind: %s" % v["kind"],
            "Playable now: %s" % ("yes" if v["crewable"] else "no - AI only"),
            "Cockpit: %s" % ((v["cockpit"] + ("" if v["cockpit_exists"] else " - NAMED BUT MISSING"))
                             if v["cockpit"] else "none"),
            "Comes from: %s" % v["source"],
        ]
        if getattr(self, "trusted", False):
            lines.append("")
            lines.append("The five checks:")
            for label, ok, detail in v["checks"]:
                lines.append("   %s   %s  -  %s" % ("✔" if ok else "✘", label[3:], detail))
            for w in v["warnings"]:
                lines.append("   note:  " + w)
        self.l_details.config(text="\n".join(lines))

    # ================================================================ Make playable
    def build_make_tab(self):
        t = self.make
        t.columnconfigure(0, weight=3)
        t.columnconfigure(1, weight=2)
        t.rowconfigure(2, weight=1)

        top = ttk.Frame(t)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="1. Vehicle:", font=MID).pack(side="left")
        self.c_vehicle = ttk.Combobox(top, font=TXT, width=34, state="readonly")
        self.c_vehicle.pack(side="left", padx=8)
        ttk.Button(top, text="Work out the recipe", command=self.work_out).pack(side="left")
        # The developer self-check rebuilds murkz's own frozen PROVEN builds and compares them
        # byte for byte, so it needs his backups archive. Offering the button to someone who
        # cannot possibly have that archive only produces a red CHECK STOPPED that reads like a
        # broken tool - which is exactly what happened to the first outside tester, 2026-10-06.
        # Shown only where the archive is.
        if _golden_available():
            ttk.Button(top, text="Check the tool (must rebuild the proven builds)",
                       command=self.golden_check).pack(side="right")

        self.l_lock = ttk.Label(t, text="", font=MID)
        self.l_lock.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 4))

        # left: the recipe and the choices
        left = ttk.Frame(t)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="2. What the tool found in your game, and why:", font=MID).grid(row=0, column=0, sticky="w")
        self.t_recipe = tk.Text(left, font=("Segoe UI", 12), wrap="word", height=14, padx=8, pady=6,
                                spacing1=2, spacing3=2)
        self.t_recipe.grid(row=1, column=0, sticky="nsew")
        self.t_recipe.tag_configure("step", font=("Segoe UI", 12, "bold"))
        self.t_recipe.tag_configure("why", foreground="#555555", lmargin1=28, lmargin2=28)
        self.t_recipe.tag_configure("warn", foreground=RED, font=("Segoe UI", 12, "bold"), lmargin2=28)
        self.t_recipe.tag_configure("head", font=("Segoe UI", 14, "bold"))
        ticks = ttk.Frame(left)
        ticks.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(ticks, text="3. Your choices:", font=MID).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(ticks, text="Crew who use this tank's own positions", font=TXT).grid(row=1, column=0, sticky="w")
        ttk.Label(ticks, text="Quick-battle platoons to open", font=TXT).grid(row=1, column=1, sticky="w", padx=(20, 0))
        self.f_crew = ttk.Frame(ticks)
        self.f_crew.grid(row=2, column=0, sticky="nw")
        self.f_plat = ttk.Frame(ticks)
        self.f_plat.grid(row=2, column=1, sticky="nw", padx=(20, 0))
        self.crew_vars, self.plat_vars = {}, {}

        # right: build, install, result
        right = ttk.Frame(t)
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        bframe = ttk.Frame(right)
        bframe.grid(row=0, column=0, sticky="ew")
        bframe.columnconfigure(0, weight=1)
        self.b_build = ttk.Button(bframe, text="4. Build", command=self.do_build, state="disabled")
        self.b_build.grid(row=0, column=0, sticky="ew", ipady=6)
        self.l_block = ttk.Label(bframe, text="", font=MID, wraplength=420, justify="left")
        self.l_block.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.t_log = tk.Text(right, font=("Consolas", 9), wrap="none", height=12)
        self.t_log.grid(row=1, column=0, sticky="nsew", pady=6)
        self.l_howto = ttk.Label(right, text="", font=TXT, wraplength=420, justify="left")
        self.l_howto.grid(row=2, column=0, sticky="w")
        inst = ttk.Frame(right)
        inst.grid(row=3, column=0, sticky="w", pady=4)
        self.b_installer = ttk.Button(inst, text="Open the installer (update.cmd)", command=self.open_installer,
                                      state="disabled")
        self.b_installer.pack(side="left")
        self.b_copyzip = ttk.Button(inst, text="Copy the zip path", command=self.copy_zip_path, state="disabled")
        self.b_copyzip.pack(side="left", padx=8)
        self.zip_to_install = None

        res = ttk.Frame(right)
        res.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(res, text="5. What you saw in the game (one line):", font=MID).pack(anchor="w")
        self.v_verdict = tk.StringVar(value="")
        rb = ttk.Frame(res)
        rb.pack(anchor="w")
        ttk.Radiobutton(rb, text="GOOD", value="GOOD", variable=self.v_verdict).pack(side="left")
        ttk.Radiobutton(rb, text="BAD", value="BAD", variable=self.v_verdict).pack(side="left", padx=12)
        self.e_line = ttk.Entry(res, font=TXT)
        self.e_line.pack(fill="x", pady=4)
        self.b_result = ttk.Button(res, text="Save my result", command=self.save_result)
        self.b_result.pack(anchor="w")
        self.l_saved = ttk.Label(res, text="", font=TXT, wraplength=420, justify="left")
        self.l_saved.pack(anchor="w", pady=4)
        self.update_lock()

    def say(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.config(state="disabled")

    def log_line(self, text):
        self.t_log.config(state="normal")
        self.t_log.insert("end", text + "\n")
        self.t_log.see("end")
        self.t_log.config(state="disabled")

    def qlog(self, text):
        """build.py and golden.py log from a worker thread - post, never touch Tk."""
        self.q.put(lambda text=text: self.log_line(text))

    def update_lock(self):
        import buildlog
        try:
            events = buildlog.rows(self.log_path)
        except OSError as e:
            self.l_lock.config(text="X  Cannot read the build log: %s" % e, foreground=RED)
            self.locked = True
            self.b_build.config(state="disabled")
            return
        self.locked, why = buildlog.lock(events)
        self.next_version = "v%d" % buildlog.next_version(events)
        if self.locked:
            last = [e for e in events if e["what"] == "BUILT"][-1]
            self.l_lock.config(text="Built %s - waiting for your result.  Install it, look in the game, "
                                    "then write one line in box 5." % last["version"], foreground=AMBER)
            if not self.built or self.built[0] != last["version"]:
                self.show_pending(last)
        else:
            self.l_lock.config(text="Ready.  The next build will be %s." % self.next_version, foreground=GREEN)
        reasons = []
        if self.busy:
            reasons.append("working - please wait")
        elif self.locked:
            reasons.append("the last build is waiting for your result in box 5")
        elif self.plan is None:
            reasons.append("pick a vehicle and press 'Work out the recipe' first")
        elif not any(v.get() for v in self.plat_vars.values()):
            reasons.append("tick at least one platoon - otherwise nobody can pick this tank in quick battle")
        self.b_build.config(state="disabled" if reasons else "normal")
        if reasons:
            self.l_block.config(text="Can't build yet: " + reasons[0],
                                foreground=AMBER if self.locked or self.busy else RED)
        else:
            self.l_block.config(text="Ready to build %s." % self.next_version, foreground=GREEN)

    def pending_from_log(self, row):
        """(zip path, unit, platoon ids) for a BUILT row written by this window."""
        import re
        import buildlog
        zpath = os.path.join(self.install, "users", "modwork", "sabow_ext",
                             "sabow_ext_v%03d.zip" % buildlog.number(row["version"]))
        m = re.match(r"^for (\S+),", row["notes"])
        p = re.search(r"platoons opened: ([^.]*)\.", row["notes"])
        return zpath, (m.group(1) if m else None), ([x.strip() for x in p.group(1).split(",")] if p else [])

    def show_pending(self, row):
        """A build from an earlier session is waiting: show how to install it."""
        zpath, unit, platoons = self.pending_from_log(row)
        labels = self.plan.platoon_labels if self.plan and self.plan.unit == unit else {}
        self.l_howto.config(text=(
            "Waiting for your result - %s (%s):\n"
            "  a) Open the installer below and choose:\n      %s\n"
            "  b) Quit the game fully, then relaunch it from Steam.\n"
            "  c) In quick battle, pick:\n%s\n"
            "  d) Look, then write one line in box 5." % (row["version"], unit or "?", zpath, "\n".join(
                "      %s" % labels.get(p, p) for p in platoons) or "      (see BUILD_LOG.md)")))
        update = os.path.join(self.install, "update.cmd")
        self.b_installer.config(state="normal" if os.path.isfile(update) else "disabled")
        self.zip_to_install = zpath
        self.b_copyzip.config(state="normal")

    def selected_unit(self):
        v = self.c_vehicle.get()
        return v[v.rfind("(") + 1:v.rfind(")")] if "(" in v else None

    def to_make(self):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.shown[int(sel[0])]
        if v["crewable"]:
            self.l_details.config(text="%s is already playable." % READABLE.get(v["vehicle"], v["vehicle"]))
            return
        self.c_vehicle.set("%s   (%s)" % (READABLE.get(v["vehicle"], v["vehicle"]), v["unit"]))
        self.nb.select(self.make)
        self.work_out()

    def work_out(self):
        import recipe
        unit = self.selected_unit()
        if not unit or self.busy:
            return
        self.plan = None
        self.update_lock()
        self.say(self.t_recipe, "Reading your game for %s ..." % unit)
        install = self.install
        self.bg(lambda: recipe.derive(install, unit), self.show_plan)

    def show_plan(self, plan, err):
        for f in (self.f_crew, self.f_plat):
            for w in f.winfo_children():
                w.destroy()
        self.crew_vars, self.plat_vars = {}, {}
        if err:
            self.say(self.t_recipe, "The tool could not work out a recipe:\n\n%s" % err)
            self.update_lock()
            return
        self.plan = plan
        self.show_recipe(plan)
        for chunk, real, where in plan.crew_candidates:
            var = tk.BooleanVar(value=chunk in plan.sync_modes)
            label = chunk if real else "%s  (no position in its model)" % chunk
            ttk.Checkbutton(self.f_crew, text=label, variable=var, command=self.update_lock,
                            state="normal" if real else "disabled").pack(anchor="w")
            self.crew_vars[chunk] = var
        words = {"off": "switch its crew flag on", "no flag": "ADD a crew flag - new, not yet proven",
                 "on": "already crewable"}
        for name, text, state in plan.platoon_candidates:
            var = tk.BooleanVar(value=name in plan.platoons)
            label = plan.platoon_labels.get(name, name)
            ttk.Checkbutton(self.f_plat, text="%s\n      %s" % (label, words[state]), variable=var,
                            command=self.update_lock,
                            state="disabled" if state == "on" else "normal").pack(anchor="w")
            self.plat_vars[name] = var
        self.update_lock()

    def show_recipe(self, plan):
        """The recipe in plain, spaced text: each step bold, its reason under it in
        grey, and anything the tool cannot do in red at the top."""
        w = self.t_recipe
        w.config(state="normal")
        w.delete("1.0", "end")
        w.insert("end", "%s  -  %s\n" % (READABLE.get(plan.vehicle, plan.vehicle), plan.unit), "head")
        if plan.warnings:
            w.insert("end", "\nThings to know (%d):\n" % len(plan.warnings), "warn")
            for text in plan.warnings:
                w.insert("end", "  !  %s\n" % text, "warn")
        w.insert("end", "\nWhat it will do:\n", "head")
        for name, answer, why in plan.steps:
            w.insert("end", "%s:  %s\n" % (name.capitalize(), answer), "step")
            w.insert("end", "because %s\n" % why, "why")
        w.config(state="disabled")

    def do_build(self):
        import recipe
        import build
        import buildlog
        self.update_lock()
        if self.locked or self.plan is None or self.busy:
            return
        unit, version, install = self.plan.unit, self.next_version, self.install
        choices = {"crew": [c for c, v in self.crew_vars.items() if v.get()],
                   "platoons": [p for p, v in self.plat_vars.items() if v.get()]}
        if not choices["platoons"]:
            self.log_line("Tick at least one platoon - otherwise nobody can pick the tank in quick battle.")
            return
        self.busy = True
        self.update_lock()
        self.t_log.config(state="normal")
        self.t_log.delete("1.0", "end")
        self.log_line("Building %s for %s ..." % (version, unit))

        def work():
            plan = recipe.derive(install, unit, choices)
            zpath = build.build(plan, int(version[1:]), install=install, log=self.qlog, zip_name=self.zip_name)
            what = ["for %s, built by SABoW Ext Control" % unit,
                    "donor %s, cockpit %s" % (plan.donor_unit, plan.cockpit)]
            for station, fields in plan.station_edits.items():
                what.append("%s %s" % (station, ", ".join("%s %s" % kv for kv in sorted(fields.items()))))
            what.append("crew following its own positions: %s" % (", ".join(plan.sync_modes) or "none"))
            what.append("hidden donor models: %s" % ", ".join(plan.hide_models))
            if plan.own_sight:
                what.append("own gunner sight %s (reticle %s) replacing %s" % (
                    plan.own_sight["row"], plan.own_sight["mesh"], plan.own_sight["donor_row"]))
            what.append("platoons opened: %s" % ", ".join(plan.platoons))
            what.append("md5 %s" % buildlog.md5(zpath))
            buildlog.append(self.log_path, "BUILT", version, ". ".join(what))
            return plan, zpath
        self.bg(work, lambda r, e: self.built_done(version, r, e))

    def built_done(self, version, result, err):
        self.busy = False
        if err:
            self.log_line("")
            self.log_line("BUILD STOPPED: %s" % err)
            self.log_line("Nothing was written to the build log. Nothing to install.")
            self.update_lock()
            return
        plan, zpath = result
        self.built = (version, zpath, plan)
        self.log_line("")
        self.log_line("BUILT %s - written to the build log." % version)
        update = os.path.join(self.install, "update.cmd")
        self.l_howto.config(text=(
            "Install it:\n"
            "  a) Open the installer below and choose:\n      %s\n"
            "  b) Quit the game fully, then relaunch it from Steam.\n"
            "  c) In quick battle, pick:\n%s\n"
            "  d) Look, then write one line in box 5." % (zpath, "\n".join(
                "      %s" % plan.platoon_labels.get(p, p) for p in plan.platoons))))
        self.b_installer.config(state="normal" if os.path.isfile(update) else "disabled")
        self.zip_to_install = zpath
        self.b_copyzip.config(state="normal")
        self.update_lock()

    def open_installer(self):
        # update.cmd is one line, "starter.exe root\programs\updater.progpack" - both
        # paths relative to the GAME folder. Started from anywhere else it cannot
        # find starter.exe and its console just closes, which is what os.startfile
        # did. Run it the way a double-click in the game folder does.
        import subprocess
        update = os.path.join(self.install, "update.cmd")
        if not os.path.isfile(update):
            self.log_line("No update.cmd in %s" % self.install)
            return
        if self.zip_to_install:
            self.copy_to_clipboard(self.zip_to_install)
        subprocess.Popen(["cmd.exe", "/c", update], cwd=self.install,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.log_line("Installer started from %s - the zip path is copied, paste it with Ctrl+V:" % self.install)
        self.log_line("  %s" % self.zip_to_install)

    def copy_zip_path(self):
        if self.zip_to_install:
            self.copy_to_clipboard(self.zip_to_install)
            self.log_line("Zip path copied - paste it with Ctrl+V in the installer's file box:")
            self.log_line("  %s" % self.zip_to_install)

    def save_result(self):
        import buildlog
        verdict, line = self.v_verdict.get(), self.e_line.get().strip()
        if verdict not in ("GOOD", "BAD") or not line:
            self.l_saved.config(text="Pick GOOD or BAD and write what you saw.", foreground=RED)
            return
        events = buildlog.rows(self.log_path)
        locked, _ = buildlog.lock(events)
        if not locked:
            self.l_saved.config(text="There is no build waiting for a result.", foreground=AMBER)
            return
        # Refuse if the row this would be recorded against is not one of THIS window's builds.
        # 2026-09-29: a hand-written "| BUILT | v016 |" row for the gtos_sokolovo_ob add-on became the
        # newest numbered build, so the window asked for a verdict on it, murkz gave one, and the
        # backup step archived sabow_ext_v016.zip as PROVEN with his words attached.
        target, problem = buildlog.newest_numbered_build(events)
        if problem:
            self.l_saved.config(text="X  " + problem, foreground=RED)
            return
        version = target["version"]
        if self.built and self.built[0] == version:
            _, zpath, plan = self.built
            unit, report = plan.unit, plan.report()
        else:          # built in an earlier session of the window
            row = [e for e in events if e["what"] == "BUILT" and e["version"] == version][-1]
            zpath, unit, _ = self.pending_from_log(row)
            unit = unit or "unknown unit"
            report = "(built in an earlier session of the window)\n" + row["notes"]
        notes = "murkz: \"%s\"" % line
        if verdict == "GOOD":
            try:
                folder = buildlog.backup(zpath, version, unit, line, report, self.backup_root)
                notes += " Backed up to %s." % folder
            except Exception as e:
                self.l_saved.config(text="X  Could not back it up, so nothing was saved: %s" % e, foreground=RED)
                return
        buildlog.append(self.log_path, verdict, version, notes)
        self.l_saved.config(text="Saved: %s %s.%s" % (verdict, version,
                                                      " Backed up as proven." if verdict == "GOOD" else ""),
                            foreground=GREEN if verdict == "GOOD" else AMBER)
        self.v_verdict.set("")
        self.e_line.delete(0, "end")
        self.update_lock()

    def golden_check(self):
        import golden
        if self.busy:
            return
        self.busy = True
        self.update_lock()
        self.t_log.config(state="normal")
        self.t_log.delete("1.0", "end")
        self.log_line("Checking the tool: it must rebuild every proven build exactly (T-55 v9, v21, v24; Olifant v12; Chieftain v14, v15) ...")
        self.bg(lambda: golden.run(log=self.qlog), self.golden_done)

    def golden_done(self, ok, err):
        self.busy = False
        self.log_line("")
        if err:
            self.log_line("CHECK STOPPED: %s" % err)
        else:
            self.log_line("THE TOOL IS RIGHT - it rebuilds the proven builds exactly." if ok
                          else "THE TOOL IS WRONG - do not build with it until this is fixed.")
        self.update_lock()

    # ================================================================ GTOS maps
    # A Graviteam Tactics map pack, made playable in SABoW (gtos_maps.py). Everything goes
    # into the SANDBOX install: a GTOS pack's tables sit in front of SABoW Ext's own.
    def build_maps_tab(self):
        import gtos_maps
        t = self.maps
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)
        t.rowconfigure(3, weight=1)
        self.m_packs, self.m_info, self.m_final, self.m_busy = [], None, None, False
        self.m_sandbox = settings.get("sandbox")

        r0 = ttk.Frame(t)
        r0.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(r0, text="1. GTOS pack:", font=MID).pack(side="left")
        self.m_combo = ttk.Combobox(r0, font=TXT, width=48, state="readonly")
        self.m_combo.pack(side="left", padx=8)
        self.m_combo.bind("<<ComboboxSelected>>", lambda e: self.maps_picked())
        ttk.Button(r0, text="Browse...", command=self.maps_browse).pack(side="left")
        ttk.Button(r0, text="Look for packs again", command=self.maps_find).pack(side="left", padx=8)

        r1 = ttk.Frame(t)
        r1.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r1a = ttk.Frame(r1)
        r1a.pack(fill="x")
        ttk.Label(r1a, text="Converts and installs into:", font=MID).pack(side="left")
        self.m_l_sandbox = ttk.Label(r1a, text="", font=TXT)
        self.m_l_sandbox.pack(side="left", padx=8)
        ttk.Button(r1a, text="Choose...", command=self.maps_choose_sandbox).pack(side="right")

        # Operation Star's own maps need its tables, models and textures (gtos_opstar.py).
        # Read from the Operation Star install itself - pristine, never BoW43's copies.
        import gtos_opstar
        saved = settings.get("opstar")
        self.m_opstar = saved if gtos_opstar.is_opstar(saved) else ""
        r1b = ttk.Frame(r1)
        r1b.pack(fill="x", pady=(6, 0))
        ttk.Label(r1b, text="Missing game data from:", font=MID).pack(side="left")
        self.m_l_opstar = ttk.Label(r1b, text="", font=TXT)
        self.m_l_opstar.pack(side="left", padx=8)
        ttk.Button(r1b, text="Choose...", command=self.maps_choose_opstar).pack(side="right")

        r2 = ttk.Frame(t)
        r2.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        self.m_b_check = ttk.Button(r2, text="2. Check it", command=self.maps_check)
        self.m_b_check.pack(side="left", ipady=4)
        self.m_b_convert = ttk.Button(r2, text="3. Convert for SABoW", command=self.maps_convert, state="disabled")
        self.m_b_convert.pack(side="left", padx=10, ipady=4)
        self.m_l_status = ttk.Label(r2, text="", font=MID, wraplength=620, justify="left")
        self.m_l_status.pack(side="left", padx=10)

        self.m_report = tk.Text(t, font=("Segoe UI", 12), wrap="word", height=14, padx=8, pady=6)
        self.m_report.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        self.m_log = tk.Text(t, font=("Consolas", 9), wrap="none", height=14)
        self.m_log.grid(row=3, column=1, sticky="nsew")

        r4 = ttk.Frame(t)
        r4.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r4.columnconfigure(1, weight=1)
        self.m_b_install = ttk.Button(r4, text="4. Open the sandbox installer (update.cmd)",
                                      command=self.maps_open_installer, state="disabled")
        self.m_b_install.grid(row=0, column=0, sticky="w")
        ttk.Label(r4, text="Pack to choose:", font=MID).grid(row=1, column=0, sticky="w", pady=(6, 0))
        # an Entry, not a Label: the path can be selected, and the button copies it
        self.m_path = tk.StringVar(value="")
        ttk.Entry(r4, textvariable=self.m_path, font=TXT, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=8, pady=(6, 0))
        self.m_b_copy = ttk.Button(r4, text="Copy path", command=self.maps_copy_path, state="disabled")
        self.m_b_copy.grid(row=1, column=2, sticky="e", pady=(6, 0))
        self.m_l_howto = ttk.Label(r4, text="", font=TXT, wraplength=1000, justify="left")
        self.m_l_howto.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        r5 = ttk.Frame(t)
        r5.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(r5, text="5. What you saw in the game (one line):", font=MID).pack(side="left")
        self.m_verdict = tk.StringVar(value="")
        ttk.Radiobutton(r5, text="GOOD", value="GOOD", variable=self.m_verdict).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(r5, text="BAD", value="BAD", variable=self.m_verdict).pack(side="left", padx=8)
        self.m_line = ttk.Entry(r5, font=TXT, width=40)
        self.m_line.pack(side="left", fill="x", expand=True)
        ttk.Button(r5, text="Save my result", command=self.maps_save_result).pack(side="left", padx=8)
        self.m_l_saved = ttk.Label(t, text="", font=TXT)
        self.m_l_saved.grid(row=6, column=0, columnspan=2, sticky="w")

        self.maps_show_sandbox()
        self.maps_show_opstar()
        self.maps_find()

    def maps_log(self, text):
        self.m_log.config(state="normal")
        self.m_log.insert("end", text + "\n")
        self.m_log.see("end")
        self.m_log.config(state="disabled")

    def maps_qlog(self, text):
        self.q.put(lambda text=text: self.maps_log(text))

    def maps_show_sandbox(self):
        live = os.path.normcase(os.path.normpath(self.m_sandbox)) == os.path.normcase(os.path.normpath(self.install))
        if live:
            self.m_l_sandbox.config(text=self.m_sandbox + "   <- YOUR LIVE GAME: GTOS packs sit in front of SABoW Ext. "
                                    "Use the sandbox.", foreground=RED)
        elif not settings.is_sabow(self.m_sandbox):
            self.m_l_sandbox.config(text=self.m_sandbox + "   <- NOT FOUND: press Choose...", foreground=RED)
        else:
            self.m_l_sandbox.config(text=self.m_sandbox, foreground="black")

    def maps_choose_sandbox(self):
        d = filedialog.askdirectory(title="Choose the SANDBOX Steel Armor install",
                                    initialdir=self.m_sandbox if os.path.isdir(self.m_sandbox) else "")
        if not d:
            return
        d = os.path.normpath(d)
        if not settings.is_sabow(d):
            self.m_l_status.config(text="X  That folder is not a Steel Armor install (no starter.exe or tables).",
                                   foreground=RED)
            return
        self.m_sandbox = settings.put("sandbox", d)
        self.maps_show_sandbox()
        self.maps_picked()

    def maps_show_opstar(self):
        if self.m_opstar:
            self.m_l_opstar.config(text="Operation Star - " + self.m_opstar, foreground="black")
        else:
            self.m_l_opstar.config(text="(no Operation Star install - Operation Star's own maps cannot be made playable)",
                                   foreground=AMBER)

    def maps_choose_opstar(self):
        import gtos_opstar
        d = filedialog.askdirectory(title="Choose the Graviteam Tactics: Operation Star install",
                                    initialdir=self.m_opstar or "G:\\")
        if not d:
            return
        d = os.path.normpath(d)
        if not gtos_opstar.is_opstar(d):
            self.m_l_status.config(text="X  That folder is not an Operation Star install (no data\\k43t).",
                                   foreground=RED)
            return
        self.m_opstar = settings.put("opstar", d)
        self.maps_show_opstar()
        self.maps_picked()

    def maps_find(self):
        import gtos_maps
        self.m_packs = gtos_maps.find_packs()
        self.m_combo.config(values=[os.path.basename(p) for p in self.m_packs])
        self.m_l_status.config(text="%d GTOS packs found in %s" % (len(self.m_packs), ", ".join(gtos_maps.PACK_FOLDERS)),
                               foreground="black")

    def maps_browse(self):
        f = filedialog.askopenfilename(title="Choose a GTOS pack", filetypes=[("GTOS pack", "*.gt2extension")])
        if f:
            f = os.path.normpath(f)
            if f not in self.m_packs:
                self.m_packs.append(f)
                self.m_combo.config(values=[os.path.basename(p) for p in self.m_packs])
            self.m_combo.set(os.path.basename(f))
            self.maps_picked()

    def maps_pack(self):
        i = self.m_combo.current()
        return self.m_packs[i] if 0 <= i < len(self.m_packs) else None

    def maps_picked(self):
        self.m_info = self.m_final = None
        self.m_b_convert.config(state="disabled")
        self.m_b_install.config(state="disabled")
        self.m_b_copy.config(state="disabled")
        self.m_path.set("")
        self.m_l_howto.config(text="")
        self.say(self.m_report, "Press 2. Check it - nothing is changed by checking.")
        self.m_l_status.config(text="", foreground="black")

    def maps_set_busy(self, busy, text=""):
        self.m_busy = busy
        state = "disabled" if busy else "normal"
        self.m_b_check.config(state=state)
        if busy:
            self.m_b_convert.config(state="disabled")
        self.m_l_status.config(text=text, foreground=AMBER if busy else "black")

    def maps_check(self):
        import gtos_maps
        pack = self.maps_pack()
        if not pack or self.m_busy:
            self.m_l_status.config(text="Pick a pack first.", foreground=RED)
            return
        self.maps_picked()
        self.m_log.config(state="normal")
        self.m_log.delete("1.0", "end")
        self.maps_set_busy(True, "Checking %s ... (reads every map cell, can take a minute)" % os.path.basename(pack))
        sandbox, opstar = self.m_sandbox, self.m_opstar
        self.bg(lambda: gtos_maps.check(pack, sandbox, self.maps_qlog, opstar), self.maps_check_done)

    def maps_check_done(self, info, err):
        import gtos_maps
        self.maps_set_busy(False)
        if err:
            self.say(self.m_report, "Could not check this pack:\n\n%s" % err)
            self.m_l_status.config(text="X  Check failed", foreground=RED)
            return
        self.m_info = info
        self.say(self.m_report, gtos_maps.report(info))
        if info["problems"]:
            self.m_l_status.config(text="X  This pack cannot be converted safely.", foreground=RED)
        elif info["missing_map_tables"]:
            self.m_l_status.config(text="X  Can't play yet - the map needs game data SABoW doesn't have (see the report).",
                                   foreground=RED)
        elif gtos_maps.needs_converting(info):
            self.m_l_status.config(text="Needs converting - press 3." + (
                "  It copies in Operation Star data, so it takes longer." if info.get("borrow") else ""),
                foreground=AMBER)
            self.m_b_convert.config(state="normal")
        else:
            self.m_l_status.config(text="Nothing to convert - it can be installed as it is.", foreground=GREEN)
            self.maps_ready(info["pack"])

    def maps_convert(self):
        import gtos_maps
        if not self.m_info or self.m_busy:
            return
        info, sandbox = self.m_info, self.m_sandbox
        self.maps_set_busy(True, "Converting - this takes a few minutes. The window stays usable.")
        self.maps_log("")
        self.bg(lambda: gtos_maps.convert(info["pack"], sandbox, self.maps_qlog, info), self.maps_convert_done)

    def maps_convert_done(self, final, err):
        self.maps_set_busy(False)
        if err:
            self.maps_log("")
            self.maps_log("CONVERT STOPPED: %s" % err)
            self.maps_log("Nothing was produced. Nothing to install.")
            self.m_l_status.config(text="X  Convert stopped - see the log on the right.", foreground=RED)
            return
        self.m_l_status.config(text="Converted and checked.", foreground=GREEN)
        self.maps_ready(final or self.m_info["pack"])

    def maps_ready(self, pack_file):
        self.m_final = pack_file
        update = os.path.join(self.m_sandbox, "update.cmd")
        self.m_b_install.config(state="normal" if os.path.isfile(update) else "disabled")
        self.m_path.set(pack_file)
        self.m_b_copy.config(state="normal")
        self.m_l_howto.config(text=(
            "a) Press 4 - it opens the installer AND copies the path above.  Press Install, click in the\n"
            "    file-name box and paste it with Ctrl+V.\n"
            "b) Save and Play, then start a quick battle on this pack's map.   c) Write one line in 5."))

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()          # keeps the text on the clipboard after the window loses focus

    def maps_copy_path(self):
        if self.m_final:
            self.copy_to_clipboard(self.m_final)
            self.m_l_status.config(text="Path copied - paste it with Ctrl+V in the installer's file box.",
                                   foreground=GREEN)

    def maps_open_installer(self):
        import subprocess
        update = os.path.join(self.m_sandbox, "update.cmd")
        if not os.path.isfile(update):
            self.maps_log("No update.cmd in %s" % self.m_sandbox)
            return
        if self.m_final:
            self.copy_to_clipboard(self.m_final)
        subprocess.Popen(["cmd.exe", "/c", update], cwd=self.m_sandbox, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.maps_log("Installer started from %s - the pack path is copied, paste it with Ctrl+V:" % self.m_sandbox)
        self.maps_log("  %s" % self.m_final)
        self.m_l_status.config(text="Installer opening - the path is copied, paste it with Ctrl+V.", foreground=GREEN)

    def maps_save_result(self):
        import buildlog
        import gtos_maps
        import shutil
        verdict, line = self.m_verdict.get(), self.m_line.get().strip()
        if verdict not in ("GOOD", "BAD") or not line:
            self.m_l_saved.config(text="Pick GOOD or BAD and write what you saw.", foreground=RED)
            return
        if not self.m_info or not self.m_final or not os.path.isfile(self.m_final):
            self.m_l_saved.config(text="Check (and convert) a pack first - there is nothing to record yet.", foreground=RED)
            return
        name, digest = self.m_info["name"], gtos_maps.md5(self.m_final)
        notes = "murkz: \"%s\". Pack %s md5 %s, installed in %s." % (line, self.m_final, digest, self.m_sandbox)
        if verdict == "GOOD":
            # Never overwrite an earlier proven pack (2026-09-17: a GOOD for Sokolovo with object models replaced the
            # proven ce01e1d0 in map_..._PROVEN). Same pack again -> same folder; a different pack -> the next _vN.
            folder, n = os.path.join(self.backup_root, "map_%s_PROVEN" % name), 1
            while True:
                old = os.path.join(folder, os.path.basename(self.m_final))
                if not os.path.isfile(old) or gtos_maps.md5(old) == digest:
                    break
                n += 1
                folder = os.path.join(self.backup_root, "map_%s_PROVEN_v%d" % (name, n))
            try:
                os.makedirs(folder, exist_ok=True)
                dest = os.path.join(folder, os.path.basename(self.m_final))
                shutil.copy2(self.m_final, dest)
                if gtos_maps.md5(dest) != digest:
                    raise OSError("the backup copy does not match")
                with open(os.path.join(folder, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(gtos_maps.report(self.m_info) + "\n\nmurkz: %s\nmd5 %s\n" % (line, digest))
            except OSError as e:
                self.m_l_saved.config(text="X  Could not back it up, so nothing was saved: %s" % e, foreground=RED)
                return
            notes += " Backed up to %s." % folder
        buildlog.append(self.log_path, verdict, "map:" + name, notes)
        self.m_l_saved.config(text="Saved: %s for %s.%s" % (verdict, name, " Backed up as proven." if verdict == "GOOD" else ""),
                              foreground=GREEN if verdict == "GOOD" else AMBER)
        self.m_verdict.set("")
        self.m_line.delete(0, "end")

    # ================================================================ GTOS vehicles
    # An Operation Star vehicle brought into SABoW as the add-on gtos_ww2 (gtos_vehicle.py), built into
    # the same install the GTOS maps tab uses - never the live game. One build, one look, one line.
    def build_gv_tab(self):
        import gtos_vehicle
        t = self.gv
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)
        t.rowconfigure(3, weight=1)
        self.gv_busy, self.gv_info, self.gv_zip, self.gv_version = False, None, None, None

        r0 = ttk.Frame(t)
        r0.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(r0, text="1. Operation Star vehicle:", font=MID).pack(side="left")
        self.gv_keys = sorted(gtos_vehicle.VEHICLES)
        self.gv_combo = ttk.Combobox(r0, font=TXT, width=36, state="readonly",
                                     values=["%s  (%s)" % (gtos_vehicle.READABLE.get(k, k), k) for k in self.gv_keys])
        self.gv_combo.pack(side="left", padx=8)
        self.gv_combo.bind("<<ComboboxSelected>>", lambda e: self.gv_picked())
        ttk.Button(r0, text="Add an Operation Star vehicle...", command=self.gv_add_dialog).pack(side="left")
        ttk.Button(r0, text="Make this one playable...", command=self.gv_make_playable).pack(side="left", padx=6)
        ttk.Button(r0, text="Check the tool (must rebuild the proven builds)", command=self.gv_check_tool).pack(side="right")
        ttk.Button(r0, text="Check the build (will it build?)", command=self.gv_check_build).pack(side="right", padx=8)
        ttk.Button(r0, text="Repack / flat back...", command=self.gv_repack).pack(side="right", padx=8)
        ttk.Button(r0, text="Extract to workspace...", command=self.gv_extract).pack(side="right")
        rarc = ttk.Frame(t)
        rarc.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(rarc, text="Any archive:", font=MID).pack(side="left")
        ttk.Button(rarc, text="Unflat an archive...", command=self.gv_unflat).pack(side="left", padx=6)
        ttk.Label(rarc, text="every record out as a file you can edit, then flat back",
                  font=TXT).pack(side="left")
        rcfg = ttk.Frame(t)
        rcfg.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(rcfg, text="Tables:", font=MID).pack(side="left")
        ttk.Button(rcfg, text="Tables to text...", command=self.gv_cfg_out).pack(side="left", padx=6)
        ttk.Button(rcfg, text="Text back to tables...", command=self.gv_cfg_in).pack(side="left")
        ttk.Label(rcfg, text="readable, editable, and proven to compile back before you touch it",
                  font=TXT).pack(side="left", padx=8)
        ttk.Button(rcfg, text="Show its fields...", command=self.gv_techn_show).pack(side="left", padx=(18, 6))
        ttk.Button(rcfg, text="Change a field...", command=self.gv_techn_set).pack(side="left")
        ttk.Button(rarc, text="Textures to DDS...", command=self.gv_atf2dds).pack(side="left", padx=(18, 6))
        ttk.Button(rarc, text="DDS back to texture...", command=self.gv_dds2atf).pack(side="left")

        r1 = ttk.Frame(t)
        r1.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r1a = ttk.Frame(r1)
        r1a.pack(fill="x")
        ttk.Label(r1a, text="Builds into:", font=MID).pack(side="left")
        self.gv_l_install = ttk.Label(r1a, text="", font=TXT)
        self.gv_l_install.pack(side="left", padx=8)
        ttk.Label(r1a, text="(the same install as the GTOS maps tab - choose it there)", font=TXT).pack(side="left")
        r1b = ttk.Frame(r1)
        r1b.pack(fill="x", pady=(4, 0))
        ttk.Label(r1b, text="Operation Star:", font=MID).pack(side="left")
        self.gv_l_opstar = ttk.Label(r1b, text="", font=TXT)
        self.gv_l_opstar.pack(side="left", padx=8)

        r2 = ttk.Frame(t)
        r2.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        self.gv_b_check = ttk.Button(r2, text="2. Check it", command=self.gv_check)
        self.gv_b_check.pack(side="left", ipady=4)
        self.gv_b_build = ttk.Button(r2, text="3. Build", command=self.gv_build, state="disabled")
        self.gv_b_build.pack(side="left", padx=10, ipady=4)
        self.gv_l_status = ttk.Label(r2, text="", font=MID, wraplength=700, justify="left")
        self.gv_l_status.pack(side="left", padx=10)

        self.gv_report = tk.Text(t, font=("Segoe UI", 12), wrap="word", height=14, padx=8, pady=6)
        self.gv_report.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        self.gv_log = tk.Text(t, font=("Consolas", 9), wrap="none", height=14)
        self.gv_log.grid(row=3, column=1, sticky="nsew")

        r4 = ttk.Frame(t)
        r4.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r4.columnconfigure(1, weight=1)
        self.gv_b_install = ttk.Button(r4, text="4. Open the installer (update.cmd)", command=self.gv_open_installer,
                                       state="disabled")
        self.gv_b_install.grid(row=0, column=0, sticky="w")
        ttk.Label(r4, text="Add-on to install:", font=MID).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.gv_path = tk.StringVar(value="")
        ttk.Entry(r4, textvariable=self.gv_path, font=TXT, state="readonly").grid(row=1, column=1, sticky="ew", padx=8, pady=(6, 0))
        self.gv_b_copy = ttk.Button(r4, text="Copy path", command=lambda: self.gv_zip and self.copy_to_clipboard(self.gv_zip),
                                    state="disabled")
        self.gv_b_copy.grid(row=1, column=2, sticky="e", pady=(6, 0))
        self.gv_l_howto = ttk.Label(r4, text="", font=TXT, wraplength=1000, justify="left")
        self.gv_l_howto.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        r5 = ttk.Frame(t)
        r5.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(r5, text="5. What you saw in the game (one line):", font=MID).pack(side="left")
        self.gv_verdict = tk.StringVar(value="")
        ttk.Radiobutton(r5, text="GOOD", value="GOOD", variable=self.gv_verdict).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(r5, text="BAD", value="BAD", variable=self.gv_verdict).pack(side="left", padx=8)
        self.gv_line = ttk.Entry(r5, font=TXT, width=40)
        self.gv_line.pack(side="left", fill="x", expand=True)
        ttk.Button(r5, text="Save my result", command=self.gv_save_result).pack(side="left", padx=8)
        self.gv_l_saved = ttk.Label(t, text="", font=TXT)
        self.gv_l_saved.grid(row=6, column=0, columnspan=2, sticky="w")

        if self.gv_keys:
            self.gv_combo.current(0)
        self.gv_picked()

    def gv_log_line(self, text):
        self.gv_log.config(state="normal")
        self.gv_log.insert("end", text + "\n")
        self.gv_log.see("end")
        self.gv_log.config(state="disabled")

    def gv_qlog(self, text):
        self.q.put(lambda text=text: self.gv_log_line(text))

    def gv_vehicle(self):
        i = self.gv_combo.current()
        return self.gv_keys[i] if 0 <= i < len(self.gv_keys) else None

    # ---------- "Add an Operation Star vehicle" (2026-09-18): murkz adds vehicles himself, no code change.
    # The tool works the settings out of the two games (gtos_vehicle.propose) and saves them to his own file.
    def gv_refill_vehicles(self, pick=None):
        import gtos_vehicle
        self.gv_keys = sorted(gtos_vehicle.VEHICLES)
        self.gv_combo.config(values=["%s  (%s)" % (gtos_vehicle.READABLE.get(k, k), k) for k in self.gv_keys])
        if pick in self.gv_keys:
            self.gv_combo.current(self.gv_keys.index(pick))
        elif self.gv_keys:
            self.gv_combo.current(0)
        self.gv_picked()

    def gv_add_dialog(self):
        import gtos_vehicle
        install, opstar, live = self.gv_folders()
        if live:
            return
        win = tk.Toplevel(self.root)      # App is not a widget - Toplevel(self) raises, and pythonw shows nothing
        win.title("Add an Operation Star vehicle")
        win.geometry("1100x640")
        win.transient(self.root)
        top = ttk.Frame(win, padding=10)
        top.pack(fill="both", expand=True)
        top.rowconfigure(2, weight=1)
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Every Operation Star vehicle the tool can bring in as an AI vehicle.", font=MID)\
            .grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(top, text="Pick one, read what the tool works out, then Add it. It joins the next build you make.",
                  font=TXT).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        listing = tk.Listbox(top, font=("Segoe UI", 11), width=46, exportselection=False)
        listing.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        report = tk.Text(top, font=("Segoe UI", 11), wrap="word", padx=8, pady=6)
        report.grid(row=2, column=1, sticky="nsew")
        bottom = ttk.Frame(top)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        status = ttk.Label(bottom, text="Reading both games ...", font=TXT)
        status.pack(side="left")
        b_add = ttk.Button(bottom, text="Add this vehicle", state="disabled")
        b_add.pack(side="right")
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right", padx=8)
        # plan-automate-playable.md step 4. Default OFF on purpose: importing AI-only stays the safe
        # default, and a playable vehicle costs a cockpit and a sight row. Ticking it makes the SAME
        # import crewable in one pass, using derive_playable - and if the deriver refuses, Add stops
        # rather than writing a crewable row that names something which does not exist.
        playable = tk.BooleanVar(value=False)
        cb_playable = ttk.Checkbutton(bottom, text="Also make it playable (crewable)", variable=playable)
        cb_playable.pack(side="right", padx=12)
        state = {"rows": [], "spec": None, "vehicle": None}

        def show(text):
            report.config(state="normal")
            report.delete("1.0", "end")
            report.insert("1.0", text)
            report.config(state="disabled")

        def listed(result, err):
            if err:
                status.config(text="Could not read the vehicles: %s" % err, foreground=RED)
                return
            state["rows"] = result
            listing.delete(0, "end")
            for v, label, kind, known in result:
                listing.insert("end", "%s%s  [%s]" % ("* " if known else "", label, kind))
            status.config(text="%d vehicles; * = already in the tool." % len(result), foreground="black")

        def catalogue():
            cat = gtos_vehicle.opstar_catalogue(opstar)
            texts = gtos_vehicle.stock_texts(install)
            src = gtos_vehicle.gtos_opstar.Index(gtos_vehicle.gtos_opstar.opstar_archives(opstar))
            tb = gtos_vehicle.azcf.Table(gtos_vehicle.gtos_opstar.read(*src.records[("techn_base", "config")]))
            blocks = dict(gtos_vehicle.azcf.vehicles(tb))
            rows = []
            for v, c in cat.items():
                kind = ""
                if v in blocks and "props" in blocks[v]:
                    k = tb.props(blocks[v]["props"]).get("type")
                    kind = gtos_vehicle.recipe.fourcc(k) if isinstance(k, int) else str(k)
                label = texts.get(c["squad_text"], v).replace("$n", " / ")
                rows.append((v, "%s  (%s)" % (label, v), kind, v in gtos_vehicle.VEHICLES))
            return sorted(rows, key=lambda r: (r[2], r[1].lower()))

        def picked(_e=None):
            sel = listing.curselection()
            if not sel:
                return
            v = state["rows"][sel[0]][0]
            state["vehicle"], state["spec"] = v, None
            b_add.config(state="disabled")
            show("Working out %s ..." % v)

            def done(result, err):
                if err:
                    show("Could not work it out: %s" % err)
                    return
                spec, problems, facts = result
                state["spec"] = None if problems else spec
                show(gtos_vehicle.report_proposal(v, spec, problems, facts))
                b_add.config(state="normal" if state["spec"] else "disabled")
            self.bg(lambda: gtos_vehicle.propose(v, install, opstar), done)

        def add():
            v, spec = state["vehicle"], state["spec"]
            if not spec:
                return
            import gtos_vehicle as gvmod
            playable_note = ""
            if playable.get():
                merged, notes, problems = gvmod.playable_spec(v, install, spec, opstar)
                if merged is None:
                    status.config(text="X  cannot make it playable: %s" % problems[0], foreground=RED)
                    return
                spec = merged
                playable_note = (" Made playable (crewable) in the same import: %s."
                                 % "; ".join(notes))
            readable = gvmod.stock_texts(install).get(spec["squad_text"], v).replace("$n", " / ")
            try:
                path = gvmod.add(v, spec, readable)
            except (Exception, SystemExit) as e:
                status.config(text="X  %s" % e, foreground=RED)
                return
            import buildlog
            buildlog.append(self.log_path, "NOTE", gvmod.LABEL % (self.gv_version or 0),
                            "murkz added the Operation Star vehicle %s with the window: %s, side %s, platoon %s code %d, "
                            "battalion %s code %d, uid 0x%08x, squad text %s. Saved in %s. It is in every build from now on."
                            % (v, readable, spec["side"], spec["platoon"], spec["platoon_code"], spec["battalion"],
                               spec["battalion_code"], spec["uid"], spec["squad_text"], path) + playable_note)
            status.config(text="Added %s. It is in the list, and in the next build you make." % v, foreground=GREEN)
            b_add.config(state="disabled")
            self.gv_refill_vehicles(pick=v)
            self.bg(catalogue, listed)
        listing.bind("<<ListboxSelect>>", picked)
        b_add.config(command=add)
        show("Pick a vehicle on the left.")
        self.bg(catalogue, listed)

    def gv_folders(self):
        """The install and Operation Star folders, read fresh from settings (the maps tab may have changed them)."""
        install, opstar = settings.get("sandbox"), settings.get("opstar")
        live = os.path.normcase(os.path.normpath(install)) == os.path.normcase(os.path.normpath(self.install))
        self.gv_l_install.config(text=install + ("   <- YOUR LIVE GAME - choose the fresh install in the GTOS maps tab"
                                                 if live else ""), foreground=RED if live else "black")
        self.gv_l_opstar.config(text=opstar)
        return install, opstar, live

    def gv_make_playable(self):
        """plan-automate-playable.md step 5: promote the picked vehicle from AI-only to crewable.

        Writes the tool's OWN settings file, with a .bak, and never a game file. It does NOT build:
        the vehicle becomes crewable at the next build, which stays a separate, deliberate press.
        Refuses a built-in, one that is already crewable, and one the deriver will not vouch for.
        """
        import gtos_vehicle
        v = self.gv_vehicle()
        if not v or self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        self.gv_set_busy(True, "Working out what %s needs ..." % v)
        self.bg(lambda: gtos_vehicle.make_playable(v, install, opstar), self.gv_make_playable_done)

    def gv_make_playable_done(self, lines, err):
        self.gv_set_busy(False)
        if err:
            self.say(self.gv_report, "Could not work it out:" + chr(10) + chr(10) + str(err))
            self.gv_l_status.config(text="X  failed", foreground=RED)
            return
        self.say(self.gv_report, chr(10).join(lines))
        refused = any(ln.startswith("REFUSED") for ln in lines)
        self.gv_l_status.config(
            text=("X  refused, and it did not guess - see the report" if refused
                  else "Settings written. It becomes crewable at the next build."),
            foreground=RED if refused else GREEN)
        self.gv_info = None                 # the numbers changed, so a stale Check must not be reused
        self.gv_update_lock()

    def gv_picked(self):
        self.gv_folders()
        self.gv_info = None
        self.gv_b_build.config(state="disabled")
        self.say(self.gv_report, "Press 2. Check it - nothing is changed by checking.")
        self.gv_l_status.config(text="", foreground="black")
        self.gv_update_lock()

    def gv_update_lock(self):
        import gtos_vehicle
        locked, why = gtos_vehicle.lock(self.log_path)
        n = gtos_vehicle.next_version(self.log_path)
        self.gv_version = n
        self.gv_b_build.config(text="3. Build %s" % (gtos_vehicle.LABEL % n))
        ready = (self.gv_info and not self.gv_info["problems"] and self.gv_info["buildable"] and not locked
                 and not self.gv_busy and not self.gv_folders()[2])
        self.gv_b_build.config(state="normal" if ready else "disabled")
        if locked:
            self.gv_l_status.config(text="Build locked: " + why, foreground=AMBER)
        return locked

    def gv_set_busy(self, busy, text=""):
        self.gv_busy = busy
        self.gv_b_check.config(state="disabled" if busy else "normal")
        self.gv_l_status.config(text=text, foreground=AMBER if busy else "black")
        if busy:
            self.gv_b_build.config(state="disabled")

    def gv_check(self):
        import gtos_vehicle
        v = self.gv_vehicle()
        if not v or self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Checking %s ... (reads Operation Star, takes a minute)" % v)
        self.bg(lambda: gtos_vehicle.check(v, install, opstar, self.gv_qlog), self.gv_check_done)

    def gv_check_done(self, info, err):
        import gtos_vehicle
        self.gv_set_busy(False)
        if err:
            self.say(self.gv_report, "Could not check:\n\n%s" % err)
            self.gv_l_status.config(text="X  Check failed", foreground=RED)
            return
        self.gv_info = info
        self.say(self.gv_report, gtos_vehicle.report(info))
        if info["problems"]:
            self.gv_l_status.config(text="X  Cannot build - see the report.", foreground=RED)
        elif not info["buildable"]:
            self.gv_l_status.config(text="X  The tool has no settings for this vehicle yet.", foreground=RED)
        else:
            self.gv_l_status.config(text="Ready - press 3 to build.", foreground=GREEN)
        self.gv_update_lock()

    def gv_check_build(self):
        """Will what I have now actually build? Every validator, nothing installed, no version spent.

        The question Check the tool does NOT answer - it rebuilds the proven builds and compares,
        which protects the past. This runs the pipeline against the CURRENT settings, which is what
        the Build button is about to do. Full detail in the log below.
        """
        import gtos_vehicle
        if self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Checking the build ...")
        self.bg(lambda: gtos_vehicle.check_build(install, opstar, self.gv_qlog),
                self.gv_check_build_done)

    def gv_check_build_done(self, ok, err):
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  check failed", foreground=RED)
        elif ok:
            self.gv_l_status.config(text="Build is clean - press Build.", foreground=GREEN)
        else:
            self.gv_l_status.config(text="X  the build would stop - see the log", foreground=RED)

    def gv_techn_show(self):
        """Every named field of the selected vehicle, from the vehicle table itself.

        Read only. This is the table the text route could not carry, because 71 of its
        ostov_type values hold a comma inside a single string and the decompiler truncates
        them. These fields are read straight from the compiled table and shown by name.
        """
        import gtos_vehicle
        v = self.gv_vehicle()
        if not v or self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        try:
            rows = gtos_vehicle.techn_show(install, v, log=self.gv_log_line)
        except Exception as e:
            self.say(self.gv_report, "Could not read the table:" + chr(10) + str(e))
            return
        if rows is None:
            self.gv_l_status.config(text="X  that vehicle is not in the vehicle table",
                                    foreground=RED)
            return
        self.gv_l_status.config(text="%d field(s) of %s - nothing was changed." % (len(rows), v),
                                foreground=GREEN)

    def gv_techn_set(self):
        """Change one field. Dry first, always, and then it asks before writing anything.

        Writes a single 32-byte value cell in place so the table never changes length. A string
        of a different length is refused: string bytes live in a pool everything points into.
        """
        import gtos_vehicle
        from tkinter import simpledialog, messagebox
        v = self.gv_vehicle()
        if not v or self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        field = simpledialog.askstring(
            "Change a field",
            "Which field of " + str(v) + "?" + chr(10) + chr(10)
            + "Press Show its fields... first if you want the list.")
        if not field:
            return
        value = simpledialog.askstring("New value", "New value for %s.%s:" % (v, field))
        if value is None:
            return
        try:
            gtos_vehicle.techn_set(install, v, field, value, log=self.gv_log_line, dry=True)
        except SystemExit as e:
            self.gv_l_status.config(text="X  " + str(e)[:110], foreground=RED)
            return
        ask = ("Write %s.%s = %s into the game table?" % (v, field, value) + chr(10) + chr(10)
               + "The archive is backed up first.")
        if not messagebox.askyesno("Write it?", ask):
            self.gv_l_status.config(text="Nothing written.", foreground=AMBER)
            return
        try:
            gtos_vehicle.techn_set(install, v, field, value, log=self.gv_log_line, dry=False)
        except SystemExit as e:
            self.gv_l_status.config(text="X  " + str(e)[:110], foreground=RED)
            return
        self.gv_l_status.config(text="%s.%s written and verified." % (v, field),
                                foreground=GREEN)

    def gv_cfg_out(self):
        """Every table in a workspace out as editable text, using the game own decompiler.

        Each table is decompiled, repaired, compiled straight back and compared to stock BEFORE
        the text is handed over. A table whose text does not reproduce it exactly is refused, so
        an edit can never be made against text that was not sound to begin with.
        """
        self.gv_cfg("Tables to text", "config_text_out")

    def gv_cfg_in(self):
        """Edited text back into the compiled tables, ready to flat back."""
        self.gv_cfg("Text back to tables", "config_text_in")

    def gv_cfg(self, title, fn):
        import gtos_vehicle
        if self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        d = filedialog.askdirectory(title=title + " - which workspace?")
        if not d:
            return
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, title + " - this uses the game own converter, so it takes a moment")
        self.bg(lambda: getattr(gtos_vehicle, fn)(d, install, log=self.gv_qlog),
                lambda n, err: self.gv_cfg_done(n, err, title))

    def gv_cfg_done(self, n, err, title):
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  " + title + " failed - see the log", foreground=RED)
            return
        k = len(n) if isinstance(n, list) else (n or 0)
        self.gv_l_status.config(
            text="%s: %d table(s). Now run Repack / flat back." % (title, k), foreground=GREEN)

    def gv_atf2dds(self):
        """Write every texture in a workspace out as a .dds any image editor will open.

        The ATF1 record is an 8192-byte header and then a plain DXT1/DXT5 mip chain, which is
        exactly what a DDS holds. The header is kept as .atfhead so it goes back untouched.
        """
        self.gv_tex("Textures to DDS", "textures_out")

    def gv_dds2atf(self):
        """Edited .dds files back into the .atf records, ready to flat back.

        Save the DDS as DXT1 or DXT5 - Paint.NET and GIMP both can. A DDS holding only the top
        level is fine: it is spliced into the mip chain the record already had.
        """
        self.gv_tex("DDS back to texture", "textures_in")

    def gv_tex(self, title, fn):
        import gtos_vehicle
        if self.gv_busy:
            return
        d = filedialog.askdirectory(title=title + " - which workspace?")
        if not d:
            return
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, title + " ...")
        self.bg(lambda: getattr(gtos_vehicle, fn)(d, log=self.gv_qlog),
                lambda n, err: self.gv_tex_done(n, err, title))

    def gv_tex_done(self, n, err, title):
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  " + title + " failed - see the log", foreground=RED)
            return
        self.gv_l_status.config(
            text="%s: %d file(s) done. Now run Repack / flat back." % (title, n or 0),
            foreground=GREEN)

    def gv_unflat(self):
        """Open ANY archive and put its records on disk as files. The plain unflat.

        Nothing to do with the selected vehicle or with tables: pick a .flatdata and everything
        in it comes out, with the manifest that flat back needs to put any of it back. Read only -
        nothing in the game is touched, and it is fast even on a 148 MB archive.
        """
        import gtos_vehicle
        if self.gv_busy:
            return
        f = filedialog.askopenfilename(
            title="Which archive?",
            filetypes=[("Compiled archives", "*.flatdata"), ("All files", "*.*")])
        if not f:
            return
        out = filedialog.askdirectory(title="Where should it go?")
        if not out:
            return
        dest = os.path.join(out, os.path.splitext(os.path.basename(f))[0])
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Unflattening " + os.path.basename(f) + " ...")
        self.bg(lambda: gtos_vehicle.unflat(f, dest, log=self.gv_qlog),
                lambda man, err: self.gv_unflat_done(man, err, dest))

    def gv_unflat_done(self, man, err, dest):
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  unflat failed - see the log", foreground=RED)
            return
        n = 0
        try:
            with open(man, encoding="utf-8") as f:
                n = sum(1 for line in f if line.strip() and not line.startswith("#") and " | " in line)
        except Exception:
            n = 0
        self.gv_l_status.config(
            text="Wrote %d record(s) to %s - the game is untouched." % (n, dest),
            foreground=GREEN)

    def gv_extract(self):
        """Write the chosen vehicle out into a workspace, to inspect or edit by hand.

        Read only. Nothing in the game is touched. The workspace carries a manifest recording where
        every file came from - archive, offset, size, md5 - which is what lets Repack put a changed
        file back in the same place, and refuse to if it cannot.
        """
        import gtos_vehicle
        v = self.gv_vehicle()
        if not v or self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        out = filedialog.askdirectory(title="Where should the workspace go?")
        if not out:
            return
        dest = os.path.join(out, str(v))
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Extracting " + str(v) + " ...")
        self.bg(lambda: gtos_vehicle.extract_vehicle(v, install, dest, log=self.gv_qlog),
                lambda man, err: self.gv_extract_done(man, err, dest))

    def gv_extract_done(self, man, err, dest):
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  extract failed - see the log", foreground=RED)
            return
        self.gv_l_status.config(
            text="Wrote the workspace to " + str(dest) + " - the game is untouched.",
            foreground=GREEN)

    def gv_repack(self):
        """Check a workspace against the game, then offer to write back the files that changed.

        The check runs first and nothing is written without it. A file whose SIZE changed is refused,
        because these go back in place at a recorded offset, and so is one the archive has changed
        since it was extracted - in that case the game has moved on and the workspace is stale.
        """
        import gtos_vehicle
        if self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        d = filedialog.askdirectory(title="Which workspace?")
        if not d:
            return
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Checking the workspace ...")
        self.bg(lambda: gtos_vehicle.repack_vehicle(install, d, log=self.gv_qlog, dry=True),
                lambda rows, err: self.gv_repack_done(rows, err, install, d))

    def gv_repack_done(self, rows, err, install, d):
        import gtos_vehicle
        from tkinter import messagebox
        self.gv_set_busy(False)
        if err:
            self.gv_l_status.config(text="X  the workspace cannot be read - see the log", foreground=RED)
            return
        todo = [r for r in rows if r[1].startswith("WOULD WRITE")]
        bad = [r for r in rows if r[1].startswith("REFUSED")]
        self.say(self.gv_report, chr(10).join("%-36s %s" % r for r in rows))
        if bad:
            self.gv_l_status.config(
                text="X  %d file(s) refused - nothing was written" % len(bad), foreground=RED)
            return
        if not todo:
            self.gv_l_status.config(text="Nothing changed - this workspace matches the game.",
                                    foreground=GREEN)
            return
        msg = ("%d of %d file(s) changed." % (len(todo), len(rows)) + chr(10) + chr(10) +
               "Write them into the game? Each one is backed up first. The game folder then differs" +
               " from the shipped one until you rebuild.")
        if not messagebox.askyesno("Write them back?", msg):
            self.gv_l_status.config(text="Nothing written.", foreground=AMBER)
            return
        got = gtos_vehicle.repack_vehicle(install, d, log=self.gv_qlog, dry=False)
        self.say(self.gv_report, chr(10).join("%-36s %s" % r for r in got))
        self.gv_l_status.config(text="Written, and backed up. Rebuild to make it real.",
                                foreground=GREEN)

    def gv_build(self):
        import gtos_vehicle
        if self.gv_busy or not self.gv_info or self.gv_update_lock():
            return
        install, opstar, live = self.gv_folders()
        if live:
            return
        v, n = self.gv_info["vehicle"], self.gv_version
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Building %s - a few minutes. The window stays usable." % (gtos_vehicle.LABEL % n))
        # every vehicle the tool knows goes into the one gtos_ww2 add-on - building one alone would drop the others (v10)
        self.bg(lambda: gtos_vehicle.build_ai(n, install, opstar, gtos_vehicle.ADDON_VEHICLES, self.gv_qlog),
                self.gv_build_done)

    def gv_build_done(self, result, err):
        import buildlog
        import gtos_vehicle
        self.gv_set_busy(False)
        if err:
            self.gv_log_line("")
            self.gv_log_line("BUILD STOPPED: %s" % err)
            self.gv_log_line("Nothing was produced. Nothing to install.")
            self.gv_l_status.config(text="X  Build stopped - see the log on the right.", foreground=RED)
            self.gv_update_lock()
            return
        zpath, digest = result
        n = self.gv_version
        buildlog.append(self.log_path, "BUILT", gtos_vehicle.LABEL % n,
                        "Built by the GTOS vehicles tab: %s. Zip %s md5 %s." % (gtos_vehicle.contents(), zpath, digest))
        self.gv_zip = zpath
        self.gv_path.set(zpath)
        self.gv_b_copy.config(state="normal")
        install = self.gv_folders()[0]
        self.gv_b_install.config(state="normal" if os.path.isfile(os.path.join(install, "update.cmd")) else "disabled")
        self.gv_l_howto.config(text=(
            "a) Press 4 - it opens the installer AND copies the path above. Uninstall the old gtos_ww2 first, then Install and\n"
            "    paste the path with Ctrl+V.   b) Quick battle: YOUR side needs a crewable tank platoon (the Panzer IV,\n"
            "    Germany), the enemy France (the Soviet T-34s) - or the battle auto-resolves.   c) Write one line in 5."))
        self.gv_l_status.config(text="Built and checked: %s." % (gtos_vehicle.LABEL % n), foreground=GREEN)
        self.gv_update_lock()

    def gv_open_installer(self):
        import subprocess
        install = self.gv_folders()[0]
        update = os.path.join(install, "update.cmd")
        if not os.path.isfile(update):
            return
        if self.gv_zip:
            self.copy_to_clipboard(self.gv_zip)
        subprocess.Popen(["cmd.exe", "/c", update], cwd=install, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.gv_l_status.config(text="Installer opening - the path is copied, paste it with Ctrl+V.", foreground=GREEN)

    def gv_save_result(self):
        import gtos_vehicle
        verdict, line = self.gv_verdict.get(), self.gv_line.get().strip()
        if verdict not in ("GOOD", "BAD") or not line:
            self.gv_l_saved.config(text="Pick GOOD or BAD and write what you saw.", foreground=RED)
            return
        ev = gtos_vehicle.events(self.log_path)
        built = [e for e in ev if e["what"] == "BUILT"]
        if not built or not gtos_vehicle.lock(self.log_path)[0]:
            self.gv_l_saved.config(text="There is no build waiting for a result.", foreground=RED)
            return
        label = built[-1]["version"]
        n = int(label.split("v")[-1])
        zpath = self.gv_zip or os.path.join(gtos_vehicle.work_dir(self.gv_folders()[0]), "%s_v%03d.zip" % (gtos_vehicle.ADDON, n))
        if not os.path.isfile(zpath):
            self.gv_l_saved.config(text="The build's zip is missing: %s" % zpath, foreground=RED)
            return
        vehicles = list(gtos_vehicle.ADDON_VEHICLES)       # the add-on holds them all (v10)
        try:
            msg = gtos_vehicle.record(self.log_path, self.backup_root, n, vehicles, verdict, line, zpath)
        except (Exception, SystemExit) as e:
            self.gv_l_saved.config(text="X  %s" % e, foreground=RED)
            return
        self.gv_l_saved.config(text=msg, foreground=GREEN if verdict == "GOOD" else AMBER)
        self.gv_verdict.set("")
        self.gv_line.delete(0, "end")
        self.gv_update_lock()

    def gv_check_tool(self):
        import gtos_vehicle
        if self.gv_busy:
            return
        install, opstar, live = self.gv_folders()
        if live:
            return
        self.gv_log.config(state="normal")
        self.gv_log.delete("1.0", "end")
        self.gv_set_busy(True, "Checking the tool: rebuilding every proven GTOS build from scratch (a few minutes) ...")
        self.bg(lambda: gtos_vehicle.check_tool(install, opstar, self.gv_qlog), self.gv_check_tool_done)

    def gv_check_tool_done(self, ok, err):
        self.gv_set_busy(False)
        self.gv_log_line("")
        if err:
            self.gv_log_line("CHECK STOPPED: %s" % err)
            self.gv_l_status.config(text="X  Tool check stopped - see the log.", foreground=RED)
        elif ok:
            self.gv_log_line("THE TOOL IS RIGHT - it rebuilds the proven GTOS builds exactly.")
            self.gv_l_status.config(text="The tool is right: proven builds rebuild exactly.", foreground=GREEN)
        else:
            self.gv_log_line("THE TOOL IS WRONG - do not build with it until this is fixed.")
            self.gv_l_status.config(text="X  THE TOOL IS WRONG - see the log.", foreground=RED)
        self.gv_update_lock()


def main():
    import sys
    root = tk.Tk()
    app = App(root)
    # --tab <name> or --tab=<name>, so SABoW GTOS Maps.lnk opens on the maps tab
    want = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--tab" and i + 1 < len(args):
            want = args[i + 1]
        elif a.startswith("--tab="):
            want = a.split("=", 1)[1]
    if want and not app.select_tab(want):
        print("no tab called %r - the tabs are Vehicles, Make playable, GTOS maps,"
              " GTOS vehicles" % want)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _startup_error('SABoW Ext Control', "SABoW Ext Control hit an error while starting.")
