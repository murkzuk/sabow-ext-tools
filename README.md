# SABoW Ext — tools

Three tools for modding **Steel Armor: Blaze of War**, released as-is.

They are what I use myself. They are not polished products, they do not have an installer, and
there is no support — but they do work, and everything they do is explained on screen as it
happens rather than hidden.

| tool | what it does |
|---|---|
| **SABoW Ext Control** | the main window. Looks at the vehicles in your game, works out which AI-only ones can be made playable, builds and installs the add-on, and converts Graviteam Tactics maps so Steel Armor can play them. |
| **Player Tank Tool** | reads an operation and tells you, platoon by platoon, whether you could actually crew a tank in it — and which of the five things that stop you is missing. |
| **SABoW Operations Tool** | authoring new operations: project from the Graviteam stencil, convert the spreadsheets, open the editor, compile, and pack the `.campack2` the campaign menu reads. |

## What you need

- **Windows**, and **Steel Armor: Blaze of War** installed.
- **Python 3** from [python.org](https://www.python.org/downloads/). Tick **"Add python.exe to
  PATH"** during setup.
- **Graviteam Tactics: Operation Star** — only for the parts that borrow from it (some vehicles,
  the maps, the operation stencil). Everything else works without it.

There is nothing to `pip install`. These use only what comes with Python.

## Running them

Unzip anywhere you like — **not** inside `C:\Program Files`, or Windows will block the game files
being written. Keep all the files in one folder; they need each other.

Then double-click:

- `SABoW_Ext_Control.pyw`
- `player_tank_tool.py` — or `run_player_tank_tool.cmd`, which keeps a window open so you can read
  any error
- `sabow_op_tool.py`

The first time the Control opens it will look for your games **through Steam**. If you bought the
game anywhere else — GamersGate, a disc, GOG — it will not find them, which is not a fault: press
**Choose…** and point it at the folder with `starter.exe` in it.

### If you have the retail / GamersGate build, read this first

Steel Armor ships through two channels that are **not the same game inside**. The retail build
carries game update 1.16 as a separate `dev_updates` add-on; the Steam build has it baked in.

**A user add-on cannot override `dev_updates`.** On the retail build, everything this tool installs
is ignored by the game — silently, with no error anywhere. The build will look as though it worked
and nothing will change in game.

The Control detects this and says so in red when you pick the folder. Everything that only **reads**
— the vehicle lists, the playability reports, the operation audit — is still completely correct on
retail. It is only installing that cannot work.

Your choices are remembered in `%LOCALAPPDATA%\SABoWExt\settings.json`.

## If a tool does not start

It should tell you why, in a message box. If something goes wrong before it can even do that, look
for **`sabow_tool_error.txt`** next to the files (or in your temp folder) — that is written before
anything is shown, and it names what failed.

The commonest causes:

- **Python is not installed, or not on PATH.** Re-run the python.org installer and tick "Add
  python.exe to PATH".
- **The files were separated.** All of them must sit in the same folder.
- **"needs Python's tkinter"** — install Python from python.org rather than a cut-down build.

## What it changes, and what it does not

The tools **read** your game and **write** into their own work folders. The only thing that writes
into the game itself is the game's own `starter.exe`, run by the tools the same way Graviteam's
own modding tools run it.

Builds are kept as frozen packages so you can go back to an earlier one. Nothing is installed
without you pressing the button that says so.

**Back up your save games before using any of this.** It is modding; things break.

## Credit

Steel Armor: Blaze of War and Graviteam Tactics are by **Graviteam**. These tools only drive
Graviteam's own file formats and their own command-line programs — nothing of theirs is
redistributed here.

Tools by **murkz**, under the MIT licence - see `LICENSE`. Do what you like with them;
they come with no warranty of any kind.
