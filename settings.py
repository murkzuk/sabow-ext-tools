# settings.py - the game folders the tools work on, chosen in SABoW Ext Control and remembered
# between runs.
#
#   live     the game SABoW Ext builds for and installs into (Vehicles / Make playable tabs)
#   sandbox  the throwaway install the GTOS maps tab converts into
#   opstar   the Graviteam Tactics: Operation Star install, read-only source of missing game data
#   backups  where frozen, proven packages are kept
#
# WHERE THE FILE LIVES (changed 2026-10-06, release audit H2). It used to be settings.json BESIDE
# this script. That works on a development machine and fails silently for anyone who unpacks the
# tools under C:\Program Files, which is not user-writable - so every save would error. It is now
# under %LOCALAPPDATA%, with the old location read once and migrated.
#
# WHY THE DEFAULTS ARE EMPTY (release audit H1). They used to be this developer's own drive
# letters, so a new user opened the Control and saw three red NOT FOUNDs - it read like a broken
# program. Empty means "not chosen yet", and discover() goes looking through Steam first.

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_FILE = os.path.join(HERE, "settings.json")


def _config_dir():
    r"""%LOCALAPPDATA%\SABoWExt, or beside the script if it cannot be made."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        d = os.path.join(base, "SABoWExt")
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except OSError:
            pass
    return HERE


FILE = os.path.join(_config_dir(), "settings.json")

DEFAULTS = {"live": "", "sandbox": "", "opstar": "", "backups": ""}


# ---------------------------------------------------------------- what a real install looks like

def is_sabow(folder):
    """Steel Armor: starter.exe AND its base tables. Not just 'the folder exists'."""
    return (bool(folder)
            and os.path.isfile(os.path.join(folder, "starter.exe"))
            and os.path.isfile(os.path.join(folder, "data", "mtc80", "shared", "packed_data", "tabs.flatdata")))


def is_opstar(folder):
    """Operation Star: starter.exe AND its own k43t data tree, which Steel Armor does not have.
    Added 2026-10-06: nothing checked this, so a wrong Operation Star path produced a confusing
    failure somewhere downstream instead of being refused up front."""
    return (bool(folder)
            and os.path.isfile(os.path.join(folder, "starter.exe"))
            and os.path.isdir(os.path.join(folder, "data", "k43t")))


def channel(folder):
    """"steam", "retail" or "unknown" - and on retail the add-on will be IGNORED.

    Steel Armor ships through two channels that are not the same game inside. The retail /
    GamersGate build (assembly 2410) carries game update 1.16 as a registered `dev_updates`
    add-on; the Steam build (2899) has it baked into the base game.

    A USER ADD-ON CANNOT OVERRIDE dev_updates. Proven by two play-tests with the registry order
    tried both ways. So on retail every shadowing table this project ships - qbattle,
    div_units_misc, common_res_mod, cocpits - is silently ignored, with no error anywhere. The
    build looks like it worked and the game does not change.

    Told apart by two signals that agree on every install here:
        retail  no steam_api.dll, data/<prefix>/dev_updates present, base tabs 6,488,064
        steam   steam_api.dll present, no dev_updates,               base tabs 6,815,744
    """
    if not folder or not os.path.isdir(folder):
        return "unknown"
    steam_api = os.path.isfile(os.path.join(folder, "steam_api.dll"))
    dev = False
    data = os.path.join(folder, "data")
    if os.path.isdir(data):
        try:
            for prefix in os.listdir(data):
                if os.path.isdir(os.path.join(data, prefix, "dev_updates")):
                    dev = True
                    break
        except OSError:
            pass
    if dev and not steam_api:
        return "retail"
    if steam_api and not dev:
        return "steam"
    return "unknown"


# ---------------------------------------------------------------- finding the games by themselves

def _steam_libraries():
    """Every Steam library folder on this PC, from the registry and the usual places."""
    roots, out = [], []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass                                   # not Windows
    for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        roots.append(p)
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        out.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        import re
        for m in re.finditer(r'"path"\s*"([^"]+)"', text):
            out.append(m.group(1).replace("\\\\", "\\"))   # the vdf doubles them
    seen, uniq = set(), []
    for p in out:
        q = os.path.normcase(os.path.normpath(p))
        if q not in seen and os.path.isdir(p):
            seen.add(q)
            uniq.append(p)
    return uniq


def discover():
    """{key: folder} for whatever can be found without asking. Never writes; the caller offers it.

    Added 2026-10-06 so a new user is not met by empty boxes: the commonest support question is
    'where is my install', and Steam already knows.
    """
    found = {}
    for lib in _steam_libraries():
        common = os.path.join(lib, "steamapps", "common")
        if not os.path.isdir(common):
            continue
        try:
            names = os.listdir(common)
        except OSError:
            continue
        for name in names:
            folder = os.path.join(common, name)
            if "live" not in found and is_sabow(folder):
                found["live"] = folder
            if "opstar" not in found and is_opstar(folder):
                found["opstar"] = folder
    return found


# ---------------------------------------------------------------- read and write

def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {k: v for k, v in saved.items() if k in DEFAULTS and isinstance(v, str) and v}
    except (OSError, ValueError):
        return {}


def load():
    out = dict(DEFAULTS)
    saved = _read(FILE)
    if not saved and FILE != OLD_FILE:
        saved = _read(OLD_FILE)            # migrate a pre-2026-10-06 file, once
    out.update(saved)
    if not out["backups"]:
        # beside the tools by default, so a release unpacked anywhere still has somewhere to put
        # frozen packages. It used to be the literal L:\sabow-ext-backups (release audit H3),
        # which on a machine with no L: made the SAFETY NET the thing that failed.
        out["backups"] = os.path.join(os.path.dirname(HERE), "backups")
    return out


def get(key):
    return load()[key]


def put(key, value):
    if key not in DEFAULTS:
        raise KeyError(key)
    data = load()
    data[key] = os.path.normpath(value) if value else ""
    tmp = FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, FILE)
    except OSError as e:
        raise RuntimeError("Could not save settings to:\n  %s\n\n%s" % (FILE, e))
    return data[key]
