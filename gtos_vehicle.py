# gtos_vehicle.py - bring a Graviteam Tactics: Operation Star vehicle into SABoW as its own add-on.
# PLAN.md "GTOS WW2 content", step 3. v1-v6 AI-only; from v7 crewable (the SABoW Ext recipe - see "crewable (v7)").
#
# Worked out read-only on the Panzer IV F2 (docs/gtos-pz4f2-check.md, docs/gtos-pz4f2-vs-bow43.md):
#   - stock SABoW already has its weapons, shells, tracks, crew animations and German side, row for row
#   - Operation Star adds 7 files (model, track model, textures + winter versions, armour map)
#   - the vehicle block goes in a table of our own; BoW43 v685 did the same (techn_ww2)
#   - the squad takes the stock T-62 squad's shape and costs; v1-v4 used the T-62 crew, from v5 the vehicle's
#     own German crew (Operation Star's crew squad, humans in hum_gtos, their bodies in bodys_gtos);
#     from v6 their voice lines too (speech_ger's built names, which the name-follower cannot find)
#   - a German platoon is invisible in quick battle until common_res sides GER field[11] is 2 (notes/26),
#     a one-byte patch in the compiled table because common_res cannot round-trip (notes/44 4c)
#
# Every table is built the proven SABoW Ext way: the game's own decompile/compile, a round-trip gate
# before any edit, and the finished table read back and compared with stock plus exactly our change.
# Everything happens in the install passed in - the fresh stock install, never the live game.

import glob
import hashlib
import os
import re
import shutil
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import azcf         # noqa: E402
import build        # noqa: E402
import crewpoints   # noqa: E402
import gtos_opstar  # noqa: E402
import recipe       # noqa: E402
import textable     # noqa: E402

ADDON = "gtos_ww2"
AUTHOR = "murkz"
DESCRIPTION = "GTOS WW2 - Operation Star vehicles in Steel Armor"
TECHN = "techn_gtos"                 # our vehicle table
CRLF = b"\r\n"

# One vehicle per entry. Names are ours (gt*), so nothing collides with stock or with BoW43.
VEHICLES = {
    "pz4f2": {
        "unit": "gtu_pz4f2", "squad": "gt_pz4f2", "opstar_unit": "weru_pz4f2",
        # v5 German crew: Operation Star's squad wer_pz4f2 names its crew squad (wer_crew_pz4 - commander,
        # crewman, 3 with pistols); ours is a copy under our own names, humans in HUM.
        "opstar_squad": "wer_pz4f2", "crew_squad": "gt_crew_pz4",
        "donor_squad": "sa_t62",               # stock squad whose shape, costs and crew we copy
        "platoon": "gt_plat_pz4f2", "battalion": "p_gt_ger_bat",
        "platoon_code": 200, "battalion_code": 201, "uid": 0x0000f700,
        "camo": "pat2", "max_squads": 3,
        # Names (v2). The unit name already exists in STOCK SABoW text - "Medium tank / PzIV ausf. F/2",
        # the same Operation Star entry - so the squad points at it and ships nothing. Platoon and
        # battalion names are ours, in the add-on's own text archive (new ids work; stock ids cannot
        # be redefined - 2026-09-16). One line each: pd2text drops "\n" (tested), as BoW43 shipped.
        "squad_text": "txt_ce_wer_pz4f2",
        "platoon_name": "Tank platoon (Panzer IV F2)",
        "battalion_name": "Panzer-Abteilung (1943)",
        # user_in draws the crew icon and marks the platoon as one the player can crew. v1/v2 had it
        # TRUE and murkz saw the Panzer IV marked playable (2026-09-17). Stock AI-only T-55 platoons ship
        # FALSE; BoW43 notes/52 claimed FALSE empties the list - measured on its big fleet, not here. v3 tests it.
        "user_in": False,
        # v7 crewable: the T-62 cockpit's guns paired by hand (recipe.py class match cannot - flag bits)
        "weapons": {"U5TS": "KWK40", "PKT": "MG34"},
        # side (v10 made these per vehicle; the values are the ones v1-v9 had written in)
        "side": "GER", "opstar_units_table": "div_units_ger",
        "sold_fams": "txt_sn_ger_fams", "sold_names": "txt_sn_ger_nams", "marks": "wer_marks_01",
        "own_crew": True, "crewable": True,
        "sight_stubs": ("tzf5f",),          # its one empty stub row
        # The FROZEN v19 reticle, not the live one. Byte-identical today, but the live file is
        # rewritten by every tzf5f_moving.py run and a PROVEN build must not depend on that.
        "gunner_sight": "tzf5f_g_moving_v19",
        "fifth_station": True,              # five stations against the donor cockpit's four
    },
    # v10: the first Soviet tank, AI-only, on the FR side opened for quick battle (murkz, 2026-09-17: "use france as
    # the side just rename as we did in bow"). T-34/76 model 1942 (UTZ), BoW43 notes/51's choice. Its gun, MG, shells,
    # tracks and wreck are all in stock SABoW; Operation Star adds the model, armour map and textures (12 files).
    # Crew: the donor T-62 squad's, as the Panzer IV had before v5. The unit name text is stock SABoW's.
    "t34_utz_m42": {
        "unit": "gtu_t34_42_uztm", "squad": "gt_t34_42_uztm", "opstar_unit": "rkkau_t34_42_uztm",
        "donor_squad": "sa_t62",
        "platoon": "gt_plat_t34_42", "battalion": "p_gt_sov_bat",
        "platoon_code": 202, "battalion_code": 203, "uid": 0x0000f701,
        "camo": "pat2", "max_squads": 3,
        "squad_text": "txt_ce_rkka_t34_42_uztm",
        "platoon_name": "Tank platoon (T-34/76 1942)",
        "battalion_name": "Tank battalion, RKKA (1943)",
        "user_in": False,
        "side": "FR", "opstar_units_table": "div_units_ussr",
        "sold_fams": "txt_sn_ussr_fams", "sold_names": "txt_sn_ussr_nams", "marks": "sa_marks_01",
        # v20: CREWABLE. Gun pairing measured from its own techn entry: the F-34 76 mm and two DT machine
        # guns, exactly parallel to the Panzer IV's KWK40 + MG34.
        # v99: OWN_CREW TRUE. v20 left it False because "the donor T-62 squad's crew is SOVIET, which is
        # right for a T-34, and SABoW's Russian intercom is right too" - which is true of the VOICES and
        # false about the men: the donor squad is sau_tank_com + sau_tank_agun, T-62 tankers in modern kit.
        # Operation Star fields this T-34 with rkka_crew_t34 - four men out of rus_hum_base for its four
        # manned stations - and murkz asked for exactly that (2026-09-28: "we have the t62 crew models not
        # the crew from gtos"). The voices do not change: SABoW's own Russian lines are stock, so
        # crew_voices finds nothing missing for a Soviet crew.
        "own_crew": True, "crewable": True,
        "weapons": {"U5TS": "F34", "PKT": "DT"},
        # Both gunner rows are empty stubs, exactly as tzf5f was before v7: the PT-4-7 periscope and the
        # TMFD-7 telescope. Muling both means neither can 001 and murkz can switch between them.
        "sight_stubs": ("pt4_7", "tmfd_7"),
        # v78: THE TELESCOPE IS HIS FIRST VIEW. The engine takes the gunner's views by index and
        # view 1 is the sight the gun drives, so the TMFD-7 must be first and the PT-4 second - which
        # is the real tank (he aimed through the telescope and observed through the periscope) and what
        # the T-62 and M60 do. GTOS ships them the other way round. v75 did this by hand in 13 bytes of
        # a built table; this field makes the tool do it, so a rebuild keeps it.
        # and the LOADER gets his OWN side slit first: both slits sit in the sig_loader group with
        # the gunner's first, so his view 1 was the other man's slit. murkz: "the loaders side slit is
        # looking out of the gunners side slit!"
        "sight_order": ("sig_gunner_tmfd", "sig_gunner_pt4", "sig_loader_side"),
        # murkz: "the gunner needs the 3rd sight as a slit" - his own side slit, which GTOS left in the
        # LOADER's group. Moving it gives the gunner three views (telescope, PT-4, slit) and leaves the
        # loader with his own slit alone.
        "sight_group": {"sig_gunner_side": "sig_gunner"},
        # v82: both side slits get their own masked row instead of the shared vision block.
        # v84 DERIVED it; v93 REMOVES THE OVERRIDE. This said "slit_g" as a plain string, which beat the
        # build-wide VISION_BLOCKS rule and gave this vehicle's DRIVER the 20 degree slit instead of his
        # own 35 degree one - caught by comparing the T-34's rows against the Panzer IV's after v92, where
        # the Panzer IV (no entry at all) came out right and this one did not. THE DEFAULT IS THE ANSWER:
        # a vehicle states a vision_blocks entry only to DIFFER from the fleet.
        # v92: NO LONGER LISTED. vision_blocks finds the driver's PAD row itself (VISION_BLOCK_PADS), so
        # this vehicle - and every other - gets its driver's slit without an entry here.
        # v88 was: THE DRIVER'S PSEUDO-SLIT. He has no port of his own - his tank gave him none, and in the
        # stock game he looks through the hull's geometry - but he DOES have two view rows, and the one the
        # cockpit actually looks through is the PADDED one, sig_driver_x2: coc_t62's driver plc_states asks
        # for sight index 2, which a vehicle with two driver sights gets from the pad (v36's own finding,
        # and v35 changed index 1 and nothing looked through it). So the pad is the lever, and pointing it
        # at the slit row gives him a masked slit to look through instead of the plain 35 deg window.

    # v71: THE PT-4 PERISCOPE. GTOS's ui_params names BOTH of this tank's sights (TMFD-7 and PT-4)
    # and we have shipped only the TMFD-7. The stub row already existed - this gives it a sight, which
    # is the whole of extra_sights' purpose. No mask field is needed for the traverse: the donor row
    # carries the limits. See docs/VISION_PORTS.md sections 11-12.
    "extra_sights": {"pt4_7": "pt4_7_g"},
        # v29: its own TMFD-7 instead of the T-62 mule. See GUNNER_SIGHTS["tmfd_7_g"].
        # v108: back off the v107 diagnostic probe and onto the real sight, with the drum travel
        # doubled to -1.0 from the F-34's own ballistics. See GUNNER_SIGHTS["tmfd_7_g_moving_v108"].
        # v109: the artwork lifted to the gun axis. Fired at a known range for the first time on
        # 2026-09-30 and the sight was zeroed at 600 m. See GUNNER_SIGHTS["tmfd_7_g_moving_v109"].
        # ROLLBACK: "tmfd_7_g_moving_v108" is the same sight unlifted; "tmfd_7_g_moving_v30" is the
        # -0.5 travel murkz called "v30 excellent".
        "gunner_sight": "tmfd_7_g_moving_v109",
        # notes/20 (BoW43, proven by murkz driving it): field [11] is the ROLE and [18] the index, and
        # renaming a station does NOTHING. A T-34/76 has no commander station because the commander IS the
        # gunner, so its hull machine-gunner takes the commander role - keeping the s_mgunner anchors, which
        # the model has and s_commander* it does not, and which is where that crewman historically sat.
        # v24 EXPERIMENT, one variable. "cmdr head is poking out of the hull in f3 view" - and the
        # cockpit's own d_com_head is already hidden (measured), so it is the CREW FIGURE. The only
        # change on this station is the role, and a commander-posed crewman at a hull machine-gunner's
        # seat would sit taller than a hull crewman. notes/20 changed [11] and [18] together, so [11]
        # has never been tested on its own. If the commander place stops binding, the log will say so
        # and [11] goes straight back to "commander".
        "wp_edits": {"wp_mgunner": {11: "driver", 18: 4}},
        # v22, from murkz on v21 ("radio op is sticking through the hull and the cmdr can not turn out").
        # The tool's own warning said why: no s_commander or s_commander_out in this model, so that
        # crewman keeps the DONOR's position - the T-62's, in a differently shaped turret. Mode 0 cannot
        # help because it follows the chunk of the same name, so point the rows at chunks the T-34 has:
        # its own hull station to sit at, and the TURRET hatch to stand in - which is where a T-34
        # commander actually went, he being the gunner. Both measured present in the t34_42_utz mesh.
        # s_commander -> s_mgunner WORKED: murkz on v22 confirms the commander now sits next to the driver,
        # at the radio operator's station, which is where that crewman really was. s_commander_out is NOT
        # retargeted: he has no hatch there (murkz: "no hatch for him anyways"), and pointing it at the
        # turret hatch would have two crewmen claiming the same one as the gunner.
        # v25, murkz on v24: "cmdr is next to the driver but to far forward, he is actually the hull
        # gunner radio man, the gunner should be the cmdr as well as gunner". He is right about the
        # tank - a T-34/76 commander WAS the gunner - and it lands on the one place that can do what
        # he wants. The COMMANDER place has a turn-out state and binoculars; the GUNNER place has
        # neither (docs/sync-modes.md: coc_t62 has no s_gunner_out at all). So put the commander
        # place at the gunner's station and he gets the turret seat, the turret hatch and the binos,
        # while the gunner place keeps the sight. The hull radio man stops being presented as the
        # commander, which is what was wrong.
        "sync_retarget": {"s_commander": "s_gunner", "s_commander_out": "s_gunner_out"},
        # v28: the gunner's hatch, properly this time. The T-34 has s_gunner_out and its AI gunner
        # uses it; what was missing is a STATE for the place to enter. Three parts of one mechanism -
        # the plc_states row, the sync row, and the vehicle's own hatch fields left alone.
        "gunner_hatch": True,
        "sync_add": {"s_gunner_out": "s_gunner_out"},
        "gunner_turnout": True,
        # *** SUPERSEDED BY v105/v106 - READ THE TWO BLOCKS BELOW THIS ONE, NOT THIS ONE. What follows
        # is kept because it is the record of what four builds believed, and because it is exactly how a
        # reader goes wrong. IT TREATS z AS HEIGHT. z IS FORWARD/BACK on these models; y is the height.
        # So "the driver moves forward to their own value" was accurate about the AXIS and wrong about
        # the intent - the number 1.644 is 34 cm FORWARD of the model's own 1.3043, which is why the
        # build it describes was reported as "worse now the driver is poking out as well as the mgunner".
        # The 35.4 cm z gap between the two seats is a FORWARD/BACK gap, not a height one; the height
        # gap between those two men is in y, and it is 10.4 cm (v106). Axis convention, evidence and the
        # finished values: notes_117_HOW_TO_MOVE_A_CREWMAN.md, docs/crew-position-layers.md.
        # v102: THE DRIVER SITS BESIDE HIS HULL GUNNER - and it was never the gunner who was wrong.
        # The whole history of this seat, in one place, because it took four builds to see it:
        #   v26  murkz: "move the s_mgunner to X +0.34 Z 1.30" - he saw the hull gunner 35 cm ahead of the
        #        driver and moved the GUNNER back. Right for the T-62 crewmen of the day, and it took the
        #        gunner off his own MG mount and under the driver's hatch.
        #   v100 the gunner's head came through the roof (the men were Operation Star's own by then, v99).
        #   v101 put the gunner back where Operation Star has him (z 1.658) - and murkz: "has put the
        #        mgunner back as it was builds ago, to far forward... if we are using the correct ai per
        #        tank positions, then this should be the same on every t34 and it is not, only the player
        #        tank has this position sticking out".
        # He was right, and the two models side by side say what is actually different:
        #     t34_41_stz  (their 1941)  driver z 1.644   hull gunner z 1.658   -> 1.4 cm apart
        #     t34_42_utz  (their 1942)  driver z 1.304   hull gunner z 1.658   -> 35.4 cm apart
        # THE HULL GUNNER'S SEAT IS IDENTICAL IN BOTH. The DRIVER is the one that differs - and the AI
        # T-34 murkz compared IS their 1941 model, which is why only his tank looked wrong. In a real
        # T-34 the driver's hatch and the MG ball mount are side by side at the front, so their 1941
        # model is the one to copy. The driver moves forward to their own value and the gunner stays on
        # his mount. His periscope cameras (s_camera_driver_02/03) are separate nodes and do not move,
        # so what he looks THROUGH is untouched.
        # v105: BOTH MEN BACK TO THE PAIR MURKZ ASKED FOR, and the two builds that broke it undone.
        #   v26  murkz's own instruction: "move the s_mgunner to X +0.34 Z 1.30" - and the driver was
        #        left at the 1942 model's own 1.3043, so both men sat on the SAME line, 35.4 cm ahead
        #        of the turret. That is a T-34: the driver's hatch and the MG ball mount are side by side.
        #   v101 restored the gunner to Operation Star's own 1.658 and v102 moved the driver to their
        #        1941 model's 1.644 - each was reported as "too far forward", and the two together are
        #        what murkz is looking at now. A T-34's two front men 35 cm apart on the same axis is not
        #        what the 1941 model says either: t34_41_stz has them 1.4 cm apart.
        # Measured on the model, not assumed: s_driver and s_mgunner are both children of d_hull, and
        # every other hull fitting agrees with them - d_hatch_01 sits 5 cm above and 5 cm ahead of
        # s_driver. What the two builds changed was the axis the men are separated along, and murkz's
        # reports say which way it moved them: forward.
        # v106: AND THE HULL GUNNER COMES DOWN TO THE DRIVER'S HEIGHT. murkz on v105: "driver is now
        # perfect mgunner needs lowered to the same height (up/down) as the driver". Which axis is the
        # height is settled by that sentence, and by the three builds before it: the DRIVER is perfect
        # with z 1.3043 and the gunner sits at z 1.300 - the same to 4 mm - so the axis he is still
        # wrong on is NOT z. It is y: s_driver y +0.2730, s_mgunner y +0.3769, 10.4 cm apart, and the
        # gunner is the high one. So for this model z is FORWARD/BACK and y is UP/DOWN, which is also
        # what the two seat builds did when murkz said each of them went "too far forward": v101 took
        # the gunner's z 1.300 -> 1.658 and v102 the driver's 1.3043 -> 1.644, both FORWARD. The
        # gunner's y is left at Operation Star's own +0.3769 in BOTH of their T-34s, so this is a
        # deliberate departure from their data on one float, and the honest cost of it is that our
        # 1942 model no longer matches theirs at that node.
        "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30, "y": 0.2730}}},
        "keep_live_mesh": True,
        # v107: AND THE LIVE COPY OF THE MODEL KEEPS THEM. The engine reads whichever copy wins and a
        # Sokolovo battle reads gtos_sokolovo_ob's, so v26's seat move and v101-v106 all had to be
        # hand-applied there - a loan, not a fix, and an add-on reinstall would have wiped it (BUILD_LOG
        # 436). This flag makes the BUILD keep this model's live patch (and only this model's: the
        # Panzer III's held-back camera fix is still put back).
        # v23 TRIED and FAILED: adding an s_gunner_out sync row and giving the hatch back produced
        # "gunner 001 on hatch open". docs/sync-modes.md says why, and it was written before any of
        # this: coc_t62's mode-1 rows are "exactly the 7 crew points", and s_gunner_out is not one of
        # them. The T-62 gunner has no turn-out STATE, not just a missing row, so a row binds to
        # nothing. The T-34 really does have the hatch (murkz: "look at the model") and its AI gunner
        # uses it - but the PLAYER cannot, on this cockpit. An authored cockpit is the only route
        # (notes/22 did that for the Tiger, coc_ww2_5). Back to v21's arrangement, which murkz proved
        # as "no 001".
        # Four stations against the donor cockpit's four places - nothing to add.
        "fifth_station": False,
        # v111: THE HULL MACHINE-GUNNER HAD NOWHERE TO LOOK. murkz, 2026-10-01: he is the one
        # crewman with no V destination, so he sits in an unmodelled hull permanently - and he
        # cannot simply be removed, because on a T-34 the commander IS the gunner and this man
        # takes the commander place, which the cockpit must have to bind at all.
        #
        # The vehicle side was already complete: work_places `wp_mgunner` names the sight group
        # `sig_mgunner`, and that group's one entry points camera `s_camera_radist` at the stock
        # row `gunner_mg` - FOV 20, no reticle, no magnification, a plain forward aperture view,
        # which is also the historically right answer. A 1942 T-34's bow gun had no telescope; the
        # PPU-8T is a T-34-85 obr.1960 fitting, and the mantlet aperture was for rough aiming.
        #
        # What was wrong is ONE FIELD. The cockpit is a clone of the T-62's, whose commander had
        # three sights, so its place-2 view row asks for sight index 2. `sig_mgunner` has only
        # index 0, so the engine is asked for a sight that does not exist and nothing happens.
        # This is precisely the failure `docs/plc-states-decoded.md` predicted for cloned cockpits.
        # The match pins place 2, button slot -1, flags 0x200 and sight 2, and the editor refuses
        # unless exactly one row answers to all four.
        "plc_edits": ((
            {0: "2", 1: "4294967295", 2: "512", 5: "2"},
            {5: "0"},
        ),),
        # v112: AND NOW HE HAS SOMETHING TO SEE THROUGH. murkz on v111: "no mg sight for mgunner
        # just full screen visor view" - because v111 gave him a V destination and the row it
        # resolves to draws nothing. Read out of the installed package, not inferred: the stock
        # `gunner_mg` is FOV (20, 0, 0, 0) with field [9] EMPTY and no type token, so the engine
        # opens a 20 degree window with no art on it. That IS the full screen view he reported.
        #
        # `slit_g` is the same 20 degrees - (20, 20) - and carries the `m60_cperiscope` mask, so
        # nothing about the field of view moves; only the art appears. It is ours, already in the
        # package, already proven in game on this very tank's gunner and loader side views, and
        # its token is empty exactly as `gunner_mg`'s is, so what he can and cannot aim does not
        # change either.
        #
        # ONE CELL. `sig_mgunner` is row 6 of this vehicle's own sights block, traverse 0.0, which
        # is byte-for-byte the shape of `sig_loader_side` and `sig_gunner_side` above it - both of
        # which point at `slit_g` and work. So this makes a third row identical to two proven ones.
        # The v95 traverse rule cannot bite: it judges PADDED rows, and this is a real row at 0.0.
        #
        # KNOWN AND ACCEPTED, so the next reader does not file it as a bug: `slit_g`'s label text
        # is `txt_sig_periscope`, so the bow gunner's view is captioned "periscope", and his
        # picture is identical to the gunner's and loader's slits. It reads as a periscope, not as
        # a bow MG aperture. murkz chose this knowingly as the cheap half of a two-step: Steel
        # Fury's `mg_bow` chevron is the authentic answer and is the SAME one-cell swap later,
        # through this same field (its art is extracted and converted - BUILD_LOG 2026-10-01).
        #
        # ROLLBACK: delete this entry and the row goes back to `gunner_mg`, which is v111.
        "other_sights": {"sig_mgunner": "slit_g"},
        # v115: STEEL FURY'S OWN T-34 MODEL 1942 INTERIOR, in place of the T-62's.
        # The mesh ships through OWN_ASSETS (v114) and is converted by sabow-docs Tools/go2x.py;
        # the route and the per-node index rebasing that made it work are in notes/81.
        # Slot 0 only: slots 1 and 2 are the T-62's devices and labels, which we do not have a
        # T-34 equivalent for, so they stay hidden exactly as before.
        "interior": {"mesh": "coc_t34_42", "slot": 0,
                     "was": "coc_t62",
                     "file": r"L:\sabow-ext-backups\interiors\coc_t34_42\coc_t34_42.loc_def.mesh",
                     # the other models the cockpit can still reach, so a chunk is only called
                     # dead when none of them has it either
                     "also": ("coc_t62_devs", "coc_t62_labels", "t62", "t34_42_utz")},
    },
    # v12: second Soviet tank, AI-only - KV-1 model 1942 (UZTM, ZIS-5 gun). murkz chose "more Soviet tanks as AI" next.
    # Own battalion: a heavy tank regiment, as KV-1s were organised in 1942-43. Gun, MG, shells, tracks (kv1_700)
    # and wreck (kv_ostov) are in stock SABoW; Operation Star adds 9 files.
    # v99: OWN_CREW TRUE - Operation Star's own rkka_crew_kv1 is FIVE men out of rus_hum_base for this
    # vehicle's five manned stations, where the donor's four-man T-62 squad was neither the right men nor
    # the right count.
    "kv1_42_uztm": {
        "unit": "gtu_kv1_42_uztm", "squad": "gt_kv1_42_uztm", "opstar_unit": "rkkau_kv1_42_uztm",
        "donor_squad": "sa_t62",
        "platoon": "gt_plat_kv1_42", "battalion": "p_gt_sov_hvy",
        "platoon_code": 204, "battalion_code": 205, "uid": 0x0000f702,
        "camo": "pat2", "max_squads": 3,
        "squad_text": "txt_ce_rkka_kv1_42_uztm",
        "platoon_name": "Heavy tank platoon (KV-1 1942)",
        "battalion_name": "Heavy tank regiment, RKKA (1943)",
        "user_in": False,
        "side": "FR", "opstar_units_table": "div_units_ussr",
        "sold_fams": "txt_sn_ussr_fams", "sold_names": "txt_sn_ussr_nams", "marks": "sa_marks_01",
        "own_crew": True, "crewable": False,
    },
    # v13: third Soviet tank, AI-only - T-70 (Operation Star t70m, model t70; 45 mm 20KM + DT, tracks t70_260, wreck
    # rltank_ostov - all stock). murkz chose it next. Crew 2: v99 gives it Operation Star's own rkka_crew_t70,
    # two men out of rus_hum_base for its two manned stations, instead of the donor's four T-62 tankers.
    "t70m": {
        "unit": "gtu_t70_42", "squad": "gt_t70_42", "opstar_unit": "rkkau_t70_42",
        "donor_squad": "sa_t62",
        "platoon": "gt_plat_t70_42", "battalion": "p_gt_sov_lt",
        "platoon_code": 206, "battalion_code": 207, "uid": 0x0000f703,
        "camo": "pat2", "max_squads": 3,
        "squad_text": "txt_ce_rkka_t70_42",
        "platoon_name": "Light tank platoon (T-70 1942)",
        "battalion_name": "Light tank battalion, RKKA (1943)",
        "user_in": False,
        "side": "FR", "opstar_units_table": "div_units_ussr",
        "sold_fams": "txt_sn_ussr_fams", "sold_names": "txt_sn_ussr_nams", "marks": "sa_marks_01",
        "own_crew": True, "crewable": False,
    },
}
# RECORDS THIS PROJECT AUTHORS, shipped inside the add-on from a file on disk. Added 2026-10-01 for
# the Steel Fury interiors: a converted .go becomes an AZG2 mesh and a converted .dds an ATF1
# texture, and neither could reach the game before - `assets` only ever held reticle meshes made in
# memory and records borrowed from Operation Star.
#
# Each entry is {"name": the RECORD name, "kind": "mesh" or "texture", "file": where it is}.
# A mesh's texture TOKEN is its record name with the leading prefix stripped (x2go does the
# stripping), so the record `coc_coc_t34_42_dift` is what the token `coc_t34_42_dift` resolves to.
# Written up in sabow-docs notes/81_azgo_indices_are_per_node.md.
#
# EMPTY BY DEFAULT, and pinned per build through build_ai(own_assets=...), for the reason spec_over
# exists: a PROVEN entry has to be able to pin anything a later build can move.
OWN_ASSETS = []


ADDON_VEHICLES = ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m")     # what "Build" in the tab puts in the one gtos_ww2 add-on, in order
# WHAT THE SETTINGS FILE MAY CHANGE ON A BUILT-IN. A built-in's names, codes, uid and side stay in
# this file, where they were proven by hand; what the file may set is how it is CREWED. Refusing
# everything - the old rule, "a built-in is never overridden by the file" - meant a built-in could
# never be made playable at all, which is how the KV-1 sat AI-only while looking ready.
# Safe because PROVEN builds carry their own pinned specs (SPEC_PINNED / proven_specs.json): a change
# here cannot alter a build that has already been proven.
PLAYABLE_OVERRIDE = (
    "crewable", "weapons", "sight_stubs", "fifth_station", "gunner_sight", "own_crew",
    "opstar_squad", "crew_squad", "wp_edits", "mesh_points", "other_sights", "extra_sights",
    "sync_retarget", "sync_add", "sync_retarget", "gunner_hatch", "gunner_turnout",
    "commander_freelook", "plc_edits",
)
BUILT_IN_OVERRIDDEN = {}          # name -> [fields the file set], for the build to report

BUILT_IN = tuple(ADDON_VEHICLES)     # the four proven by hand; anything after them is murkz's own, from the file below

# Vehicles murkz adds himself with "Add an Operation Star vehicle" (2026-09-18). They live in a settings FILE, not in
# this code, so adding one is not a code change: propose() works the settings out of the game's own tables, add()
# writes them here, and they join VEHICLES and ADDON_VEHICLES on the next start. The PROVEN builds name their own
# vehicles, so they keep rebuilding whatever is in this file.
USER_VEHICLES = os.path.join(HERE, "gtos_user_vehicles.json")


def load_user_vehicles(path=USER_VEHICLES):
    """Merge the user's own vehicles into VEHICLES / ADDON_VEHICLES / READABLE. Returns their names, in order."""
    global ADDON_VEHICLES
    if not os.path.isfile(path):
        return []
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    order = []
    for name, spec in sorted(data.items(), key=lambda kv: kv[1].get("added", "")):
        if name in BUILT_IN:
            base = VEHICLES.get(name)
            if not isinstance(base, dict):
                continue
            changed = [k for k in PLAYABLE_OVERRIDE if k in spec and base.get(k) != spec[k]]
            for k in changed:
                base[k] = spec[k]
            if changed:
                BUILT_IN_OVERRIDDEN[name] = sorted(changed)
            continue
        spec = dict(spec)
        READABLE[name] = spec.pop("readable", name)
        spec.pop("added", None)
        spec["uid"] = int(spec["uid"])    # JSON has no hex
        VEHICLES[name] = spec
        order.append(name)
    ADDON_VEHICLES = BUILT_IN + tuple(order)
    return order

VEHICLE_NAMES = set()               # every vehicle name in Operation Star's techn_base, filled on read
WRECKS = []                          # (placeholder, real value) swapped into the compiled vehicle table
SIDES_GATE = 11                      # common_res sides[] field that gates quick battle (notes/26)
GER = 5391687                        # the side token as stored ("GER")
# side -> (token, stock name text id, stock gate). A side is listed in quick battle when its gate is >= 2.
SIDES = {"GER": (GER, "txt_side_german", 1), "FR": (21062, "txt_side_france", 0)}
USSR = 1381192533                    # the stock USSR side token
# v11: a side repainted as another: every field copied from `like` except the token, the name and the gate. BoW43's
# FR row was exactly this (v685's common_res vs stock, 2026-09-17): USSR's colour, call group, flag, background,
# medals, key panel, box, level text and language "rus", with its own name txt_side_ww2_sov = "Soviets".
REPAINT = {"FR": {"like": USSR, "name": "txt_side_ww2_sov", "text": "Soviets"}}


def work_dir(install):
    return os.path.join(install, "users", "modwork", ADDON)


# ---------------------------------------------------------------- the vehicle's own table

def opstar_record(opstar, name):
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    return gtos_opstar.read(*src.records[(name, "config")])


def opstar_text(install, opstar, name, log):
    """An Operation Star table decompiled by the game's cfgp2pd (cached while the table is unchanged).
    cfgfix is not used: it cannot pair the whole techn_base (it stops at '53k'), and we only cut
    whole top-level blocks out of the text."""
    folder = os.path.join(work_dir(install), "text", name)
    os.makedirs(folder, exist_ok=True)
    blob = opstar_record(opstar, name)
    cfg = os.path.join(folder, name + ".stock.config")
    raw = os.path.join(folder, name + ".cfgp2pd.engcfg2")
    if not (os.path.isfile(cfg) and open(cfg, "rb").read() == blob and os.path.isfile(raw)):
        with open(cfg, "wb") as f:
            f.write(blob)
        if os.path.exists(raw):
            os.remove(raw)
        build.starter(install, "cfgp2pd,", build.rel(cfg, install) + ",", build.rel(raw, install),
                      expect=raw, timeout=900)
        log("OK  Operation Star %s decompiled (%d bytes of text)" % (name, os.path.getsize(raw)))
    with open(raw, "rb") as f:
        return f.read()


def opstar_techn_text(install, opstar, log):
    return azcf.Table(opstar_record(opstar, "techn_base")), opstar_text(install, opstar, "techn_base", log)


def cut_blocks(raw, names, what):
    """The text of whole top-level blocks `name=() { ... } //endof name`, each found exactly once."""
    out = []
    for n in names:
        head = CRLF + n.encode() + b"=()" + CRLF
        if raw.count(head) != 1:
            raise SystemExit("%s: block %s found %d times in the text" % (what, n, raw.count(head)))
        start = raw.find(head) + 2
        tail = b"} //endof " + n.encode() + CRLF
        end = raw.find(tail, start)
        if end < 0:
            raise SystemExit("%s: block %s has no end" % (what, n))
        out.append(raw[start:end + len(tail)])
    return out


def top_names(raw):
    """Every top-level block name in a cfgp2pd text (a `name=()` line at column 0)."""
    return {m.decode("latin1") for m in re.findall(rb"\r\n([A-Za-z0-9_]+)=\(\)\r\n\{", raw)}


def top_spans(t, names, tops=None):
    """{name: [(block name, letters, rows, values)]} - each wanted top-level block with its sub-blocks, up to
    the next TOP-LEVEL block of the table (`tops`; default: just `names`). Its own properties read as properties."""
    blocks = t.blocks
    tops = set(tops or names)
    out = {}
    for i, b in enumerate(blocks):
        if b.name not in names or b.name in out:
            continue
        seq, j = [], i
        while j < len(blocks) and (j == i or blocks[j].name not in tops):
            x = blocks[j]
            if j == i and x.rows and x.spec.replace("\0", "") in ("s", "u"):
                # a crew or body block keeps its properties in the block itself, field type 'u' (or 's');
                # read as plain rows they are pointers and lengths, and a check on those proves nothing
                vals = t.props(x)
            else:
                vals = t.rows(x) if x.rows else []
            seq.append((x.name, x.spec.replace("\0", ""), x.rows, vals))
            j += 1
        out[b.name] = seq
    return out


def compile_blocks(install, name, texts, swaps, log):
    """Compile top-level block texts into our table `name`, then swap each (placeholder -> value) back in.
    Every occurrence is swapped; each changes exactly 2 bytes (', ' for '__')."""
    folder = os.path.join(work_dir(install), "text", name)
    src_txt = os.path.join(folder, name + ".loc_def.engcfg2")
    os.makedirs(folder, exist_ok=True)
    with open(src_txt, "wb") as f:
        f.write(b"//Cfgp2Pd auto converter" + CRLF + CRLF + CRLF.join(texts))
    built = textable.compile_text(install, src_txt, os.path.join(folder, "out", name + ".config"), log)
    for placeholder, value in sorted(set(swaps)):     # several blocks can share one value
        n = built.count(placeholder + b"\0")
        if n < 1:
            raise SystemExit("%s: placeholder %r not found after compiling" % (name, placeholder))
        before = built
        built = built.replace(placeholder + b"\0", value + b"\0")
        if len(built) != len(before) or sum(1 for x, y in zip(before, built) if x != y) != 2 * n:
            raise SystemExit("%s: the swap of %r changed the wrong bytes" % (name, placeholder))
    return built


def _placeholder(text, what):
    """Replace each ostov_type value 'tabs\\x.cfgpack, y*' with a same-length placeholder; returns (text, swaps)."""
    swaps = []

    def sub(m):
        value = m.group(2)
        if value.count(b", ") != 1 or b"__" in value:
            raise SystemExit("%s: ostov_type %r is not the shape the placeholder handles" % (what, value))
        ph = value.replace(b", ", b"__")
        swaps.append((ph, value))
        return m.group(1) + ph + b";"
    text = re.sub(rb"(\tostov_type\[s\]\t= )([^\r\n]*);", sub, text)
    return text, swaps


# ---------------------------------------------------------------- v5: the German crew (humans and bodies)

HUM = "hum_gtos"                     # our crew table: only the crew blocks this add-on uses
BODYS = "bodys_gtos"                 # our dead-body table: only the bodies those crews name


def build_crew_tables(install, opstar, by_table, log):
    """Our hum_gtos (the crew blocks, and their _summer versions the engine picks in summer) and bodys_gtos
    (the bodies they name), for EVERY crew table the fleet draws on. Operation Star's blocks; the only
    change is the body table's name inside ostov_type, tabs\\bodys.cfgpack -> tabs\\bodys_gtos.cfgpack.

    by_table: {"ger_hum_base": [blocks], "rus_hum_base": [blocks]} - a fleet that mixes German and Soviet
    crews puts both sets of men in the ONE table the add-on ships, which is why this takes a map now
    (until 2026-09-28 it read ger_hum_base and nothing else).
    Returns (hum, bodys, report, tokens)."""
    braw = opstar_text(install, opstar, "bodys", log)
    btab = azcf.Table(opstar_record(opstar, "bodys"))
    patterns = set()
    fixed, swaps = [], []
    hnames = []
    report, tokens = [], set()
    sources = []
    for table in sorted(by_table):
        humans = sorted(by_table[table])
        hraw = opstar_text(install, opstar, table, log)
        htab = azcf.Table(opstar_record(opstar, table))
        names = []
        for h in humans:
            names += [h, h + "_summer"]
        for txt in cut_blocks(hraw, names, table):
            txt = txt.replace(b"= tabs\\bodys.cfgpack, ", b"= tabs\\%s.cfgpack, " % BODYS.encode())
            head = txt.split(b"=()", 1)[0].decode("latin1")
            for old, new in crew_row_edits(head).items():
                row = b"\t\t" + old.encode() + b","
                if txt.count(row) != 1:
                    raise SystemExit("%s: %s's %s row found %d times in the block, expected 1"
                                     % (table, head, old, txt.count(row)))
                txt = txt.replace(row, b"\t\t" + new.encode() + b",")
            txt, s = _placeholder(txt, table)
            swaps += s
            fixed.append(txt)
            for ph, value in s:
                patterns.add(value.split(b", ")[1].rstrip(b"*").decode())
        sources.append((table, htab, names, hraw))
        hnames += names
    all_bodies = sorted({b.name for b in btab.blocks if any(b.name.startswith(p) for p in patterns)
                         and re.match(r"^[a-z_]+\d+$", b.name)})
    # a pattern like ghum_body* also matches ghum_body_sum0 - keep only names that are the pattern + digits
    bnames = [n for n in all_bodies if any(re.match("^%s\\d+$" % re.escape(p), n) for p in patterns)]
    btexts = cut_blocks(braw, bnames, "bodys")
    hum = compile_blocks(install, HUM, fixed, swaps, log)
    bodys = compile_blocks(install, BODYS, btexts, [], log)
    for label, orig, new, names, rename, raw in (
            [("crew %s" % t, ht, azcf.Table(hum), ns, True, rw) for t, ht, ns, rw in sources] +
            [("bodies", btab, azcf.Table(bodys), bnames, False, braw)]):
        # tops = EVERY crew block in the compiled table, not just this table's: the compiled hum_gtos
        # holds the German and the Soviet men side by side, and a span that only knows its own table's
        # names runs to the end of the table and swallows the other side's blocks. Caught on the probe
        # build, where the last German block came out 36 blocks long.
        a = top_spans(orig, names, top_names(raw))
        b = top_spans(new, names, hnames if label.startswith("crew") else names)
        for n in names:
            if n not in a or n not in b or len(a[n]) != len(b[n]):
                raise SystemExit("%s: block %s missing or a different size" % (label, n))
            for x, y in zip(a[n], b[n]):
                if x == y:
                    continue
                if x[0] == y[0] and x[2] == y[2] == 0 and x[3] == y[3]:
                    continue                                     # empty block's field letters (as v685)
                if rename and isinstance(x[3], dict) and isinstance(y[3], dict):
                    want = dict(x[3])
                    want["ostov_type"] = want["ostov_type"].replace("tabs\\bodys.cfgpack, ", "tabs\\%s.cfgpack, " % BODYS)
                    if y[3] == want:
                        continue
                if label.startswith("crew") and isinstance(x[3], list) and isinstance(y[3], list):
                    # a row this build deliberately replaced (CREW_ROW_EDITS): compare the SOURCE with
                    # the substitution applied, so the check still demands an explanation for every
                    # other difference
                    ed = crew_row_edits(n)
                    want = [[ed.get(r[0], r[0])] + list(r[1:]) for r in x[3]]
                    if [list(v) for v in y[3]] == want:
                        continue
                raise SystemExit("%s: %s block %s differs from Operation Star's" % (label, n, x[0]))
            head = a[n][0][3]
            if isinstance(head, dict):
                tokens.update(re.findall(r"[A-Za-z0-9_]{3,48}", " ".join(str(v) for v in head.values())))
        report.append("  %s: %d blocks identical to Operation Star's%s: %s" % (
            label, len(names), " (bodies table renamed to %s)" % BODYS if rename else "", ", ".join(names)))
    return hum, bodys, report, tokens


def crew_voices(install, opstar, by_table):
    """The crew's voice lines SABoW lacks (v6). Each human names a voice set (speech = speech_ger); the set's
    rows in hum_params are bases (safe_ger, tanks_ger, ...) and the engine asks for BUILT names from them -
    safe_ger_01_* was in the v5 log as "Unable to find audio fragment" - so no name-follower finds them.
    Stock SABoW has speech_ger but none of its sounds; Operation Star has 146 (3.8 MB). A SOVIET crew
    usually needs nothing: SABoW's own T-62 crew already speaks Russian, so the lines are stock.
    by_table: {"ger_hum_base": [blocks], "rus_hum_base": [blocks]}.
    Returns ([(archive, entry)], [report lines])."""
    have = gtos_opstar.Index(gtos_opstar.sabow_archives(install))
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    sets = set()
    for table in sorted(by_table):
        ht = azcf.Table(opstar_record(opstar, table))
        want = set(by_table[table]) | {h + "_summer" for h in by_table[table]}
        sets |= {ht.props(b).get("speech") for b in ht.blocks if b.name in want} - {None, ""}
    sets = sorted(sets)
    hp = azcf.Table(gtos_opstar.read(*have.records[("hum_params", "config")]))
    bases = sorted({r[0] for b in hp.blocks if b.name in sets for r in hp.rows(b)})
    found = sorted((src.records[(n, k)] for (n, k) in src.records
                    if k == "sound" and not have.has((n, k)) and any(n.startswith(b + "_") for b in bases)),
                   key=lambda pe: pe[1][0])
    lines = ["  voice set %s: %d voice lines SABoW lacks (%.1f MB), groups %s" % (
        ", ".join(sets), len(found), sum(e[2] for p, e in found) / 1e6, ", ".join(bases))]
    return found, lines


# ---------------------------------------------------------------- the gunner's "set target" line
# MEASURED 2026-10-01 out of murkz's common_engine.log:
#     ERROR! [i_audioman:audioman] Bind() Unable to find audio fragment 'set_target_gun_eng_*'!
# three times in five minutes - it fires once per target designation, so it is constant in play.
#
# Only TWO set_target sounds exist anywhere on the install: `set_target_com_eng_01` and
# `set_target_com_rus_01`, both AAF1, 38,492 B, kind `sound`, loc `loc_def`, in SABoW's own
# speech_cocpits archives. **Operation Star and Tunisia 1943 have NONE** (searched every flatdata
# in both), so unlike crew_voices this is not a port from a richer game - there is nothing to
# borrow and the only possible fix is a duplicate under the name the engine asks for.
#
# The engine composes the name from a role token and only the COMMANDER variant was ever recorded.
# WHY it asks for the gunner's is NOT ESTABLISHED - it may key off the seat the player is in, or
# off a vehicle's crew layout, and nothing measured distinguishes them. This fix deliberately does
# not depend on knowing: providing the file satisfies the request either way. (An earlier guess,
# that the T-34 has no commander station, was wrong - its cockpit does carry commander rows.)
#
# On a T-34 the commander's recording is the RIGHT voice regardless: that crewman is the commander.
# These are NEW ids, so the rule that an add-on cannot redefine a base string id (which silently
# ignores duplicates) works in our favour here rather than against.
SPEECH_DUPES = {
    "set_target_gun_eng_01": "set_target_com_eng_01",
    "set_target_gun_rus_01": "set_target_com_rus_01",
}


def speech_dupes(install):
    """[(name, kind, loc, bytes, group)] for sounds the engine asks for that exist under another
    name, plus report lines.

    ALWAYS EMITS, and that is deliberate. Every build replaces our archives wholesale, so a record
    that is skipped because "it already exists" would be skipped on the strength of the copy that
    is about to be deleted - the v017 defect exactly. The only thing that stops the build is a
    MISSING SOURCE, which would mean the duplicate could not be made at all.
    """
    have = gtos_opstar.Index(gtos_opstar.sabow_archives(install))
    out, lines = [], []
    for new, src in sorted(SPEECH_DUPES.items()):
        key = (src, "sound")
        if not have.has(key):
            raise SystemExit("speech_dupes: %s is not on the install, so %s cannot be made" % (src, new))
        blob = gtos_opstar.read(*have.records[key])
        out.append((new, "sound", "loc_def", blob, "speech_opstar"))
        lines.append("  %-24s <- %-24s %d B (byte copy)" % (new, src, len(blob)))
    return out, lines


# ---------------------------------------------------------------- crewable (v7)
#
# The SABoW Ext recipe (recipe.py: donor cockpit, gun and shells, crew positions, hide + hide fix) run on OUR
# vehicle, plus three things only a GTOS vehicle needs:
#   - the gunner sight: Operation Star's tzf5f exists in stock SABoW as an EMPTY stub (no reticle, colours,
#     zoom - BoW43 notes/44 2b) and a crewed gunner on it 001s. BoW43's working Panzer IV pointed the gunner
#     at tzf5f_r, a renamed copy of the stock T-62 sight row tsh2b (magnification 9, 3.5/7, reticle tnsh2b_41).
#   - sight views: the donor cockpit opens each crewman on sight numbers 0..n in his sight group (plc_states
#     field 2). The T-62 cockpit uses 3 driver, 3 gunner and 3 commander views; the Panzer IV has 2, 2 and 1.
#     Missing numbers are padded with copies of the group's first row - the gunner's with tzf5f_r and head1.
#   - a fifth crew station: a cockpit binds only if it has at least the vehicle's work_places stations
#     (driver, gunner, loader, mgunner, commander). BoW43 notes/22 variant C, proven on the Tiger: an mgunner
#     block before the loader, loader views renumbered 3 -> 4, two basic views for place 3. The engine builds
#     blocks 0, 1, 2 and the last - the hull machine-gunner is the seat it skips.

# The commander's turned-out row from stock coc_t62, place 2 -> 1. A view with no sight (0xffffffff),
# no device, and the wide look-around angles a head-out crewman gets.
GUNNER_TURNOUT_STATE = ("1, 4294967295, 4096, 0, 0, 0xffffffff, , , , , -0.07, -0.1, 0.05, 0, "
                        "-160, 160, -80, 30, 4294967295, 1, 0, 0, 0, , , , 0, 0, 0, 0, ")

# v42: A COMMANDER SIGHT VIEW THAT IS NOT A DEVICE. Measured in coc_t62: the commander's only two
# sight rows, 7 and 10, BOTH name button tnks_rfinder and device tnk_rfinder, and neither free-looks.
# Row 17, the T-62 LOADER's rotating periscope, is the shape that does: slot -1, flags 0x0000, no
# button, no device. This is that shape for the commander, on SIGHT INDEX 1 - the one index his
# plc_states never selects, although the sights table already pads sig_commander_x1 to fill it.
# So it ADDS a third view and disturbs neither of the two that exist.
#
# ONE VARIABLE: the pad copies sig_commander, so this view shows THE SAME OPTIC as view 1. If it
# turns and view 1 does not, the binding is the cockpit row and nothing else - which is the whole
# question v37-v41 kept asking of the sight row instead.
#
# Geometry is row 10's, unchanged: chunk tnk_head, its offset, its -160..160 azimuth. The NAME is
# left BLANK on purpose. Every one of the cockpit's 8 sight rows ends with a name that the click
# block also carries (com_sight_01, load_sight_01 ...), and coc_t62 has no com_sight_03 - naming a
# row after something that is not there is exactly the cockpit-ceiling 001. Blank, like row 9.
# If the view does not appear in the C cycle at all, the click row is the next thing to add.
COMMANDER_FREELOOK_STATE = ("2, 4294967295, 0, 0, 0, 1, , , tnk_head, , -0.09, -0.14, 0.05, 0, "
                            "-160, 160, -60, 17, 4294967295, 1, 0, 0, 0, , , , 0, 0, 0, 0, ")

SIGHT_STUB = "tzf5f"                            # the Panzer IV's stub row; per vehicle in VEHICLES["sight_stubs"]
# WHICH SIGHT A VEHICLE'S VISION BLOCKS USE, for every vehicle, unless one overrides it. Same shape as
# GUNNER_SIGHT and SIGHT_STUB: a build-wide default with a per-vehicle spec field (vision_blocks) that can
# change it or set it to {} for none.
# ONE KEY PER STATION GROUP, because the two kinds of vision block are not the same device:
#   sig_driver  a driver's view is 35 deg at 1x (driver_tech's own field), so his slit is too. murkz on
#               v88: "remove the magnification from it" - a 20 degree slit in a driver's seat reads as
#               magnified, and he was right.
#   default     every other place: the gunner's and loader's side slits, which were on the shared 20 deg
#               vision block and stay at 20.
# The rows are found by their SIGHT (whatever is still on VISION_BLOCK), so a vehicle with three slits gets
# three, one with none gets none, and nothing is listed per vehicle anywhere.
VISION_BLOCKS = {"default": "slit_g", "sig_driver": "drv_slit_g"}
# GROUPS WHOSE **PAD** ROW IS THE ONE THE COCKPIT ACTUALLY READS. v36 found this for the driver - coc_t62's
# driver plc_states asks for sight index 2, and a vehicle with two driver sights gets its index 2 from the
# pad, so "changing index 1" changed a row nothing looked through. The same trap bit again on v90: the
# Panzer IV's driver had no mask because the row he reads is sig_driver_x2 and only sig_driver_01 had been
# changed. So the pad takes the vision-block row for these groups too, and NO VEHICLE NEEDS LISTING.
# murkz: "teach vision_blocks to find the pad itself so no vehicle needs listing".
VISION_BLOCK_PADS = ("sig_driver",)
VISION_BLOCK = "hole"                           # the SHARED vision block every crewman looks through by default -
# THE SAME PLAIN APERTURE UNDER ANOTHER NAME. An imported tank's driver does not sit on "hole": he sits
# on driver_tech, the stock driver's row at HIS OWN 35 degrees - and the sweep below only ever looked
# for "hole", so it walked straight past him. Measured 2026-09-28 on the KV-1S: its gunner got slit_g
# automatically (that row WAS on hole) and its driver got nothing; the KV-1 has the same shape.
# murkz: "why does not the tool build it with the rest of the build?" - it should, so a DRIVER's row on
# this row takes the driver's vision-block row like every other driver already does.
# DRIVERS ONLY, AND BY GROUP: the commander's rows sit on commander_tech at 25 degrees and his stock
# view is a DELIBERATE choice (v87, step 20), not a gap - so nothing outside sig_driver is touched. It
# is drv_slit_g, at 35 degrees, and not slit_g at 20: that is the whole of v89's lesson, because a
# 20-degree row in a 35-degree view reads as magnification.
DRIVER_PLAIN = "driver_tech"                    # the stock row an imported driver's own view sits on
                                                # a slit or a port with no art and so no mask. A vehicle can give
                                                # its own vision blocks a masked row; see spec["vision_blocks"]

# A work_place row, by position. notes/20 (BoW43, 2026-09-02) measured these the hard way: renaming a station
# does NOTHING, the label is cosmetic. Field [11] is the ROLE the engine binds a cockpit place to, and [18] is
# the index. A T-34 with role "driver" and index 7 on its hull machine-gunner fails; "commander" and 4 works,
# keeping the s_mgunner anchors, because the T-34 model has no commander chunks at all.
WP_GROUP, WP_ROLE = 10, 11
PLACE_ROLES = {0: "driver", 1: "gunner", 2: "commander", 3: "loader"}


def place_groups(t, vehicle, wp_edits=None):
    """{cockpit place -> the sight group the VEHICLE uses for it}, read from its own work_places.

    The donor cockpit opens place N on a numbered view within one sight group. Which group is not fixed:
    it is whatever the work_place holding that ROLE names in field [10]. For the Panzer IV this reproduces
    the old hardcoded map exactly (sig_driver, sig_gunner, sig_commander, sig_loader). A T-34 has no
    commander station at all - notes/20 declares its hull machine-gunner's role as commander, and that
    station's group is sig_mgunner - so the fixed map cannot describe it.

    wp_edits are applied in memory first, because the role fix lives in the text and the table read here
    still has the vehicle's original rows.
    """
    blocks = dict(azcf.vehicles(t))[vehicle]
    if "work_places" not in blocks:
        raise SystemExit("%s has no work_places block" % vehicle)
    rows = [list(r) for r in t.rows(blocks["work_places"])]
    for r in rows:
        for f, v in (wp_edits or {}).get(r[0], {}).items():
            r[int(f)] = v      # JSON keys are strings
    out = {}
    for place, role in PLACE_ROLES.items():
        hit = [r for r in rows if len(r) > WP_ROLE and r[WP_ROLE] == role]
        if hit:
            out[place] = hit[0][WP_GROUP]
    return out

# The gunner sights the crewable build can give it. Each is ONE common_res_mod row: donor_row copied, with
# `fields` changed ({flat position: (text token, value as the table decodes it)}), plus its reticle mesh.
GUNNER_SIGHTS = {
    # v7: BoW43's first working alias - the stock T-62 TSh-2B-41, renamed (notes/44)
    "tzf5f_r": dict(row="tzf5f_r", donor_row="tsh2b", fields={}, mesh=None,
                    label="tzf5f_r, a renamed stock tsh2b (the T-62's TSh-2B reticle)"),
    # v8: murkz's own TZF 5f, drawn from Bild 52 - BoW43 v685 "perfect" (2026-09-11, notes/85). The row is stock
    # tzf5f's optics (18x, 2.5 deg) with the drawing fields of tsh2b and field 36 1.427; values read from the v685
    # zip's common_res_mod. The mesh is not in git (*.mesh ignored): read from the v685 backup, md5-checked.
    "tzf5f_g": dict(row="tzf5f_g", donor_row="tzf5f", fields={
        2: ("45", 45.0), 24: ("tzf5f_c", "tzf5f_c"), 25: ("cross", "cross"),
        26: ("3221225472", 3221225472), 27: ("4293318077", 4293318077), 28: ("4294967295", 4294967295),
        29: ("4289571728", 4289571728), 30: ("3", 3), 36: ("1.427", 1.427), 37: ("1.43", 1.43), 38: ("0.2", 0.2),
        53: ("txt_sig_tnsh2b_41", "txt_sig_tnsh2b_41"), 54: ("tnk_sig_tele", "tnk_sig_tele")},
        mesh=("tzf5f_c", r"L:\sabow-backups\v685_PROVEN_TZF5F_COMPLETE\tzf5f_c.loc_def.mesh",
              "9fcae17503a7145e4659c5a56f180621"),
        label="tzf5f_g, murkz's TZF 5f (BoW43 v685, mesh tzf5f_c)"),
}
# v9: the same row, the reticle rebuilt at 1 px (murkz, v8: "gunsight lines need to be thinner"). Same drawing and
# --box as v685, mksight --width 0.0004 instead of 0.0016; the 0.0016 control rebuilt v685's mesh exactly.
# Recipe and md5s: L:\sabow-ext-backups\reticles\tzf5f_c_1px\README.md
GUNNER_SIGHTS["tzf5f_g_1px"] = dict(GUNNER_SIGHTS["tzf5f_g"],
    mesh=("tzf5f_c", r"L:\sabow-ext-backups\reticles\tzf5f_c_1px\tzf5f_c.loc_def.mesh",
          "a034bec533ba018ddc1d2bcc2f4a4c0c"),
    label="tzf5f_g, murkz's TZF 5f (BoW43 v685 drawing, mesh tzf5f_c rebuilt at 1 px)")
# v17/v18: the same 1 px drawing, re-split so the aiming strich (the seven triangles) and the vertical post
# below them sit in d_distance - the ONE node the engine's range drum moves (BoW43 notes/79, 86). The row
# carries the travel in fields 31-34. Mesh: tool/tzf5f_moving.py, geometry vertex-for-vertex the 1 px one's.
#
# v17 was BUILT and played (murkz: the strich does move). Three faults, all answered in v18:
#   - half the bar, half a small triangle and half the post stayed put - the selection split three quads.
#     Fixed in tzf5f_moving.py: 20069..20112, whole pairs, 44 triangles (was 41).
#   - "a box outline around the gunsight" - mksight's d_base frame. NOT new in v17 (the static reticle has
#     it too, v8 onward) but the moving template draws it 0.0013 wide against m17c_cross's 0.0009, so it
#     reads as a box. tzf5f_moving.hide_frame() sets those 15 vertices to alpha 0; geometry untouched.
#   - "the movement is to slow... many mouse wheel rotations to move it a bit". THE RATE IS NOT PER RANGE
#     STEP, IT IS PER SECOND: notes/86 disassembled it as `drum += [row+0x88] * dt`, box units per second
#     with the translate flag. At the Matilda's 0.0152 our 0.5-tall box takes 33 s to traverse, which is
#     exactly what he describes. 0.2 is the stock T-62's own proven number in this engine (0.8 box-heights
#     per second against its 0.25 box); for our 0.5 box that is 0.4 box-heights/s. Tune from his next look.
#
# v19, from murkz on v18: "mouse movement is very good now" (rate 0.2 CONFIRMED, leave it), "the strich
# starting point is too high, I have to rotate it down to start with", "we still have the outer square line".
#   - THE SQUARE was the frame TWICE. The source is itself an mksight product and already carries a d_base
#     frame in its first 15 triangles; build() prepends another. v18 blanked the one build() adds and left
#     the source's own copy opaque - so alpha was never the question. v19 drops the source's 15 frame
#     triangles and pins the bounding box with two degenerate corner triangles instead (keeping the frame's
#     points does not work: resplit drops any vertex no triangle references, and the artwork alone stops
#     0.00148 short in y, which would renormalise the whole drawing). Verified: bbox still 0,0,0.5,0.5 and
#     no frame-sized triangle can draw.
#   - THE START POSITION is now measured, not guessed. The square itself was the ruler: its sides sit at art
#     x 0 and 0.5, 1026 px apart in his shot, centred on the screen centre, so art 0.25 is screen y 540 at
#     2052 px per art unit. His point-blank tip photographed at screen y 544 = art y 0.2481, against the
#     0.2880 the mesh draws - he had wound it down 0.0399. Point blank therefore puts the tip on the sight's
#     own centre, which is what a zeroed sight should do, so the art simply started 0.0380 too high.
#     tzf5f_moving.DROP lowers the whole strich by that, tip verified resting at exactly 0.2500.
GUNNER_SIGHTS["tzf5f_g_moving"] = dict(
    GUNNER_SIGHTS["tzf5f_g_1px"],
    fields=dict(list(GUNNER_SIGHTS["tzf5f_g_1px"]["fields"].items())
                + [(31, ("0", 0.0)), (32, ("-0.5", -0.5)), (33, ("0.2", 0.2)), (34, ("3", 3.0))]),
    mesh=("tzf5f_c", r"L:\sabow-ext-backups\reticles\tzf5f_c_moving\tzf5f_c.loc_def.mesh",
          "10d9f627acf4557aaa249d55216f37ee"),
    label="tzf5f_g, murkz's TZF 5f with a MOVING strich (1 px art, strich + post in d_distance)")
# The v19 reticle, FROZEN. gtos_ww2 v19 is proven against exactly this mesh (murkz: "perfect"), and the live
# tzf5f_c_moving folder is overwritten by every tzf5f_moving.py run - so PROVEN points here, not there.
GUNNER_SIGHTS["tzf5f_g_moving_v19"] = dict(
    GUNNER_SIGHTS["tzf5f_g_moving"],
    mesh=("tzf5f_c", r"L:\sabow-ext-backups\reticles\tzf5f_c_moving_v19\tzf5f_c.loc_def.mesh", "10d9f627acf4557aaa249d55216f37ee"),
    label="tzf5f_g, murkz's TZF 5f, moving strich as shipped in v19 (frozen)")
# murkz's rule, 2026-09-22: "always use the t62 sight unless there is a real one to use". This is the default
# for any crewable vehicle with no hand-drawn reticle - the vehicle's stub rows point straight at the STOCK
# tsh2b row and NOTHING is added to common_res_mod. notes/44 records that BoW43's tzf5f_r was a renamed copy
# for a COSMETIC reason (a German name over the Soviet TSh-2B reticle), not a technical one, so the stock row
# serves as it stands - and on a Soviet tank it is the right name as well as the right picture.
GUNNER_SIGHTS["tsh2b_stock"] = dict(
    row="tsh2b", donor_row=None, fields={}, mesh=None, stock=True,
    label="the stock T-62 TSh-2B row, used as it is")
# v37: the Matilda commander's ROTATING CUPOLA. murkz: "the entire cupola was seated on a ball-bearing
# race, allowing the commander to manually rotate it to look around". SABoW already has the row -
# periscope_rot, 25 deg at 1x, tnk_sig_pere, mode 2 - and a whole rot family beside it
# (periscope_n_rot, driver_tech_rot). His commander currently reads commander_tech at 25 deg and 2x
# MAGNIFICATION, which is wrong for a cupola periscope.
#
# STOCK, so it adds NOTHING to common_res_mod and ships no mesh - the vehicle's row is simply
# repointed. That also makes it the cleanest possible test of the open question: the stock periscope
# rows all have BLANK reticles, so if this masks, a vision block costs one row and no art, and murkz's
# ask for the block on every tank WITHOUT the Matilda's vertical line is table edits only.
GUNNER_SIGHTS["periscope_rot_stock"] = dict(
    row="periscope_rot", donor_row=None, fields={}, mesh=None, stock=True,
    label="the stock rotating periscope, 25 deg at 1x, used as it is")
# The commander's UNCHANGED view, pinned so v37 carries its own control. Padding copies the FIRST row
# of the group AFTER other_sights has edited it, so repointing sig_commander silently repointed both
# pads too and all three commander views came out identical - caught by reading the plan back, which
# is the only reason this entry exists. Index 2 is held at the stock commander_tech, 25 deg at 2x, so
# murkz can switch between his two commander views and compare the cupola against what he had.
GUNNER_SIGHTS["commander_tech_stock"] = dict(
    row="commander_tech", donor_row=None, fields={}, mesh=None, stock=True,
    label="the stock commander_tech row, 25 deg at 2x, used as it is")
# v29: THE T-34 GETS ITS OWN SIGHT. Until now it has looked through the T-62's TSh-2B - 9.0 deg at 3.5-7.0x,
# about half the field of view at up to 2.8x too much magnification, with range marks cut for a 115 mm
# smoothbore. The T-34/76's real optics were in SABoW's table all along with correct values and blank art, and
# Steel Fury has the art. CROSS-CHECKED, two independent files: SABoW's tmfd_7 row and Steel Fury's
# common_res.engcfg:1059 both read 12.5 deg at 2.5x. Apparent FOV is therefore 31.25 (= 12.5 x 2.5), the same
# rule tzf5f_g uses (18 x 2.5 = 45), and notes/76's constraint is met - FOV[1] is well over 0.001 rad.
# Mesh: tool/mkt34_sight.py, the three Steel Fury parts combined - a the etched ladders and Cyrillic
# ammunition labels, b the horizontal line, c the vertical. STATIC on purpose: the engine moves ONE node and
# which layer should be it is not settled (docs/t34-sight-scope.md section 4), so the art is proven first.
# Field 36 stays at tzf5f_g's 1.427 rather than being raised, because notes/78 measured field 15[0] as the
# reticle SCALE (0.791 -> ~40% of the sight circle, 1.5 -> fills it) and says 1.5 is the largest any shipped
# optic uses - so the art was grown inside its own 0..0.5 box instead, which mkt34_sight does by declaring a
# square box centred on the optical axis. The art now fills the box exactly as the proven TZF 5f's does.
# TEXT: field 53 keeps txt_sig_tnsh2b_41, so the sight is LABELLED "TSh-2B-41" and is not one. Cosmetic, and
# deliberately not fixed here - a new string id is its own job (an addon cannot redefine a base id, only add),
# and on a Soviet tank a Soviet sight name at least does not jar. One variable at a time.
# NOTE both gunner rows take the alias: a T-34 has TWO stubs (pt4_7 and tmfd_7) and the tool has one alias, so
# the periscope view shows the telescope too. No worse than today, where both show the T-62 - but it is why
# the PT-4-7 is a separate job and not a second entry here.
# v55: THE PANZER III DRIVER'S VIEW PORT. murkz: "we have a perfect reference example of a viewport
# in the matilda ... It has a black mask all around the outer edge. Also our pzr 3 drivers viewport
# should inherit the fov, position etc for this port from the AI stats."
#
# WHICH ROW: plc_states field [2] is the sight index within the place's sight group
# (docs/plc-states-decoded.md, certain). pz3jlg's driver has SIX plc_states rows and reads a sight on
# exactly ONE - index 2. The rest are 0xffffffff, free head. So the row to repoint is the driver's
# sight row at INDEX 2, which is the PAD the tool copies in because the cockpit wants three driver
# views and the vehicle declares two. v35 repointed index 1, which nothing reads, and drew a wrong
# conclusion from a test that could not work.
#
# THE FOV IS OPERATION STAR'S OWN NUMBER, not a guess: its driver rows are
#     sig_driver     s_camera_driver     driver_tech
#     sig_driver_01  s_camera_driver_01  hole
# and SABoW reads driver_tech at 35.0 deg. driver_tech_rot is the same device in the periscope rot
# family - the one v37 identified as carrying tnk_sig_pere - so cloning THAT and setting 35 keeps the
# vision-block mask and takes the FOV from the AI s own stats.
#
# STOCK ART, NO MESH SHIPPED. donor_row is a stock row and mesh is None, so nothing new is drawn and
# nothing is added to common_res_mod but this row. If the mask appears it costs one row and no art.
GUNNER_SIGHTS["drv_port_g"] = dict(
    row="drv_port_g", donor_row="driver_tech_rot",
    fields={1: ("35", 35.0), 2: ("35", 35.0)}, mesh=None,
    plain=True,        # v95: its donor carries no token either, so it is a plain vision block
    label="the Panzer III driver's view port, 35 deg - the AI's own FOV, stock periscope art")


# v82: THE SIDE SLITS. A T-34/76 has one slit each for the gunner and the loader, and both were pointed at
# the shared vision block "hole" - the generic-row problem again: it carries no art, so it carries no mask.
# murkz: "yes loaders slit is now look to the right, it needs a mask but good".
# THE MASK COMES WITH THE ROW, which is the mechanism proven twice: mk4_g ("the first 2nd sight with a mask
# (block border)") and pt4_7_g ("wow perfect") are both clones of m60_periscope. So is this one, and
# mesh=None because m60_periscope's own art is stock - nothing new is drawn.
#   [1] 45 -> 20 and [2] 45 -> 20   THE SLIT'S OWN FIELD, taken from the row it replaces: the shared
#        vision block "hole" is 20 deg at 1x, so nothing about what he sees changes except the mask. The
#        aperture that makes it a SLIT rather than a square window is the next question, not this build.
# v83: AND IT MUST NOT BE SOMETHING HE AIMS WITH. murkz on v82: "the loader can rotate his via via the
# turret, which is not possible as the controls are on the other side of the turret to him". Measured: every
# stock view that DRIVES something carries the type token tnk_sig_pere (periscope, periscope_rot) and none
# of the plain ones does (hole, zero, driver_tech, commander_tech, and stock mk4 - which is the nearest
# thing to a slit in the game: mode 2, aperture (6.0, 1.0), NO token). slit_g inherited the token from the
# periscope it copied, so it is cleared here. The MASK comes from the row's ART (the mesh it names), which
# this does not touch - the same row still names m60_periscope.
GUNNER_SIGHTS["slit_g"] = dict(
    row="slit_g", donor_row="m60_periscope",
    # v87: FIELD [3] IS NOT THE APERTURE - IT IS THE RANGE THE PLAYER CAN MOVE THE VIEW THROUGH, AND A
    # VISION BLOCK MUST NOT HAVE ONE. murkz on v86: "loader can rotate the turret again and the mask never
    # changed" - two findings in one line. (6.0, 1.0) left the mask identical, so field [3] does not draw
    # it; but moving it from the donor's (6.0, 4.0) to (6.0, 1.0) gave the loader a view he can move again,
    # and a loader with no independent traverse moves the TURRET with it. So it goes back to the donor's,
    # and the slit is left exactly as v83 shipped it - the build murkz called perfect.
    # v91: THE MESH IS THE MASK. murkz on v90: "none of the new visions slots have changed pzr4". The rows
    # were right and installed; the ART was not. mesh=None keeps the DONOR's own mesh, and m60_periscope's
    # is a bare cross, 8 KB, no window. The mask murkz saw on the M60's commander cupola is
    # m60_cperiscope - 61,440 bytes of rectangular window - a DIFFERENT mesh entirely. Both are stock, so
    # naming it ships nothing new. This is also why the T-34's PT-4 has a mask and the slits never did: the
    # PT-4 names our own pt4_7_c, built from Steel Fury art that carries a frame.
    fields={1: ("20", 20.0), 2: ("20", 20.0), 24: ("m60_cperiscope", "m60_cperiscope"), 54: ("", "")},
    mesh=None,
    # v95: A PLAIN VISION BLOCK. Field [54] is cleared above, which is what makes it plain rather than
    # a device you aim (v83), and v87 recorded the other half of the same rule: a plain vision block
    # has no traverse either. The padding loop reads this flag - a pad that takes a plain row must not
    # go on carrying the traverse it inherited from the row it was copied from. See the pad rule.
    plain=True,
    label="slit_g, a T-34/76 side slit - the shared vision block's own 20 deg at 1x, with the stock "
          "periscope row's mask")
# v89: THE DRIVER'S OWN SLIT, AND NO MAGNIFICATION. murkz on v88: "remove the magnification from it". The
# driver used to read driver_tech - 35 deg at 1x - and slit_g is 20 deg, so his view got TIGHTER, which
# reads as magnification. This row is the same masked slit but at HIS OWN field: 35 deg true, 35 deg
# apparent, so 1x. The gunner's and loader's slits keep 20 deg, which is the shared vision block's own
# value and what they had.
GUNNER_SIGHTS["drv_slit_g"] = dict(
    row="drv_slit_g", donor_row="m60_periscope",
    fields={1: ("35", 35.0), 2: ("35", 35.0), 24: ("m60_cperiscope", "m60_cperiscope"), 54: ("", "")},
    mesh=None,
    plain=True,        # see slit_g above: token cleared, so no traverse either (v95)
    label="drv_slit_g, a driver's slit - his own 35 deg at 1x, with the stock periscope row's mask")
GUNNER_SIGHTS["pt4_7_g"] = dict(
    # A CLONE OF m60_periscope, THE ROW THAT ALREADY CARRIES THE VISION-BLOCK MASK.
    # murkz, 2026-09-28: "we have already done this for the matilda and you re wrote it down yesterday
    # do reinvent" - and he is right, it was in BUILD_LOG.md all along. 2026-09-23: "mk4_g clones
    # m60_periscope and changes four fields; the mask was already in the other 51", and murkz then: "it
    # is the first 2nd sight with a mask (block border) how did you do that?" v34 is PROVEN on exactly
    # this route, so nothing is invented here either - four fields and the donor's other 51:
    #   [1]  45   -> 17.5    the PT-4's true field, GTOS's own number
    #   [2]  45   -> 43.75   apparent = true x 2.5, the rule every other sight here uses
    #   [24] m60_periscope -> pt4_7_c   our PT-4 reticle
    #   [36] 0.15 -> 1.5     the MK-4's own value: our art spans the canvas, so 1.5 fills the circle
    # The donor brings the rest - the mask, the mode 2, the colours, and field [54] tnk_sig_pere, which
    # is already what a periscope carries. The old version cloned GTOS's pt4_7 STUB and had to write
    # every one of those fields by hand; the stub is why v72 drew nothing at all.
    row="pt4_7_g", donor_row="m60_periscope", fields={
        1: ("17.5", 17.5), 2: ("43.75", 43.75),
        24: ("pt4_7_c", "pt4_7_c"), 36: ("1.5", 1.5),
    },
    mesh=("pt4_7_c", r"L:\sabow-ext-backups\reticles\pt4_7_c\pt4_7_c.loc_def.mesh",
          "f4f83483151460f93b53df90ef3bf777"),
    label="pt4_7_g, the T-34/76's PT-4 periscope (17.5 deg at 2.5x, static)")
GUNNER_SIGHTS["tmfd_7_g"] = dict(
    row="tmfd_7_g", donor_row="tmfd_7", fields={
        2: ("31.25", 31.25), 24: ("tmfd_7_c", "tmfd_7_c"), 25: ("cross", "cross"),
        26: ("3221225472", 3221225472), 27: ("4293318077", 4293318077), 28: ("4294967295", 4294967295),
        29: ("4289571728", 4289571728), 30: ("3", 3), 36: ("1.427", 1.427), 37: ("1.43", 1.43),
        38: ("0.2", 0.2),
        53: ("txt_sig_tnsh2b_41", "txt_sig_tnsh2b_41"), 54: ("tnk_sig_tele", "tnk_sig_tele")},
    mesh=("tmfd_7_c", r"L:\sabow-ext-backups\reticles\tmfd_7_c\tmfd_7_c.loc_def.mesh",
          "9512771703b971af969b94dfb7087e5c"),
    label="tmfd_7_g, the T-34/76's own TMFD-7 (12.5 deg at 2.5x, Steel Fury art, static)")
# The v29 reticle, FROZEN. gtos_ww2 v29 is proven against exactly these bytes (murkz: "v29 is very
# good"), and mkt34_sight.py rewrites the live tmfd_7_c folder on every run - so PROVEN points here,
# not there. Same arrangement, and the same reason, as tzf5f_g_moving_v19.
GUNNER_SIGHTS["tmfd_7_g_v29"] = dict(
    GUNNER_SIGHTS["tmfd_7_g"],
    mesh=("tmfd_7_c", r"L:\sabow-ext-backups\reticles\tmfd_7_c_v29\tmfd_7_c.loc_def.mesh",
          "9512771703b971af969b94dfb7087e5c"),
    label="tmfd_7_g, the T-34/76's TMFD-7 as shipped in v29 (frozen)")
# v30, murkz on v29: "lets make the long horizontal line move as we do for the tzf and matilda sight".
# Same mechanism, third time - the long horizontal line goes into d_distance, the ONE node the engine's
# range drum moves (notes/86: translate OR rotate, never both). Fields 31-34 carry the travel and are the
# STOCK T-62's own proven numbers, 0, -0.5, 0.2, 3 - exactly what tzf5f_g_moving took, and the rate 0.2 is
# the one murkz confirmed on v19 ("mouse movement is very good now"). It is per SECOND, not per range step.
# Our box is 0.5 tall, the same as the TZF 5f's, so it should feel identical.
# The donor tmfd_7 row has field 13 all zeros, so all four values have to be written; tsh2b is where they
# come from. Mesh: mkt34_sight.py --moving, which emits the horizontal line LAST so it owns a contiguous
# tail of the vertex array, and runs the result through tzf5f_moving.hide_frame - the moving template
# draws its d_base frame wider than the static one and that is the outer square that cost v18 and v19.
GUNNER_SIGHTS["tmfd_7_g_moving"] = dict(
    GUNNER_SIGHTS["tmfd_7_g"],
    fields=dict(list(GUNNER_SIGHTS["tmfd_7_g"]["fields"].items())
                + [(31, ("0", 0.0)), (32, ("-0.5", -0.5)), (33, ("0.2", 0.2)), (34, ("3", 3.0))]),
    mesh=("tmfd_7_c", r"L:\sabow-ext-backups\reticles\tmfd_7_c_moving\tmfd_7_c.loc_def.mesh",
          "887e83dbc12f18502997aab126b646ca"),
    label="tmfd_7_g, the T-34/76's TMFD-7 with a MOVING horizontal line")
# The v30 reticle, FROZEN. gtos_ww2 v30 is proven against exactly these bytes (murkz: "v30 excellent"), and
# mkt34_sight.py --moving rewrites the live tmfd_7_c_moving folder on every run. Same arrangement as
# tzf5f_g_moving_v19 and tmfd_7_g_v29; the v29 STATIC reticle stays frozen alongside, so a fallback to the
# non-moving sight is one word in the recipe.
GUNNER_SIGHTS["tmfd_7_g_moving_v30"] = dict(
    GUNNER_SIGHTS["tmfd_7_g_moving"],
    mesh=("tmfd_7_c", r"L:\sabow-ext-backups\reticles\tmfd_7_c_moving_v30\tmfd_7_c.loc_def.mesh",
          "887e83dbc12f18502997aab126b646ca"),
    label="tmfd_7_g, the T-34/76's TMFD-7 with a moving line, as shipped in v30 (frozen)")
# ---------------------------------------------------------------- DIAGNOSTIC, NOT A GUNSIGHT
# scaleprobe_g: measures the scale at which d_static and d_distance are actually drawn.
#
# WHY. murkz: "the main gunners sight feels off", and there is no way to test range in game. From the
# tables alone (BUILD_LOG 2026-09-29): the F-34 needs 13.96 mrad at 1000 m against the U5TS APFSDS's
# 3.52 (3.96x) or its HEAT's 7.75 (1.80x), and the ONLY sight in the whole game carrying a drum travel
# is tsh2b, whose (0,-0.5,0.2,3) both WW2 sights copied because there was nothing else to copy.
# mksight's own formula - reticle_px = 0.5 (box) x sx x field15[0] x 1920 - says the travel's angular
# value scales WITH field 36, so our 1.427 against tsh2b's 0.791183 (1.804x) against half the apparent
# FOV nets ~0.9x its sweep: under-compensation of roughly 2x (vs HEAT) to 4x (vs APFSDS).
#
# THAT PREDICTION IS NOT TRUSTED YET. BoW43 notes/86 and mkscaleprobe.py record that a wire in
# d_distance drew at roughly HALF the width the same wire drew in d_static - an unquantified second
# factor that six builds (v649-v655) died on. mkscaleprobe.py was written to measure it and its result
# was never recorded anywhere. This row IS that measurement.
#
# HOW TO READ IT IN GAME. d_static carries a ruler: five tick groups at 20/40/60/80/100% of the box
# half-width, right of centre, group N having N ticks so it is countable at any scale, plus corner
# diagonals and a chevron at the TOP edge (chevron at the bottom = y is flipped). d_distance carries
# ONE full-width horizontal bar. Count the outermost tick group still inside the circle for d_static's
# scale; see where the bar's end falls against the ruler for d_distance's. The ratio is the answer.
#
# field 36 is 1.0 ON PURPOSE - mksight baked the probe's own scale into its placement matrix and
# printed "field15 = 1.0", so any other value would confound the thing being measured. Travel and
# apparent FOV are left exactly as the real sight's, so the bar sweeps in situ.
# v108: THE SAME PROVEN v30 SIGHT WITH TWICE THE DRUM TRAVEL, from the ballistics.
#
# v107's scale probe settled the last unknown: d_static and d_distance draw at the SAME scale
# (measured 0.993, RMS 1.1 px over 8 ticks), and y is not inverted. So mksight's own formula -
# sweep proportional to travel x field36 x apparent FOV - carries straight across with no hidden
# factor:
#     TSh-2B   0.5 x 0.791183 x 63    = 24.92
#     tmfd_7_g 0.5 x 1.427    x 31.25 = 22.30   -> ours is 0.895x the TSh-2B's sweep
# and the F-34 (76L42_BR_350A, 662 m/s, 6.30 kg) needs 13.96 mrad at 1000 m against the U5TS HEAT's
# 7.75 (1.80x) or its APFSDS's 3.52 (3.96x). Required travel = 0.5 x needed / 0.895, so -1.00
# against the HEAT reading and -2.21 against the APFSDS one.
#
# -1.0 IS THE SMALLER CORRECTION AND IT GOES FIRST. One change, one look: if the fall of shot is
# still short, -2.21 is the next stop and that would also tell us which round the TSh-2B is
# graduated for. The MESH IS UNCHANGED - v30's frozen reticle, byte for byte; only field 32 moves.
#
# WATCH FOR, and it is a real tension rather than a bug: the etched ladder on the Steel Fury art
# spans about 20% of the box while the line already sweeps the whole of it, so doubling the travel
# makes the line track the shell better and the ETCHED marks less. The real TMFD-7 had no moving
# strich at all - you read an etched line - so that art is reference, not a scale the line must
# agree with. murkz asked for a moving line on v29 and that is what is being tuned.
GUNNER_SIGHTS["tmfd_7_g_moving_v108"] = dict(
    GUNNER_SIGHTS["tmfd_7_g_moving_v30"],
    fields=dict(list(GUNNER_SIGHTS["tmfd_7_g_moving_v30"]["fields"].items())
                + [(32, ("-1.0", -1.0))]),
    label="tmfd_7_g, the T-34/76's TMFD-7, drum travel -1.0 from the F-34's ballistics")
# ---------------------------------------------------------------- v109: the sight was zeroed at 600 m
# THE FIRST TIME THIS SIGHT WAS EVER FIRED AT A KNOWN RANGE IT FAILED, and it failed in a way none of
# the checks on v108 could see. murkz, 2026-09-30, drum AT REST: "ap 0 elevation on the sight, a
# direct hit at 600meters", and earlier "at 500m the impact point of the round is about 25% up above
# 0 on the scale". The reticle's 0 mark was already carrying 600 m of elevation, so every label read
# 600 m short and the scale was unusable.
#
# WHAT THE v108 WORK ACTUALLY PROVED, AND WHY IT MISSED THIS. The ladder was fitted THROUGH THE
# ORIGIN, so it tested the SPACING between rungs; the click test then compared the drum against those
# same rungs. Both are the sight agreeing with ITSELF. Neither can see a constant offset between the
# whole reticle and the gun - and such an offset leaves every one of those checks passing. That is
# [[feedback_matching_the_number_is_not_validation]] in its exact shape.
#
# THE SIZE, from two unrelated routes agreeing to 1%:
#   the ladder's own 0->6 rung gap, measured on the screenshot     21.5 px
#   the F-34's elevation at 600 m (mk24b.drop_mrad, Cd 0.318)      7.11 mrad
#   the frame renders 653 px for 0.541 of itself, so 1.0 = 1207 px and 21.5 px = 0.017813
#
# WHERE THE WRONG ASSUMPTION WAS. `mksight --centre` pins the STEEL FURY FRAME's centre to the
# optical axis - the build even reports the moving line at rest at 0.2486 of a 0..0.5 box, dead
# centre. That convention came across with the art and is not this gun's axis. `mksight.Y_SHIFT`
# lifts d_static and d_distance TOGETHER, so the ladder, the comb and the moving line keep their
# relationship - which is what murkz asked for: "if that moves up, then the aiming line should also
# move up to match the higher starting point".
#
# CONTROL: with Y_SHIFT 0.0 the pipeline reproduces the frozen v30 mesh byte for byte
# (887e83dbc12f18502997aab126b646ca), so the regeneration is faithful and the lift is the only
# change. The shifted mesh differs in SIX BYTES, all inside nodes 2 and 3's translation.
#
# CHECKABLE WITHOUT FIRING: the 6 rung should now sit where 0 sat. Then confirm by firing.
# ROLLBACK: "tmfd_7_g_moving_v108" is this same sight without the lift.
GUNNER_SIGHTS["tmfd_7_g_moving_v109"] = dict(
    GUNNER_SIGHTS["tmfd_7_g_moving_v108"],
    mesh=("tmfd_7_c", r"L:\sabow-ext-backups\reticles\tmfd_7_c_moving_v109\tmfd_7_c.loc_def.mesh",
          "313da2e128aa2e0ab7adb4fad104ff59"),
    label="tmfd_7_g, the T-34/76's TMFD-7, drum travel -1.0 and the artwork lifted to the gun axis")
GUNNER_SIGHTS["scaleprobe_g"] = dict(
    GUNNER_SIGHTS["tmfd_7_g_moving"],
    row="scaleprobe_g",
    fields=dict(list(GUNNER_SIGHTS["tmfd_7_g_moving"]["fields"].items())
                + [(24, ("scaleprobe", "scaleprobe")), (36, ("1.0", 1.0))]),
    mesh=("scaleprobe", r"L:\sabow-ext-backups\reticles\scaleprobe\scaleprobe.loc_def.mesh",
          "aa257d606576934bb3b6dc1fed219a9e"),
    label="scaleprobe_g, DIAGNOSTIC - measures the d_static / d_distance draw scale")
# v32: the Matilda II's No. 24B Mk.I - MURKZ'S OWN DRAWING, traced from a photograph taken down a real one,
# with the six range marks later corrected to the 2-pdr's ballistics (Tools/mk24b.py). It was the FIRST WW2
# gunsight reticle ever to render in this engine (BoW43 notes/77, 2026-09-09, after twenty builds), and v664
# is the build he hits targets with. Not "art found on disk" - his.
#
# THE ROW IS HIS PROVEN ONE, REPRODUCED, not a new combination. BoW43 v673 shipped it and the file is kept at
# L:\sabow-backups\v673_PROVEN_MANY_SIGHTS\common_res_mod.SHIPPED.engcfg2. Diffed both candidate donors
# against it by value rather than by eye: from tsh2b it is SEVEN fields, from the stock 24b_mk1 row it would
# be TWENTY and would invent a combination nothing has ever proven. So the donor is tsh2b, exactly as BoW43
# did it, and the seven edits below reproduce that row field for field.
#
#     [1]  9      -> 21        true FOV, the No. 24B is 21 deg at 1.9x (notes/78)
#     [2]  63     -> 39.9      apparent = 21 x 1.9, the same rule as tzf5f_g and tmfd_7_g
#     [5]  3.5    -> 1.9       magnification
#     [6]  7      -> 1.9       it is a fixed-power sight, so both ends are the same
#     [24] tnsh2b_41 -> 24b_mk1   his reticle
#     [33] 0.2    -> 0.0152    the drum rate HE PROVED. Slow - notes on v17 measured 0.0152 as ~33 s to
#                              cross a 0.5 box - but it is the proven value and changing it would be a
#                              second untested variable in a build that already carries a new vehicle.
#     [36] 0.7912 -> 1.5       the reticle scale, and 1.5 is the largest any shipped optic uses (notes/78)
#
# The mesh already carries the moving wire - drawable chunks [1,2,3], four nodes - so fields 31-34 are the
# travel that drives it, and they come straight from the proven row too.
GUNNER_SIGHTS["24b_mk1_g"] = dict(
    row="24b_mk1_g", donor_row="tsh2b", fields={
        1: ("21", 21.0), 2: ("39.9", 39.9), 5: ("1.9", 1.9), 6: ("1.9", 1.9),
        24: ("24b_mk1", "24b_mk1"), 33: ("0.0152", 0.0152), 36: ("1.5", 1.5)},
    mesh=("24b_mk1", r"L:\sabow-ext-backups\reticles\24b_mk1_v664\24b_mk1.loc_def.mesh",
          "bffbc05dc890e1591c3f10271cc5c3c2"),
    label="24b_mk1_g, murkz's No. 24B Mk.I for the Matilda II (21 deg at 1.9x, moving wire, BoW43 v664)")
# v33, murkz on v32: "perfect but sight needs 1 px lines and the horizontal aiming line needs to move up and
# down at the same speed as the t34 aiming line. Positions perfect also, turned out positions also perfect."
# TWO changes, and only two - the positions and the turn-out are proven and nothing here touches them.
#
# 1 PX. Line width is GEOMETRY, not a field: mksight.tessellate turns each segment into a quad of the given
# width, so the mesh has to be rebuilt. v647/v648/v664 all shipped 0.0016; 1 px is 0.0004, the value murkz
# approved on the TZF 5f at v9 and shipped at v19 - so his No. 24B has been four times too thick all along.
# tool/mk24b_1px.py re-tessellates HIS drawing (it redraws nothing) and re-splits the H-wire with
# resplit.find_hwire, which picked triangles [2, 3] - exactly v664's 4 verts / 6 idx moving element.
# THE CONTROL CAME FIRST: rebuilt at 0.0016 it reproduces v664's counts exactly, 3307 tris / 6599 verts and
# the same three drawable chunks, so the route was proven before the width moved. Not byte-identical, and
# that is expected - v664 was re-split from a finished mesh, and mksight now writes the placement matrices
# explicitly rather than inheriting them, which was v664's own fix.
#
# THE RATE. Field 33 goes 0.0152 -> 0.2, "the same speed as the t34 aiming line". 0.2 is the stock T-62's
# own number, what tzf5f_g_moving and tmfd_7_g_moving both use, and the value murkz confirmed on v19
# ("mouse movement is very good now"). 0.0152 was measured at about 33 s to cross a 0.5 box, which is the
# slowness he is describing. Every other field stays exactly as his proven v673 row had it.
GUNNER_SIGHTS["24b_mk1_g_1px"] = dict(
    GUNNER_SIGHTS["24b_mk1_g"],
    fields=dict(list(GUNNER_SIGHTS["24b_mk1_g"]["fields"].items()) + [(33, ("0.2", 0.2))]),
    mesh=("24b_mk1", r"L:\sabow-ext-backups\reticles\24b_mk1_1px\24b_mk1.loc_def.mesh",
          "71b3d922b94f4e989239614c050a4efb"),
    label="24b_mk1_g, murkz's No. 24B at 1 px with the T-34's drum rate")
# The v33 reticle, FROZEN. murkz: "sight is perfect". mk24b_1px.py rewrites the live 24b_mk1_1px folder
# on every run, so PROVEN points here. v664's 0.0016 mesh stays frozen alongside at 24b_mk1_v664.
GUNNER_SIGHTS["24b_mk1_g_1px_v33"] = dict(
    GUNNER_SIGHTS["24b_mk1_g_1px"],
    mesh=("24b_mk1", r"L:\sabow-ext-backups\reticles\24b_mk1_1px_v33\24b_mk1.loc_def.mesh",
          "71b3d922b94f4e989239614c050a4efb"),
    label="24b_mk1_g, murkz's No. 24B at 1 px as shipped in v33 (frozen)")
# v34: the Matilda's SECOND gunner sight - the MK-4 periscope, 1x. murkz: "always historical if
# possible". Operation Star already gives the Matilda mk4 on sig_gunner_01, so the AI uses it;
# SABoW carries the row with correct optics and blank art, as 24b_mk1 and tmfd_7 were. The art is
# Steel Fury's mk4a.go and it is ONE STROKE - a single vertical line, floor to ceiling, centred.
# A 1x periscope is for observation with a centre reference, not for laying a gun, so there is no
# ladder and nothing to move.
#
# DONOR CHOSEN BY MEASUREMENT, as the No. 24B's was: against the row this needs, m60_periscope
# differs on THREE fields where tsh2b differs on five and the stock mk4 row is blank in six more.
# m60_periscope is also the right KIND - a shipping 1x periscope that already carries art, mode 2
# rather than the telescopes' mode 3. Cloning it keeps that shape instead of inventing one.
#   [1] 45 -> 25   the MK-4's field, from SABoW's own mk4 row
#   [2] 45 -> 25   apparent = true x 1, the same rule as the other three sights
#   [24] m60_periscope -> mk4_c
#   [36] 0.15 -> 1.5  THE ONE NUMBER TO JUDGE IN PLAY. m60_periscope's own art is drawn large in
#        its box; ours is a line already spanning the full canvas, so 1.5 makes it span the view
#        as the real reference line did (notes/78: 1.5 fills the circle). If it renders as a short
#        stub in the middle, 0.15 is the donor's value and the thing to try.
GUNNER_SIGHTS["mk4_g"] = dict(
    row="mk4_g", donor_row="m60_periscope", fields={
        1: ("25", 25.0), 2: ("25", 25.0), 24: ("mk4_c", "mk4_c"), 36: ("1.5", 1.5)},
    mesh=("mk4_c", r"L:\sabow-ext-backups\reticles\mk4_c\mk4_c.loc_def.mesh",
          "f726e975a30dd49e1977a3426e693877"),
    label="mk4_g, the Matilda's MK-4 periscope (25 deg at 1x, Steel Fury art, static)")
# The v34 periscope, FROZEN. murkz: "v34 perfect, gunner's second sight is wonderful". mk_mk4.py
# rewrites the live mk4_c folder on every run, so PROVEN points here.
GUNNER_SIGHTS["mk4_g_v34"] = dict(
    GUNNER_SIGHTS["mk4_g"],
    mesh=("mk4_c", r"L:\sabow-ext-backups\reticles\mk4_c_v34\mk4_c.loc_def.mesh",
          "f726e975a30dd49e1977a3426e693877"),
    label="mk4_g, the Matilda's MK-4 periscope as shipped in v34 (frozen)")
# v36: the DRIVER's MK-4, which is the same device but not the same row. Steel Fury's own cockpit
# (LEVELS/cocpits/coc_mk2.engcfg, cameras block) gives its Matilda driver s_camera_driver_01 at
# 30 deg with tight limits; SABoW's mk4 row is 25 deg. The gunner's second sight is PROVEN at 25
# (murkz: "wonderful") so it is left alone and the driver gets his own row at SF's number.
# The look LIMITS are not here - they live in the cockpit's plc_states row, which the tool cannot
# edit yet. That is the next piece, and it is what makes a periscope feel like one.
GUNNER_SIGHTS["mk4_drv_g"] = dict(
    GUNNER_SIGHTS["mk4_g_v34"],
    row="mk4_drv_g",
    fields=dict(list(GUNNER_SIGHTS["mk4_g_v34"]["fields"].items())
                + [(1, ("30", 30.0)), (2, ("30", 30.0))]),
    label="mk4_drv_g, the Matilda driver's MK-4 periscope (30 deg at 1x, Steel Fury's number)")
GUNNER_SIGHT = "tzf5f_g_moving"
PLACE_GROUPS = {0: "sig_driver", 1: "sig_gunner", 2: "sig_commander", 3: "sig_loader"}


class GtosGame(recipe.Game):
    """recipe.Game over the stock install, with our vehicle added: its unit row (shaped like the donor's),
    its vehicle table read from Operation Star, and Operation Star's models."""

    def __init__(self, install, opstar, spec, vehicle):
        recipe.Game.__init__(self, install)
        self.src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
        self.spec, self.vehicle = spec, vehicle
        self._t[TECHN] = azcf.Table(gtos_opstar.read(*self.src.records[("techn_base", "config")]))

    def units(self):
        units = recipe.Game.units(self)
        row = list(units["sau_t62"])
        row[0], row[2], row[3] = self.spec["unit"], "tabs\\%s.cfgpack" % TECHN, self.vehicle
        row[recipe.CREWABLE], row[recipe.COCKPIT], row[recipe.ANIMS] = False, "", ""
        units[self.spec["unit"]] = row
        return units

    def mesh(self, name):
        if name not in self._mesh and self.src.has((name.lower(), "mesh")):
            b = gtos_opstar.read(*self.src.records[(name.lower(), "mesh")])
            self._mesh[name] = (b, crewpoints.read_mesh(b))
        return recipe.Game.mesh(self, name)


# v104: WHICH CREW ANIMATION SET OUR UNITS CARRY. v103 asked for the vehicle's own and got EMPTY,
# and v103 did not fix the fault (murkz: "both are poking out of the front glacis"). The crew are now
# given the generic IN-VEHICLE set by name: it exists as a record on both installs, the engine loads it
# as a base on every run, and its states (sit_in_tech, techn_out) match the crew's own skeleton rather
# than the T-62 tanker's.
# v105: back to the vehicle's own (empty) so the seat change is the ONLY change from v103, the state
# murkz has actually looked at. v104 (anims_in_techn) is built and recorded; it was aimed at a fault the
# AI was said not to have, and murkz has since reported the AI driver poking TOO, which removes that
# fault's whole rationale.
ANIMS_FROM = "vehicle"


def crew_plan(install, opstar, vehicle, gunner_sight=GUNNER_SIGHT):
    """(recipe plan, sight plan) for making `vehicle` crewable. Read-only."""
    spec = dict(VEHICLES[vehicle], **OVERRIDE.get(vehicle, {}))
    game = GtosGame(install, opstar, spec, vehicle)
    # v103: anims_from="vehicle" - the crew animate with the set the VEHICLE's own unit row carries,
    # which for these imported vehicles is Operation Star's own (usually empty), not the donor cockpit's
    # anims_t62/anims_m60a1. See recipe.derive for the whole measurement.
    plan = recipe.derive(install, spec["unit"],
                         choices={"weapons": spec["weapons"], "anims_from": ANIMS_FROM}, game=game)
    # v22: point a cockpit crew chunk at a vehicle chunk of a DIFFERENT name. The recipe can only set
    # mode 0 where the vehicle has the same-named point, and warns about the rest; this covers the rest.
    for chunk, target in (spec.get("sync_retarget") or {}).items():
        plan.sync_retarget[chunk] = target
        plan.sync_modes[chunk] = 0
    if spec.get("gunner_hatch"):
        # the gunner's turned-out state, modelled exactly on the commander's own 0x1000 row in stock
        # coc_t62 with the place changed from 2 to 1: no sight, no device, the wide head-out angles.
        plan.plc_add.append(GUNNER_TURNOUT_STATE)
        plan.step("gunner hatch", "plc_states place 1 flag 0x1000 + sync s_gunner_out",
                  "the place needs a STATE to enter, not just a crew point (v28)")
    if spec.get("commander_freelook"):
        plan.plc_add.append(COMMANDER_FREELOOK_STATE)
        plan.step("commander free look", "plc_states place 2 slot -1 flag 0x0000 sight 1, no button, no device",
                  "both of his sight rows are the rangefinder DEVICE and neither turns (v41)")
    for chunk, target in (spec.get("sync_add") or {}).items():
        plan.sync_add[chunk] = target
    if plan.sync_add:
        plan.step("sync add", ", ".join("%s -> %s" % kv for kv in sorted(plan.sync_add.items())),
                  "the donor cockpit has no such row, so the crewman could never use that hatch (v23)")
    if plan.sync_retarget:
        plan.step("retarget", ", ".join("%s -> %s" % kv for kv in sorted(plan.sync_retarget.items())),
                  "the vehicle has no chunk of that name, so the row follows one it does have (v22)")
        # the recipe warned that these crewmen keep the donor's position; they no longer do, and a stale
        # warning is exactly what cost a session today
        fixed = []
        for w in plan.warnings:
            if w.startswith("no position in the") and " for: " in w:
                head, rest = w.split(" for: ", 1)
                names = [n for n in rest.split(" - ")[0].split(", ") if n not in plan.sync_retarget]
                if not names:
                    continue
                w = "%s for: %s - those crewmen keep the donor's" % (head, ", ".join(names))
            fixed.append(w)
        plan.warnings[:] = fixed
    t = game.table(TECHN)
    rows = [list(r) for r in t.rows(dict(azcf.vehicles(t))[vehicle]["sights"])]
    c, blocks = game.cockpit_blocks(plan.donor_cockpit)
    plc = next(b for b in blocks if b.name == "plc_states")
    need = {}
    for r in c.rows(plc):
        if r[2] != 0xffffffff and r[0][0] in PLACE_GROUPS:
            need[r[0][0]] = max(need.get(r[0][0], 0), (r[2] & 0x7fffffff) + 1)
    heads = dict(plan.sight_heads)
    # Which of the vehicle's own sight rows are the empty stubs to point at a working sight. The Panzer IV
    # has one (tzf5f); a T-34 has two, pt4_7 and tmfd_7, both stubs in exactly the same way.
    stubs = tuple(spec.get("sight_stubs") or (SIGHT_STUB,))
    alias, label = GUNNER_SIGHTS[gunner_sight]["row"], GUNNER_SIGHTS[gunner_sight]["label"]
    # extra_sights: {stub row -> its OWN sight}, for a vehicle whose gunner views are different
    # DEVICES rather than two views of one. The Matilda is the first: sig_gunner is the No. 24B
    # telescope at 1.9x and sig_gunner_01 is the MK-4 periscope at 1x, and pointing both at one
    # row put the telescope's ladder in the periscope. murkz's rule - always historical if
    # possible. Every named sight is shipped as its own common_res_mod row, which costs nothing
    # since that route grew to N rows (notes/82).
    vision_blocks = spec.get("vision_blocks", VISION_BLOCKS)
    extra = spec.get("extra_sights") or {}
    for stub, key in extra.items():
        if stub not in stubs:
            raise SystemExit("extra_sights names %s, which is not one of %s's stub rows (%s)"
                             % (stub, vehicle, ", ".join(stubs)))
        if key not in GUNNER_SIGHTS:
            raise SystemExit("extra_sights names an unknown sight %s" % key)
    # other_sights: {ROW NAME -> its own sight}, for any group. extra_sights above only reaches
    # sig_gunner rows, which is right for a gunsight; this is the lever for a DRIVER's or
    # commander's periscope. Added 2026-09-23 to test whether field [54] is what draws the
    # vision-block mask - the Matilda's driver has no mask today because both his rows leave
    # [54] blank, so pointing his periscope at a tnk_sig_pere row should give him one.
    other = spec.get("other_sights") or {}
    by_name = {r[0]: i for i, r in enumerate(rows)}
    for name, key in other.items():
        if key not in GUNNER_SIGHTS:
            raise SystemExit("other_sights names an unknown sight %s" % key)
        # A name may be a PADDED row (group_xN), which does not exist yet - checked after padding.
        if name not in by_name and "_x" not in name:
            raise SystemExit("other_sights names row %s, which %s does not have (%s)"
                             % (name, vehicle, ", ".join(sorted(by_name))))
    # sight_order: (ROW NAMES) - the named rows take the FIRST POSITIONS of their own group, in that
    # order, and the gunner's head moves with the POSITION rather than with the row. Added 2026-09-28.
    #
    # WHY IT IS NEEDED: the engine takes a station's views BY INDEX - recipe.py's own note on the v11
    # Olifant fault says so in as many words, and plc_states field [2] is that index - and view 1 is the
    # sight the gun drives. On a T-34/76 the gunner AIMED through the TMFD-7 telescope and OBSERVED
    # through the PT-4 periscope, so the telescope must be his first row. GTOS ships them the other way
    # round, because in GTOS the T-34's commander was the gunner and both rows were his.
    #
    # v75 did this by hand - 13 bytes of a built table, and a rebuild would have undone it. This is the
    # tool doing the same thing to its own output, so the arrangement survives every future build.
    edits, added, lines, vb_pads = {}, [], [], []
    order = tuple(spec.get("sight_order") or ())
    perm = None
    if order:
        missing = [n for n in order if n not in by_name]
        if missing:
            raise SystemExit("%s has no sights row named %s" % (vehicle, ", ".join(missing)))
        # THE NAMES MAY SPAN MORE THAN ONE GROUP, and on the T-34 they must: its two side slits are
        # BOTH in sig_loader - sig_gunner_side first, which is the GUNNER's slit - so the loader's view
        # 1 is the other man's slit. murkz: "the loaders side slit is looking out of the gunners side
        # slit!" Each group named is reordered on its own, and only the named rows move.
        groups_seen = []
        for n in order:
            g = rows[by_name[n]][4]
            if g not in groups_seen:
                groups_seen.append(g)
        perm = list(range(len(rows)))
        moved = {}
        for g in groups_seen:
            names = [n for n in order if rows[by_name[n]][4] == g]
            slots = [i for i, r in enumerate(rows) if r[4] == g]
            seq = [by_name[n] for n in names] + [i for i in slots if rows[i][0] not in names]
            for pos, src in zip(slots, seq):
                perm[pos] = src
            for k, pos in enumerate(slots):
                moved[seq[k]] = heads.get(slots[k], rows[slots[k]][8])
            lines.append("sight order %s: %s - and the head stays on the position, not the row"
                         % (g, " -> ".join(rows[i][0] for i in seq)))
        heads = moved
    for name, key in other.items():
        if name not in by_name:
            continue                     # a padded row; handled after the padding loop
        i = by_name[name]
        r = rows[i]
        new = list(r)
        new[2] = GUNNER_SIGHTS[key]["row"]
        edits[i] = new
        lines.append("%s sight %s: %s -> %s" % (r[4], name, r[2], GUNNER_SIGHTS[key]["label"]))
    for i, r in enumerate(rows):
        if r[4] == "sig_gunner" and r[2] in stubs:
            key = extra.get(r[2])
            row_alias = GUNNER_SIGHTS[key]["row"] if key else alias
            row_label = GUNNER_SIGHTS[key]["label"] if key else label
            new = list(r)
            new[2] = row_alias
            new[8] = heads.get(i, r[8])
            edits[i] = new
            lines.append("gunner sight %s: %s -> %s, head '%s'" % (r[0], r[2], row_label, new[8]))
    for i in heads:
        if i in edits:
            continue
        # THE HEAD IS NOT A STUB MATTER, and refusing it stopped the KV-1 dead.
        #
        # A stub is a gunner row whose sight has BLANK ART - the tool's rule for "safe to repoint".
        # A head is different: it says the row the gunner STARTS in must move with the gun's head1,
        # or he cannot aim up and down from it at all (v11). On the KV-1 that starting row is
        # sig_gunner_side, camera s_camera_gunner, whose sight row is the shared vision block hole -
        # correctly NOT a stub, and for a reason that has nothing to do with heads.
        #
        # So only the SIGHT-ROW repointing is gated on stubs. The head is applied to whatever row
        # the recipe names, and its sight row is left exactly as it is.
        r = rows[i]
        new = list(r)
        new[8] = heads[i]
        edits[i] = new
        lines.append("gunner sight %s: head '%s' - the view he starts in, which must follow the gun; "
                     "its sight row %s is left as it is (a shared vision block, not a stub)"
                     % (r[0], heads[i], r[2]))
    # vision_blocks: the sight key a vehicle's VISION-BLOCK rows should use, or None to leave them on the
    # shared stock row "hole". murkz: "working now the mask then making the tool do this?" - so the tool
    # does it. A row still on VISION_BLOCK is a crewman looking through a plain aperture - a slit or a port
    # - and pointing it at its own row is what gives it the mask (the mask comes with the row: mk4_g,
    # pt4_7_g and slit_g are all clones of one stock periscope). Nothing is hardcoded per vehicle: the rows
    # are found by their SIGHT, so a vehicle with three slits gets three and a vehicle with none gets none.
    if vision_blocks:
        vb = vision_blocks if isinstance(vision_blocks, dict) else {"default": vision_blocks}
        for i, r in enumerate(rows):
            # A plain aperture, under either of its two names: the shared hole row, or - for a DRIVER
            # only - the stock driver row. See DRIVER_PLAIN above.
            if r[2] == VISION_BLOCK:
                pass
            elif r[2] == DRIVER_PLAIN and r[4] == "sig_driver":
                pass
            else:
                continue
            # BY STATION: the group a row sits in decides which device it is. A driver's group gets the
            # driver's row, everything else the default. See VISION_BLOCKS above.
            key = vb.get(r[4], vb.get("default"))
            if not key:
                continue
            if key not in GUNNER_SIGHTS:
                raise SystemExit("vision_blocks names an unknown sight %s" % key)
            new = list(edits.get(i, r))
            new[2] = GUNNER_SIGHTS[key]["row"]
            edits[i] = new
            lines.append("%s vision block %s: %s -> %s" % (r[4], r[0], r[2], GUNNER_SIGHTS[key]["label"]))
    # sight_group: {ROW NAME: group} - MOVE A ROW INTO ANOTHER STATION'S SIGHT GROUP. The engine takes a
    # station's views by index within that station's group, so a row in the wrong group is a view the
    # wrong man has. The T-34's own fault: its GUNNER's side slit sits in sig_loader, so the loader had
    # two views (his own and the gunner's) and the gunner had none.
    # murkz: "the gunner needs the 3rd sight as a slit" - third because the telescope and the PT-4 are his
    # first two.
    for name, grp in (spec.get("sight_group") or {}).items():
        if name not in by_name:
            raise SystemExit("%s has no sights row named %s (sight_group)" % (vehicle, name))
        i = by_name[name]
        new = list(edits.get(i, rows[i]))
        new[4] = grp
        edits[i] = new
        lines.append("sight group %s: %s -> %s" % (name, rows[i][4], grp))
    for place, group in sorted(place_groups(t, vehicle, spec.get("wp_edits")).items()):
        mine = [edits.get(i, r) for i, r in enumerate(rows) if r[4] == group]
        if not mine:
            raise SystemExit("%s has no %s sights to copy" % (vehicle, group))
        for k in range(len(mine), need.get(place, 0)):
            new = list(mine[0])
            new[0] = "%s_x%d" % (group, k)
            added.append(new)
            lines.append("%s view %d: none in %s - copy of %s as %s" % (group, k, vehicle, mine[0][0], new[0]))
            if vision_blocks and group in VISION_BLOCK_PADS and k == need.get(place, 0) - 1:
                key = (vb.get(group, vb.get("default")) if isinstance(vision_blocks, dict)
                       else vision_blocks)
                if key:
                    new[2] = GUNNER_SIGHTS[key]["row"]
                    vb_pads.append(new)          # judged again by the v95 rule, AFTER other_sights
                    lines.append("%s pad %s is the row the cockpit READS: sight -> %s"
                                 % (group, new[0], GUNNER_SIGHTS[key]["label"]))
    # THE PADDED ROW IS OFTEN THE ONE THE ENGINE ACTUALLY ASKS FOR. coc_t62's driver plc_states
    # row asks for sight INDEX 2, and a vehicle with two driver sights gets its index 2 from the
    # pad - so pointing sig_driver_01 at a sight changes a row nothing looks through. v35 shipped
    # exactly that and read as a failed experiment. Hence: other_sights can name a padded row.
    by_added = {r[0]: n for n, r in enumerate(added)}
    for name, key in other.items():
        if name in by_name:
            continue
        if name not in by_added:
            raise SystemExit("other_sights names row %s, which %s has neither of its own nor as a "
                             "padded copy (%s)" % (name, vehicle,
                                                   ", ".join(sorted(by_name) + sorted(by_added))))
        r = added[by_added[name]]
        was = r[2]
        r[2] = GUNNER_SIGHTS[key]["row"]
        lines.append("%s sight %s (padded): %s -> %s" % (r[4], name, was, GUNNER_SIGHTS[key]["label"]))
    # v95: A PLAIN VISION BLOCK HAS NO TRAVERSE, SO THE PAD THAT READS ONE MUST NOT CARRY ANY.
    # The pad is a COPY of the group's FIRST row - on the Panzer IV that is sig_driver, which carries
    # the donor's 0.1 - so the moment v93 pointed the pad at drv_slit_g the vehicle said "this sight
    # can swing" about a row that is not a device (v83 cleared its token). murkz on v94: "t34 perfect
    # drivers view with black rectangular mask, pzr 4 NO driver view". Those two pads read the SAME
    # row and differ in exactly three cells - the camera, this traverse and the cap - and the
    # Matilda's driver settles the other two: it reads an ART row from the SAME camera
    # (s_camera_driver) with NO cap and draws its mask. A survey of every vehicle in the game (stock
    # 36 + ours 13, 316 rows) found this pad to be the ONLY row that pairs a non-zero traverse with
    # art on a row that is not a device; every art-bearing view in stock sits on a zero-traverse row.
    # v87's rule, applied to the pad.
    # JUDGED LAST, ON THE ROW THE PAD ENDS UP WITH: a vehicle that repoints its pad through
    # other_sights (the Matilda, at mk4_drv_g, a device) keeps its own limits.
    plain_rows = {GUNNER_SIGHTS[k]["row"] for k in GUNNER_SIGHTS if GUNNER_SIGHTS[k].get("plain")}
    for r in vb_pads:
        if str(r[2]) in plain_rows and r[3]:
            lines.append("%s pad %s: traverse %.6g -> 0 (the row it now reads is a plain vision block)"
                         % (r[4], r[0], r[3]))
            r[3] = 0.0
    after = [edits.get(i, r) for i, r in enumerate(rows)]
    if perm:
        after = [after[perm[k]] for k in range(len(after))]
    expected = after + added
    return plan, {"edits": edits, "added": added, "expected": expected, "need": need, "lines": lines,
                  "perm": perm}


def _sight_text(row):
    """A sights row as the text route writes it: sig_driver, s_camera_driver, driver_tech, 0.1, sig_driver, , , ;"""
    def cell(v):
        if isinstance(v, float):
            return ("%.6g" % v)
        return str(v)
    return ("\t\t" + ", ".join(cell(v) for v in row) + ";").encode()


def edit_work_places_text(text, vehicle, wp_edits):
    """Change named fields of named work_place rows in the vehicle's techn text.

    notes/20 (BoW43, proven by murkz driving the result): field [11] is the ROLE a cockpit place binds to
    and [18] is the index; the station's NAME is cosmetic and renaming it achieves nothing. A T-34/76 has
    no commander station - the commander IS the gunner - so its hull machine-gunner takes the commander
    role, keeping its own s_mgunner anchors, which the model has and s_commander* it does not.
    """
    lines = text.split(CRLF)
    start = [i for i, l in enumerate(lines) if l.startswith(b"\twork_places[") and l.endswith(b"]()")]
    end = [i for i, l in enumerate(lines) if l == b"\t} //endof work_places"]
    if len(start) != 1 or len(end) != 1:
        raise SystemExit("techn_base: %s has %d work_places blocks" % (vehicle, len(start)))
    done, lines_out = set(), []
    for i in range(start[0] + 2, end[0]):
        s = lines[i].strip()
        if not s:
            continue
        cells = s.rstrip(b";").split(b", ")
        name = cells[0].decode()
        if name not in wp_edits:
            continue
        # FIELD KEYS ARRIVE AS STRINGS FROM JSON. Two reasons this must be coerced, not just
        # tolerated: "11" >= 4 is a TypeError, which is how this was found (the build stopped at
        # "The vehicle table"), and sorting string keys puts "11" BEFORE "4", so a multi-field edit
        # would also have been applied in the wrong order. Only the built-in t34_utz_m42, whose
        # wp_edits live in Python source with int keys, had ever exercised this path.
        for f, val in sorted((int(k), w) for k, w in wp_edits[name].items()):
            if f >= len(cells):
                raise SystemExit("%s %s has %d fields, no field [%d]" % (vehicle, name, len(cells), f))
            lines_out.append("%s [%d] %s -> %s" % (name, f, cells[f].decode(), val))
            cells[f] = str(val).encode()
        lines[i] = b"\t\t" + b", ".join(cells) + b";"
        done.add(name)
    missing = sorted(set(wp_edits) - done)
    if missing:
        raise SystemExit("%s has no work_place row named %s" % (vehicle, ", ".join(missing)))
    return CRLF.join(lines), lines_out


def edit_sights_text(text, vehicle, sights):
    """The vehicle's sights block in its techn text: edited rows replaced, padded rows appended."""
    lines = text.split(CRLF)
    start = [i for i, l in enumerate(lines) if l.startswith(b"\tsights[") and l.endswith(b"]()")]
    end = [i for i, l in enumerate(lines) if l == b"\t} //endof sights"]
    if len(start) != 1 or len(end) != 1:
        raise SystemExit("techn_base: %s has %d sights blocks" % (vehicle, len(start)))
    body = [i for i in range(start[0] + 2, end[0]) if lines[i].strip()]
    for i, row in sights["edits"].items():
        name = row[0].encode()
        if not lines[body[i]].startswith(b"\t\t" + name + b", "):
            raise SystemExit("techn_base: %s sights row %d is not %s: %r" % (vehicle, i, row[0], lines[body[i]]))
        lines[body[i]] = _sight_text(row)
    at = body[-1] + 1
    lines[at:at] = [_sight_text(r) for r in sights["added"]]
    # sight_order: the edits above were applied AT the donor's positions, so this moves whole rows
    # afterwards and the names travel with their geometry. Identity elsewhere.
    perm = sights.get("perm")
    if perm:
        moved = [lines[body[perm[k]]] for k in range(len(body))]
        for k, ln in enumerate(moved):
            lines[body[k]] = ln
    return CRLF.join(lines)


MGUNNER_TAIL = [                     # the fixed part of the hull gunner's block, from BoW43 notes/22
    b"", b"			controls[s]()", b"			{", b"				tnk_sights;", b"",
    b"			} //endof controls", b"", b"		} //endof mgunner", b""]


def mgunner_from_driver(lines, st, en):
    """The hull gunner's block, built from THIS cockpit's own driver block.

    MGUNNER_BLOCK used to be a hardcoded byte list carrying the T-62 driver's values - camera_up
    -0.07,0.75,0.72,2, periscope_01 s_light_drv_hl_01, pmesh 1. check_fifth_station builds its
    expectation from the vehicle's OWN driver block (mprops = dict(dprops, ...)), so the two agreed
    only when the cockpit WAS the T-62's. The KV-1's is not: its driver reads s_periscope_drv_01..03,
    camera_up -0.23,0.9,0.88,1.5, pmesh 2 - and the build stopped there.

    So: take the driver's own property lines, make the three changes the check expects, drop
    periscope_02, and append the fixed controls tail. The rule this restores - NO PER-VEHICLE VALUE
    MAY BE HARDCODED IN THE FIFTH-STATION PATH - is the same class as every other guard that broke
    today when a second vehicle appeared.
    """
    d = [i for i in range(st, en) if lines[i] == b"		driver=()"]
    if len(d) != 1:
        raise SystemExit("cocpits: %d driver blocks to take the mgunner from" % len(d))
    ds = d[0]
    de = next(i for i in range(ds, en) if lines[i] == b"		} //endof driver")
    props, seen = [], set()
    for i in range(ds, de):
        s = lines[i]
        if not s.startswith(b"			") or b"	= " not in s:
            continue
        name = s.strip().split(b"[")[0]
        seen.add(name)
        if name == b"periscope_02":
            continue                       # the hull gunner has no second periscope
        props.append(s)
    fix = {b"int_sprite": b"			int_sprite[s]	= tnk_gunner;",
           b"int_sprite_dead": b"			int_sprite_dead[s]	= tnk_gunner_u;",
           b"plc_name": b"			plc_name[s]	= txt_mt_plc_mgunner;"}
    out = [fix.get(s.strip().split(b"[")[0], s) for s in props]
    for name in (b"int_sprite", b"int_sprite_dead", b"plc_name"):
        if name not in seen:
            out.append(fix[name])
    return [b"		mgunner=()", b"		{"] + out + MGUNNER_TAIL


PREFIX = bytes([9, 9, 9])          # every plc_states row line starts with three tabs
TAB = bytes([9])
QUOTES = (chr(34), chr(39))       # a double and a single quote


def _split_top(text):
    """Split one plc_states row on TOP-LEVEL commas only.

    A row's fields are separated by comma-space and its TUPLE fields contain comma-space
    themselves, so the obvious split corrupts them. Parens and quotes protect their contents.
    """
    out, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in QUOTES:
            quote = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def plc_states_rows(text, cockpit):
    """[(line index, [field, ...])] for every plc_states row of one cockpit.

    Fields are TEXT FRAGMENTS, split on top-level commas only, never parsed into values - so a
    tuple cannot be mangled by a round trip. The same two guards add_fifth_station uses: the
    cockpit and its plc_states block must each be found exactly once.
    """
    lines = text.split(CRLF)
    name = cockpit.encode()
    st = [i for i, l in enumerate(lines) if l == TAB + name + b"=()"]
    en = [i for i, l in enumerate(lines) if l == TAB + b"} //endof " + name]
    if len(st) != 1 or len(en) != 1:
        raise SystemExit("cocpits: %s not found exactly once" % cockpit)
    ps = [i for i in range(st[0], en[0]) if lines[i].startswith(TAB + TAB + b"plc_states[")]
    pe = [i for i in range(st[0], en[0]) if lines[i] == TAB + TAB + b"} //endof plc_states"]
    if len(ps) != 1 or len(pe) != 1:
        raise SystemExit("cocpits: %s has no single plc_states block" % cockpit)
    out = []
    for i in range(ps[0] + 2, pe[0]):
        if not lines[i].strip():
            continue
        out.append((i, _split_top(lines[i][len(PREFIX):].decode("latin1"))))
    return out


def find_plc_row(text, cockpit, match):
    """The ONE row whose fields equal match, or refuse. match is {field index: exact text}."""
    hits = [(i, f) for i, f in plc_states_rows(text, cockpit)
            if all(k < len(f) and f[k] == v for k, v in match.items())]
    if len(hits) != 1:
        raise SystemExit("cocpits: %s: %d plc_states rows match %r, expected exactly 1"
                         % (cockpit, len(hits), match))
    return hits[0]


def edit_plc_state(text, cockpit, match, changes):
    """Change named FIELDS of the ONE row that matches. Returns (new text, line index, [fields]).

    Refuses rather than corrupts:
      - 0 matches, or more than 1 - an ambiguous edit is not an edit;
      - a row whose text does not re-render exactly from its fields, so a line with unusual
        spacing is left alone instead of being silently rewritten;
      - a field index the row does not have.
    """
    lines = text.split(CRLF)
    i, fields = find_plc_row(text, cockpit, match)
    rendered = PREFIX + ", ".join(fields).encode("latin1")
    if rendered != lines[i]:
        raise SystemExit("cocpits: %s row %d does not re-render from its fields, so it is not safe "
                         "to rewrite: %r" % (cockpit, i, lines[i]))
    for k, v in sorted(changes.items()):
        if k >= len(fields):
            raise SystemExit("cocpits: %s row %d has %d fields, no field %d"
                             % (cockpit, i, len(fields), k))
        fields[k] = v
    lines[i] = PREFIX + ", ".join(fields).encode("latin1")
    return CRLF.join(lines), i, fields


def mesh_chunk_names(blob):
    """Every node name in an AZG2 model. Table at header 0x08, count 0x0c, stride 0x140."""
    tbl = struct.unpack_from("<I", blob, 0x08)[0]
    cnt = struct.unpack_from("<I", blob, 0x0c)[0]
    return {blob[tbl + i * 0x140:tbl + i * 0x140 + 0x20].split(b"\x00")[0].decode("latin1")
            for i in range(cnt)}


def _find_mesh(install, name, required=True):
    import glob
    for p in glob.glob(os.path.join(install, "data", "**", "packed_data", "*.flatdata"),
                       recursive=True):
        try:
            recs = azcf.archive_records(p)
        except Exception:
            continue
        if name in recs and recs[name][2] == "mesh":
            return azcf.read_record(p, name)
    if required:
        raise SystemExit("interior: model %s is not in the install" % name)
    return None


def interior_dead_chunks(install, old_model, new_mesh_file, also, log=None):
    """Chunk names that USED to resolve in the cockpit's old slot-0 model and now resolve in no
    model the cockpit can reach.

    THIS IS THE QUESTION v115 FAILED TO ASK. It checked the `hide` block, found 30 of 30 names
    missing and fixed that block - but THIRTY-ONE blocks look a chunk up in slot 0, and the two
    interiors share two names out of 90 and 84, so 162 references were left dangling and the load
    001'd on ~90% of attempts. A name is only dead if NOTHING has it: the other model slots and the
    vehicle's own model keep most of them alive, including every `hit_*` row and 26 of the 31
    `sync` rows.
    """
    old = mesh_chunk_names(_find_mesh(install, old_model))
    with open(new_mesh_file, "rb") as f:
        new = mesh_chunk_names(f.read())
    alive = set(new)
    for name in also:
        blob = _find_mesh(install, name, required=False)
        if blob is not None:
            alive |= mesh_chunk_names(blob)
    dead = {c for c in old if c not in alive}
    if log:
        log("    slot 0 %s -> %s: %d chunks become %d, %d names shared; %d of the old names resolve "
            "nowhere else, so every row using one must go"
            % (old_model, os.path.basename(new_mesh_file), len(old), len(new), len(old & new),
               len(dead)))
    return dead


INTERIOR_SLOT_PROP = {0: b"mesh", 1: b"mesh_01", 2: b"mesh_02", 3: b"mesh_03", 4: b"mesh_04"}


def edit_cockpit_interior(text, cockpit, mesh_name, slot=0, dead=None):
    """Point a cockpit's model SLOT at an interior of ours, and stop hiding that slot.

    THE TWO EDITS BELONG TOGETHER. The hide rows exist to hide the DONOR's interior - loaded but
    not drawn (v8). The moment the slot holds OUR mesh those same rows do two wrong things:

      1. they name chunks our mesh has not got, and adv_tnksim copies a chunk's matrix with NO
         check that the lookup succeeded, so a missing one is an access violation that base_shell
         catches as "001" (docs/cockpit-ceiling.md). MEASURED on the T-34: 31 rows aim at slot 0
         and our interior has 1 of those 30 names, so a bare swap is 30 guaranteed faults.
      2. even if every name resolved, they would hide the interior we just put there.

    So the rows for that slot are DROPPED rather than rewritten - there is nothing to hide any
    more. Rows for the other slots (the donor's devices and labels, which we do not replace) and
    the mesh -1 rows on the vehicle's own external model are left exactly alone.

    Returns (new text, prop line index, the old mesh name, [dropped chunk names]).
    """
    lines = text.split(CRLF)
    st = [i for i, l in enumerate(lines) if l == b"	" + cockpit.encode() + b"=()"]
    en = [i for i, l in enumerate(lines) if l == b"	} //endof " + cockpit.encode()]
    if len(st) != 1 or len(en) != 1:
        raise SystemExit("cocpits: %s not found exactly once" % cockpit)
    a, b = st[0], en[0]
    if slot not in INTERIOR_SLOT_PROP:
        raise SystemExit("cocpits: %s has no model slot %r" % (cockpit, slot))
    prop = INTERIOR_SLOT_PROP[slot]
    hits = [i for i in range(a, b) if lines[i].startswith(b"		" + prop + b"[s]	= ")]
    if len(hits) != 1:
        raise SystemExit("cocpits: %s has %d %s lines, expected 1"
                         % (cockpit, len(hits), prop.decode()))
    was = lines[hits[0]].split(b"= ", 1)[1].rstrip(b";").decode("latin1")
    if was == mesh_name:
        raise SystemExit("cocpits: %s %s is already %s" % (cockpit, prop.decode(), mesh_name))
    lines[hits[0]] = b"		" + prop + b"[s]	= " + mesh_name.encode() + b";"
    hs = [i for i in range(a, b) if lines[i] == b"		hide[suu]()"]
    he = [i for i in range(a, b) if lines[i] == b"		} //endof hide"]
    if len(hs) != 1 or len(he) != 1:
        raise SystemExit("cocpits: %s has no single hide block" % cockpit)
    keep, dropped = [], []
    for l in lines[hs[0] + 2:he[0]]:
        f = l.strip().rstrip(b";").split(b", ")
        if len(f) == 3 and f[1] == str(slot).encode():
            dropped.append(f[0].decode("latin1"))
        else:
            keep.append(l)
    if not dropped:
        raise SystemExit("cocpits: %s has no hide rows on slot %d - refusing, because that is not "
                         "the cockpit this edit was written for" % (cockpit, slot))
    lines[hs[0] + 2:he[0]] = keep
    # AND EVERY OTHER BLOCK. v115 dropped the hide rows and 001'd anyway, because 31 blocks look a
    # chunk up in this model, not one. A row goes only if it names a chunk that resolves NOWHERE
    # now - `dead` is computed by interior_dead_chunks, which checks the other slots and the
    # vehicle's own model before calling a name lost.
    swept = []
    if dead:
        a2 = [i for i, l in enumerate(lines) if l == b"	" + cockpit.encode() + b"=()"][0]
        b2 = [i for i, l in enumerate(lines) if l == b"	} //endof " + cockpit.encode()][0]
        out = []
        for i, l in enumerate(lines):
            if a2 < i < b2 and l.startswith(b"			"):
                f = [x.decode("latin1") for x in l.strip().rstrip(b";").split(b", ")[:3]]
                hit = next((x for x in f if x in dead), None)
                if hit is not None:
                    swept.append(hit)
                    continue
            out.append(l)
        lines = out
    return CRLF.join(lines), hits[0], was, dropped, swept


def check_cockpit_interior(before, after, cockpit, mesh_name, was, slot, dropped, swept=()):
    """after = before with ONE prop line rewritten and exactly the named hide rows gone.

    A control that cannot fail is not a control: this compares the two texts as multisets of
    lines, so anything else that moved shows up as an unexplained difference.
    """
    import collections
    bl, al = before.split(CRLF), after.split(CRLF)
    if len(bl) - len(al) != len(dropped) + len(swept):
        raise SystemExit("cocpits: %s interior dropped %d lines, expected %d hide + %d swept"
                         % (cockpit, len(bl) - len(al), len(dropped), len(swept)))
    gone = collections.Counter(bl) - collections.Counter(al)
    came = collections.Counter(al) - collections.Counter(bl)
    prop = INTERIOR_SLOT_PROP[slot]
    want_new = b"		" + prop + b"[s]	= " + mesh_name.encode() + b";"
    want_old = b"		" + prop + b"[s]	= " + was.encode() + b";"
    if list(came) != [want_new] or came[want_new] != 1:
        raise SystemExit("cocpits: %s interior added %r, expected only %r" % (cockpit, dict(came), want_new))
    if gone[want_old] != 1:
        raise SystemExit("cocpits: %s interior did not remove its old %s line" % (cockpit, prop.decode()))
    accounted = set(dropped) | set(swept)
    unexplained = [l for l in gone if l != want_old
                   and not any(x.decode("latin1") in accounted
                               for x in l.strip().rstrip(b";").split(b", ")[:3])]
    if unexplained:
        raise SystemExit("cocpits: %s interior removed lines it should not have: %r"
                         % (cockpit, unexplained[:4]))
    import collections as _c
    per = _c.Counter(swept)
    return ["  %s interior: %s slot %d  %s -> %s" % (cockpit, prop.decode(), slot, was, mesh_name),
            "    - %d rows swept from the other blocks, naming %d chunks that now resolve nowhere "
            "(top: %s)" % (len(swept), len(per),
                           ", ".join("%s x%d" % kv for kv in per.most_common(5))) if swept else
            "    - no rows swept",
            "    - %d hide rows on slot %d dropped, so the new interior is DRAWN rather than hidden; "
            "slots 1/2 and the mesh -1 rows untouched" % (len(dropped), slot)]


def check_plc_states(before, after, cockpit, line, changed):
    """after = before with exactly the named fields rewritten on exactly that line, nothing else.

    The same shape as check_fifth_station, and for the same reason: a control that cannot fail is
    not a control.
    """
    a, b = before.split(CRLF), after.split(CRLF)
    if len(a) != len(b):
        raise SystemExit("cocpits: %s plc_states edit changed the line count" % cockpit)
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if diff and diff != [line]:
        raise SystemExit("cocpits: %s plc_states edit touched lines %r, expected only %d"
                         % (cockpit, diff, line))
    if not diff:
        # No-op. Legitimate - the fields already held what was asked for - but it must be a no-op
        # for THAT reason, not because the edit went somewhere else.
        for i, f in plc_states_rows(after, cockpit):
            if i == line and len(_split_top(a[line][len(PREFIX):].decode("latin1"))) != len(f):
                raise SystemExit("cocpits: %s plc_states row %d changed shape" % (cockpit, line))
        return ["  %s: plc_states row %d already held %s - nothing to change"
                % (cockpit, line, sorted(changed))]
    old = _split_top(a[line][len(PREFIX):].decode("latin1"))
    new = _split_top(b[line][len(PREFIX):].decode("latin1"))
    if len(old) != len(new):
        raise SystemExit("cocpits: %s plc_states row changed its field count" % cockpit)
    bad = [k for k in range(len(old)) if old[k] != new[k] and k not in changed]
    if bad:
        raise SystemExit("cocpits: %s plc_states row changed fields %r that were not asked for"
                         % (cockpit, bad))
    return ["  %s: plc_states row %d, changed fields %s" % (cockpit, line, sorted(changed))]


def add_fifth_station(text, cockpit):
    """notes/22 variant C on one cockpit: loader views 3 -> 4, two basic views for place 3 (the driver's first
    two, renumbered), and the mgunner block before the loader."""
    lines = text.split(CRLF)
    st = [i for i, l in enumerate(lines) if l == b"\t" + cockpit.encode() + b"=()"]
    en = [i for i, l in enumerate(lines) if l == b"\t} //endof " + cockpit.encode()]
    if len(st) != 1 or len(en) != 1:
        raise SystemExit("cocpits: %s not found exactly once" % cockpit)
    ps = [i for i in range(st[0], en[0]) if lines[i].startswith(b"\t\tplc_states[")]
    pe = [i for i in range(st[0], en[0]) if lines[i] == b"\t\t} //endof plc_states"]
    if len(ps) != 1 or len(pe) != 1:
        raise SystemExit("cocpits: %s has no single plc_states block" % cockpit)
    rows = [i for i in range(ps[0] + 2, pe[0]) if lines[i].strip()]
    if any(lines[i].startswith(b"\t\t\t4, ") for i in rows):
        raise SystemExit("cocpits: %s already has place-4 views" % cockpit)
    for i in rows:
        if lines[i].startswith(b"\t\t\t3, "):
            lines[i] = b"\t\t\t4, " + lines[i][len(b"\t\t\t3, "):]
    basic = []
    for head in (b"\t\t\t0, 4294967295, 0, ", b"\t\t\t0, 4294967295, 4096, "):
        hit = [lines[i] for i in rows if lines[i].startswith(head)]
        if len(hit) != 1:
            raise SystemExit("cocpits: %s has %d driver views starting %r" % (cockpit, len(hit), head))
        basic.append(b"\t\t\t3, " + hit[0][len(b"\t\t\t0, "):])
    lines[rows[-1] + 1:rows[-1] + 1] = basic
    en = [i for i, l in enumerate(lines) if l == b"\t} //endof " + cockpit.encode()]
    ld = [i for i in range(st[0], en[0]) if lines[i] == b"\t\tloader=()"]
    if len(ld) != 1 or any(lines[i] == b"\t\tmgunner=()" for i in range(st[0], en[0])):
        raise SystemExit("cocpits: %s has %d loader blocks or already an mgunner" % (cockpit, len(ld)))
    lines[ld[0]:ld[0]] = mgunner_from_driver(lines, st[0], en[0])
    return CRLF.join(lines)


def _listed(x):
    x = list(x)
    if isinstance(x[3], list):
        x[3] = [list(r) for r in x[3]]
    return x


def check_fifth_station(before, after, cockpit):
    """after = before with exactly the variant C change on `cockpit`, nothing else."""
    a, b = build.decoded(azcf.Table(before)), build.decoded(azcf.Table(after))
    start = [i for i, x in enumerate(a) if x[0] == cockpit]
    if len(start) != 1:
        raise SystemExit("cocpits: %s not found" % cockpit)
    tops = [i for i, x in enumerate(a) if x[0].startswith("coc_")] + [len(a)]
    s, e = start[0], next(i for i in tops if i > start[0])
    want = [_listed(x) for x in a]
    plc = [i for i in range(s, e) if want[i][0] == "plc_states"][0]
    rows = want[plc][3]
    basic = [r for r in rows if r[0][0] == 0 and r[0][1] == 0xffffffff and r[0][2] in (0, 4096)]
    if len(basic) != 2:
        raise SystemExit("cocpits: %s has %d basic driver views, expected 2" % (cockpit, len(basic)))
    new_basic = [[(3,) + tuple(r[0][1:])] + list(r[1:]) for r in basic]
    for r in rows:
        if r[0][0] == 3:
            r[0] = (4,) + tuple(r[0][1:])
    rows += new_basic
    want[plc][2] = len(rows)
    loader = [i for i in range(s, e) if want[i][0] == "loader" and len(want[i][1]) == 1][0]
    dprops = dict([x for x in a[s:e] if x[0] == "driver" and len(x[1]) == 1][0][3])
    mprops = dict(dprops, int_sprite="tnk_gunner", int_sprite_dead="tnk_gunner_u", plc_name="txt_mt_plc_mgunner")
    mprops.pop("periscope_02", None)
    # PER COCKPIT, NOT ACROSS THE TABLE. Each crewable vehicle has its OWN cockpit block, so two
    # vehicles each taking a fifth station is two mgunner blocks in two different cockpits - which
    # is fine. Counting them globally made that impossible: the moment a second five-station vehicle
    # existed (the KV-1, the Tiger) this refused with "2 mgunner blocks, expected 1". The global
    # count happened to be right when only the Panzer IV ever needed one.
    tops_b = [i for i, x in enumerate(b) if x[0].startswith("coc_")] + [len(b)]
    here = [i for i, x in enumerate(b) if x[0] == cockpit]
    if len(here) != 1:
        raise SystemExit("cocpits: %s not found after the edit" % cockpit)
    bs = here[0]
    be = next(i for i in tops_b if i > bs)
    got_m = [x for x in b[bs:be] if x[0] == "mgunner"]
    # Two failures used to share one message, and it printed the dict either way - so "there are TWO mgunner
    # blocks" came out looking like "this dict differs", with the two dicts printed IDENTICAL. That cost a
    # real diagnosis on 2026-09-23, when the Matilda took a fifth station it did not need. Separate them.
    if len(got_m) != 1:
        raise SystemExit(
            "cocpits: %s has %d mgunner blocks, expected exactly 1. fifth_station defaults to True and a "
            "vehicle only needs one when it has FIVE manned work_places against the donor cockpit's four - "
            "set it False on the ones that do not. (This is per cockpit: two vehicles may each have one.)"
            % (cockpit, len(got_m)))
    if dict(got_m[0][3]) != mprops:
        diff = [(k, dict(got_m[0][3]).get(k), mprops.get(k))
                for k in set(dict(got_m[0][3])) | set(mprops)
                if dict(got_m[0][3]).get(k) != mprops.get(k)]
        raise SystemExit("cocpits: the mgunner block differs in %d field(s): %r" % (len(diff), diff))
    ctl = [x for x in a if x[0] == "controls"][0]
    want[loader:loader] = [_listed(got_m[0]), ["controls", ctl[1], 1, [["tnk_sights"]]]]
    got = [_listed(x) for x in b]
    # SCOPE THE COMPARISON TO THIS COCKPIT. Each fifth-station vehicle inserts its own two blocks
    # into its OWN cockpit, so with two of them the whole-table lengths cannot match - the count came
    # out 406 against 404, exactly the second cockpit's mgunner and controls blocks. This check is
    # about ONE cockpit's variant C, so it compares that cockpit's span: the transformed copy of the
    # recipe against what was built. Same verdict, no dependence on how many other vehicles took a
    # fifth station.
    tops_w = [i for i, x in enumerate(want) if x[0].startswith("coc_")] + [len(want)]
    ws = [i for i, x in enumerate(want) if x[0] == cockpit][0]
    we = next(i for i in tops_w if i > ws)
    want_span, got_span = want[ws:we], got[bs:be]
    if len(got_span) != len(want_span):
        raise SystemExit("cocpits: %s has %d blocks after the fifth station, expected %d"
                         % (cockpit, len(got_span), len(want_span)))
    bad = [w[0] for w, g in zip(want_span, got_span) if w != g]
    if bad:
        raise SystemExit("cocpits: fifth station changed more than planned: %s" % bad)
    return ["  %s: + mgunner station before the loader (the driver's block as a hull gunner), loader views "
            "3 -> 4, + 2 place-3 views (BoW43 notes/22 variant C); every other block identical" % cockpit]


def build_crew_cockpits(install, plans, log):
    """cocpits with ONE NEW COCKPIT PER CREWABLE VEHICLE. Returns (compiled, report).

    The engine has always taken several - stock ships the T-62 and the M60A1 playable and BoW43 ran the
    Olifant and the Chieftain in one mission - and the cockpit table holds them side by side. The old limit
    here was ours, not the engine's. build.edit_cocpits_text appends one cockpit to the text it is handed,
    so several are had by chaining it.

    The fifth station is per vehicle: the Panzer IV has five crew stations against the donor cockpit's four
    and needs one added; a T-34 has exactly four and must not have one.
    """
    folder = os.path.join(work_dir(install), "text", "cocpits")
    fixed = textable.round_trip(install, "cocpits", folder, log)
    with open(fixed, "rb") as f:
        src = f.read()
    stock = azcf.read_record(build.tabs_path(install), "cocpits")
    out = os.path.join(folder, "edited")
    os.makedirs(os.path.join(out, "recipe"), exist_ok=True)

    recipe_text = src
    for v, plan in plans.items():
        recipe_text = build.edit_cocpits_text(recipe_text, plan)
    p = os.path.join(out, "recipe", "cocpits.loc_def.engcfg2")
    with open(p, "wb") as f:
        f.write(recipe_text)
    recipe_built = textable.compile_text(install, p, os.path.join(out, "recipe", "cocpits.config"), log)
    # one call with every plan, in the order they were appended: check_cocpits walks the blocks past
    # stock and must account for all of them, so it has to see them all at once
    report = build.check_cocpits(stock, recipe_built, list(plans.values()))

    text = recipe_text
    fifth = [v for v in plans if VEHICLES.get(v, {}).get("fifth_station", True)]
    for v in fifth:
        text = add_fifth_station(text, plans[v].cockpit)
    # v111: `plc_edits` - [(match, changes)] applied to ONE plc_states row each, through the editor
    # that already refuses an ambiguous match and a row that would not re-render, with
    # check_plc_states as the control. Built for exactly this and unused until now.
    #
    # WHY IT EXISTS. A cloned cockpit picks sights by the DONOR's index order, which
    # `docs/plc-states-decoded.md` warned about three weeks ago using the T-55 as the example. The
    # T-34's hull machine-gunner is the case in our own fleet: its sight GROUPS are sig_driver 3,
    # sig_gunner 4, sig_loader 1 and sig_mgunner 1, and the cockpit's place-2 view row asks for
    # sight index 2 of a group that has only index 0. There is nothing to select, so pressing V
    # does nothing and that crewman is left in the hull with no way out (murkz, 2026-10-01).
    for v in sorted(plans):
        for match, changes in VEHICLES.get(v, {}).get("plc_edits", ()):
            before = text
            text, line, _fields = edit_plc_state(text, plans[v].cockpit, match, changes)
            report += check_plc_states(before, text, plans[v].cockpit, line, changes)
    # v115: OUR OWN INTERIOR IN A COCKPIT MODEL SLOT. Same shape as plc_edits above - a VEHICLES
    # key, an edit that refuses rather than corrupts, and a check that compares the two texts as
    # multisets of lines so anything else that moved is reported. See edit_cockpit_interior.
    for v in sorted(plans):
        spec = VEHICLES.get(v, {}).get("interior")
        if not spec:
            continue
        before = text
        dead = interior_dead_chunks(install, spec["was"], spec["file"], spec.get("also", ()),
                                    log) if spec.get("file") else None
        text, _line, was, dropped, swept = edit_cockpit_interior(
            text, plans[v].cockpit, spec["mesh"], spec.get("slot", 0), dead)
        report += check_cockpit_interior(before, text, plans[v].cockpit, spec["mesh"], was,
                                         spec.get("slot", 0), dropped, swept)
    p = os.path.join(out, "cocpits.loc_def.engcfg2")
    with open(p, "wb") as f:
        f.write(text)
    built = textable.compile_text(install, p, os.path.join(out, "cocpits.config"), log)
    for v in plans:
        if v in fifth:
            report += check_fifth_station(recipe_built, built, plans[v].cockpit)
        else:
            report += ["  %s: no fifth station - its stations match the cockpit's places" % v]
    return built, report


def build_sight_alias(install, log, gunner_sight=GUNNER_SIGHT):
    """common_res_mod with OUR gunner sight rows (ownsight.py's proven route), and their reticle meshes.
    Returns (compiled table, report, [(mesh name, bytes)]).

    Takes one sight name or several. It was one until 2026-09-22, when a second crewable vehicle got its own
    reticle - the Panzer IV keeps its TZF 5f and the T-34 gains its TMFD-7 - and the build stopped dead rather
    than quietly shipping one of them. The table route itself was never the limit: notes/82 established that
    an addon should ship only its own rows and that a sights row costs nothing, so N rows are no more
    dangerous than the first was.
    """
    import ownsight
    names = []
    for n in ([gunner_sight] if isinstance(gunner_sight, str) else list(gunner_sight)):
        if n not in names:
            names.append(n)
    if not names:
        raise SystemExit("build_sight_alias called with no sights")
    gs = [GUNNER_SIGHTS[n] for n in names]
    text_specs = [{"donor_row": g["donor_row"], "row": g["row"],
                   "fields": {p: t for p, (t, v) in g["fields"].items()}} for g in gs]
    value_specs = [{"donor_row": g["donor_row"], "row": g["row"],
                    "fields": {p: v for p, (t, v) in g["fields"].items()}} for g in gs]
    folder = os.path.join(work_dir(install), "text", "common_res_mod")
    fixed = textable.round_trip(install, "common_res_mod", folder, log)
    with open(fixed, "rb") as f:
        text = ownsight.common_res_mod_text(f.read(), text_specs)
    edited = os.path.join(folder, "edited", "common_res_mod.loc_def.engcfg2")
    os.makedirs(os.path.dirname(edited), exist_ok=True)
    with open(edited, "wb") as f:
        f.write(text)
    crm = textable.compile_text(install, edited, os.path.join(folder, "edited", "common_res_mod.config"), log)
    report = ["  " + line for line in ownsight.check_common_res_mod(
        azcf.read_record(build.tabs_path(install), "common_res_mod"), crm, value_specs)]
    meshes, by_name = [], {}
    for n, g in zip(names, gs):
        if not g["mesh"]:
            continue
        name, path, md5 = g["mesh"]
        if not os.path.isfile(path):
            raise SystemExit("the %s reticle mesh is missing: %s" % (name, path))
        with open(path, "rb") as f:
            blob = f.read()
        got = hashlib.md5(blob).hexdigest()
        if got != md5:
            raise SystemExit("the %s reticle mesh at %s is not the proven one (md5 %s, expected %s)"
                             % (name, path, got, md5))
        # Two sights may share a mesh name only if they are the same bytes; otherwise one would
        # silently overwrite the other in the pack and the wrong reticle would ship.
        if name in by_name and by_name[name] != got:
            raise SystemExit("two sights both ship a reticle mesh called %s, with different bytes" % name)
        if name not in by_name:
            by_name[name] = got
            meshes.append((name, blob))
        report.append("  reticle mesh %s for %s: %d bytes, md5 %s as recorded (%s)"
                      % (name, n, len(blob), md5, path))
    return crm, report, meshes


# ---------------------------------------------------------------- the vehicle's own table (from v1)


def _vehicle_span(t, name):
    """How many blocks vehicle `name` spans: up to the next vehicle-shaped block (no fields, no rows)."""
    names = [b.name for b in t.blocks]
    i = names.index(name)
    j = i + 1
    while j < len(t.blocks) and not (t.blocks[j].spec.replace("\0", "") == "" and t.blocks[j].rows == 0
                                     and t.blocks[j].name in VEHICLE_NAMES):
        j += 1
    return j - i


def _block_seq(t, name, count):
    names = [b.name for b in t.blocks]
    i = names.index(name)
    out = []
    for b in t.blocks[i:i + count]:
        vals = t.props(b) if b.name == "props" else (t.rows(b) if b.rows else [])
        out.append((b.name, b.spec.replace("\0", ""), b.rows, vals))
    return out


EFFECTIVE_SPECS = {}  # vehicle -> the spec a build ACTUALLY used, filled by build_ai and read by
                      # the proven-spec snapshot. Same warning as OVERRIDE: per-build only.
OVERRIDE = {}        # vehicle -> per-BUILD spec overrides, cleared at the start of build_ai. Never
                     # write to VEHICLES itself: Check the tool builds every proven entry in one
                     # process, so a mutation there leaks into the next build and quietly changes it.
WP_REPORT = {}       # vehicle -> the work_places field changes made, for the read-back report
# REPINNED 2026-09-29 from bb4c2bb1c8ff2515bc7cceb15fe7e1bc. The file legitimately advanced:
# gtos_sokolovo_ob v020 shipped t34_42_utz/s_mgunner at (0.3436, 0.2730, 1.3000) IN THE PACKAGE,
# which is exactly what patch_shadowing_models() wants to write, so that patch is now a NO-OP and a
# backup of this state is a valid way back - which is the whole point of the pin. Verified before
# repinning: the T-34 node already reads the target and only pz3jlg's cameras (1.7563/1.6801, wanted
# 1.4431) are still to move. A pin must never be bumped just to make a build pass; it is bumped here
# because the new state is the PROVEN one and carries the intended values already.
LIVE_PINS = {"gos_main_ob.flatdata": "e43a227bb6113ca40820c85535bf6b09"}
# v105: it is the SOKOLOVO ADD-ON'S OWN FILE (e26fbb3e...) with the T-34's TWO front seats moved to the
# values v105 ships - s_driver back on the 1942 model's own 1.3043 and s_mgunner back to v26's 1.30.
# v106: plus s_mgunner's HEIGHT, y +0.3769 -> +0.2730, the driver's own.
# v107: and the two seats are now applied BY THE BUILD, which keeps them - see keep_live_mesh above.
#       The pin is therefore what the build produced, not what a hand patch produced, and the live
#       copy's two nodes are byte-identical to the package's. Proved by tool/test_live_wiring.py:
#       start from Operation Star's own value (what a Sokolovo reinstall gives you), build, and the
#       log reads "KEPT ... t34_42_utz's mesh_points is a real fix and stays" while pz3jlg is restored.
# Both copies of the model must agree or a Sokolovo battle reads the unpatched one (BUILD_LOG 436).
                     # whole-file state we KNOW for a file the build patches. Reported after every
                     # build: the tool put its own edits back, so a mismatch means something else
                     # moved the file, and that is worth seeing rather than passing over.
                     # v101: this value was the SOKOLOVO ADD-ON'S OWN FILE, byte for byte (e26fbb3e...),
                     # because the only thing that had ever differed was our T-34 hull-gunner seat move.
                     # v102: it is that file PLUS the T-34 DRIVER's seat - e26fbb3e plus one node's z,
                     # 1.3043 -> 1.6440, which puts the driver beside his hull gunner as Operation Star's
                     # own 1941 T-34 has him (see the T-34's mesh_points above). That patch is part of the
                     # state we know, so the pin is the patched file, dd6d49cf..., and the add-on's own
                     # bytes remain re-derivable from gtos_sokolovo_ob_v001.gt2extension with this one
                     # node moved.
SHADOWED = []        # (path, offset, backup, was, model) for every file OUTSIDE our add-on this
                     # build patched. The MODEL name is what lets one of them be kept while the rest
                     # are put back (v107) - see restore_shadowed_models().
                     # WITH patch_shadowing_models - so build_ai can put them ALL back at the end. See
                     # restore_shadowed_models() for why that is the tool's job and not the script's.
WP_PLANNED = {}      # vehicle -> the edits actually applied (spec's, plus the gunner turn-out removal)


def gunner_turnout_edit(table, vehicle):
    """The work_places edit that removes the gunner's turned-out position, matching the stock T-62.

    A T-62 gunner has no hatch: its wp_gunner names no out-position at all, while driver, loader and
    commander all do, and the cockpit has no turned-out gunner state to go with one. An imported
    vehicle whose own rows DO name one is offering a view the cockpit cannot make, and asking for it
    001s - murkz hit it on the Panzer IV and again on the T-34, and the stock T-62 is clean.

    Returns {} when the vehicle already matches the T-62, so it is safe on anything.
    """
    blocks = dict(azcf.vehicles(table))[vehicle]
    if "work_places" not in blocks:
        return {}
    rows = [list(r) for r in table.rows(blocks["work_places"])]
    hit = [r for r in rows if len(r) > WP_GROUP and r[WP_GROUP] == "sig_gunner"]
    if not hit:
        return {}
    r = hit[0]
    fields = {f: "" for f in (13, 15) if f < len(r) and r[f]}
    return {r[0]: fields} if fields else {}


# AZG2 node table, as crewpoints.read_mesh decodes it: header holds the node table at 0x08, the node
# count at 0x0c, the matrix table at 0x18. Each node record is 0x140 bytes - name at +0, then 8 ints at
# +0x20 of which field[0] is the matrix index (high bit set for static nodes, clear for animated ones)
# and field[1] > 0 marks geometry. A matrix is 16 floats; [12],[13],[14] are its translation.
MESH_NODE_TABLE, MESH_NODE_COUNT, MESH_MATRIX_TABLE = 0x08, 0x0c, 0x18
MESH_NODE_STRIDE, MESH_NODE_FIELDS, MESH_MATRIX_STRIDE = 0x140, 0x20, 0x40
AXIS = {"x": 12, "y": 13, "z": 14}


def model_copies(install, name):
    """Every archive in the install holding a mesh of this name, as (path, offset, size).

    A MODEL CAN EXIST MORE THAN ONCE. Ours is written into gtos_ww2; the engine may load another
    add-on's copy instead, and then a mesh_points edit lands in a file nothing reads. Measured
    2026-09-25: pz3jlg's mesh is in BOTH gtos_ww2 and gtos_sokolovo_ob, and the engine read the
    sokolovo one - which is why the anchor NAME moved the driver (resolved in the loaded model)
    while mesh_points never did (written to the unread one). Four builds went into that.
    """
    out = []
    for p in glob.glob(os.path.join(install, "data", "**", "*.flatdata"), recursive=True):
        try:
            recs = azcf.archive_records(p)
        except Exception:
            continue
        e = recs.get(name)
        if e and e[2] == "mesh":
            out.append((p, e[0], e[1]))
    return sorted(out)


def recipe_mesh_points():
    """{model name: {node: {axis: value}}} taken from every vehicle recipe."""
    out = {}
    for _v, _spec in VEHICLES.items():
        for _model, _nodes in (_spec.get("mesh_points") or {}).items():
            out.setdefault(_model, {}).update(_nodes)
    return out


def patch_packed_records(records, log=print):
    """Apply the recipes' mesh_points to mesh records ANOTHER builder is about to pack.

    THE CAMPAIGN AND MAP ADD-ONS SHIP THEIR OWN COPIES OF VEHICLE MESHES. gtos_sokolovo_ob's
    gos_main_ob.flatdata holds t34_42_utz, and it is the copy a Sokolovo battle reads. A mesh_points
    edit that only ever reaches gtos_ww2 is therefore invisible: measured 2026-09-27, the hull MG
    seat stood 0.358 m too far forward in the campaign copy while the vehicle copy was correct, and
    Jeff had to report it twice. Any builder that packs mesh records should pass them through here.

    records is [(name, kind, loc, blob)]. Returns a NEW list; the inputs are not touched.
    """
    want = recipe_mesh_points()
    out, patched = [], []
    for name, kind, loc, blob in records:
        if kind == "mesh" and name in want:
            new, said = blob, []
            for node, axes in sorted(want[name].items()):
                try:
                    new, s = patch_mesh_point(new, node, axes)
                    said.append(s)
                except SystemExit as e:
                    said.append("not patched: %s" % e)
            if new != blob:
                patched.append((name, "; ".join(said)))
            blob = new
        out.append((name, kind, loc, blob))
    for name, said in patched:
        log("      mesh_points applied to packed %s: %s" % (name, said))
    return out


def live_keep_models(vehicles, mesh_points=None):
    """WHICH MODELS' LIVE-COPY PATCHES THIS BUILD MUST KEEP, by name (v107).

    The live copies are the ones outside our add-on that the engine may read instead of ours, and a
    real fix has to be in EVERY copy - the T-34's crew seats are exactly that, and an add-on reinstall
    would otherwise put a man back where he was (BUILD_LOG 436). The old switch was all or nothing:
    keep_mesh_points kept every copy this build patched, so keeping the seats also kept the Panzer III
    camera fix the project holds back on purpose. This is the per-model answer, and it is a function so
    a test can check it rather than a claim in a comment.

    A vehicle opts in with mesh_points + "keep_live_mesh": True. A build that names its own mesh_points
    (a PROVEN entry pinning what it shipped) keeps nothing, exactly as it always did.
    """
    keep = set()
    if mesh_points is not None:
        return keep
    for v in vehicles:
        eff = dict(VEHICLES.get(v, {}), **OVERRIDE.get(v, {}))
        if eff.get("keep_live_mesh"):
            for model in (eff.get("mesh_points") or {}):
                keep.add(model.lower())
    return keep


def patch_shadowing_models(install, wanted, ours, log):
    """Apply the mesh_points edits to every OTHER copy of the model too.

    ours is the add-on we are building. The engine reads whichever copy wins, so patching only ours
    is a coin flip - and it came up wrong on pz3jlg. Each copy is backed up before it is touched and
    every write is reported, because these are files outside our own add-on: an add-on reinstall can
    wipe them, and that backup is the only way back.

    Same offset, same size, only the node's floats change - no repacking, so nothing else in the
    archive can move.
    """
    lines = []
    # files this build has already checked or already patched - see the pin check below
    verified = {p for p, _o, _b, _w, _m in SHADOWED}
    for name, nodes in sorted(wanted.items()):
        for path, off, size in model_copies(install, name):
            # EVERY COPY, our own included. It used to skip `ours`, on the assumption that the build
            # patches its own copy. Measured 2026-09-27: that assumption is false - gtos_ww2's copy of
            # pz3jlg held the UNPATCHED node (s_camera_driver z 1.356) while gtos_sokolovo_ob held the
            # fix (1.756), and gtos_ww2 loads LATER in paths.cfgpack, so the engine read the unpatched
            # one and the fix was invisible. `ours` is kept in the signature because the caller names
            # the add-on it is building, but no copy is skipped. Same offset, same size, backup first.
            with open(path, "rb") as f:
                f.seek(off)
                blob = f.read(size)
            try:
                new, said = blob, []
                for node, axes in sorted(nodes.items()):
                    new, s = patch_mesh_point(new, node, axes)
                    said.append(s)
            except SystemExit as e:
                lines.append("  %s: not patched - %s" % (os.path.basename(path), e))
                continue
            if new == blob:
                continue
            # A FILE AT ITS PIN, OR NOTHING. The backup this takes IS the way back, so a backup taken
            # from an ALREADY-PATCHED file puts the patch back instead of the original - and the only
            # sign is the pin mismatch in restore_shadowed_models()'s report, after the damage.
            # Measured 2026-09-28: probe builds that stopped between the patch and the restore left
            # gos_main_ob.flatdata patched, the next build backed THAT up, and putting it back was a
            # no-op that still read as "restored, read back identical". So: a pinned file that is not
            # at its pin stops the build, and says which backup holds the original.
            # AND THE PIN IS CHECKED ONCE PER FILE, NOT ONCE PER MODEL (v107). Several models can live
            # in the SAME archive - pz3jlg and t34_42_utz are both in gtos_sokolovo_ob's
            # gos_main_ob.flatdata - so the first patch legitimately takes that file off its pin and the
            # SECOND model's check then read the already-patched file and stopped the build with "it was
            # already patched by something else". Measured 2026-09-28: v105, v106 and the v107 wiring
            # test all died here, and it is the reason a live copy had only ever been patched BY HAND -
            # the tool could not do it for two models at once. "verified" holds the files this build has
            # already looked at or already patched.
            known = LIVE_PINS.get(os.path.basename(path))
            if known and path not in verified:
                verified.add(path)
                with open(path, "rb") as f:
                    digest = hashlib.md5(f.read()).hexdigest()
                if digest != known:
                    raise SystemExit(
                        "%s is NOT at its known pin (%s, found %s), so it was already patched by "
                        "something else and this build's backup would be a copy of a patched file.\n"
                        "  Put it back first, from the backup beside it in %s, then build again."
                        % (os.path.relpath(path, install), known[:12], digest[:12],
                           os.path.join(work_dir(install), "shadow")))
            bak = os.path.join(work_dir(install), "shadow",
                               "%s_%s_%d.bak" % (os.path.basename(path), name, off))
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            with open(bak, "wb") as f:
                f.write(blob)
            with open(path, "r+b") as f:
                f.seek(off)
                f.write(new)
            SHADOWED.append((path, off, bak, blob, name))   # v107: the MODEL, so one can be kept
            verified.add(path)
            lines.append("  %s: %s   (backup %s)"
                         % (os.path.relpath(path, install), "; ".join(said), os.path.basename(bak)))
    return lines


def restore_shadowed_models(install, log, pins=None, keep=None):
    """Put every file this build patched OUTSIDE our add-on back exactly as it was, and verify it.

    WHY THIS IS IN THE TOOL. patch_shadowing_models() edits LIVE game files - the other copies of a
    model the engine may read instead of ours - with the backup as the only way back. The putting-back
    used to be a HAND STEP in each build's own script, so a build run from the window left them
    patched: measured 2026-09-28, a probe build (the exact call the window makes) moved pz3jlg's two
    camera points inside gtos_sokolovo_ob's gos_main_ob.flatdata and left them moved. murkz's rule is
    that proven work belongs in the tool, and a fix a rebuild undoes is a loan, not a fix.

    IT PATCHES, SO IT PUTS BACK - UNLESS THE BUILD SAYS OTHERWISE. The mesh_points patch is a REAL
    FIX for the Panzer III that we hold back on purpose (one change per build), so the default is to
    restore; the build that eventually ships it passes keep_mesh_points=True to build_ai and keeps it.
    That way forgetting is not what decides it.

    Verified, not assumed: each region is read back and compared with the backup, and a mismatch stops
    the build. pins is {filename: md5} for files whose whole-file state is known - reported because a
    file that is NOT at its pin means something else changed it, which the next person should see.
    """
    if not SHADOWED:
        log("OK  no file outside the add-on was touched - nothing to put back")
        return
    # WHICH PATCHES STAY, ONE MODEL AT A TIME (v107). It used to be all or nothing: keep_mesh_points
    # kept EVERY copy this build patched, so a build that must keep the T-34's crew seats in the live
    # Sokolovo copy would have kept the Panzer III camera fix the project holds back on purpose - and
    # the other way round, the seats were a hand patch that an add-on reinstall would wipe (BUILD_LOG
    # 436). keep is a set of MODEL names; a named model's patch is a real fix and stays, everything
    # else is put back. A model that is named and turns out to be UNPATCHED stops the build, because
    # that means the keep did nothing and the log would have said it did.
    keep = {k.lower() for k in (keep or ())}
    log("")
    log("7b. Putting the LIVE game files back (this build patched %d of them)" % len(SHADOWED))
    for path, off, bak, was, model in SHADOWED:
        if model.lower() in keep:
            with open(path, "rb") as f:
                f.seek(off)
                got = f.read(len(was))
            if got == was:
                raise SystemExit("%s was named to KEEP but its region is the ORIGINAL - the patch did "
                                 "not land and this build must not claim it did" % model)
            log("KEPT  %s at 0x%x, %d bytes - %s's mesh_points is a real fix and stays "
                "(backup %s)" % (os.path.relpath(path, install), off, len(was), model,
                                 os.path.basename(bak)))
            continue
        with open(bak, "rb") as f:
            want = f.read()
        if want != was:
            raise SystemExit("the backup %s does not hold what we overwrote - stopping" % bak)
        with open(path, "r+b") as f:
            f.seek(off)
            f.write(want)
        with open(path, "rb") as f:
            f.seek(off)
            got = f.read(len(want))
        if got != want:
            raise SystemExit("could not put %s back at 0x%x - STOPPING (backup: %s)"
                             % (os.path.basename(path), off, bak))
        line = "OK  %s restored at 0x%x, %d bytes, and read back identical" % (
            os.path.relpath(path, install), off, len(want))
        known = (pins or {}).get(os.path.basename(path))
        if known:
            with open(path, "rb") as f:
                digest = hashlib.md5(f.read()).hexdigest()
            line += "   whole file md5 %s %s" % (digest[:12],
                                                 "= its pin" if digest == known else
                                                 "*** NOT its known pin %s ***" % known[:12])
        log(line)


def patch_mesh_point(blob, node, axes):
    """Move one node's translation in an AZG2 model. Returns (new blob, report line).

    Only for points whose parents are identity, which is checked by the caller reading the world
    position back. A crew point with no geometry cannot be hidden - the figure is anchored to it - so
    moving it is the only way to put a crewman somewhere else without touching the config.
    """
    out = bytearray(blob)
    tbl = struct.unpack_from("<I", out, MESH_NODE_TABLE)[0]
    cnt = struct.unpack_from("<I", out, MESH_NODE_COUNT)[0]
    mbase = struct.unpack_from("<I", out, MESH_MATRIX_TABLE)[0]
    hit = None
    for i in range(cnt):
        o = tbl + i * MESH_NODE_STRIDE
        if out[o:o + 0x20].split(b"\0")[0].decode("latin1") == node:
            hit = i
            break
    if hit is None:
        raise SystemExit("mesh patch: no node called %s" % node)
    f0 = struct.unpack_from("<i", out, tbl + hit * MESH_NODE_STRIDE + MESH_NODE_FIELDS)[0]
    if f0 == -1:
        raise SystemExit("mesh patch: %s has no matrix of its own" % node)
    mo = mbase + (f0 & 0x7fffffff) * MESH_MATRIX_STRIDE
    said = []
    for ax, val in sorted(axes.items()):
        if ax not in AXIS:
            raise SystemExit("mesh patch: %s is not an axis" % ax)
        at = mo + AXIS[ax] * 4
        was = struct.unpack_from("<f", out, at)[0]
        struct.pack_into("<f", out, at, float(val))
        said.append("%s %.4f -> %.4f" % (ax, was, float(val)))
    return bytes(out), "%s: %s" % (node, ", ".join(said))


def build_techn(install, opstar, vehicles, log, sights=None, gunner_turnout=False):
    # sights: {vehicle: crew_plan's sight plan} - v7 crewable; None builds Operation Star's rows unchanged
    sights = sights or {}
    table, raw = opstar_techn_text(install, opstar, log)
    VEHICLE_NAMES.update(n for n, _ in azcf.vehicles(table))
    parts = [b"//Cfgp2Pd auto converter" + CRLF + CRLF]
    for v in vehicles:
        start = raw.find(CRLF + v.encode() + b"=()" + CRLF)
        end = raw.find(b"} //endof " + v.encode() + CRLF, start)
        if start < 0 or end < 0 or raw.count(CRLF + v.encode() + b"=()" + CRLF) != 1:
            raise SystemExit("techn_base: vehicle %s not found exactly once in the text" % v)
        text = raw[start + 2:end + len(b"} //endof " + v.encode() + CRLF)]
        # ostov_type (the wreck) holds a comma - "tabs\ostovs.cfgpack, gtank_ostov*" - and pd2cfgp cuts every
        # string at a comma, quoted, escaped or not (tested offline 2026-09-17; v1-v3 blanked it, no wreck).
        # So compile a SAME-LENGTH placeholder with "__" for ", " and swap the two bytes back in the compiled
        # table afterwards (tested: one occurrence, 2 bytes, every other field identical).
        m = re.search(rb"\t\tostov_type\[s\]\t= ([^\r\n]*);", text)
        if not m or len(re.findall(rb"\t\tostov_type\[s\]\t= ", text)) != 1:
            raise SystemExit("techn_base: %s has no single ostov_type line" % v)
        value = m.group(1)
        if value.count(b", ") > 1 or b"__" in value:
            raise SystemExit("techn_base: %s ostov_type %r is not the shape the placeholder handles" % (v, value))
        if value.count(b", ") == 1:
            placeholder = value.replace(b", ", b"__")
            text = text[:m.start(1)] + placeholder + text[m.end(1):]
            WRECKS.append((placeholder, value))
        wp_edits = dict(VEHICLES[v].get("wp_edits") or {}) if v in VEHICLES else {}
        eff = dict(VEHICLES.get(v, {}), **OVERRIDE.get(v, {}))
        if v in sights and not (gunner_turnout or eff.get("gunner_turnout")):
            for station, fields in gunner_turnout_edit(table, v).items():
                merged = dict(wp_edits.get(station, {}))
                merged.update(fields)          # int keys, so not dict(a, **b)
                wp_edits[station] = merged
        if v in sights and wp_edits:
            # only for a vehicle being crewed: an AI-only build must stay exactly as it was
            text, wp_lines = edit_work_places_text(text, v, wp_edits)
            WP_REPORT[v] = wp_lines
            WP_PLANNED[v] = wp_edits
        if v in sights:
            text = edit_sights_text(text, v, sights[v])
        parts.append(text + CRLF)
    folder = os.path.join(work_dir(install), "text", TECHN)
    src_txt = os.path.join(folder, TECHN + ".loc_def.engcfg2")
    os.makedirs(folder, exist_ok=True)
    with open(src_txt, "wb") as f:
        f.write(b"".join(parts))
    built = textable.compile_text(install, src_txt, os.path.join(folder, "out", TECHN + ".config"), log)
    # Two vehicles can share one wreck - the Panzer III and the Panzer IV both use gtank_ostov*, and the two
    # Marders share marder_ostov*. The compiled table pools an identical string ONCE, so the swap is done per
    # unique placeholder; doing it per vehicle made the second one look for a string the first had already
    # swapped back, and every build stopped (murkz, 2026-09-22).
    unique = []
    for pair in WRECKS:
        if pair not in unique:
            unique.append(pair)
    for placeholder, value in unique:
        n = built.count(placeholder + b"\0")
        if n < 1:
            raise SystemExit("techn_gtos: wreck placeholder %r found %d times" % (placeholder, n))
        before = built
        built = built.replace(placeholder + b"\0", value + b"\0")
        if len(built) != len(before) or sum(1 for x, y in zip(before, built) if x != y) != 2 * n:
            raise SystemExit("techn_gtos: the wreck swap changed more than %d bytes" % (2 * n))
    del WRECKS[:]
    # read back: every block equal to Operation Star's - the wreck pointer included - except the field
    # letters of EMPTY blocks, which the text route drops, exactly as in BoW43's proven v685
    new = azcf.Table(built)
    report = []
    for v in vehicles:
        count = _vehicle_span(table, v)
        a, b = _block_seq(table, v, count), _block_seq(new, v, count)
        if len(a) != len(b):
            raise SystemExit("%s: %d blocks came back as %d" % (v, len(a), len(b)))
        empties = 0
        for x, y in zip(a, b):
            if x == y:
                continue
            if v in sights and x[0] == y[0] == "sights":
                want = sights[v]["expected"]
                same = y[2] == len(want) and len(y[3]) == len(want) and all(
                    len(g) == len(w) and all(abs(p - q) < 1e-6 if isinstance(q, float) else p == q for p, q in zip(g, w))
                    for g, w in zip(y[3], want))
                if not same:
                    raise SystemExit("%s: sights read %r, expected %r" % (v, y[3], want))
                report.append("  %s sights: %d rows as planned - %s" % (v, len(want), "; ".join(sights[v]["lines"])))
                continue
            if v in sights and x[0] == y[0] == "work_places" and WP_PLANNED.get(v):
                # the planned fields must have changed and NOTHING else - a work_places row carries the
                # crew anchors and the weapon's station, so a stray edit here is silent and serious
                wp = WP_PLANNED[v]        # the branch only runs when edits were applied
                bad = []
                if len(x[3]) != len(y[3]):
                    raise SystemExit("%s: work_places had %d rows, came back %d" % (v, len(x[3]), len(y[3])))
                for ra, rb in zip(x[3], y[3]):
                    # FIELD KEYS ARE STRINGS WHEN THEY COME FROM JSON. This is the FOURTH site with
                    # the same cause - place_groups, derive_playable, edit_work_places_text and now
                    # here - so it is written down once: a wp_edits map read from the settings file
                    # has string field indices, and every consumer must coerce before comparing.
                    # Here f is an int from enumerate(), so "f in want" was False for every planned
                    # field, and a perfectly good edit was reported as UNPLANNED.
                    want = {int(k): w for k, w in (wp.get(ra[0], {}) or {}).items()}
                    for f, (p, q) in enumerate(zip(ra, rb)):
                        if f in want:
                            if str(q) != str(want[f]):
                                bad.append((ra[0], f, "wanted %r, got %r" % (want[f], q)))
                        elif p != q:
                            bad.append((ra[0], f, "unplanned %r -> %r" % (p, q)))
                if bad:
                    raise SystemExit("%s: work_places changed beyond the plan: %r" % (v, bad[:4]))
                report.append("  %s work_places: only the planned fields changed - %s"
                              % (v, "; ".join(WP_REPORT.get(v, []))))
                continue
            if x[0] == y[0] and x[2] == y[2] == 0 and x[3] == y[3]:
                empties += 1
                continue
            raise SystemExit("%s: block %s differs from Operation Star's" % (v, x[0]))
        wreck = [y[3].get("ostov_type") for y in b if y[0] == "props"][0]
        report.append("  %s: %d blocks identical to Operation Star's, wreck %r kept; %d empty blocks "
                      "without field letters (as v685)" % (v, len(a), wreck, empties))
    return built, report


# ---------------------------------------------------------------- div_units_misc (text, rows ADDED)

def _insert_before(lines, end_marker, new_lines, what):
    idx = [i for i, l in enumerate(lines) if l == end_marker]
    if len(idx) != 1:
        raise SystemExit("%s: %r found %d times" % (what, end_marker, len(idx)))
    # stock leaves one blank line before the closing marker
    at = idx[0] - 1 if lines[idx[0] - 1] == b"" else idx[0]
    lines[at:at] = new_lines


def units_rows(opstar_units, spec, v, plan=None):
    """The unit row text for vehicle v. With a crew plan (v7): crewable, its own cockpit, the donor's anims."""
    o = opstar_units[spec["opstar_unit"]]
    crew, second = o[4], o[5]
    tail = b"true, %s, %s" % (plan.cockpit.encode(), plan.anims.encode()) if plan else b"false, , "
    unit = b"\t%s, i_techn, tabs\\%s.cfgpack, %s, %d, %d, 0, 0, 0, 0, , , , , %s;" % (
        spec["unit"].encode(), TECHN.encode(), v.encode(), crew, second, tail)
    return unit


# The one crew table every PROVEN package from v5 to v98 shipped, and whose unit ids (gtu_tank_com,
# gtu_tank_agun, ...) are therefore inside those packages and byte-compared by Check the tool. A second
# crew table must NOT claim the same ids: see crew_rows.
PROVEN_CREW_TABLE = "ger_hum_base"

# EQUIPMENT WE TAKE OFF A CREWMAN, by human block: {what the row says: what it becomes}.
#
# murkz, on v99: "one of the crew in the hull has a large mg on his back, it is stick through the hull
# roof, remove it from that ai". The data says which man and why: rkkau_tank_mgun - the hull
# machine-gunner, the ONE crew unit bound to a weapon station (role wp_mgunner) - is the only Soviet
# crewman whose human carries a MACHINE GUN. Operation Star gives rus_tank_crew2 a DP; his crewmates
# have a PPSH41, a NAGANT and a TT33, all of them small enough to sit on a seated man's back inside a
# T-34. So he takes the ammunition too (762_AP is the DP's), which is why the shells row is edited
# rather than left pointing at a weapon that is no longer there. He keeps a personal weapon - a PPSH41 -
# and stops carrying a machine gun into the roof. The row is replaced BY NAME, so the counts and every
# other field stay Operation Star's, and the build stops if the row is not found exactly once.
CREW_ROW_EDITS = {"rus_tank_crew2": {"DP": "PPSH41", "762_AP": "762_TT"}}


def crew_row_edits(head):
    """{what the row says: what it becomes} for one crew block, winter or summer."""
    return CREW_ROW_EDITS.get(head.replace("_summer", ""), {})


def hum_table_of(pack):
    r"""The crew table a human unit draws on: 'tabs\rus_hum_base.cfgpack' -> 'rus_hum_base'. None when
    it is not a crew table at all.

    THE SECOND HALF OF THE GERMAN-ONLY LIMIT, removed 2026-09-28. crew_rows was made table-driven for
    the UNITS table (div_units_ussr as well as div_units_ger) on 2026-09-23, but it still compared every
    crew unit's cfgpack against the literal tabs\ger_hum_base.cfgpack, so a Soviet crew stopped the
    build and every Soviet vehicle kept the donor T-62 squad - modern tankers in a T-34. The pack the
    row names IS the answer; nothing needs hardcoding."""
    s = pack.decode("latin1") if isinstance(pack, bytes) else str(pack)
    if not s.startswith("tabs\\") or not s.endswith(".cfgpack"):
        return None
    name = s[5:-8]
    return name if name.endswith("_hum_base") else None


def crew_rows(install, opstar, spec, log):
    """The vehicle's OWN crew, cut from whichever Operation Star units table it belongs to. Returns
    {"squad": name, "squad_row": text, "unit_rows": [text], "renames": {opstar unit: ours},
     "opstar_squad": name, "hum_table": the crew table those men come from}.
    Rows are Operation Star's, with our names and our crew table (HUM) - nothing else changed.

    TABLE-DRIVEN since 2026-09-23. It was hardcoded to div_units_ger because the Panzer IV was the
    only vehicle that used it; giving the Soviet tanks their own crews would have sent them looking
    for a Soviet squad in the German table."""
    table = spec["opstar_units_table"]
    raw = opstar_text(install, opstar, table, log)
    lines = raw.split(CRLF)
    tank_squad = [l for l in lines if l.startswith(b"\t" + spec["opstar_squad"].encode() + b", ")]
    if len(tank_squad) != 1:
        raise SystemExit("%s: squad %s found %d times" % (table, spec["opstar_squad"], len(tank_squad)))
    crew_name = tank_squad[0].rstrip(b";").split(b", ")[18].decode()
    crew = [l for l in lines if l.startswith(b"\t" + crew_name.encode() + b", ")]
    if len(crew) != 1:
        raise SystemExit("%s: crew squad %s found %d times" % (table, crew_name, len(crew)))
    cells = crew[0].rstrip(b";").split(b", ")
    if len(cells) != 28 or cells[1] != b"sq_crew":
        raise SystemExit("%s: crew squad %s is not the shape this build knows" % (table, crew_name))
    renames, unit_rows, hum_table = {}, [], None
    for i in (16, 18, 20, 22, 24, 26):
        u = cells[i].strip().decode()
        if not u:
            continue
        row = [l for l in lines if l.startswith(b"\t" + u.encode() + b", ")]
        if len(row) != 1:
            raise SystemExit("%s: unit %s found %d times" % (table, u, len(row)))
        rc = row[0].rstrip(b";").split(b", ")
        hum = hum_table_of(rc[2])
        if rc[1] != b"i_human" or hum is None:
            raise SystemExit("%s: unit %s is not a human of a crew table this build can cut (%r)"
                             % (table, u, rc[:3]))
        if hum_table and hum != hum_table:
            raise SystemExit("%s: crew squad %s draws on TWO human tables, %s and %s"
                             % (table, crew_name, hum_table, hum))
        hum_table = hum
        # THE NAME IS AN ID, AND TWO CREWS CANNOT SHARE ONE. weru_tank_com becomes gtu_tank_com, and
        # rkkau_tank_com would become gtu_tank_com as well - the same four ids for a German and a Soviet
        # crew, in one table, which the "crew units are shared" rule would then emit once and give to
        # both. So a crew from any table but the one every PROVEN package used keeps its own side code:
        # gtu_rkka_tank_com. Found by reading the two squads side by side, before a build, not by murkz
        # seeing a Soviet crewman in a German uniform.
        ours = "gtu_" + u.split("_", 1)[1]            # weru_tank_com -> gtu_tank_com (PROVEN, v5-v98)
        if hum_table != PROVEN_CREW_TABLE:
            ours = "gtu_%s_%s" % (u.split("u_", 1)[0], u.split("_", 1)[1])   # rkkau_tank_com -> gtu_rkka_tank_com
        renames[u] = ours
        cells[i] = ours.encode()
        rc[0], rc[2] = ours.encode(), b"tabs\\%s.cfgpack" % HUM.encode()
        unit_rows.append(b", ".join(rc) + b";")
    cells[0] = spec["crew_squad"].encode()
    return {"squad": spec["crew_squad"], "squad_row": b", ".join(cells) + b";", "unit_rows": unit_rows,
            "renames": renames, "opstar_squad": crew_name, "hum_table": hum_table}


def edit_units(src, plans):
    lines = src.split(CRLF)
    new_units, new_squads = [], []
    _crew_units = {}      # crew unit row by name: two vehicles share one copy
    for v, spec, unit_text, crew in plans:
        donor = [l for l in lines if l.startswith(b"\t" + spec["donor_squad"].encode() + b", ")]
        if len(donor) != 1:
            raise SystemExit("div_units_misc: donor squad %s found %d times" % (spec["donor_squad"], len(donor)))
        cells = donor[0].rstrip(b";").split(b", ")
        if len(cells) != 28:
            raise SystemExit("div_units_misc: squad %s is not the 28-cell shape this build knows" % spec["donor_squad"])
        donor_unit = cells[16]
        cells[0], cells[2], cells[16] = spec["squad"].encode(), spec["squad_text"].encode(), spec["unit"].encode()
        for name in (spec["unit"], spec["squad"]):
            if any(l.startswith(b"\t" + name.encode() + b", ") for l in lines):
                raise SystemExit("div_units_misc: %s already exists" % name)
        new_units.append(unit_text)
        if crew:
            cells[18] = crew["squad"].encode()          # the tank squad's crew: ours, not the T-62's
            for name in [crew["squad"]] + list(crew["renames"].values()):
                if any(l.startswith(b"\t" + name.encode() + b", ") for l in lines):
                    raise SystemExit("div_units_misc: %s already exists" % name)
            # THE CREW UNITS ARE SHARED, and the guard above used to miss it. crew_rows names them
            # after the SOURCE units - weru_tank_com becomes gtu_tank_com - so every German tank that
            # takes its own crew produces the SAME three unit rows. That check only looked at lines
            # already in the table, not at what this build had queued, so a second vehicle appended a
            # duplicate gtu_tank_com and the game had one unit defined twice. It shipped as v40 and
            # murkz's own side shot at his Panzer IIs. Emit each unit ONCE, and refuse if a name ever
            # turns up with different content.
            for _row in crew["unit_rows"]:
                _name = _row.split(b", ")[0].lstrip(b"\t")
                _seen = _crew_units.get(_name)
                if _seen is None:
                    _crew_units[_name] = _row
                    new_units.append(_row)
                elif _seen != _row:
                    raise SystemExit("div_units_misc: crew unit %s is defined two different ways "
                                     "in one build" % _name.decode())
            new_squads.append(crew["squad_row"])
        new_squads.append(b", ".join(cells) + b";")
        spec["_donor_unit"] = donor_unit.decode()
    _insert_before(lines, b"} //endof units", new_units, "div_units_misc")
    _insert_before(lines, b"} //endof squads", new_squads, "div_units_misc")
    return CRLF.join(lines)


def check_units(stock, built, plans, opstar_tables=None, crew_plans=None):
    """Stock plus exactly our rows. With an own crew, its unit and squad rows must equal Operation Star's
    (opstar_tables = {the crew table's name: the compiled units table it came from} - div_units_ger for a
    German crew, div_units_ussr for a Soviet one, and each row is checked against the table ITS MEN come
    from) except our names and our crew table."""
    a, b = build.decoded(azcf.Table(stock)), build.decoded(azcf.Table(built))
    if [x[:2] for x in a] != [x[:2] for x in b]:
        raise SystemExit("div_units_misc: block layout changed")
    ostar = {}
    for table, rec in (opstar_tables or {}).items():
        for name, _, _, rows in build.decoded(azcf.Table(rec)):
            if name in ("units", "squads"):
                ostar.update({(table, name, r[0]): list(r) for r in rows})
    report = []
    for (name, spec_letters, rows, va), (_, _, rows_b, vb) in zip(a, b):
        va, vb = [list(r) for r in va], [list(r) for r in vb]
        if name not in ("units", "squads"):
            if va != vb:
                raise SystemExit("div_units_misc: block %s changed and should not have" % name)
            continue
        want_rows = []
        seen_crew_units = set()
        for v, spec, _, crew in plans:
            if name == "units":
                want_rows.append(("tank", v, spec, crew))
                if crew:
                    # THE CREW UNITS ARE SHARED, and this list did not know it. crew_rows names them
                    # after the SOURCE units - weru_tank_com becomes gtu_tank_com - so EVERY German
                    # tank taking its own crew produces the SAME three rows. edit_units has emitted
                    # each of them once since v40, when a duplicate shipped and murkz's own side shot
                    # at his Panzer IIs. This verifier still counted three PER VEHICLE, so the moment
                    # a second crewed tank existed it demanded rows the build deliberately does not
                    # write: "div_units_misc: units is not stock plus 17 new rows", 2026-09-25.
                    # Count each crew unit once, in the order edit_units emits them.
                    for o in crew["renames"]:
                        if o in seen_crew_units:
                            continue
                        seen_crew_units.add(o)
                        want_rows.append(("crew_unit", o, spec, crew))
            else:
                if crew:
                    want_rows.append(("crew_squad", None, spec, crew))
                want_rows.append(("tank_squad", v, spec, crew))
        added = vb[len(va):]
        if vb[:len(va)] != va or len(added) != len(want_rows):
            raise SystemExit("div_units_misc: %s is not stock plus %d new rows" % (name, len(want_rows)))
        for (kind, key, spec, crew), row in zip(want_rows, added):
            if kind == "tank":
                want = [spec["unit"], "i_techn", "tabs\\%s.cfgpack" % TECHN, key]
                cp = (crew_plans or {}).get(key)
                if cp:
                    if row[:4] != want or row[11] is not True or row[12] != cp.cockpit or row[13] != cp.anims:
                        raise SystemExit("div_units_misc: unit row reads %r" % row)
                    report.append("  unit  %s: %s in %s, crew %s, CREWABLE, cockpit %s, anims %s"
                                  % (row[0], row[3], row[2], row[4], row[12], row[13]))
                    continue
                if row[:4] != want or row[11] is not False or row[12] or row[13]:
                    raise SystemExit("div_units_misc: unit row reads %r" % row)
                report.append("  unit  %s: %s in %s, crew %s, AI-only (not crewable, no cockpit)"
                              % (row[0], row[3], row[2], row[4]))
            elif kind == "crew_unit":
                want = list(ostar[(crew["hum_table"], "units", key)])
                want[0], want[2] = crew["renames"][key], "tabs\\%s.cfgpack" % HUM
                if row != want:
                    raise SystemExit("div_units_misc: crew unit reads %r, expected %r" % (row, want))
                report.append("  unit  %s: Operation Star's %s, human %s in %s" % (row[0], key, row[3], row[2]))
            elif kind == "crew_squad":
                want = list(ostar[(crew["hum_table"], "squads", crew["opstar_squad"])])
                want[0] = crew["squad"]
                want = [crew["renames"].get(c, c) if isinstance(c, str) else c for c in want]
                if row != want:
                    raise SystemExit("div_units_misc: crew squad reads %r, expected %r" % (row, want))
                report.append("  squad %s: Operation Star's %s - %s" % (row[0], crew["opstar_squad"],
                              ", ".join("%s x%d" % (row[i], row[i + 1]) for i in range(10, 22, 2) if row[i])))
            else:
                donor = [r for r in va if r[0] == spec["donor_squad"]][0]
                want = list(donor)
                want[0], want[2], want[10] = spec["squad"], spec["squad_text"], spec["unit"]
                if crew:
                    want[12] = crew["squad"]
                if row != want:
                    raise SystemExit("div_units_misc: squad row reads %r, expected %r" % (row, want))
                report.append("  squad %s: stock %s's shape and costs, crew %s, vehicle %s"
                              % (row[0], spec["donor_squad"], row[12], row[10]))
    report.append("  every stock unit, squad and block reads the same as before")
    return report


# ---------------------------------------------------------------- qbattle (text, blocks ADDED)

def battalion_text(spec):
    n = spec["battalion"].encode()
    return [
        b"\t%s=()" % n, b"\t{",
        b"\t\tcode[u]\t= %d;" % spec["battalion_code"],
        b"\t\tname[s]\t= txt_qb_%s;" % n,
        b"\t\tsold_fams[s]\t= %s;" % spec["sold_fams"].encode(),
        b"\t\tsold_names[s]\t= %s;" % spec["sold_names"].encode(),
        b"\t\tmarks_name[s]\t= %s;" % spec["marks"].encode(),
        b"\t\tdiv_sprite[s]\t= div_tanks;",
        b"\t\tdiv_sprite_op[s]\t= divh_batn;",
        b"\t\tside[*]\t= %s;" % spec["side"].encode(),
        b"", b"\t\tpool[suus]()", b"\t\t{",
        b"\t\t\t%s, %d, 0, ;" % (spec["squad"].encode(), spec["max_squads"]),
        b"", b"\t\t} //endof pool", b"", b"\t} //endof %s" % n, b""]


def platoon_text(spec):
    n = spec["platoon"].encode()
    return [
        b"\t%s=()" % n, b"\t{",
        b"\t\tcode[u]\t= %d;" % spec["platoon_code"],
        b"\t\tname[s]\t= txt_qb_pl_%s;" % n,
        b"\t\tstr_sprite[s]\t= pl_tank_t62;",
        b"\t\tmax_squads[u]\t= %d;" % spec["max_squads"],
        b"\t\tmobility[*]\t= PIL;",
        b"\t\tpool[s]\t= %s;" % spec["battalion"].encode(),
        b"\t\ttype[*]\t= STR;",
        b"\t\tuid[u]\t= 0x%08x;" % spec["uid"],
        b"\t\tuser_in[b]\t= %s;" % (b"true" if spec["user_in"] else b"false"),
        b"\t\tcamo[s]\t= %s;" % spec["camo"].encode(),
        b"", b"\t\tpool[sus]()", b"\t\t{",
        b"\t\t\t%s, %d, ;" % (spec["squad"].encode(), spec["max_squads"]),
        b"", b"\t\t} //endof pool", b"", b"\t} //endof %s" % n, b""]


def edit_qbattle(src, plans):
    lines = src.split(CRLF)
    text = src
    codes = {int(x) for x in re.findall(rb"\tcode\[u\]\t= (\d+);", text)}
    uids = {int(x, 16) for x in re.findall(rb"\tuid\[u\]\t= 0x([0-9a-fA-F]+);", text)}
    bats, plats = [], []
    for v, spec in plans:
        for name in (spec["battalion"], spec["platoon"]):
            if (b"\t" + name.encode() + b"=()") in lines:
                raise SystemExit("qbattle: %s already exists" % name)
        for code in (spec["battalion_code"], spec["platoon_code"]):
            if code in codes:
                raise SystemExit("qbattle: code %d is already used" % code)
        if spec["uid"] in uids:
            raise SystemExit("qbattle: uid 0x%08x is already used" % spec["uid"])
        bats += battalion_text(spec)
        plats += platoon_text(spec)
    _insert_before(lines, b"} //endof reserves", bats, "qbattle")
    _insert_before(lines, b"} //endof act_platoons", plats, "qbattle")
    return CRLF.join(lines)


def check_qbattle(stock, built, plans):
    """Stock (with the proven duplicate renames) plus exactly our battalion and platoon blocks."""
    a, b = build.decoded(azcf.Table(stock)), build.decoded(azcf.Table(built))
    ours = set()
    for v, spec in plans:
        ours.update({spec["battalion"], spec["platoon"]})
    # drop our blocks and the pool sub-block right after each
    kept, added, skip = [], {}, False
    for x in b:
        if x[0] in ours:
            added[x[0]] = [x]
            skip = x[0]
            continue
        if skip and x[0] == "pool":
            added[skip].append(x)
            skip = False
            continue
        skip = False
        kept.append(x)
    if sorted(added) != sorted(ours):
        raise SystemExit("qbattle: new blocks found %s, expected %s" % (sorted(added), sorted(ours)))
    counts = {}
    for x in a:
        counts[x[0]] = counts.get(x[0], 0) + 1
    if len(kept) != len(a):
        raise SystemExit("qbattle: %d stock blocks came back as %d" % (len(a), len(kept)))
    for x, y in zip(a, kept):
        if x != y and not (y[0] == x[0] + "_2" and counts[x[0]] > 1 and x[1:] == y[1:]):
            raise SystemExit("qbattle: stock block %s changed" % x[0])
    report = []
    for v, spec in plans:
        bat, plat = added[spec["battalion"]], added[spec["platoon"]]
        bp, pp = bat[0][3], plat[0][3]
        want_bp = {"side": SIDES[spec["side"]][0], "code": spec["battalion_code"], "sold_fams": spec["sold_fams"],
                   "sold_names": spec["sold_names"], "marks_name": spec["marks"]}
        if any(bp.get(k) != val for k, val in want_bp.items()):
            raise SystemExit("qbattle: battalion %s reads %r" % (spec["battalion"], bp))
        if pp.get("pool") != spec["battalion"] or pp.get("user_in") is not spec["user_in"] or pp.get("uid") != spec["uid"]:
            raise SystemExit("qbattle: platoon %s reads %r" % (spec["platoon"], pp))
        if len(bat) != 2 or len(plat) != 2 or bat[1][3][0][0] != spec["squad"] or plat[1][3][0][0] != spec["squad"]:
            raise SystemExit("qbattle: the pools of %s do not list %s" % (v, spec["squad"]))
        report.append("  battalion %s: side %s, code %d, names %s, marks %s, pool %s" % (
            spec["battalion"], spec["side"], bp["code"], bp["sold_fams"], bp["marks_name"], bat[1][3][0]))
        report.append("  platoon %s: code %d, uid 0x%08x, user_in %s, pool %s" % (
            spec["platoon"], pp["code"], pp["uid"], str(pp["user_in"]).lower(), plat[1][3][0]))
    report.append("  every stock block reads the same as before (duplicate copies renamed as proven)")
    return report


# ---------------------------------------------------------------- common_res: the German gate

def patch_ger_gate(stock):
    """v1-v9 name for the German gate alone."""
    return patch_side_gates(stock, ["GER"])


def patch_side_gates(stock, sides):
    """One byte per side: sides[] field[11] (the quick-battle gate) -> 2. GER 1 -> 2 (v1), FR 0 -> 2 (v10, the
    slot BoW43 made "USSR 1943"). common_res cannot round-trip (BoW43 notes/44 4c: its comma strings split -
    BoW43's shipped table has 7 broken expl_snds rows from exactly that), so it is patched in the compiled table,
    with every side row read before and after."""
    t = azcf.Table(stock)
    blk = t.find("sides")
    if len(blk) != 1:
        raise SystemExit("common_res: expected one sides block, found %d" % len(blk))
    b = blk[0]
    if len(b.spec) != 14 or any(c in "va" for c in b.spec):
        raise SystemExit("common_res: sides block is not the shape this patch knows (%r)" % b.spec)
    before = t.rows(b)
    data = bytearray(stock)
    done, report = [], []
    for side in sides:
        token, name, gate = SIDES[side]
        idx = [i for i, r in enumerate(before) if r[0] == token]
        if len(idx) != 1:
            raise SystemExit("common_res: %s side found %d times" % (side, len(idx)))
        row = before[idx[0]]
        if row[1] != name or row[SIDES_GATE] not in (gate, 2):
            raise SystemExit("common_res: %s row reads %r" % (side, row))
        if row[SIDES_GATE] == 2:
            report.append("  common_res: %s already at 2 - unchanged" % side)
            continue
        at = b.data_ptr + idx[0] * len(b.spec) * 32 + SIDES_GATE * 32
        if data[at:at + 4] != gate.to_bytes(4, "little"):
            raise SystemExit("common_res: the %s gate cell at %d does not hold %d" % (side, at, gate))
        data[at:at + 4] = (2).to_bytes(4, "little")
        done.append((idx[0], side, gate))
    if not done:
        return stock, report
    patched = bytes(data)
    after = azcf.Table(patched).rows(azcf.Table(patched).find("sides")[0])
    changed_rows = {i for i, s, g in done}
    for i, (x, y) in enumerate(zip(before, after)):
        want = list(x)
        if i in changed_rows:
            want[SIDES_GATE] = 2
        if list(y) != want:
            raise SystemExit("common_res: side row %d reads wrong after the patch" % i)
    changed = sum(1 for p, q in zip(stock, patched) if p != q)
    if changed != len(done) or len(patched) != len(stock):
        raise SystemExit("common_res: %d bytes changed, expected exactly %d" % (changed, len(done)))
    gates = ", ".join("%s=%d" % (r[1].replace("txt_side_", ""), r[SIDES_GATE]) for r in after)
    what = " and ".join("%s gate %d -> 2" % (s, g) for i, s, g in done)
    report.append("  common_res: quick-battle %s, exactly %d byte%s; all %d side rows read back: %s"
                  % (what, len(done), "" if len(done) == 1 else "s", len(after), gates))
    return patched, report


def build_common_res(install, sides, repaint, log):
    """v11: common_res through the TEXT route, so a repainted side can carry a new name id. The table has 7 strings
    holding ", " (expl_snds: 'expl_gndl*, cols' ...) that pd2cfgp splits - BoW43 shipped exactly that damage. So
    those rows are rewritten from the stock values with a same-length "__" placeholder, compiled, and the bytes
    swapped back. Gate: that route with NO edit must give stock byte for byte (measured 2026-09-17: md5 0b80ef90).
    Then the edit: every side in `sides` gate -> 2, and each repainted side's row = its `like` row except token,
    name and gate. Checked: every block reads as stock except those rows. Returns (compiled, report)."""
    folder = os.path.join(work_dir(install), "text", "common_res")
    stock, fixed = textable.decompile(install, "common_res", folder, log)
    t = azcf.Table(stock)
    with open(fixed, "rb") as f:
        lines = f.read().split(CRLF)
    s = [i for i, l in enumerate(lines) if l.startswith(b"expl_snds[")]
    e = [i for i, l in enumerate(lines) if l == b"} //endof expl_snds"]
    blk = t.find("expl_snds")
    if len(s) != 1 or len(e) != 1 or len(blk) != 1:
        raise SystemExit("common_res: expl_snds not found once")
    rows = t.rows(blk[0])
    body = [i for i in range(s[0] + 2, e[0]) if lines[i].strip()]
    if len(body) != len(rows):
        raise SystemExit("common_res: expl_snds has %d text rows, %d compiled" % (len(body), len(rows)))
    swaps = set()
    for i, r in zip(body, rows):
        cells = [lines[i].strip().split(b",")[0]]
        for c in r[1:]:
            if "__" in c:
                raise SystemExit("common_res: %r already holds the placeholder" % c)
            if ", " in c:
                swaps.add(c)
            cells.append(c.replace(", ", "__").encode())
        lines[i] = b"\t" + b", ".join(cells) + b";"

    def compile_swapped(text_lines, sub):
        src = os.path.join(folder, sub, "common_res.loc_def.engcfg2")
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src, "wb") as f:
            f.write(CRLF.join(text_lines))
        out = textable.compile_text(install, src, os.path.join(folder, sub, "out", "common_res.config"), log)
        for c in sorted(swaps):
            ph = c.replace(", ", "__").encode() + b"\0"
            if out.count(ph) != 1:
                raise SystemExit("common_res: placeholder %r found %d times" % (ph, out.count(ph)))
            out = out.replace(ph, c.encode() + b"\0")
        return out
    gate = compile_swapped(lines, "gate")
    if gate != stock:
        raise SystemExit("common_res: the placeholder route does not give stock back - do not build from it")
    report = ["  common_res: text route with %d placeholder strings compiles back to stock byte for byte (md5 %s)"
              % (len(swaps), hashlib.md5(stock).hexdigest())]

    # the edit, on the text of the sides rows
    sb = t.find("sides")[0]
    srows = t.rows(sb)
    by_token = {r[0]: i for i, r in enumerate(srows)}
    ss = [i for i, l in enumerate(lines) if l.startswith(b"sides[")]
    se = [i for i, l in enumerate(lines) if l == b"} //endof sides"]
    sbody = [i for i in range(ss[0] + 2, se[0]) if lines[i].strip()]
    if len(sbody) != len(srows):
        raise SystemExit("common_res: sides has %d text rows, %d compiled" % (len(sbody), len(srows)))
    text_rows = [lines[i].strip().rstrip(b";").split(b", ") for i in sbody]
    if any(len(r) != 14 for r in text_rows):
        raise SystemExit("common_res: a sides text row is not 14 cells")
    want = [list(r) for r in srows]
    for side in sides:
        token, name, stock_gate = SIDES[side]
        i = by_token[token]
        if srows[i][1] != name or srows[i][SIDES_GATE] != stock_gate:
            raise SystemExit("common_res: %s row reads %r" % (side, srows[i]))
        cells = text_rows[i]
        if side in repaint:
            like = by_token[repaint[side]["like"]]
            cells = [cells[0], repaint[side]["name"].encode()] + text_rows[like][2:]
            want[i] = [token, repaint[side]["name"]] + list(srows[like][2:])
        cells[SIDES_GATE] = b"2"
        want[i][SIDES_GATE] = 2
        lines[sbody[i]] = b"\t" + b", ".join(cells) + b";"
    built = compile_swapped(lines, "edited")
    a, b = build.decoded(t), build.decoded(azcf.Table(built))
    if [x[:3] for x in a] != [x[:3] for x in b]:
        raise SystemExit("common_res: block layout changed")
    for x, y in zip(a, b):
        if x[0] == "sides":
            if [list(r) for r in y[3]] != want:
                bad = [i for i, (g, w) in enumerate(zip(y[3], want)) if list(g) != w]
                raise SystemExit("common_res: side rows %s read %r" % (bad, [y[3][i] for i in bad]))
        elif x != y:
            raise SystemExit("common_res: block %s changed and should not have" % x[0])
    for side in sides:
        r = want[by_token[SIDES[side][0]]]
        report.append("  common_res: %s gate %d -> 2%s" % (side, SIDES[side][2], "" if side not in repaint else
                      ", repainted as %s: name %s, %s" % (srows[by_token[repaint[side]["like"]]][1], r[1],
                                                          ", ".join(str(v) for v in r[2:] if v not in ("", 2)))))
    report.append("  common_res: every other block and side row reads the same as stock (%d bytes, stock %d)"
                  % (len(built), len(stock)))
    return built, report


# ---------------------------------------------------------------- names (the add-on's own text)

def read_names(text_flatdata):
    """{text id: text} from an AZTX text archive; multi-line entries joined with ' / '."""
    import ammotext
    out = {}
    for key, e in gtos_opstar.directory(text_flatdata).items():
        blob = gtos_opstar.read(text_flatdata, e)
        for off, name, cnt, ptr in ammotext.entries(blob):
            out[name] = " / ".join(t.decode("cp1251") for _, _, t in ammotext.lines_of(blob, ptr, cnt))
    return out


def build_names(install, work, plans, log, extra=None):
    """Our platoon and battalion names (and, from v11, `extra` ids such as a repainted side's name), compiled by
    the game's pd2text (BoW43's proven route) and packed as a loc_eng text record.
    Returns (archive path, {id: text} expected)."""
    names = dict(extra or {})
    for v, spec in plans:
        names["txt_qb_pl_" + spec["platoon"]] = spec["platoon_name"]
        names["txt_qb_" + spec["battalion"]] = spec["battalion_name"]
    folder = os.path.join(work, "text", "names")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    src = os.path.join(folder, ADDON + "_text.loc_eng.engcfg2")
    body = ["// %s - platoon and battalion names" % ADDON, "", "loc_eng()", "{"]
    for k in sorted(names):
        if any(c in names[k] for c in ";{}\\"):
            raise SystemExit("name %r holds a character the text compiler treats specially" % names[k])
        body.append("\t%s[s]() { %s; }" % (k, names[k]))
    body += ["} // endof loc_eng", ""]
    with open(src, "wb") as f:
        f.write("\r\n".join(body).encode("cp1251"))
    out = os.path.join(folder, ADDON + "_text.loc_eng.text")
    import subprocess
    subprocess.run([os.path.join(install, "starter.exe"), "pd2text,", build.rel(src, install)], cwd=install, timeout=120)
    if not os.path.isfile(out):
        raise SystemExit("pd2text produced no %s" % out)
    with open(out, "rb") as f:
        blob = f.read()
    tflat = os.path.join(work, "CORE", "loc_eng", "packed_data", ADDON + "_text.flatdata")
    os.makedirs(os.path.dirname(tflat), exist_ok=True)
    gtos_opstar._mkflat([(ADDON + "_text", "text", "loc_eng", blob)], tflat, install, os.path.join(work, "pack"), log)
    got = read_names(tflat)
    if got != names:
        raise SystemExit("compiled names read %r, expected %r" % (got, names))
    log("OK  names compiled and read back: %d" % len(got))
    return tflat, names


# ---------------------------------------------------------------- the build

def vehicle_tokens(opstar, vehicles):
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
    cr = azcf.Table(gtos_opstar.read(*src.records[("common_res_mod", "config")]))
    tokens = set()

    def grab(v):
        if isinstance(v, str):
            tokens.update(re.findall(r"[A-Za-z0-9_]{3,48}", v))
        elif isinstance(v, (list, tuple)):
            [grab(x) for x in v]
        elif isinstance(v, dict):
            [grab(x) for x in v.values()]
    rows = {bn: {r[0]: r for r in cr.rows(cr.find(bn)[0])} for bn in ("weapons", "tracks")}
    for v in vehicles:
        blocks = dict(azcf.vehicles(tb))[v]
        for bn, b in blocks.items():
            vals = tb.props(b) if bn == "props" else tb.rows(b)
            grab(vals)
            if bn == "weapons":
                for r in vals:
                    grab(rows["weapons"].get(r[0]))
            if bn == "cpillars":
                for r in vals:
                    grab(rows["tracks"].get(r[0]))
    return tokens


def opstar_units(opstar, tables=("div_units_ger",)):
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    out = {}
    for name in tables:
        t = azcf.Table(gtos_opstar.read(*src.records[(name, "config")]))
        for b in t.blocks:
            if b.name == "units":
                for r in t.rows(b):
                    if r[0] in out:
                        raise SystemExit("Operation Star unit %s is in more than one table" % r[0])
                    out[r[0]] = r
    return out


ZIP_TIME = (2026, 9, 17, 0, 0, 0)    # every zip member gets this date, so the same build gives the same md5


def _zip_add(z, path, member):
    info = zipfile.ZipInfo(member, date_time=ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    with open(path, "rb") as f:
        z.writestr(info, f.read())


def build_ai(version, install, opstar=gtos_opstar.OPSTAR, vehicles=("pz4f2",), log=print, zip_path=None,
             german_crew=True, german_voices=True, crewable=True, gunner_sight=None,
             repaint_sides=True, gunner_turnout=False, mesh_points=None, gunner_hatch=None,
             sight_stubs=None, extra_sights=None, other_sights=None, spec_over=None,
             keep_mesh_points=False, own_assets=None):
    # keep_mesh_points: False (the default) puts every LIVE game file this build patched back, and
    # reads it back to be sure - see restore_shadowed_models(). True is for the ONE build that ships
    # the Panzer III camera fix the patch exists for, and says so in the log. It is a parameter rather
    # than a hand step because a hand step is what a window-run build forgets (measured 2026-09-28).
    # gunner_hatch: None = each vehicle's own. False pins it off, which is what v26 needs - it shipped
    # before the state row existed.
    # mesh_points: None = each vehicle's own (VEHICLES[v]["mesh_points"]). A dict here REPLACES them
    # for the whole build, which is how a PROVEN entry pins the points its build actually shipped -
    # later tuning of the same vehicle would otherwise make its rebuild differ.
    # gunner_turnout: False (the default from v21) blanks a crewable vehicle's gunner out-position so it
    # matches the stock T-62, which has none. True keeps whatever the vehicle declares - what v7-v19
    # shipped, and what made the gunner's outside view 001.
    # crewable: True = every vehicle flagged crewable, False = none, or a tuple naming which ones. The tuple
    # exists because a vehicle gaining the flag later would otherwise join every earlier PROVEN build's
    # rebuild and break Check the tool - v7 onward name ("pz4f2",) for exactly that reason.
    # spec_over: {vehicle: {field: value}} - the GENERIC pin, and the one that should have existed
    # first. gunner_sight, sight_stubs, extra_sights and other_sights each got their own parameter
    # because each was discovered separately, and own_crew would have been the fifth. A PROVEN entry
    # has to be able to pin ANY spec field a later build can move; naming them one at a time only
    # works while somebody keeps noticing. Use this for anything new.
    # sight_stubs: None = each vehicle's own. A DICT {vehicle: tuple} pins which of a vehicle's sight rows
    # get repointed, and a PROVEN entry needs it for the same reason gunner_sight does - the derived rule
    # can change, and then an old build would rebuild with a different set of rows. Added 2026-09-23.
    # own_assets: None = the module's OWN_ASSETS. A list here REPLACES it for this build, so a
    # PROVEN entry can pin exactly which authored records it shipped - as spec_over does.
    # gunner_sight: None = each vehicle's own (VEHICLES[v]["gunner_sight"], else GUNNER_SIGHT). A value here
    # overrides every crewable vehicle, which is what the PROVEN entries rely on.
    if os.path.normcase(os.path.normpath(install)) == os.path.normcase(os.path.normpath(build.INSTALL)):
        raise SystemExit("refusing to build into the live game (%s) - use the fresh install" % install)
    ok, msg = azcf.self_test(build.tabs_path(install))
    if not ok:
        raise SystemExit("table reader check failed: " + msg)
    log("OK  " + msg)
    OVERRIDE.clear()     # per-build only; see the note on OVERRIDE
    del SHADOWED[:]      # per-build only: what THIS build patched outside the add-on, so the end of
                         # the build can put exactly those files back (restore_shadowed_models)
    EFFECTIVE_SPECS.clear()
    WP_REPORT.clear()
    WP_PLANNED.clear()
    work = work_dir(install)
    os.makedirs(work, exist_ok=True)

    for v in vehicles:
        if v not in VEHICLES:
            raise SystemExit("the tool has no settings for %s" % v)
    # the build options switch features OFF (Check the tool rebuilds v4-v9 with them); a vehicle's own settings
    # say whether it has the feature at all (v10: the T-34 has no own crew and is not crewable)
    if isinstance(crewable, (tuple, list, set)):
        to_crew = [v for v in vehicles if v in crewable and VEHICLES[v].get("crewable")]
        unknown = [v for v in crewable if v not in vehicles]
        if unknown:
            raise SystemExit("crewable names %s, which this build does not include" % ", ".join(unknown))
    else:
        to_crew = [v for v in vehicles if crewable and VEHICLES[v].get("crewable")]
    crew_plans, sight_plans, sight_of = {}, {}, {}
    if to_crew:
        log("")
        log("0. The crew recipe (SABoW Ext's, run on %s)" % ", ".join(to_crew))
        for v in to_crew:
            if gunner_hatch is not None and not gunner_hatch:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), gunner_hatch=False, sync_add={},
                                   gunner_turnout=False)
            # gunner_sight may be a NAME (build-wide, the old shape) or a DICT {vehicle: name}.
            # The dict exists because a PROVEN build can no longer be reproduced once a vehicle's own
            # sight moves on - v29 and v30 differ ONLY in the T-34's reticle, and with three crewable
            # tanks a single build-wide name cannot pin them separately. Found 2026-09-23, before Check
            # the tool was run against it; see the PROVEN rows for v29 and v32.
            # extra_sights: None = each vehicle's own; a DICT {vehicle: map} pins it, and a PROVEN
            # entry needs that for the same reason gunner_sight and sight_stubs do.
            if spec_over and v in spec_over:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), **spec_over[v])
            if other_sights is not None and v in other_sights:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), other_sights=other_sights[v])
            if extra_sights is not None and v in extra_sights:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), extra_sights=extra_sights[v])
            if sight_stubs and v in sight_stubs:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), sight_stubs=tuple(sight_stubs[v]))
            if isinstance(gunner_sight, dict):
                sight_of[v] = gunner_sight.get(v) or VEHICLES[v].get("gunner_sight") or GUNNER_SIGHT
            else:
                sight_of[v] = gunner_sight or VEHICLES[v].get("gunner_sight") or GUNNER_SIGHT
            EFFECTIVE_SPECS[v] = dict(VEHICLES[v], **OVERRIDE.get(v, {}))
            crew_plans[v], sight_plans[v] = crew_plan(install, opstar, v, sight_of[v])
            for line in crew_plans[v].report().split("\n"):
                log("    " + line)
            for line in sight_plans[v]["lines"]:
                log("    sights     " + line)

    # ---- THE PINS, FOR EVERY VEHICLE IN THIS BUILD, AND THEN WHO TAKES HIS OWN CREW ------------------
    # spec_over is the generic pin a PROVEN entry freezes a field with. It used to be applied only
    # inside the crewable loop above, so a pin written for a vehicle this build does NOT crew - and the
    # v13-v40 entries pin kv1_42_uztm, t70m and others exactly so - was written and never applied. It
    # is applied here instead, for every vehicle, and before anything reads an effective spec. The
    # crewable loop still applies its own pins as it did, so nothing about a crewable vehicle changes.
    if spec_over:
        for v in vehicles:
            if v in spec_over:
                OVERRIDE[v] = dict(OVERRIDE.get(v, {}), **spec_over[v])
    # own_crew is read from the EFFECTIVE spec for the same reason: it is what those pins are for.
    # A spec may say own_crew True and leave the two names the path needs to the tool; they are read
    # from Operation Star here, so that turning the flag on can never be the KeyError 'opstar_squad'
    # that stopped the v40 build.
    for v in vehicles:
        eff = dict(VEHICLES[v], **OVERRIDE.get(v, {}))
        if eff.get("own_crew") and not eff.get("opstar_squad"):
            men, squad = opstar_crew_men(v, eff, opstar)
            if not squad:
                raise SystemExit("%s: own_crew is on, but Operation Star fields no squad with a crew "
                                 "for it" % v)
            OVERRIDE[v] = dict(OVERRIDE.get(v, {}), opstar_squad=squad,
                               crew_squad=OVERRIDE.get(v, {}).get("crew_squad") or ("gt_crew_" + v))
    own_crew = [v for v in vehicles if german_crew and dict(VEHICLES[v], **OVERRIDE.get(v, {})).get("own_crew")]
    if own_crew:
        log("")
        log("   own crews: %s" % ", ".join(own_crew))

    log("")
    log("1. The vehicle table (%s)" % TECHN)
    techn, report = build_techn(install, opstar, vehicles, log, sights=sight_plans,
                                gunner_turnout=gunner_turnout)
    for line in report:
        log("OK" + line)

    log("")
    log("2. Units and squads (div_units_misc)")
    ou = opstar_units(opstar, sorted({VEHICLES[v]["opstar_units_table"] for v in vehicles}))
    plans = [(v, VEHICLES[v], units_rows(ou, VEHICLES[v], v, crew_plans.get(v)),
              # the EFFECTIVE spec: the crew path needs the squad names, and a spec that says
              # own_crew without them has just had them derived into OVERRIDE (v99)
              crew_rows(install, opstar, dict(VEHICLES[v], **OVERRIDE.get(v, {})), log)
              if v in own_crew else None) for v in vehicles]
    folder = os.path.join(work, "text", "div_units_misc")
    fixed = textable.round_trip(install, "div_units_misc", folder, log)
    with open(fixed, "rb") as f:
        edited_text = edit_units(f.read(), plans)
    edited = os.path.join(folder, "edited", "div_units_misc.loc_def.engcfg2")
    os.makedirs(os.path.dirname(edited), exist_ok=True)
    with open(edited, "wb") as f:
        f.write(edited_text)
    units = textable.compile_text(install, edited, os.path.join(folder, "edited", "div_units_misc.config"), log)
    # each crew is checked against the Operation Star units table ITS OWN rows were cut from:
    # a German crew from div_units_ger, a Soviet one from div_units_ussr (keyed by the crew table)
    ostar_src = {}
    for v, s, u, crew in plans:
        if not crew:
            continue
        old = ostar_src.setdefault(crew["hum_table"], s["opstar_units_table"])
        if old != s["opstar_units_table"]:
            raise SystemExit("%s and another vehicle share the crew table %s but come from %s and %s"
                             % (v, crew["hum_table"], old, s["opstar_units_table"]))
    for line in check_units(azcf.read_record(build.tabs_path(install), "div_units_misc"), units, plans,
                            {t: opstar_record(opstar, n) for t, n in ostar_src.items()} if own_crew else None,
                            crew_plans):
        log("OK" + line)

    log("")
    log("3. Battalion and platoon (qbattle)")
    # crewable: the platoon's user_in flag on - it is what lists the platoon as one the player can crew
    qplans = [(v, dict(VEHICLES[v], user_in=True) if v in crew_plans else VEHICLES[v]) for v in vehicles]
    folder = os.path.join(work, "text", "qbattle")
    fixed = textable.round_trip(install, "qbattle", folder, log, accept=build.qbattle_renames_only)
    with open(fixed, "rb") as f:
        edited_text = edit_qbattle(f.read(), qplans)
    edited = os.path.join(folder, "edited", "qbattle.loc_def.engcfg2")
    os.makedirs(os.path.dirname(edited), exist_ok=True)
    with open(edited, "wb") as f:
        f.write(edited_text)
    qb = textable.compile_text(install, edited, os.path.join(folder, "edited", "qbattle.config"), log)
    for line in check_qbattle(azcf.read_record(build.tabs_path(install), "qbattle"), qb, qplans):
        log("OK" + line)

    log("")
    sides = [s for s in SIDES if any(VEHICLES[v]["side"] == s for v in vehicles)]
    repaint = {s: REPAINT[s] for s in sides if repaint_sides and s in REPAINT}
    side_names = {r["name"]: r["text"] for r in repaint.values()}
    if repaint:
        log("4. The sides (common_res): gates %s, %s repainted - text route with placeholders" % (
            ", ".join(sides), ", ".join(repaint)))
        common_res, report = build_common_res(install, sides, repaint, log)
    else:
        log("4. The quick-battle gate (common_res): %s" % ", ".join(sides))
        common_res, report = patch_side_gates(azcf.read_record(build.tabs_path(install), "common_res"), sides)
    for line in report:
        log("OK" + line)

    log("")
    crew_tables, crew_tokens, voices = [], set(), []
    if own_crew:
        # who comes from which crew table: a German crew from ger_hum_base, a Soviet one from
        # rus_hum_base, both cut into the one hum_gtos/bodys_gtos this add-on ships (v99)
        by_table = {}
        for v, s, u, crew in plans:
            if not crew:
                continue
            for row in crew["unit_rows"]:
                by_table.setdefault(crew["hum_table"], set()).add(row.split(b", ")[3].decode())
        log("4b. The crews: %s (%s, %s)" % (
            ", ".join("%s %d men for %s" % (t, len(n), ", ".join(sorted(
                v for v, s, u, c in plans if c and c["hum_table"] == t))) for t, n in sorted(by_table.items())),
            HUM, BODYS))
        hum, bodys, report, crew_tokens = build_crew_tables(install, opstar, by_table, log)
        for line in report:
            log("OK" + line)
        crew_tables = [(HUM, hum), (BODYS, bodys)]
        if german_voices:
            voices, report = crew_voices(install, opstar, by_table)
            for line in report:
                log("OK" + line)
        log("")
    log("5. Files from Operation Star - only what SABoW lacks, with seasonal textures")
    res = gtos_opstar.resolve([], install, opstar, log, seed_tokens=vehicle_tokens(opstar, vehicles) | crew_tokens,
                              season_variants=True)
    log("    %s" % gtos_opstar.summary(res))
    for p, e in res["borrow"]:
        log("    %-8s %s" % (e[3], e[0]))
    if voices:
        # v6: the crew's voice lines, added after the followed files so v5 and earlier rebuild unchanged
        taken = {(e[0].lower(), e[3]) for p, e in res["borrow"]}
        extra = [(p, e) for p, e in voices if (e[0].lower(), e[3]) not in taken]
        res["borrow"] = res["borrow"] + extra
        log("    + %d German voice lines (%.1f MB)" % (len(extra), sum(e[2] for p, e in extra) / 1e6))

    cockpit_tables = []
    if crew_plans:
        log("")
        log("5b. The cockpits (cocpits) and the gunner sights (common_res_mod)")
        cocpits, report = build_crew_cockpits(install, crew_plans, log)
        for line in report:
            log("OK" + line)
        # murkz's rule keeps this cheap: a vehicle with no hand-drawn reticle points at the STOCK tsh2b row
        # and adds nothing, so only a vehicle that HAS one costs a common_res_mod row.
        needs_row = [v for v in to_crew if not GUNNER_SIGHTS[sight_of[v]].get("stock")]
        # A vehicle's extra per-stub sights each need their own row too - the Matilda ships the
        # No. 24B AND the MK-4, which is only possible because the route writes N rows.
        extra_keys = []
        for v in to_crew:
            eff = dict(VEHICLES[v], **OVERRIDE.get(v, {}))
            # vision_blocks belongs in this list: it names a sight key the same way the other two do, and
            # when it was left out the row was never shipped - v84 pointed the T-34's slits at a row that
            # did not exist, which the record-by-record comparison against v83 caught (slit_g missing from
            # common_res_mod). ANY NEW FIELD THAT NAMES A SIGHT KEY MUST BE ADDED HERE.
            # BEWARE THE PRECEDENCE: "A if C else [] + B" parses as "A if C else ([] + B)", so the first
            # version of this line dropped extra_sights and other_sights whenever vision_blocks was set -
            # and v85 shipped 311 records instead of 312 because the T-34's pt4_7_g row vanished. The list
            # is built first, then concatenated.
            # v94: THE FLEET DEFAULT COUNTS TOO. This read only the VEHICLE's own entry, so the moment no
            # vehicle listed the build-wide VISION_BLOCKS the rows it names stopped being shipped - while
            # the planner, which has always defaulted to VISION_BLOCKS, went on pointing the tanks at them.
            # v92 lost drv_slit_g that way (the T-34's stale string still supplied slit_g) and v93 lost both
            # when that string went. The vehicle table POINTS AT a row by name: a row that is named and not
            # shipped is not a missing mask, it is nothing to look through at all - which is exactly what
            # murkz saw ("no driver view at all"). The shipment list and the planner must read the same rule.
            _vb = eff.get("vision_blocks", VISION_BLOCKS)
            vb_keys = (list(_vb.values()) if isinstance(_vb, dict) else [_vb]) if _vb else []
            for key in (vb_keys
                        + list((eff.get("extra_sights") or {}).values())
                        + list((eff.get("other_sights") or {}).values())):
                if key not in extra_keys and not GUNNER_SIGHTS[key].get("stock"):
                    extra_keys.append(key)
        for v in to_crew:
            if GUNNER_SIGHTS[sight_of[v]].get("stock"):
                log("OK  %s gunner sight: %s - nothing added" % (v, GUNNER_SIGHTS[sight_of[v]]["label"]))
        # Grown 2026-09-22: was "one vehicle may have its own reticle", and it stopped the v29 build dead
        # when the T-34 gained its TMFD-7 beside the Panzer IV's TZF 5f. build_sight_alias now writes a row
        # per sight, deduped, so the only remaining rule is the useful one - a vehicle on the stock tsh2b
        # costs nothing at all.
        crm = None
        if needs_row or extra_keys:
            crm, report, sight_meshes = build_sight_alias(
                install, log, [sight_of[v] for v in needs_row] + extra_keys)
            for line in report:
                log("OK" + line)
            cockpit_tables = [("cocpits", cocpits), ("common_res_mod", crm)]
        else:
            sight_meshes = []
            cockpit_tables = [("cocpits", cocpits)]
        # THE CHECK THAT WOULD HAVE CAUGHT v92 AND v93. What a crewman looks through is a ROW NAME in the
        # vehicle's sights table; the row itself lives in common_res_mod. Nothing compared the two, so the
        # tool spent two builds pointing tanks at rows it had stopped shipping, and the build reported
        # success both times ("sight -> drv_slit_g" for a row that was not in the package). Every row every
        # crewable vehicle names must exist, in the table we ship or in the one it is built on.
        shipped = set()
        if crm is not None:
            _ct = azcf.Table(crm)
            shipped = {str(r[0]) for b in _ct.blocks if b.rows for r in _ct.rows(b)}
        _bt = azcf.Table(azcf.read_record(build.tabs_path(install), "common_res_mod"))
        known = shipped | {str(r[0]) for b in _bt.blocks if b.rows for r in _bt.rows(b)}
        missing = {}
        for v in to_crew:
            for r in sight_plans[v]["expected"]:
                if r[2] and str(r[2]) not in known:
                    missing.setdefault(str(r[2]), []).append("%s/%s" % (v, r[0]))
        if missing:
            raise SystemExit(
                "STOPPING: a vehicle names a sight row that is in neither the shipped common_res_mod nor "
                "the table it is built on, so that crewman would have NOTHING to look through (v92 lost "
                "drv_slit_g this way, v93 lost slit_g as well): %s"
                % "; ".join("%s <- %s" % (k, ", ".join(x[:2])) for k, x in sorted(missing.items())))
        log("OK  %d sight rows shipped, %d in the base table - every row a crewable vehicle names exists"
            % (len(shipped), len(known) - len(shipped)))
    else:
        sight_meshes = []

    log("")
    log("6. The add-on")
    tables = [("div_units_misc", units), ("qbattle", qb), ("common_res", common_res), (TECHN, techn)] + crew_tables \
        + cockpit_tables
    # every borrowed record carries the Operation Star archive it came from: that is the group it is
    # packed into (see the packing step below)
    assets = [(e[0], e[3], e[4], gtos_opstar.read(p, e),
               os.path.splitext(os.path.basename(p))[0] + "_opstar") for p, e in res["borrow"]]
    # v26: move crew points in the vehicle's own model, where Operation Star put one somewhere the
    # borrowed cockpit cannot live with. Done here, on the copy we ship, so the source game and the
    # objects pack are untouched.
    wanted = {}
    if mesh_points is not None:
        for model, nodes in mesh_points.items():
            wanted.setdefault(model.lower(), {}).update(nodes)
    else:
        # ONLY for a vehicle being crewed. The point is moved because a borrowed cockpit cannot live
        # with where Operation Star put it; an AI-only vehicle has no cockpit and must ship the model
        # exactly as it was - v10-v19 carry this T-34 as AI-only and Check the tool caught it.
        for v in to_crew:
            for model, nodes in (VEHICLES.get(v, {}).get("mesh_points") or {}).items():
                wanted.setdefault(model.lower(), {}).update(nodes)
    # v107: WHICH OF THOSE LIVE PATCHES IS A REAL FIX AND STAYS. A vehicle whose spec sets
    # keep_live_mesh has mesh_points that move the crew the ENGINE places, so every copy of the model
    # must carry them - including the one outside our add-on, or reinstalling that add-on silently
    # puts a man back where he was (BUILD_LOG 436). Named PER MODEL so the Panzer III camera fix the
    # project holds back on purpose is still restored. Only computed on the spec-driven path: a
    # PROVEN build names its own mesh_points and keeps/restores exactly as it always did.
    keep_live = live_keep_models(to_crew, mesh_points)
    if wanted:
        done = set()
        for i, (n, k, l, b, src) in enumerate(assets):
            if k == "mesh" and n.lower() in wanted:
                for node, axes in sorted(wanted[n.lower()].items()):
                    b, said = patch_mesh_point(b, node, axes)
                    log("OK  model %s moved %s" % (n, said))
                assets[i] = (n, k, l, b, src)
                done.add(n.lower())
        missing = sorted(set(wanted) - done)
        if missing:
            raise SystemExit("mesh_points names %s, which this build does not ship" % ", ".join(missing))
        # AND THE COPIES THE ENGINE MIGHT ACTUALLY READ. A model can exist in more than one add-on
        # and the engine loads whichever wins; patching only ours is what made a whole afternoon of
        # mesh_points edits invisible. Reported line by line, each copy backed up first.
        for ln in patch_shadowing_models(install, wanted, ADDON, log):
            log(ln)
    if any(e[0].lower() == n.lower() for p, e in res["borrow"] for n, b in sight_meshes):
        raise SystemExit("a reticle mesh name is also a file from Operation Star")
    assets += [(n, "mesh", "loc_def", b, ADDON) for n, b in sight_meshes]   # v8: our own reticle meshes
    # v110: the sounds the engine asks for and no game has. See SPEECH_DUPES.
    dupes, dupe_lines = speech_dupes(install)
    taken = {(a[0].lower(), a[1]) for a in assets}
    for d in dupes:
        if (d[0].lower(), d[1]) in taken:
            raise SystemExit("speech_dupes: %s is already an asset in this build" % d[0])
    assets += dupes
    # v113: RECORDS WE AUTHOR OURSELVES, read from a file on disk - the Steel Fury interiors and
    # their textures. Everything else in `assets` is generated in memory (the reticle meshes) or
    # copied from Operation Star (the borrow); there was no way to ship a record that simply EXISTS
    # AS A FILE, which is what a converted .go or .dds becomes.
    #
    # WHY IT HAS TO GO THROUGH THE ADD-ON, measured 2026-10-01 in the sandbox: a .flatdata placed by
    # hand beside the game's own archives is NOT loaded, and neither is one dropped into a registered
    # add-on's packed_data folder. Proven rather than assumed, by packing our texture under the STOCK
    # record name coc_coc_t62_dift - the stock texture still rendered, so the override never
    # happened. The only route that works is the one this builder already uses for everything else:
    # pack into the add-on's CORE and let the updater install it.
    own = OWN_ASSETS if own_assets is None else own_assets
    if own:
        taken = {(a[0].lower(), a[1]) for a in assets}
        borrowed = {e[0].lower() for p, e in res['borrow']}
        lines = []
        for entry in own:
            name, kind, path = entry['name'], entry['kind'], entry['file']
            if (name.lower(), kind) in taken:
                raise SystemExit('own_assets: %s (%s) is already an asset in this build' % (name, kind))
            if name.lower() in borrowed:
                raise SystemExit('own_assets: %s is also borrowed from Operation Star - shipping '
                                 'both silently is how a record goes missing' % name)
            if not os.path.isfile(path):
                raise SystemExit('own_assets: %s names %s, which does not exist' % (name, path))
            with open(path, 'rb') as f:
                blob = f.read()
            if not blob:
                raise SystemExit('own_assets: %s is empty' % path)
            want = {'mesh': b'AZG2', 'texture': b'ATF1'}.get(kind)
            if want and blob[:4] != want:
                raise SystemExit('own_assets: %s is kind %s so it must start %r, not %r - a .dds or '
                                 'an unconverted .go would pack without complaint and fail in game'
                                 % (name, kind, want, blob[:4]))
            assets.append((name, kind, 'loc_def', blob, ADDON))
            taken.add((name.lower(), kind))
            lines.append('OK  %-26s %-8s %10s B  %s  <- %s'
                         % (name, kind, format(len(blob), ','),
                            blob[:4].decode('latin1'), os.path.basename(path)))
        log('')
        log('5d. Records this build authors itself')
        for ln in lines:
            log(ln)
    if dupe_lines:
        log("")
        log("5c. Sounds the engine asks for that exist only under another name")
        for ln in dupe_lines:
            log("OK" + ln)
    core = os.path.join(work, "CORE")
    shutil.rmtree(core, ignore_errors=True)
    pd = os.path.join(core, "shared", "packed_data")
    os.makedirs(pd)
    # ---- THE ADD-ON IS MORE THAN ONE ARCHIVE, AND IT HAS TO BE -------------------------------------
    # THE GAME'S OWN mkflat PACKS AT MOST 340 RECORDS AND SILENTLY DROPS THE REST (measured 2026-09-28
    # with a synthetic flatlist of 400 one-field records: 340 in, 60 gone, no message). This add-on was
    # at 312 - one build away from losing records - and the fleet's own crews took it to 498, where the
    # build's own read-back is what caught the loss. So the records are packed the way SABoW Ext already
    # ships them: the tables and our own art in gtos_ww2.flatdata, everything borrowed BESIDE it, one
    # archive per Operation Star archive it came from (<archive>_opstar.flatdata, pack_into's own rule).
    # All of them in the same folder, which is where the engine reads every .flatdata it finds.
    LIMIT = 300                      # inside the 340, so the next few records do not fall off
    groups = {}
    for n, b in tables:
        groups.setdefault(ADDON, []).append((n, "config", "loc_def", b))
    for n, k, l, b, src in assets:
        groups.setdefault(src, []).append((n, k, l, b))
    for g in sorted(groups):
        if len(groups[g]) > LIMIT:
            raise SystemExit("%s.flatdata would hold %d records; mkflat packs 340 and drops the rest - "
                             "split it further before shipping" % (g, len(groups[g])))
    packed = []
    for g in sorted(groups):
        out = os.path.join(pd, g + ".flatdata")
        gtos_opstar._mkflat(groups[g], out, install, os.path.join(work, "pack"), log)
        packed.append((out, g + ".flatdata"))
    flat = packed[0][0]

    desc_src = os.path.join(work, "desc.addpack.engcfg2")
    with open(desc_src, "w", encoding="utf-8", newline="\n") as f:
        f.write(build.DESC_TEMPLATE.format(path=ADDON, desc=DESCRIPTION, author=AUTHOR, version=version))
    desc_out = os.path.join(core, "desc.addpack")
    build.starter(install, "pd2cfgp,", build.rel(desc_src, install) + ",", build.rel(desc_out, install), expect=desc_out)
    log("OK  add-on description compiled")

    tflat, names = build_names(install, work, [(v, VEHICLES[v]) for v in vehicles], log, side_names)

    zpath = zip_path or os.path.join(work, "%s_v%03d.zip" % (ADDON, version))
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        _zip_add(z, desc_out, "CORE/desc.addpack")
        for out, member in packed:
            _zip_add(z, out, "CORE/shared/packed_data/%s" % member)
        _zip_add(z, tflat, "CORE/loc_eng/packed_data/%s_text.flatdata" % ADDON)
    with zipfile.ZipFile(zpath) as z:
        tblob = z.read("CORE/loc_eng/packed_data/%s_text.flatdata" % ADDON)
    ttmp = zpath + ".text.flatdata"
    with open(ttmp, "wb") as f:
        f.write(tblob)
    try:
        got = read_names(ttmp)
    finally:
        os.remove(ttmp)
    if got != names:
        raise SystemExit("the names inside the zip read %r, expected %r" % (got, names))
    log("OK  inside the zip: text %s" % ", ".join("%s = %r" % kv for kv in sorted(got.items())))
    # read the result back out of the finished zip: EVERY archive, all records together. The
    # comparison is against the whole build, so a record that fell into the wrong archive - or out of
    # the build - is caught here rather than in the game.
    records = [(n, k, l, b) for g in sorted(groups) for (n, k, l, b) in groups[g]]
    with zipfile.ZipFile(zpath) as z:
        blobs = [(m, z.read(m)) for m in sorted(z.namelist())
                 if m.startswith("CORE/shared/packed_data/") and m.endswith(".flatdata")]
    if len(blobs) != len(packed):
        raise SystemExit("the zip holds %d archives, expected %d" % (len(blobs), len(packed)))
    tmp = zpath + ".check.flatdata"
    seen = {}
    try:
        for member, blob in blobs:
            with open(tmp, "wb") as f:
                f.write(blob)
            d = gtos_opstar.directory(tmp)
            for key in d:
                if key in seen:
                    raise SystemExit("%s is in %s and in %s" % (key, seen[key], member))
                seen[key] = member
            for n, k, l, b in records:
                if (n.lower(), k) not in d:
                    continue
                if gtos_opstar.read(tmp, d[(n.lower(), k)]) != b:
                    raise SystemExit("%s %s inside the zip is not what was built" % (k, n))
                if k == "config" and b[0x20:0x40].split(b"\0")[0].decode("latin1") != n:
                    raise SystemExit("table %s inside the zip names itself wrongly in its header" % n)
    finally:
        os.remove(tmp)
    if sorted(seen) != sorted((n.lower(), k) for n, k, l, b in records):
        raise SystemExit("the zip's archives do not hold exactly the records built")
    digest = hashlib.md5(open(zpath, "rb").read()).hexdigest()
    log("OK  inside the zip: %d tables + %d files in %d archive(s), every one byte-identical to what "
        "was built" % (len(tables), len(assets), len(packed)))
    # PUT THE FILES OUTSIDE OUR ADD-ON BACK BEFORE THE BUILD IS CALLED DONE. patch_shadowing_models()
    # edits LIVE game files (the other copies of a model the engine may read instead of ours); this
    # build restored them itself, and read every one back. keep_mesh_points=True is how the build that
    # MEANS to ship the Panzer III camera fix keeps it - so forgetting is never what decides it.
    if keep_mesh_points:
        if SHADOWED:
            log("")
            log("7b. KEPT ON PURPOSE: %d live file(s) left patched (keep_mesh_points=True)" % len(SHADOWED))
    else:
        restore_shadowed_models(install, log, pins=LIVE_PINS, keep=keep_live)
    log("")
    log("DONE  %s  (%.1f MB, md5 %s)" % (zpath, os.path.getsize(zpath) / 1e6, digest))
    return zpath, digest


# ---------------------------------------------------------------- what the GTOS vehicles tab calls

LABEL = "gtos_ww2 v%d"               # the BUILD_LOG version column for this add-on
BACKUP_NAME = "gtos_ww2_v%03d_PROVEN_%s"

# Proven builds the tool must still rebuild exactly - "Check the tool". Each: (version, zip, vehicles).
PROVEN = [
    (4, r"L:\sabow-ext-backups\gtos_ww2_v004_PROVEN_AI_PZ4F2_WRECK\gtos_ww2_v004.zip", ("pz4f2",), {"german_crew": False, "crewable": False}),
    # v5: the German crew, built by murkz from the tab and proven in game (2026-09-17)
    (5, r"L:\sabow-ext-backups\gtos_ww2_v005_PROVEN_PZ4F2\gtos_ww2_v005.zip", ("pz4f2",), {"german_voices": False, "crewable": False}),
    # v6: the crew's German voice lines; log clean, murkz GOOD (2026-09-17). Heard/seen up close at the crewable stage
    (6, r"L:\sabow-ext-backups\gtos_ww2_v006_PROVEN_PZ4F2\gtos_ww2_v006.zip", ("pz4f2",), {"crewable": False}),
    # v7: crewable (T-62 cockpit copy + tzf5f_r + padded views + fifth station); 3 cockpits built, driver/gunner/
    # commander/loader, no 001; murkz GOOD "german tank crew" (2026-09-17). Intercom still Russian - no German set exists
    (7, r"L:\sabow-ext-backups\gtos_ww2_v007_PROVEN_PZ4F2\gtos_ww2_v007.zip", ("pz4f2",), {"gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_r"}),
    # v8: murkz's TZF 5f (tzf5f_g + tzf5f_c from BoW43 v685); 3 cockpits, clean log; murkz GOOD "gunsight lines need to be thinner"
    (8, r"L:\sabow-ext-backups\gtos_ww2_v008_PROVEN_PZ4F2\gtos_ww2_v008.zip", ("pz4f2",), {"gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g"}),
    # v9: the TZF 5f reticle at 1 px; clean log; murkz GOOD "perfect" (2026-09-17)
    (9, r"L:\sabow-ext-backups\gtos_ww2_v009_PROVEN_PZ4F2\gtos_ww2_v009.zip", ("pz4f2",), {"gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v10: + AI T-34/76 1942 on the FR side. Its BAD row was the Sokolovo well model (map fix); retest with the same zip
    # "no ctd played great" (2026-09-17). Default options = everything the tool builds now, both vehicles.
    (10, r"L:\sabow-ext-backups\gtos_ww2_v010_PROVEN_PZ4F2_T34_UTZ_M42\gtos_ww2_v010.zip", ("pz4f2", "t34_utz_m42"), {"gunner_turnout": True, "crewable": ("pz4f2",), "repaint_sides": False, "gunner_sight": "tzf5f_g_1px"}),
    # v11: the FR side repainted as Soviet ("Soviets"), common_res by the placeholder text route; murkz GOOD "soviets are there"
    (11, r"L:\sabow-ext-backups\gtos_ww2_v011_PROVEN_PZ4F2_T34_UTZ_M42\gtos_ww2_v011.zip", ("pz4f2", "t34_utz_m42"), {"gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v12: + AI KV-1 1942 in its own heavy tank regiment; murkz GOOD "saw the kv1 moving" (2026-09-17)
    (12, r"L:\sabow-ext-backups\gtos_ww2_v012_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM\gtos_ww2_v012.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm"), {"spec_over": {"kv1_42_uztm": {"own_crew": False}}, "gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v13: + AI T-70. Its BAD row was the well's damaged states (map fix); proven with the same zip on 2026-09-18
    (13, r"L:\sabow-ext-backups\gtos_ww2_v013_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M\gtos_ww2_v013.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m"), {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}}, "gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v14: the FIRST vehicle murkz added himself, with the window's "Add an Operation Star vehicle..." - the T-26
    # mod.1939. Nothing in this file was written for it: its settings live in tool/gtos_user_vehicles.json.
    (14, r"L:\sabow-ext-backups\gtos_ww2_v014_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39\gtos_ww2_v014.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39"), {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}}, "gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v15/v16: vehicles murkz added himself with the window - Marder II, then Marder III, Tiger and Panzer III.
    # v16 is also the build that proved the shared-wreck fix (Panzer III + IV, the two Marders). murkz: "tiger worked".
    (16, r"L:\sabow-ext-backups\gtos_ww2_v016_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v016.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1", "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}},
      "spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}},
      "spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}},
      "spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_1px"}),
    # v19: the moving strich finished - whole quads move, the doubled frame square gone, rate 0.2 (per SECOND),
    # and the strich lowered 0.0380 so its tip rests on the optical axis at point blank. murkz: "perfect" (2026-09-22)
    (19, r"L:\sabow-ext-backups\gtos_ww2_v019_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v019.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1", "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "gunner_turnout": True, "crewable": ("pz4f2",), "gunner_sight": "tzf5f_g_moving_v19"}),
    # v26: the first proven build with TWO crewable vehicles - the Panzer IV and the T-34/76 together.
    # murkz: "excellent cmdr fixed at last". No build-wide gunner_sight on purpose: it would override
    # every crewable vehicle and give the T-34 a German TZF 5f. Each takes its own - the Panzer IV its
    # frozen v19 TZF 5f, the T-34 the stock T-62 row.
    (26, r"L:\sabow-ext-backups\gtos_ww2_v026_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v026.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1", "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "crewable": ("pz4f2", "t34_utz_m42"),
      # what v26 actually shipped: the hull gunner moved back level with the driver, and nothing else.
      # The gunner/loader raise came after and is murkz's parked tuning.
      # Pinned 2026-09-23: the T-34 was on the T-62 LOANER until v29, and now points at its own
      # TMFD-7 - so without this, v26 rebuilds with a sight it never shipped.
      "gunner_sight": {"t34_utz_m42": "tsh2b_stock"},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}},
      "gunner_hatch": False}),     # v26 shipped before the gunner turn-out state existed
    # v28: the gunner turns out. murkz, v27: "they both turn out now too"; v28: "very good" once the
    # seat raise was undone. Three things had to line up and now do - the plc_states 0x1000 state, the
    # s_gunner_out sync row, and the chunk the T-34 already had. mesh_points pinned to what v28
    # shipped: the hull gunner moved back level with the driver, and nothing else.
    (28, r"L:\sabow-ext-backups\gtos_ww2_v028_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v028.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1", "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "crewable": ("pz4f2", "t34_utz_m42"),
      # Pinned 2026-09-23: the T-34 was on the T-62 LOANER until v29, and now points at its own
      # TMFD-7 - so without this, v28 rebuilds with a sight it never shipped.
      "gunner_sight": {"t34_utz_m42": "tsh2b_stock"},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v29: the T-34 stops borrowing the T-62's TSh-2B and gets its OWN TMFD-7 - 12.5 deg at 2.5x on
    # Steel Fury's own art, static. First build to ship TWO hand-drawn reticles, which is what grew
    # build_sight_alias from one common_res_mod row to N.
    (29, r"L:\sabow-ext-backups\gtos_ww2_v029_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v029.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "crewable": ("pz4f2", "t34_utz_m42"),
      # PINNED 2026-09-23: v29 shipped the STATIC reticle and the T-34 has pointed at the moving one
      # since v30, so without this v29 rebuilds as v30 and Check the tool would call it wrong.
      "gunner_sight": {"t34_utz_m42": "tmfd_7_g_v29"},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v30: the T-34's long horizontal line now tracks the range drum, the same arrangement as the TZF
    # 5f's strich and the Matilda's wire. Reticle mesh differs from v29's; everything else is v29.
    (30, r"L:\sabow-ext-backups\gtos_ww2_v030_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG\gtos_ww2_v030.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}},
      "crewable": ("pz4f2", "t34_utz_m42"),
      # Pinned for the same reason as v29 - correct today only because the T-34 still points here.
      "gunner_sight": {"t34_utz_m42": "tmfd_7_g_moving_v30"},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v32: THREE crewable tanks. The Matilda II joins the Panzer IV and the T-34, and it arrives with
    # MURKZ'S OWN No. 24B rather than the T-62 loaner - the first imported vehicle made playable with no
    # hand-written recipe. PINNED to the 0.0016 reticle it shipped; from v33 the Matilda uses the 1 px one.
    (32, r"L:\sabow-ext-backups\gtos_ww2_v032_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG_MK2_4\gtos_ww2_v032.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg", "mk2_4"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}, "mk2_4": {"commander_freelook": False}},
      "crewable": ("pz4f2", "t34_utz_m42", "mk2_4"),
      "gunner_sight": {"t34_utz_m42": "tmfd_7_g_moving_v30", "mk2_4": "24b_mk1_g"},
      # Pinned 2026-09-23: both shipped the Matilda with mk4 among its stubs, and the derived
      # rule now excludes it as a shared vision block - see the historical-accuracy rule.
      "sight_stubs": {"mk2_4": ("24b_mk1", "mk4")},
      # Pinned: both shipped before extra_sights existed, with BOTH gunner rows on the No. 24B.
      "extra_sights": {"mk2_4": {}},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v33: the No. 24B at 1 px and at the T-34's drum rate. murkz: "sight is perfect". Same ten
    # vehicles as v32; the ONLY difference is the Matilda's reticle and its rate.
    (33, r"L:\sabow-ext-backups\gtos_ww2_v033_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG_MK2_4\gtos_ww2_v033.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg", "mk2_4"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}, "mk2_4": {"commander_freelook": False}},
      "crewable": ("pz4f2", "t34_utz_m42", "mk2_4"),
      "gunner_sight": {"t34_utz_m42": "tmfd_7_g_moving_v30", "mk2_4": "24b_mk1_g_1px_v33"},
      # Pinned 2026-09-23: both shipped the Matilda with mk4 among its stubs, and the derived
      # rule now excludes it as a shared vision block - see the historical-accuracy rule.
      "sight_stubs": {"mk2_4": ("24b_mk1", "mk4")},
      # Pinned: both shipped before extra_sights existed, with BOTH gunner rows on the No. 24B.
      "extra_sights": {"mk2_4": {}},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v34: the Matilda's SECOND gunner sight becomes its real MK-4 periscope, and the first build where
    # one vehicle carries two different sights. It also brought the vision-block MASK, unplanned.
    (34, r"L:\sabow-ext-backups\gtos_ww2_v034_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG_MK2_4\gtos_ww2_v034.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg", "mk2_4"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}, "mk2_4": {"commander_freelook": False}},
      "crewable": ("pz4f2", "t34_utz_m42", "mk2_4"),
      "gunner_sight": {"t34_utz_m42": "tmfd_7_g_moving_v30", "mk2_4": "24b_mk1_g_1px_v33"},
      "sight_stubs": {"mk2_4": ("24b_mk1", "mk4")},
      "extra_sights": {"mk2_4": {"mk4": "mk4_g_v34"}},
      "other_sights": {"mk2_4": {}, "pz4f2": {}, "t34_utz_m42": {}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v36: the driver's MK-4 at Steel Fury's 30 deg, pointed at sig_driver_x2 - the PADDED row, which
    # is the one index coc_t62's driver plc_states actually asks for. v35 changed index 1 and nothing
    # looked through it. From here the spec snapshot in proven_specs.json pins the rest.
    (36, r"L:\sabow-ext-backups\gtos_ww2_v036_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG_MK2_4\gtos_ww2_v036.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg", "mk2_4"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}, "mk2_4": {"commander_freelook": False}},
      "crewable": ("pz4f2", "t34_utz_m42", "mk2_4"),
      # PINNED after the snapshot caught the drift. The snapshot DETECTS a missing pin; it does not
      # replace one - a rebuild still needs to be told what the build shipped. Claiming v36 needed no
      # pinned fields was wrong, and the guard is what said so, by name, within the hour.
      "other_sights": {"mk2_4": {"sig_driver_x2": "mk4_drv_g"}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
    # v39: REGISTERED 2026-09-23, five builds late. v37-v39 were each backed up with PROVEN in the
    # FOLDER NAME and none of them was ever added here, so "Check the tool" was proving a v36 world
    # while the driver's and commander's sight rows moved underneath it. A backup is not a pin.
    # v39 is the last build with a clean look ("same as before no moving periscope for cmdr" - the
    # cupola missed, nothing regressed). It adds pz2f over v36 and pins the v37-v39 commander
    # arrangement: periscope_rot on sig_commander, commander_tech held at index 2 as the control.
    # v41 swapped those two, so without this pin a rebuild would reproduce v41 and read as drift.
    (39, r"L:\sabow-ext-backups\gtos_ww2_v039_PROVEN_PZ4F2_T34_UTZ_M42_KV1_42_UZTM_T70M_T26_M39"
         r"_MARDER2_131_MARDER3H_PZ6H1_PZ3JLG_MK2_4_PZ2F\gtos_ww2_v039.zip",
     ("pz4f2", "t34_utz_m42", "kv1_42_uztm", "t70m", "t26_m39", "marder2_131", "marder3h", "pz6h1",
      "pz3jlg", "mk2_4", "pz2f"),
     {"spec_over": {"kv1_42_uztm": {"own_crew": False}, "t70m": {"own_crew": False}, "t26_m39": {"own_crew": False}, "marder2_131": {"own_crew": False}, "pz6h1": {"own_crew": False}, "mk2_4": {"commander_freelook": False}},
      "crewable": ("pz4f2", "t34_utz_m42", "mk2_4"),
      "other_sights": {"mk2_4": {"sig_driver_x2": "mk4_drv_g",
                                 "sig_commander": "periscope_rot_stock",
                                 "sig_commander_x2": "commander_tech_stock"}},
      "mesh_points": {"t34_42_utz": {"s_mgunner": {"z": 1.30}}}}),
]

READABLE = {"pz4f2": "Panzer IV Ausf. F2", "t34_utz_m42": "T-34/76 model 1942 (UTZ)",
            "kv1_42_uztm": "KV-1 model 1942 (UZTM)",
            "t70m": "T-70 (1942)"}


# ---------------------------------------------------------------- "Add an Operation Star vehicle" (2026-09-18)
#
# Everything a vehicle's settings hold is already written down in the two games: its unit and squad rows (crew,
# costs, the name text), its side (which of Operation Star's unit tables it is in), and its guns. The only free
# choices are the platoon and battalion numbers, which are simply the next ones nobody uses. So the tool can work
# a new vehicle out by itself, warn where SABoW lacks its gun or shells, and save it to a file murkz owns.

SIDE_OF_TABLE = {"div_units_ger": "GER", "div_units_ussr": "FR"}
SIDE_LOOK = {"GER": {"sold_fams": "txt_sn_ger_fams", "sold_names": "txt_sn_ger_nams", "marks": "wer_marks_01"},
             "FR": {"sold_fams": "txt_sn_ussr_fams", "sold_names": "txt_sn_ussr_nams", "marks": "sa_marks_01"}}
# the engine's own vehicle type (techn props `type`, a four-letter code) -> the words for a platoon name
TYPE_WORDS = {"TANK": ("Tank platoon", "Tank battalion"), "FTAN": ("Flamethrower tank platoon", "Tank battalion"),
              "SPG": ("Assault gun platoon", "Assault gun battalion"), "ATSP": ("Tank destroyer platoon", "Tank destroyer battalion"),
              "ACAR": ("Armoured car platoon", "Reconnaissance battalion"), "APC": ("Carrier platoon", "Motorised battalion"),
              "ATG": ("Anti-tank gun platoon", "Anti-tank battalion"), "AAG": ("Anti-aircraft platoon", "Anti-aircraft battalion"),
              "GUN": ("Gun platoon", "Artillery battalion"), "HOWI": ("Howitzer platoon", "Artillery battalion"),
              "MORT": ("Mortar platoon", "Mortar battalion"), "MGUN": ("Machine gun platoon", "Machine gun battalion"),
              "ATR": ("Anti-tank rifle platoon", "Infantry battalion"), "CAR": ("Transport platoon", "Transport battalion")}
FIRST_CODE, FIRST_UID = 208, 0x0000f710      # after the four built in by hand (200-207, 0xf700-0xf703)


def _slug(vehicle):
    s = re.sub(r"[^a-z0-9]+", "_", vehicle.lower()).strip("_")
    return s[:20]


def opstar_catalogue(opstar=gtos_opstar.OPSTAR):
    """{vehicle: {unit, squad, squad_text, crew, side, table}} for every Operation Star vehicle that has a unit
    AND a squad - the two rows an import copies. The plain squad is preferred over its _com / _ccom versions."""
    out = {}
    for table, side in sorted(SIDE_OF_TABLE.items()):
        rows = build.decoded(azcf.Table(opstar_record(opstar, table)))
        units = {r[0]: r for n, _, _, rs in rows if n == "units" for r in rs}
        squads = [r for n, _, _, rs in rows if n == "squads" for r in rs]
        for u, r in units.items():
            if r[1] != "i_techn":
                continue
            mine = sorted((s for s in squads if s[10] == u), key=lambda s: (len(s[0]), s[0]))
            if not mine or r[3] in out:
                continue
            out[r[3]] = {"unit": u, "squad": mine[0][0], "squad_text": mine[0][2], "crew": r[4],
                         "side": side, "table": table}
    return out


_TEXTS = {}


def stock_texts(install):
    """{text id: text} from the game's own English text archives - where a vehicle's name already lives
    (txt_ce_wer_stug3f8 = 'SPG / 7.5 cm StuG III ausf. F8'). Read once per install."""
    if install not in _TEXTS:
        import glob
        out = {}
        for path in sorted(glob.glob(os.path.join(install, "data", "mtc80", "loc_eng", "packed_data", "*.flatdata"))):
            try:
                out.update(read_names(path))
            except Exception:
                continue
        _TEXTS[install] = out
    return _TEXTS[install]


def _free_numbers(install):
    """(next platoon code, next uid) - past everything stock qbattle uses and everything the tool already has."""
    q = azcf.Table(azcf.read_record(build.tabs_path(install), "qbattle"))
    codes, uids = set(), set()
    for b in q.blocks:
        try:
            p = q.props(b)
        except Exception:
            continue
        if isinstance(p.get("code"), int):
            codes.add(p["code"])
        if isinstance(p.get("uid"), int):
            uids.add(p["uid"])
    for s in VEHICLES.values():
        codes.update({s["platoon_code"], s["battalion_code"]})
        uids.add(s["uid"])
    code = max(FIRST_CODE, max(c for c in codes if c < 4096) + 1 if codes else FIRST_CODE)
    while code in codes or code + 1 in codes:
        code += 1
    uid = FIRST_UID
    while uid in uids:
        uid += 1
    return code, uid


# ------------------------------------------------------- making an imported vehicle PLAYABLE
#
# The Matilda II (v32) proved that an imported tank needs FOUR fields to become crewable, and that
# three of them can be read out of the vehicle itself. Everything else the planner derives.
#
# Why so little is needed: every vehicle in the game already carries its own work_places, sights,
# weapons, ammunition and view ports, because the AI crews it (notes/13). "Playable" is three fields
# in div_units_misc, and the player sits where the AI sits - mode 0 on a crew sync row makes the
# cockpit point follow the TANK's point (docs/sync-modes.md), which is murkz's own idea.
#
# What this must NOT derive: wp_edits, sync_retarget, sync_add, gunner_hatch, mesh_points. Every one
# of those on the Panzer IV and the T-34 was a CORRECTION made after murkz saw something wrong in
# play - a commander through the hull, a gunner with no hatch. The Matilda needed none. Writing them
# speculatively would invent problems. See docs/import-playable-steps.md.

DONOR_GUN, DONOR_MG = "U5TS", "PKT"     # the T-62 cockpit's own weapon names, which the pairing maps FROM


CREW_SLOTS = ("wp_driver", "wp_gunner", "wp_loader", "wp_mgunner", "wp_commander")

DONOR_CREW_MEN = 4        # sa_crew_t62_55 = sau_tank_com x1 + sau_tank_agun x3. Measured, not assumed.


def opstar_crew_men(vehicle, spec, opstar=gtos_opstar.OPSTAR):
    """(men, squad name) for Operation Star's OWN crew squad, or (None, None).

    The NAME matters as much as the count: own_crew=True needs opstar_squad to find the
    squad to cut, and crew_squad to name our copy. Setting own_crew without them stopped
    the v40 build with KeyError 'opstar_squad' - a path enabled without its inputs.

    A squads row is a list of (unit, count) PAIRS from field 10 on: the tank, then its crew
    squad. That crew squad is itself pairs of men. This is what own_crew=True cuts and ships
    instead of the donor's - which is the whole spare-crewman bug, found 2026-09-23 when murkz
    reported a fourth man walking behind a three-man Panzer II.
    """
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    key = (spec.get("opstar_units_table"), "config")
    if key not in src.records:
        return None, None      # the function's contract is a PAIR; a bare None crashes the caller
    t = azcf.Table(gtos_opstar.read(*src.records[key]))
    sq = {}
    for b in t.blocks:
        if b.name == "squads" and b.rows:
            for r in t.rows(b):
                v = list(r)
                sq[v[0]] = v

    def pairs(row):
        return [(row[i], row[i + 1]) for i in range(10, len(row) - 1, 2) if row[i]]

    want = spec["opstar_unit"]
    for name, row in sq.items():
        members = pairs(row)
        if not any(u == want for u, _ in members):
            continue
        crew = [u for u, _ in members if "crew" in u]
        if not crew or crew[0] not in sq:
            continue
        return sum(c for _, c in pairs(sq[crew[0]])), name
    return None, None


def derive_playable(vehicle, tb, blocks, install, spec=None, opstar=gtos_opstar.OPSTAR):
    """The four fields that make an imported vehicle crewable, read from the vehicle itself.

    Returns (fields, notes, problems). `problems` non-empty means refuse rather than guess.
    Read-only; `tb`/`blocks` are Operation Star's vehicle table and this vehicle's blocks.
    """
    fields, notes, problems = {}, [], []

    # 1. WEAPONS. Measured across every vehicle shipped: the main gun is the one row mounted at
    #    s_gun (its mount chunk is d_gun, or d_barrel on the Tiger) and the machine guns sit at
    #    s_mgun*. Refuse rather than pick the first if that is not true.
    rows = [list(r) for r in tb.rows(blocks["weapons"])] if "weapons" in blocks else []
    guns = [r for r in rows if r[1] == "s_gun"]
    mgs = [r for r in rows if r[1].startswith("s_mgun")]
    if len(guns) != 1:
        problems.append("%d weapons are mounted at s_gun, expected exactly 1 - the main gun cannot be "
                        "identified, so the pairing would be a guess" % len(guns))
    if not mgs:
        problems.append("no weapon is mounted at s_mgun* - this vehicle has no machine gun, and the "
                        "donor cockpit's PKT has nothing to pair with")
    if len(guns) == 1 and mgs:
        fields["weapons"] = {DONOR_GUN: guns[0][0], DONOR_MG: mgs[0][0]}
        notes.append("main gun %s (mounted at s_gun), machine gun %s (at %s)"
                     % (guns[0][0], mgs[0][0], mgs[0][1]))

    # 2. SIGHT STUBS. Its own gunner sight rows whose SABoW row carries no reticle art - exactly what
    #    "stub" has always meant: the glass etching is missing, not the optics.
    crm = azcf.Table(azcf.read_record(build.tabs_path(install), "common_res_mod"))
    sb = [x for x in crm.blocks if x.name == "sights"][0]
    stock = {r[0]: azcf.flat(list(r)) for r in (list(x) for x in crm.rows(sb))}
    srows = [list(r) for r in tb.rows(blocks["sights"])] if "sights" in blocks else []
    gunner = [r for r in srows if r[4] == "sig_gunner"]
    if not gunner:
        problems.append("the vehicle has no sig_gunner sight row, so there is nothing to point at a sight")
    # A stub must be the GUNNER'S OWN optic. A blank-reticle row that the vehicle also uses in another
    # group is a shared vision block, not a gunsight - the Panzer IV's `hole` sits on its loader, driver
    # and hull gunner as well, and repointing it would put the gunsight reticle in all of them. Found by
    # the self-test below, which is the whole reason it exists.
    elsewhere = {r[2] for r in srows if r[4] != "sig_gunner"}
    stubs = []
    for r in gunner:
        f = stock.get(r[2])
        if f is None or f[24] or r[2] in stubs:
            continue
        if r[2] in elsewhere:
            notes.append("%s is NOT treated as a gunner stub - the vehicle also uses it in another "
                         "sight group, so it is a shared vision block rather than this gunner's optic"
                         % r[2])
            continue
        stubs.append(r[2])
    if gunner and not stubs:
        problems.append("none of its gunner sight rows (%s) is an empty stub - it already has art, and "
                        "the tool has never repointed a sight that draws"
                        % ", ".join(sorted({r[2] for r in gunner})))
    if stubs:
        fields["sight_stubs"] = tuple(stubs)
        notes.append("gunner sight stubs %s - present in SABoW with correct optics and blank art"
                     % ", ".join(stubs))

    # 3. FIFTH STATION. A vehicle needs one only when it has FIVE manned work_places against the donor
    #    cockpit's four. The flag DEFAULTS TO TRUE and that default is wrong for most tanks - two
    #    crewable vehicles both taking one produces two mgunner blocks and the build refuses (v32).
    wp = [list(r) for r in tb.rows(blocks["work_places"])] if "work_places" in blocks else []
    # WP_EDITS FIRST. place_groups() has always applied them in memory before reading the table -
    # "the role fix lives in the text and the table read here" - and this deriver did NOT, so a
    # vehicle whose roles are repaired by wp_edits was still counted from the RAW Operation Star
    # rows. On pz3jlg that meant the deriver said 3 manned stations and fifth_station False while
    # the build would make 5: the numbers contradicted the build. Found 2026-09-25.
    edits = (spec or {}).get("wp_edits") or {}
    for r in wp:
        for f, v in (edits.get(r[0]) or {}).items():
            r[int(f)] = v      # a JSON object key is always a string; a field index is an int
    manned = [r[0] for r in wp if r[WP_ROLE]]
    # A CREW SLOT PRESENT BUT WITH NO ROLE IS MISSING DATA, NOT A TANK THAT LACKS A CREWMAN.
    # Operation Star's Panzer III leaves wp_driver and wp_mgunner blank; reading that as "not a
    # crew station" undercounted the crew by two and sent three builds at a mesh node. Say so.
    blank = [r[0] for r in wp if r[0] in CREW_SLOTS and not r[WP_ROLE]]
    if blank:
        notes.append("MISSING DATA, not a short crew: %s exist in the model but carry NO role, so "
                     "they are not counted and not crewed. Operation Star's own data is blank "
                     "here - set role %d for each via wp_edits." % (", ".join(blank), WP_ROLE))
    fields["fifth_station"] = len(manned) > 4
    notes.append("%d manned crew stations (%s) -> fifth_station %s"
                 % (len(manned), ", ".join(manned), fields["fifth_station"]))

    # 4. THE SIGHT. murkz's rule: "always use the t62 sight unless there is a real one to use". The
    #    default is safe and costs nothing - the stock tsh2b row, no row added to common_res_mod. But
    #    the tool CAN see when a reticle already exists for one of this vehicle's own optics, and that
    #    is worth saying rather than deciding: the Matilda's No. 24B is murkz's own drawing and far
    #    better than the loaner, which no rule would have worked out.
    fields["gunner_sight"] = "tsh2b_stock"
    fields["crewable"] = True

    # 5. OWN_CREW - the spare crewman. Every vehicle we build copies the donor T-62 squad's row
    #    wholesale, so it ships the T-62's FOUR-man crew squad; a three-man tank leaves a man
    #    walking behind it. murkz hit it on the Panzer II and on v15 before that, and the fix
    #    already existed - own_crew=True cuts Operation Star's own crew squad instead.
    #
    #    THE RULE (v99): take the vehicle's own crew whenever it MATCHES its manned stations - whatever
    #    side it is on. It used to be "when it matches and the donor's four does not", with the count as
    #    the whole question; that is why t34_utz_m42 and mk2_4 stayed False ("4 for 4, the same as the
    #    donor's, so it changes nothing"). It changes the MEN: the donor's four are T-62 tankers.
    #    Where NEITHER matches it says so rather than choosing: marder3h has 3 stations against an
    #    Operation Star crew of 4, and pz3jlg 3 against 5, so Operation Star's own data is
    #    inconsistent for those two and a person should look.
    if spec is not None:
        men, os_squad = opstar_crew_men(vehicle, spec, opstar)
        n = len(manned)
        if men is None:
            notes.append("Operation Star names no crew squad for this vehicle, so it keeps the "
                         "donor's %d-man crew" % DONOR_CREW_MEN)
        elif men == n:
            # v99: NO LONGER GERMAN-ONLY, AND NO LONGER ONLY WHEN THE COUNT DIFFERS. The old rule
            # asked "does the donor's four-man squad fit?" and, when the counts matched, said it
            # "changes nothing" - which was true of the COUNT and wrong about the MEN: a four-man
            # donor squad in a T-34 is four T-62 tankers, in modern kit, in a 1943 tank. A crew that
            # fits its manned stations is now taken whatever side it is on, because the men themselves
            # are the point (murkz, 2026-09-28: "we have the t62 crew models not the crew from gtos").
            fields["own_crew"] = True
            fields["opstar_squad"] = os_squad          # the squad to cut from
            fields["crew_squad"] = "gt_crew_" + vehicle  # our copy's name
            notes.append("own_crew TRUE - its own crew squad is %d men for %d stations, where the "
                         "donor's is %d and would leave %+d; from Operation Star's %s"
                         % (men, n, DONOR_CREW_MEN, DONOR_CREW_MEN - n, os_squad))
        else:
            notes.append("CHECK THIS BY HAND: %d manned stations, but Operation Star's own crew squad "
                         "is %d men and the donor's is %d - neither fits, so somebody should look"
                         % (n, men, DONOR_CREW_MEN))
    have = [k for k, g in GUNNER_SIGHTS.items()
            if not g.get("stock") and g["mesh"] and g["fields"].get(24, (None,))[1] in
            {t.replace("_g", "") for t in stubs} | set(stubs)]
    if have:
        notes.append("A RETICLE ALREADY EXISTS for this optic: %s. The default below is the T-62 "
                     "loaner - choose one of these instead if it is the right sight."
                     % ", ".join(sorted(have)))
    else:
        notes.append("no reticle exists for its optics, so the T-62 loaner (tsh2b_stock) is used - "
                     "it points the vehicle's own stub rows at the stock row and adds nothing")
    return fields, notes, problems


# The vehicles whose playable fields were set BY HAND, before any rule existed. derive_playable must
# reproduce them or the rule is wrong - this is the control, and it has already earned its keep: the
# first version of the sight-stub rule returned `hole` for the Panzer IV, a shared vision block, and
# only this comparison caught it.
#
# mk2_4 is listed as a KNOWN DIVERGENCE rather than a control, and the distinction matters. Its values
# were not independently hand-set - they were derived by the same reasoning on 2026-09-23 and then
# shipped, so agreeing with them would only prove the rule agrees with itself. It differs on `mk4`: the
# rule now excludes it because the Matilda also uses that row for its driver, while v32 and v33 shipped
# with it included and murkz called the sight perfect. Both are defensible and it is a question for him,
# NOT something to change quietly - sight_stubs is not pinned in the PROVEN entries, so changing it
# would alter how v32 and v33 rebuild and Check the tool would go red.
DERIVE_CONTROLS = ("pz4f2", "t34_utz_m42")
# RESOLVED 2026-09-23 by murkz's rule "always historical if possible": the MK-4 was a periscope, not a
# gunsight, so the Matilda no longer repoints it and mk2_4 now agrees with the derived value outright.
# v32 and v33 keep theirs pinned, because they shipped with mk4 included.
DERIVE_KNOWN_DIVERGENCE = {}


def check_derive(install, opstar=gtos_opstar.OPSTAR, log=print):
    """Does derive_playable reproduce the hand-set vehicles? True only if every control agrees."""
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
    allb = dict(azcf.vehicles(tb))
    ok = True
    for v in DERIVE_CONTROLS + tuple(DERIVE_KNOWN_DIVERGENCE):
        if v not in allb:
            log("MISSING  %s is not in Operation Star's table" % v)
            ok = False
            continue
        fields, notes, problems = derive_playable(v, tb, allb[v], install,
                                                  spec=VEHICLES.get(v), opstar=opstar)
        spec = VEHICLES.get(v, {})
        want = {"weapons": spec.get("weapons"),
                "sight_stubs": tuple(spec.get("sight_stubs") or ()),
                "fifth_station": spec.get("fifth_station", True),
                "own_crew": bool(spec.get("own_crew"))}
        got = {"weapons": fields.get("weapons"),
               "sight_stubs": tuple(fields.get("sight_stubs") or ()),
               "fifth_station": fields.get("fifth_station"),
               "own_crew": bool(fields.get("own_crew"))}
        bad = [k for k in want if got[k] != want[k]]
        known = DERIVE_KNOWN_DIVERGENCE.get(v, {})
        unexpected = [k for k in bad if k not in known]
        if problems:
            log("REFUSED  %s: %s" % (v, problems[0]))
            ok = False
        elif unexpected:
            log("WRONG    %s: %s" % (v, ", ".join("%s derived %r, hand-set %r" % (k, got[k], want[k])
                                                  for k in unexpected)))
            ok = False
        elif bad:
            log("KNOWN    %s differs only where expected: %s"
                % (v, ", ".join("%s (%s)" % (k, known[k]) for k in bad)))
        else:
            log("RIGHT    %s: every derived field matches the hand-set one" % v)
    # A control that cannot fail is not a control: these must be REFUSED, not merely allowed.
    for v, why in (("marder2_131", "a tank destroyer with no machine gun"),):
        if v not in allb:
            continue
        _f, _n, problems = derive_playable(v, tb, allb[v], install,
                                           spec=VEHICLES.get(v), opstar=opstar)
        if problems:
            log("RIGHT    %s refused, as it should be - %s" % (v, why))
        else:
            log("WRONG    %s was allowed, but it is %s" % (v, why))
            ok = False
    return ok


def propose(vehicle, install, opstar=gtos_opstar.OPSTAR):
    """Work out a vehicle's settings from the two games. Returns (spec, problems, facts); spec is None if the
    vehicle cannot be imported at all. Read-only."""
    facts, problems = [], []
    cat = opstar_catalogue(opstar)
    if vehicle not in cat:
        return None, ["Operation Star has no unit and squad for %s" % vehicle], facts
    if vehicle in VEHICLES:
        return None, ["the tool already has settings for %s" % vehicle], facts
    c = cat[vehicle]
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
    blocks = dict(azcf.vehicles(tb)).get(vehicle)
    if not blocks or "props" not in blocks:
        return None, ["Operation Star's vehicle table has no %s" % vehicle], facts
    props = tb.props(blocks["props"])
    kind = props.get("type")
    kind = recipe.fourcc(kind) if isinstance(kind, int) else str(kind)
    words = TYPE_WORDS.get(kind, ("Platoon", "Battalion"))
    readable = stock_texts(install).get(c["squad_text"], vehicle).replace("$n", " / ").strip()
    # the game's own name is "class / vehicle" ('Heavy tank / PzVI ausf. H1 "Tiger"'); the platoon name says the
    # class itself, so it takes the vehicle half, and quotes are dropped - the text compiler is happier without them
    short = readable.split(" / ")[-1].replace('"', "").replace(";", "").strip() or vehicle
    # the guns and rounds must already be in SABoW: nothing borrows weapon or shell rows yet
    have = gtos_opstar.Index(gtos_opstar.sabow_archives(install))
    cs = azcf.Table(gtos_opstar.read(*have.records[("common_res_mod", "config")]))
    co = azcf.Table(gtos_opstar.read(*src.records[("common_res_mod", "config")]))
    for bn, rows in (("weapons", "weapons"), ("shells", "shells"), ("tracks", "cpillars")):
        want = [r[0] for r in tb.rows(blocks[rows])] if rows in blocks else []
        rs = {r[0]: r for r in cs.rows(cs.find(bn)[0])}
        ro = {r[0]: r for r in co.rows(co.find(bn)[0])}
        for n in sorted(set(want)):
            if n not in rs:
                problems.append("%s %s is not in SABoW - the tool cannot bring weapon or shell rows over yet" % (bn[:-1], n))
            elif rs[n] != ro.get(n):
                problems.append("%s %s differs between the games - it would fight with SABoW's numbers" % (bn[:-1], n))
        if want:
            facts.append("%s: %s" % (bn, ", ".join(sorted(set(want)))))
    m = re.match(r"tabs\\(\w+)\.cfgpack, (\w+)\*$", props.get("ostov_type", "") or "")
    if m:
        ts = gtos_opstar.read(*have.records[(m.group(1), "config")]) if have.has((m.group(1), "config")) else None
        if not (ts is not None and any(b.name.startswith(m.group(2)) for b in azcf.Table(ts).blocks)):
            problems.append("its wreck %s is not in SABoW" % props.get("ostov_type"))
    slug = _slug(vehicle)
    code, uid = _free_numbers(install)
    spec = {
        "unit": "gtu_" + slug, "squad": "gt_" + slug, "opstar_unit": c["unit"],
        "donor_squad": "sa_t62",
        "platoon": "gt_plat_" + slug, "battalion": "p_gt_" + slug + "_bat",
        "platoon_code": code, "battalion_code": code + 1, "uid": uid,
        "camo": "pat2", "max_squads": 3,
        "squad_text": c["squad_text"],
        "platoon_name": "%s (%s)" % (words[0], short),
        "battalion_name": "%s, %s (1943)" % (words[1], "Wehrmacht" if c["side"] == "GER" else "RKKA"),
        "user_in": False,
        "side": c["side"], "opstar_units_table": c["table"],
        "own_crew": False, "crewable": False,
    }
    spec.update(SIDE_LOOK[c["side"]])
    facts.insert(0, "Operation Star %s: unit %s, squad %s (crew %d), type %s, model %s"
                 % (vehicle, c["unit"], c["squad"], c["crew"], kind, props.get("mesh")))
    facts.insert(1, "side %s, name text %s = %r" % (c["side"], c["squad_text"], readable))
    facts.insert(2, "platoon %s code %d, battalion %s code %d, uid 0x%08x (the next free numbers)"
                 % (spec["platoon"], code, spec["battalion"], code + 1, uid))
    for key in ("unit", "squad", "platoon", "battalion"):
        if any(s.get(key) == spec[key] for s in VEHICLES.values()):
            problems.append("the name %s is already used by another vehicle in the tool" % spec[key])

    # THE CREW, decided at IMPORT rather than found in play. Every vehicle copies the donor
    # T-62 squad's row, so without this it ships the T-62's FOUR-man crew whatever it actually
    # seats - a three-man Panzer II leaves a man walking behind it, and a five-man KV-1 is a
    # man short. murkz hit the walking man on v15 and again on v37 before it was traced; the
    # answer is to take Operation Star's own crew squad when it fits the vehicle's stations.
    men, os_squad = opstar_crew_men(vehicle, spec, opstar)
    seats = len([1 for r in tb.rows(blocks["work_places"]) if list(r)[WP_ROLE]])         if "work_places" in blocks else None
    if men is not None and seats:
        if men == seats and men != DONOR_CREW_MEN and spec["opstar_units_table"] == "div_units_ger":
            spec["own_crew"] = True
            spec["opstar_squad"] = os_squad
            spec["crew_squad"] = "gt_crew_" + vehicle
            facts.append("crew: %d men for %d stations - taking its OWN crew squad %s, because the "
                         "donor's %d would leave %+d"
                         % (men, seats, os_squad, DONOR_CREW_MEN, DONOR_CREW_MEN - seats))
        elif men == seats:
            facts.append("crew: %d men for %d stations, the same as the donor's - nothing to change"
                         % (men, seats))
        else:
            facts.append("CREW MISMATCH, worth a look: %d manned stations, but its own crew squad is "
                         "%d men and the donor's is %d - neither fits, so it keeps the donor's and "
                         "somebody may see a spare or a missing crewman" % (seats, men, DONOR_CREW_MEN))
    facts += playable_lines(vehicle, install, tb, blocks, spec=spec, opstar=opstar)
    return spec, problems, facts


def add(vehicle, spec, readable, path=USER_VEHICLES):
    """Save a proposed vehicle to murkz's own settings file and make it live in this session."""
    import datetime
    import json
    data = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    if vehicle in data or vehicle in BUILT_IN:
        raise SystemExit("%s is already in the tool" % vehicle)
    row = dict(spec, readable=readable, added=datetime.datetime.now().isoformat(timespec="seconds"))
    data[vehicle] = row
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    load_user_vehicles(path)
    return path


def remove(vehicle, path=USER_VEHICLES):
    """Take a vehicle murkz added back out (a built-in cannot be removed)."""
    import json
    if vehicle in BUILT_IN:
        raise SystemExit("%s is built into the tool and proven - it cannot be removed" % vehicle)
    if not os.path.isfile(path):
        raise SystemExit("no vehicles have been added yet")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if vehicle not in data:
        raise SystemExit("%s was not added from the window" % vehicle)
    del data[vehicle]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    VEHICLES.pop(vehicle, None)
    READABLE.pop(vehicle, None)
    global ADDON_VEHICLES
    ADDON_VEHICLES = tuple(v for v in ADDON_VEHICLES if v != vehicle)
    return path


# ------------------------------------ what making a vehicle PLAYABLE would write (read-only)
#
# plan-automate-playable.md step 3. These lines describe the fields derive_playable() would write if
# a vehicle were made crewable. Nothing here writes anything - the whole point is that the numbers
# are visible BEFORE a build is spent on them.
#
# Two callers, because the question is asked in two places: the import dialog (propose ->
# report_proposal) for a vehicle not yet in the tool, and the GTOS vehicles tab (check -> report)
# for one already imported as AI-only. That second case is the one that matters most today - eight
# of the eleven vehicles in ADDON_VEHICLES are AI-only.
#
# DELIBERATELY NOT returned as problems. A vehicle the deriver refuses to make crewable can still be
# imported and built perfectly well as an AI-only one. Refusing one is not refusing the other, and
# conflating them would block imports that are fine.
#
# Never raises: a fault in a report must not be able to stop an import or a check.


def playable_lines(vehicle, install, tb=None, blocks=None, spec=None, opstar=gtos_opstar.OPSTAR):
    """The PLAYABLE section as a list of lines. Read-only; writes nothing; never raises."""
    try:
        if tb is None or blocks is None:
            src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
            tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
            blocks = dict(azcf.vehicles(tb)).get(vehicle)
        if blocks is None:
            return ["PLAYABLE: Operation Star has no vehicle %s, so nothing can be derived" % vehicle]
        fields, notes, problems = derive_playable(vehicle, tb, blocks, install,
                                                  spec=spec, opstar=opstar)
    except Exception as e:                                   # pragma: no cover - defensive
        return ["PLAYABLE: could not be worked out - %s: %s" % (type(e).__name__, e)]
    only = "" if (spec is None or spec.get("crewable")) else " - this vehicle is AI-only today"
    out = [""]
    if problems:
        out.append("PLAYABLE: the tool REFUSES to make this one crewable, and will not guess:")
        out += ["   %s" % p for p in problems]
        out.append("   It can still be imported and built as an AI-only vehicle.")
    else:
        out.append("PLAYABLE (derived, not written%s):" % only)
        out.append("   crewable      true")
        out.append("   weapons       %s" % (fields.get("weapons") or "-"))
        out.append("   sight_stubs   %s" % (", ".join(fields.get("sight_stubs") or ()) or "-"))
        out.append("   fifth_station %s" % fields.get("fifth_station"))
        out.append("   gunner_sight  %s" % fields.get("gunner_sight"))
        if fields.get("own_crew"):
            out.append("   own_crew      true, from Operation Star's %s as %s"
                       % (fields.get("opstar_squad"), fields.get("crew_squad")))
    out += ["   %s" % n for n in notes]
    return out


def make_playable(vehicle, install, opstar=gtos_opstar.OPSTAR, path=USER_VEHICLES, log=print):
    """Promote a vehicle the tool already has as AI-only into a CREWABLE one.

    plan-automate-playable.md step 5, and the Matilda's own case: it was imported as an AI vehicle
    and then made playable by hand. This applies the same fields derive_playable() works out, and
    writes them back where the vehicle's settings actually live.

    Refuses rather than guesses, in four cases:
      - the deriver refuses it (no s_gun, no machine gun, or no gunner sight stub);
      - it is already crewable;
      - it is a BUILT_IN vehicle, whose settings are in this file's own code rather than in the
        settings file. load_user_vehicles() skips a built-in deliberately, so writing the file for
        one would appear to work and silently change nothing. Saying no is better than that;
      - the tool has no settings for it at all.

    Writes a .bak beside the settings file first. Returns a list of lines describing the change -
    what it refuses, and why, is part of the answer, not an error.
    """
    import json
    out = ["Make %s playable" % vehicle, ""]
    if vehicle not in VEHICLES:
        return out + ["REFUSED: the tool has no settings for %s, so there is nothing to make playable." % vehicle]
    spec = VEHICLES[vehicle]
    if spec.get("crewable"):
        return out + ["REFUSED: %s is already crewable. Nothing to do." % vehicle]
    builtin = vehicle in BUILT_IN
    if builtin:
        out += ["%s is a BUILT-IN, so only its PLAYABLE fields are written here:" % vehicle,
                "   its name, codes, uid and side stay in the tool's own code, where they were",
                "   proven by hand. Proven builds keep their own pinned specs, so this cannot",
                "   change a build that has already been proven.", ""]
    src_idx = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src_idx.records[("techn_base", "config")]))
    blocks = dict(azcf.vehicles(tb)).get(vehicle)
    if blocks is None:
        return out + ["REFUSED: Operation Star has no vehicle %s, so nothing can be derived." % vehicle]
    got_fields, got_notes, got_problems = derive_playable(vehicle, tb, blocks, install,
                                                          spec=spec, opstar=opstar)
    out += ["Derived from the vehicle itself:"] + ["   %s" % n for n in got_notes]
    if got_problems:
        return out + ["", "REFUSED, and it will not guess:"] + ["   %s" % p for p in got_problems] + [
            "", "This vehicle stays AI-only."]
    if not os.path.isfile(path):
        return out + ["REFUSED: there is no settings file at %s." % path]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if vehicle not in data:
        if not builtin:
            return out + ["REFUSED: %s has settings but no entry in %s."
                          % (vehicle, os.path.basename(path))]
        data[vehicle] = {"readable": READABLE.get(vehicle, vehicle), "built_in": True}
    row = dict(data[vehicle])
    want = {"crewable": True,
            "weapons": got_fields.get("weapons"),
            "sight_stubs": list(got_fields.get("sight_stubs") or ()),
            "fifth_station": got_fields.get("fifth_station"),
            "gunner_sight": got_fields.get("gunner_sight")}
    if got_fields.get("own_crew"):
        want["own_crew"] = True
        want["opstar_squad"] = got_fields.get("opstar_squad")
        want["crew_squad"] = got_fields.get("crew_squad")
    if builtin:
        keep = {"readable", "built_in", "added"}
        for k in list(row):
            if k not in keep and k not in PLAYABLE_OVERRIDE:
                del row[k]
    changed = []
    for k, v in want.items():
        if row.get(k) != v:
            changed.append((k, row.get(k), v))
            row[k] = v
    if not changed:
        return out + ["Nothing to change - it already holds these values."]
    shutil.copyfile(path, path + ".bak")
    data[vehicle] = row
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    load_user_vehicles(path)
    out += ["", "Written to %s; the previous copy is kept as %s.bak"
            % (os.path.basename(path), os.path.basename(path))]
    for k, was, now in changed:
        out.append("   %-14s %r -> %r" % (k, was, now))
    out += ["", "It becomes crewable at the NEXT build. Nothing has been built, and no game file",
            "has been touched - only the tool's own settings."]
    return out


def playable_spec(vehicle, install, spec=None, opstar=gtos_opstar.OPSTAR):
    """The derived playable fields merged onto a COPY of spec. Returns (out, notes, problems).

    plan-automate-playable.md step 4 - the tick in the import dialog. `out` is None when the deriver
    refuses, and then the caller must NOT write a crewable vehicle: a crewable row naming a sight or
    a cockpit that does not exist is the dangling-reference bug that caused the Sokolovo 001
    (notes_105). Refusing is the safe answer, not a limitation.

    Kept separate from playable_lines() so the dialog can show the numbers and then decide - the
    display and the write must not be able to disagree.
    """
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
    blocks = dict(azcf.vehicles(tb)).get(vehicle)
    if blocks is None:
        return None, [], ["Operation Star has no vehicle %s" % vehicle]
    fields, notes, problems = derive_playable(vehicle, tb, blocks, install, spec=spec, opstar=opstar)
    if problems:
        return None, notes, problems
    out = dict(spec or {})
    out["crewable"] = True
    out["weapons"] = fields.get("weapons")
    out["sight_stubs"] = list(fields.get("sight_stubs") or ())
    out["fifth_station"] = fields.get("fifth_station")
    out["gunner_sight"] = fields.get("gunner_sight")
    if fields.get("own_crew"):
        out["own_crew"] = True
        out["opstar_squad"] = fields.get("opstar_squad")
        out["crew_squad"] = fields.get("crew_squad")
    return out, notes, problems


def main(argv=None):
    """The command line. The same two calls the GUI buttons make - so a modder can batch and
    script, and neither interface can do anything the other cannot.

        gtos_vehicle extract <vehicle> [--out DIR] [--all]
        gtos_vehicle repack  <DIR> [--write]        DRY BY DEFAULT
        gtos_vehicle list                           what can be extracted

    Nothing writes unless --write is given. Extract only ever reads.
    """
    import argparse
    import settings
    ap = argparse.ArgumentParser(prog="gtos_vehicle", add_help=True)
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("extract", help="a vehicle's assets into a workspace (read only)")
    e.add_argument("vehicle", nargs="?")
    e.add_argument("--all", action="store_true", help="every vehicle the tool knows")
    e.add_argument("--out", default=None)
    e.add_argument("--install", default=None)
    r = sub.add_parser("repack", help="put edited files back (dry unless --write)")
    r.add_argument("dir")
    r.add_argument("--write", action="store_true")
    r.add_argument("--install", default=None)
    sub.add_parser("list", help="the vehicles that can be extracted")
    sub.add_parser("archives", help="every AZP3 archive in the install")
    c = sub.add_parser("contents", help="what is inside an archive")
    c.add_argument("archive")
    c.add_argument("--only", default=None)
    u = sub.add_parser("unflat", help="write an archive out as files (read only)")
    u.add_argument("archive")
    u.add_argument("--out", default=None)
    u.add_argument("--only", default=None)
    u.add_argument("--limit", type=int, default=None)
    k = sub.add_parser("check-archive", help="is this archive safe to write into?")
    k.add_argument("archive")
    f = sub.add_parser("flatback", help="put edited records back (dry unless --write)")
    t1 = sub.add_parser("atf2dds", help="a workspace's textures out as .dds you can edit")
    t1.add_argument("dir")
    t2 = sub.add_parser("dds2atf", help="edited .dds back into .atf")
    t2.add_argument("dir")
    c1 = sub.add_parser("configs-out", help="tables out as editable text (uses the game)")
    c1.add_argument("dir")
    c2 = sub.add_parser("configs-in", help="edited text back into tables")
    c2.add_argument("dir")
    sub.add_parser("techn-list", help="the vehicles in the vehicle table")
    ts = sub.add_parser("techn-show", help="every field of a vehicle, by name")
    ts.add_argument("vehicle")
    ts.add_argument("--archive", default=None)
    tw = sub.add_parser("techn-set", help="change one field (dry unless --write)")
    tw.add_argument("vehicle")
    tw.add_argument("field")
    tw.add_argument("value")
    tw.add_argument("--archive", default=None)
    tw.add_argument("--write", action="store_true")
    f.add_argument("dir")
    f.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    install = a.install if getattr(a, "install", None) else settings.get("sandbox")
    if a.cmd == "list":
        for v in sorted(ADDON_VEHICLES):
            print("%-16s %s" % (v, "crewable" if VEHICLES.get(v, {}).get("crewable") else "AI-only"))
        return 0
    if a.cmd == "extract":
        vs = sorted(ADDON_VEHICLES) if a.all else [a.vehicle]
        if not a.vehicle and not a.all:
            ap.error("name a vehicle, or --all")
        for v in vs:
            out = os.path.join(a.out or os.path.join(os.getcwd(), "workspace"), v)
            print("extracting %s -> %s" % (v, out))
            extract_vehicle(v, install, out, log=print)
        print("done. Nothing in the game was changed.")
        return 0
    if a.cmd == "repack":
        rows = repack_vehicle(install, a.dir, log=print, dry=not a.write)
        for name, what in rows:
            print("  %-34s %s" % (name, what))
        if not a.write:
            print("DRY RUN - nothing written. Add --write to put the changed files back.")
        return 0
    if a.cmd == "archives":
        for p in find_archives(install, gtos_opstar.OPSTAR):
            ok, why = check_archive(p)
            print("%-4s %-56s %s" % ("ok" if ok else "BAD", os.path.basename(p), why))
        return 0
    if a.cmd == "contents":
        ok, why = check_archive(a.archive)
        print("%s: %s" % (os.path.basename(a.archive), why))
        rows = archive_summary(a.archive)
        if a.only:
            rows = [r for r in rows if a.only.lower() in r[0].lower()]
        for n, sz, kind in rows:
            print("  %-46s %-10s %10d" % (n, kind, sz))
        print("  %d record(s)" % len(rows))
        return 0
    if a.cmd == "unflat":
        out = a.out or os.path.join(os.getcwd(),
                                    os.path.splitext(os.path.basename(a.archive))[0])
        print("unflattening %s -> %s" % (os.path.basename(a.archive), out))
        unflat(a.archive, out, log=print, only=a.only, limit=a.limit)
        print("done. Nothing in the game was changed.")
        return 0
    if a.cmd == "check-archive":
        ok, why = check_archive(a.archive)
        print("%s: %s" % ("ok" if ok else "CANNOT BE WRITTEN INTO", why))
        return 0 if ok else 1
    if a.cmd == "techn-list":
        vs = techn_vehicles(install)
        for i in range(0, len(vs), 5):
            print("   " + "  ".join("%-14s" % v for v in vs[i:i + 5]).rstrip())
        print("   %d vehicle(s) in %s" % (len(vs), os.path.basename(techn_archive(install))))
        return 0
    if a.cmd == "techn-show":
        techn_show(install, a.vehicle, archive=a.archive, log=print)
        return 0
    if a.cmd == "techn-set":
        techn_set(install, a.vehicle, a.field, a.value, archive=a.archive,
                  log=print, dry=not a.write)
        return 0
    if a.cmd == "configs-out":
        config_text_out(a.dir, install, log=print)
        return 0
    if a.cmd == "configs-in":
        config_text_in(a.dir, install, log=print)
        return 0
    if a.cmd == "atf2dds":
        textures_out(a.dir, log=print)
        return 0
    if a.cmd == "dds2atf":
        textures_in(a.dir, log=print)
        return 0
    if a.cmd == "flatback":
        rows = repack_vehicle(install, a.dir, log=print, dry=not a.write)
        for name, what in rows:
            print("  %-34s %s" % (name, what))
        if not a.write:
            print("DRY RUN - nothing written. Add --write to put the changed files back.")
        return 0

    ap.print_help()
    return 0



def report_proposal(vehicle, spec, problems, facts):
    L = ["Add %s to the tool" % vehicle, ""]
    L += facts
    if problems:
        L += ["", "PROBLEMS:"] + ["   " + p for p in problems]
    L.append("")
    if spec is None:
        L.append("Verdict: cannot be added.")
    elif problems:
        L.append("Verdict: do NOT add it yet - see the problems above.")
    else:
        L.append("Verdict: ready to add as an AI-only vehicle. It joins every build from the next one on, and its "
                 "platoon appears in quick battle under %s." % ("Germany" if spec["side"] == "GER" else "Soviets"))
    return "\n".join(L)


def contents(vehicles=None):
    """One line for the BUILT row: what the add-on holds."""
    vehicles = ADDON_VEHICLES if vehicles is None else vehicles
    out = []
    for v in vehicles:
        s = VEHICLES[v]
        bits = ["crewable" if s.get("crewable") else "AI-only", "side " + s["side"]]
        if s.get("own_crew"):
            bits.append("German crew and voices")
        out.append("%s (%s)" % (v, ", ".join(bits)))
    return "; ".join(out)


def check(vehicle, install, opstar=gtos_opstar.OPSTAR, log=print):
    """Read-only: what this Operation Star vehicle needs, and whether the tool can build it. Changes nothing."""
    info = {"vehicle": vehicle, "problems": [], "facts": [], "files": None, "buildable": vehicle in VEHICLES}
    if not gtos_opstar.is_opstar(opstar):
        info["problems"].append("no Operation Star install at %s" % opstar)
        return info
    if not os.path.isfile(build.tabs_path(install)):
        info["problems"].append("no Steel Armor install at %s" % install)
        return info
    have = gtos_opstar.Index(gtos_opstar.sabow_archives(install))
    src = gtos_opstar.Index(gtos_opstar.opstar_archives(opstar))
    tb = azcf.Table(gtos_opstar.read(*src.records[("techn_base", "config")]))
    blocks = dict(azcf.vehicles(tb)).get(vehicle)
    if blocks is None:
        info["problems"].append("Operation Star has no vehicle called %s" % vehicle)
        return info
    props = tb.props(blocks["props"])
    info["facts"].append("Operation Star vehicle %s, model %s, armour map %s" % (vehicle, props.get("mesh"), props.get("armor_map")))
    # the rows it borrows from SABoW's own tables - must be identical, or the tank fights with other numbers
    cs = azcf.Table(gtos_opstar.read(*have.records[("common_res_mod", "config")]))
    co = azcf.Table(gtos_opstar.read(*src.records[("common_res_mod", "config")]))
    for bn, names in (("weapons", [r[0] for r in tb.rows(blocks["weapons"])]),
                      ("shells", [r[0] for r in tb.rows(blocks["shells"])]),
                      ("tracks", [r[0] for r in tb.rows(blocks["cpillars"])]),
                      ("sights", [r[2] for r in tb.rows(blocks["sights"])])):
        rs = {r[0]: r for r in cs.rows(cs.find(bn)[0])}
        ro = {r[0]: r for r in co.rows(co.find(bn)[0])}
        for n in sorted(set(names)):
            state = "MISSING in SABoW" if n not in rs else ("same as Operation Star" if rs[n] == ro.get(n) else "DIFFERENT from Operation Star")
            if state != "same as Operation Star":
                info["problems"].append("%s %s: %s" % (bn, n, state))
        info["facts"].append("%s in SABoW, same as Operation Star: %s" % (bn, ", ".join(sorted(set(names)))))
    # the wreck
    ostov = props.get("ostov_type", "")
    m = re.match(r"tabs\\(\w+)\.cfgpack, (\w+)\*$", ostov)
    if m:
        ts = gtos_opstar.read(*have.records[(m.group(1), "config")]) if have.has((m.group(1), "config")) else None
        found = ts is not None and any(b.name.startswith(m.group(2)) for b in azcf.Table(ts).blocks)
        info["facts"].append("wreck %s: %s" % (ostov, "in SABoW's %s" % m.group(1) if found else "NOT in SABoW"))
    # files
    tokens = vehicle_tokens(opstar, [vehicle])
    spec = VEHICLES.get(vehicle)
    if spec and spec.get("opstar_squad"):
        # the German crew, read without compiling: squad -> crew squad -> humans -> their bodies
        du = build.decoded(azcf.Table(opstar_record(opstar, "div_units_ger")))
        units = {r[0]: r for n, _, _, rows in du if n == "units" for r in rows}
        squads = {r[0]: r for n, _, _, rows in du if n == "squads" for r in rows}
        crew = squads[squads[spec["opstar_squad"]][12]]
        members = [(crew[i], crew[i + 1]) for i in range(10, 22, 2) if crew[i]]
        humans = sorted({units[u][3] for u, n in members})
        info["facts"].append("German crew (Operation Star's %s): %s - humans %s, plus their _summer versions" % (
            crew[0], ", ".join("%s x%d" % m for m in members), ", ".join(humans)))
        ht = azcf.Table(opstar_record(opstar, "ger_hum_base"))
        bt = azcf.Table(opstar_record(opstar, "bodys"))
        want = set(humans) | {h + "_summer" for h in humans}
        patterns = set()
        for b in ht.blocks:
            if b.name in want:
                p = ht.props(b)
                tokens.update(re.findall(r"[A-Za-z0-9_]{3,48}", " ".join(str(v) for v in p.values())))
                m = re.match(r"tabs\\bodys\.cfgpack, (\w+)\*$", p.get("ostov_type", ""))
                if m:
                    patterns.add(m.group(1))
        bodies = [b.name for b in bt.blocks if any(re.match("^%s\\d+$" % re.escape(x), b.name) for x in patterns)]
        for b in bt.blocks:
            if b.name in bodies:
                tokens.update(re.findall(r"[A-Za-z0-9_]{3,48}", " ".join(str(v) for v in bt.props(b).values())))
        info["facts"].append("their bodies: %s" % ", ".join(bodies))
        voices, lines = crew_voices(install, opstar, humans)
        info["facts"].append("their voices (from v6):" + lines[0][len("  voice set"):])
    log("Following %s through Operation Star ..." % vehicle)
    res = gtos_opstar.resolve([], install, opstar, log, seed_tokens=tokens, season_variants=True)
    info["files"] = res
    # crew places and the gunner's sight - for the crewable stage later
    gunner_sights = [r[2] for r in tb.rows(blocks["sights"]) if r[0].startswith("sig_gunner") and r[2] != "hole"]
    info["facts"].append("gunner sight in Operation Star: %s - stock SABoW's row is a DUMMY for crewing (BoW43 notes/44)" % ", ".join(gunner_sights))
    if spec:
        info["facts"].append("side %s, platoon \"%s\", battalion \"%s\"%s" % (
            spec["side"], spec["platoon_name"], spec["battalion_name"],
            "" if spec.get("own_crew") else ", crew borrowed from stock %s" % spec["donor_squad"]))
        info["crewable"] = bool(spec.get("crewable"))
    if spec and spec.get("crewable"):
        # v7: the crew recipe, read-only - what "Build" will do to make it crewable
        plan, sights = crew_plan(install, opstar, vehicle)
        info["facts"].append("")
        info["facts"] += plan.report().split("\n")
        info["facts"] += ["  sights     " + line for line in sights["lines"]]
        info["facts"].append("  platoon    %s user_in -> true (our own platoon, set when it is written - the "
                             "'platoons none' above counts stock platoons only)" % spec["platoon"])
        info["facts"].append("  station    + hull machine-gunner (mgunner) before the loader - five stations for five work "
                             "places; the engine builds driver, gunner, commander, loader (BoW43 notes/22)")
    if spec and not spec.get("crewable"):
        # AI-only today. Say what making it crewable would take, so the numbers are visible before a
        # build is spent on it - and say so when the tool would refuse. plan-automate-playable 3/5.
        info["facts"] += playable_lines(vehicle, install, tb, blocks, spec=spec, opstar=opstar)
    return info


def report(info):
    v = info["vehicle"]
    L = ["%s (%s)" % (READABLE.get(v, v), v), ""]
    for f in info["facts"]:
        L.append(f)
    if info["files"]:
        L.append("")
        L.append("From Operation Star - only what SABoW lacks, winter textures included: %s" % gtos_opstar.summary(info["files"]))
        L.append("   " + ", ".join(e[0] for p, e in info["files"]["borrow"]))
    if info["problems"]:
        L.append("")
        L.append("PROBLEMS:")
        L += ["   " + p for p in info["problems"]]
    L.append("")
    if info["problems"]:
        L.append("Verdict: cannot build - see the problems above.")
    elif not info["buildable"]:
        L.append("Verdict: the tool has no settings for this vehicle yet (names, codes). Nothing to build.")
    elif info.get("crewable"):
        L.append("Verdict: buildable as a CREWABLE vehicle (T-62 cockpit copy, murkz's TZF 5f from BoW43 v685 as its gunner sight) "
                 "with its German crew and their voices (German side, names, wreck).")
    else:
        L.append("Verdict: buildable as an AI-only vehicle on the %s side (names, wreck). Not crewable yet - see PLAYABLE above for what making it crewable would take."
                 % VEHICLES[v]["side"])
    L.append("")
    L.append("Build puts every vehicle the tool has settings for into the one gtos_ww2 add-on: %s."
             % ", ".join(READABLE.get(x, x) for x in ADDON_VEHICLES))
    return "\n".join(L)


def zip_parts(zpath):
    """{part: bytes} - every record of every archive in the zip, plus the other members. Zip dates ignored."""
    import tempfile
    out = {}
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            data = z.read(m)
            if m.endswith(".flatdata"):
                tmp = os.path.join(tempfile.mkdtemp(), "x.flatdata")
                with open(tmp, "wb") as f:
                    f.write(data)
                for k, e in gtos_opstar.directory(tmp).items():
                    out["%s : %s %s" % (m, e[3], e[0])] = gtos_opstar.read(tmp, e)
                shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
            else:
                out[m] = data
    return out


# ---------------------------------------------------------------- the proven-spec snapshot
#
# THE PROBLEM THIS SOLVES, in one line: a PROVEN entry does not store the build, it stores a
# POINTER to the recipe - "build the Matilda the way the Matilda is set up" - and the Matilda's
# setup keeps changing. Change a vehicle today and an old build silently starts rebuilding with
# settings it never shipped.
#
# Four fields needed pinning by hand in two days - gunner_sight, sight_stubs, extra_sights,
# other_sights - and three of the four were caught only by going looking. The patch was right
# each time and the METHOD was wrong: it depends on noticing.
#
# So: every crewable vehicle in a proven build gets its build-affecting fields SNAPSHOTTED to
# proven_specs.json. On a rebuild the effective spec is compared against that snapshot, and a
# mismatch is a loud named error instead of a silent difference. It cannot catch a field nobody
# thought of either - but it does not have to, because it compares the WHOLE set rather than the
# ones someone remembered.
#
# The snapshots were taken while all 20 proven builds rebuilt RIGHT, so the baseline is known
# good rather than assumed.

PROVEN_SPECS = os.path.join(HERE, "proven_specs.json")

# What actually changes a build's bytes. Identity fields (unit, uid, platoon...) are excluded:
# they are set once when a vehicle is added and a change there is a new vehicle, not a drift.
# commander_freelook added 2026-09-23 AFTER it slipped past this list. It is a build-affecting
# field like the rest, but the guard only looks at names IT KNOWS - so a brand-new field is
# invisible to it, and v32/33/34/36/39 rebuilt WRONG with no SPEC DRIFT line to explain why.
# Only the byte comparison caught it. WHEN YOU ADD A SPEC FIELD, ADD IT HERE IN THE SAME EDIT.
SPEC_PINNED = ("crewable", "gunner_sight", "sight_stubs", "extra_sights", "other_sights",
               "sight_order", "sight_group", "vision_blocks",
               "weapons", "fifth_station", "wp_edits", "sync_retarget", "sync_add",
               "gunner_hatch", "gunner_turnout", "mesh_points", "own_crew",
               "commander_freelook")


def spec_snapshot(spec):
    """The build-affecting fields of one vehicle's effective spec, JSON-comparable.

    An EMPTY container is dropped, so "the field is absent" and "the field is an empty dict"
    compare equal. They mean the same thing to a build, and a pin that sets a field to {} was
    otherwise reported as drift against a spec that simply does not have the key - a false
    alarm found by the controls, not in use. Booleans are kept: crewable False is not absent.
    """
    import json
    out = {}
    for k in SPEC_PINNED:
        if k not in spec:
            continue
        v = spec[k]
        if v is None or (isinstance(v, (dict, list, tuple)) and not v):
            continue
        out[k] = json.loads(json.dumps(v, sort_keys=True, default=list))
    return out


def load_proven_specs(path=PROVEN_SPECS):
    import json
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_proven_spec(version, vehicle, effective, log=print, path=PROVEN_SPECS):
    """True if this vehicle's effective spec still matches what the proven build shipped."""
    import json
    snaps = load_proven_specs(path)
    want = snaps.get(str(version), {}).get(vehicle)
    if want is None:
        return True                      # nothing recorded yet - do not invent a failure
    want = spec_snapshot(want)       # normalise a file written before empties were dropped
    got = spec_snapshot(effective)
    bad = [k for k in set(want) | set(got) if want.get(k) != got.get(k)]
    if not bad:
        return True
    for k in sorted(bad):
        log("SPEC DRIFT  %s %s: %s is now %s, but the proven build shipped %s"
            % (LABEL % version, vehicle, k, json.dumps(got.get(k)), json.dumps(want.get(k))))
    return False


# ------------------------------------------------ a vehicle's files, out and back (READ/WRITE)
#
# murkz's ask, 2026-09-26: "unpack all associated config scripts and texture files for a selected
# vehicle ... and a corresponding reverse action to compile/repack the modified ones back". The
# purpose is the human touch - an automated importer pass that is imperfect should be correctable by
# hand, inspected, and reversible.
#
# This is the ASSET half: every texture, mesh and armour map the vehicle owns, written out byte for
# byte with a manifest recording exactly where each came from, so a repack puts it back in the same
# place, at the same offset, at the same size. The CONFIG half - the vehicle's rows as editable text
# - uses the tool's existing cfgp2pd/pd2cfgp round trip and is the next piece.

def locate_record(install, name, opstar=gtos_opstar.OPSTAR):
    """Every place a record of this name lives: [(archive, offset, size, kind, loc)].

    A name can exist in more than one archive and the engine reads whichever wins - the shadow that
    cost a whole afternoon on pz3jlg. All of them are reported so a repack can write to the one that
    matters, and to the others if that is what it takes.
    """
    out = []
    roots = [os.path.join(install, "data"), os.path.join(install, "users")]
    if opstar:
        roots.append(opstar)
    for root in roots:
        if not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "*.flatdata"), recursive=True):
            try:
                recs = azcf.archive_records(p)
            except Exception:
                continue
            e = recs.get(name)
            if e:
                out.append((p, e[0], e[1], e[2], e[3]))
    return out


def vehicle_assets(vehicle, install, opstar=gtos_opstar.OPSTAR, log=print):
    """Every asset the vehicle NAMES, as [(name, kind, [(archive, offset, size)])].

    The names come from the tool's own token walk, which is what the build uses to decide what to
    borrow - so this lists what the vehicle actually needs, not what a name suggests.
    """
    names = []
    try:
        names = list(vehicle_tokens(opstar, [vehicle]))
    except Exception as e:
        log("   could not walk the tokens for %s: %s" % (vehicle, e))
    spec = VEHICLES.get(vehicle) or {}
    for extra in (spec.get("mesh_points") or {}):
        if extra not in names:
            names.append(extra)
    found, missing = [], []
    for n in names:
        where = locate_record(install, n, opstar)
        if not where:
            missing.append(n)
            continue
        found.append((n, where[0][3], [(w[0], w[1], w[2]) for w in where]))
    return found, missing


def extract_vehicle(vehicle, install, out_dir, opstar=gtos_opstar.OPSTAR, log=print):
    """Write a vehicle's assets into out_dir with a manifest. Returns the manifest path.

    Nothing is changed anywhere: this only reads. The manifest carries archive, offset, size and md5
    for every copy of every record, which is what makes the repack able to put a modified file back
    exactly where it came from - and to refuse when it cannot.
    """
    import hashlib
    assets, missing = vehicle_assets(vehicle, install, opstar, log)
    files = os.path.join(out_dir, "files")
    os.makedirs(files, exist_ok=True)
    man = ["# %s - extracted %s" % (vehicle, __import__("datetime").datetime.now().isoformat(timespec="seconds")),
           "# name | kind | archive | offset | size | md5 | written-as", ""]
    n = 0
    seen = {}
    for name, kind, copies in assets:
        path, off, size = copies[0]
        try:
            b = azcf.read_record(path, name)
        except Exception as e:
            log("   %s: could not read (%s)" % (name, e))
            continue
        md5 = hashlib.md5(b).hexdigest()
        rel = name + kind_extension(kind)
        dest = os.path.join(files, rel)
        with open(dest, "wb") as f:
            f.write(b)
        man.append("%s | %s | %s | %d | %d | %s | files/%s"
                   % (name, kind, path, off, size, md5, rel))
        seen[kind] = (seen.get(kind, (0, 0))[0] + 1, seen.get(kind, (0, 0))[1] + size)
        for p2, o2, s2 in copies[1:]:
            man.append("#   also in %s at %d (%d bytes)" % (p2, o2, s2))
        n += 1
    with open(os.path.join(out_dir, "manifest.txt"), "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(chr(10).join(man) + chr(10))
    readme = chr(10).join([
        "%s - a workspace you can edit by hand." % vehicle,
        "",
        "files/        every asset this vehicle names, byte for byte, as it is in the game now.",
        "manifest.txt  where each one came from - archive, offset, size, md5 - and where it goes back.",
        "",
        "TO CHANGE ONE: edit the file in files/, then run the repack. It compares md5s, so only the",
        "files you actually changed are written, and each is backed up first.",
        "",
        "A repack REFUSES a file whose size changed: these are written in place at their recorded",
        "offset, and a different length would corrupt everything after it in the archive.",
        "",
        "THE ASSETS ONLY. The vehicle's config rows - its weapons, crew, sights - are edited through",
        "the tool's own tables, not here.",
        "",
        "Nothing in the game has been changed by extracting. Extraction only reads.",
    ])
    write_index(out_dir, seen, "%s - what came out" % (vehicle if "vehicle" in dir() else os.path.basename(path)))
    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(readme + chr(10))
    log("   %s: %d asset(s) written to %s" % (vehicle, n, out_dir))
    if missing:
        log("   %d name(s) it references are not files at all - weapon, shell and human row names"
            " live inside tables, not as records of their own (e.g. %s)"
            % (len(missing), ", ".join(sorted(missing)[:6])))
    return os.path.join(out_dir, "manifest.txt")


def repack_vehicle(install, out_dir, log=print, dry=True):
    """Put the edited files back where the manifest says they came from. Returns [(name, action)].

    Refuses rather than corrupts, on every one of these:
      - a file whose SIZE changed, because these are written in place at a recorded offset;
      - a manifest whose recorded md5 no longer matches the archive - something else has changed
        that record since it was extracted, and overwriting it would discard that;
      - a file that has not changed at all, which is simply reported and skipped.
    Every archive record it DOES write is backed up first, under the tool's own work folder.
    """
    import hashlib
    man = os.path.join(out_dir, "manifest.txt")
    if not os.path.isfile(man):
        raise SystemExit("no manifest.txt in %s - extract first" % out_dir)
    out = []
    with open(man, encoding="utf-8") as f:
        lines = f.read().split(chr(10))
    for line in lines:
        if not line or line.startswith("#") or " | " not in line:
            continue
        name, kind, path, off, size, md5, rel = [x.strip() for x in line.split(" | ")]
        off, size = int(off), int(size)
        src = os.path.join(out_dir, rel)
        if not os.path.isfile(src):
            out.append((name, "SKIPPED - %s is not there" % rel))
            continue
        with open(src, "rb") as f:
            b = f.read()
        if hashlib.md5(b).hexdigest() == md5:
            out.append((name, "unchanged"))
            continue
        if len(b) != size:
            out.append((name, "REFUSED - size is %d, the archive holds %d; these are written in "
                              "place and a different length would corrupt the archive" % (len(b), size)))
            continue
        with open(path, "rb") as f:
            f.seek(off)
            cur = f.read(size)
        if hashlib.md5(cur).hexdigest() != md5:
            out.append((name, "REFUSED - the archive has changed since extraction, so writing this "
                              "would discard whatever changed it"))
            continue
        if dry:
            out.append((name, "WOULD WRITE %s at %d" % (os.path.basename(path), off)))
            continue
        bak = os.path.join(work_dir(install), "workspace", "%s_%s_%d.bak"
                           % (os.path.basename(path), name, off))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        with open(bak, "wb") as f:
            f.write(cur)
        with open(path, "r+b") as f:
            f.seek(off)
            f.write(b)
        out.append((name, "WRITTEN %s at %d (backup %s)" % (os.path.basename(path), off,
                                                            os.path.basename(bak))))
    return out


# ---------------------------------------------------------------- AZP3 archives, plain

ARCHIVE_EXT = (".flatdata",)

# What a record IS, from its kind, so the files come out named for what they are rather than .bin.
# The extension is the format that is actually inside, not a guess and not a wish: a texture is not
# a PNG and calling it one would be worse than calling it nothing.
KIND_EXT = {
    "texture": ".atf", "armor": ".atf", "dig_map": ".atf",
    "mesh": ".azg",
    "sound": ".aaf",
    "config": ".azcf", "program": ".azcf",
    "text": ".aztx",
    "fontmap": ".azfn",
    "shader": ".shd",
    "image": ".img",
    "progdesc": ".txt",
}

KIND_NOTE = {
    "texture": "a Graviteam texture: ATF1, then DXT5 / RGB8 / ART8 pixel data. Nothing here can open "
               "or convert one yet - it is the bytes as the game stores them.",
    "armor": "a Graviteam texture (ATF1), the armour skin. Same as any other texture - nothing here "
             "can open one yet.",
    "dig_map": "a Graviteam texture (ATF1): where the ground can be dug. Same as any other texture.",
    "mesh": "a Graviteam mesh (AZG2), the 3D model itself. Nothing here can open or convert one.",
    "sound": "a Graviteam sound container (AAF1), not a WAV. Nothing here can play or convert one.",
    "config": "a COMPILED TABLE (AZCF) - rows and cells, not text. Editing these by hand is the "
              "config-text half of the workflow, which is not built yet.",
    "program": "a compiled table (AZCF) for the game's own interface programs. Same as a config.",
    "text": "a text container (AZTX) - the localisation the game shows. Readable in principle; the "
            "tool cannot unpack it into lines yet.",
    "fontmap": "a font map (AZFN) - glyph widths for a font. Not a font file.",
    "shader": "shader source, in Graviteam's own assembled form.",
    "image": "a raw image: a small header, then uncompressed pixels. No container the usual viewers "
             "know.",
    "progdesc": "PLAIN TEXT (cp1251). This one you can open in Notepad and read right now.",
}


def kind_extension(kind):
    """The extension a record of this kind should carry. Unknown kinds keep .bin."""
    return KIND_EXT.get(kind, ".bin")


def techn_archive(install):
    """Where the WW2 vehicle table lives.

    techn_base is NOT techn_base_mtc80. The latter is the base install's MODERN table - t62, m60a1,
    olifant. The WW2 vehicles are in the Sokolovo add-on's own tabs.flatdata, which holds only seven
    tables; the shared ones come from the base install and the vehicle definitions come from here.
    """
    return os.path.join(install, "data", "mtc80", "gtos_sokolovo_ob", "shared",
                        "packed_data", "tabs.flatdata")


def techn_load(install, archive=None):
    """(archive_path, table_bytes, azcf.Table) for the vehicle table."""
    import struct as _s  # noqa: F401
    p = archive or techn_archive(install)
    blob = azcf.read_record(p, "techn_base")
    return p, blob, azcf.Table(blob)


def techn_vehicles(install, archive=None):
    """[vehicle name] in the order the table holds them."""
    return [n for n, _ in azcf.vehicles(techn_load(install, archive)[2])]


# A props block is pairs: a typed value cell, then the key name inline. The tag at +16 says
# the type. azcf.props decodes the same thing; this map exists so a field can also be WRITTEN.
PROP_FIELD = {0: "f", 1: "v", 2: "s", 3: "a", 4: "u", 5: "b", 6: "a"}

def techn_fields(t, block):
    """[(key, letter, value, value_cell_offset)] for a props block, in table order."""
    import struct
    out = []
    for r in range(block.rows):
        base = block.data_ptr + r * 64
        vc = t.data[base:base + 32]
        key = t.data[base + 32:base + 64].split(bytes([0]))[0].decode("latin1")
        tag = struct.unpack_from("<I", vc, 16)[0]
        letter = PROP_FIELD.get(tag)
        if tag == 0:
            v = struct.unpack_from("<f", vc)[0]
        elif tag == 1:
            v = tuple(struct.unpack_from("<4f", vc))
        elif tag == 2:
            v = t.string(vc)
        elif tag in (3, 6):
            v = tuple(struct.unpack_from("<4I", vc))
        elif tag == 4:
            v = struct.unpack_from("<i", vc)[0]
        elif tag == 5:
            v = bool(struct.unpack_from("<I", vc)[0])
        else:
            v = None
        out.append((key, letter or "?", v, base))
    return out


def techn_vehicle(t, name):
    """(props block, [(key, letter, value, offset)], {sub-block name: block}) for one vehicle."""
    for vname, subs in azcf.vehicles(t):
        if vname == name:
            props = subs.get("props")
            return props, (techn_fields(t, props) if props else []), subs
    return None, [], {}


def _fmt_field(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "%.6g" % value
    if isinstance(value, tuple):
        return ", ".join(("%.6g" % x) if isinstance(x, float) else str(x) for x in value)
    return str(value)


def techn_show(install, vehicle, archive=None, log=print, limit=None):
    """Print every field of one vehicle, by name, with its value.

    Fields come from the props block, which is where a vehicle's named settings live - armour,
    weight, engine, gun, ostov_type and the rest. The other sub-blocks are tables (gears, wheels,
    sights) and are listed by shape rather than printed in full.
    """
    p, blob, t = techn_load(install, archive)
    props, fields, subs = techn_vehicle(t, vehicle)
    if props is None:
        log("no vehicle called %s in %s" % (vehicle, os.path.basename(p)))
        return None
    log("%s  -  %d field(s), from %s" % (vehicle, len(fields), os.path.basename(p)))
    log("")
    for key, letter, value, _off in (fields[:limit] if limit else fields):
        log("   %-22s %-2s  %s" % (key, letter, _fmt_field(value)))
    if limit and len(fields) > limit:
        log("   ... %d more" % (len(fields) - limit))
    log("")
    log("   and its tables:")
    for name, b in subs.items():
        if name == "props":
            continue
        log("      %-18s spec=%-10r rows=%d" % (name, b.spec, b.rows))
    return fields


def techn_set(install, vehicle, field, value, archive=None, log=print, dry=True):
    """Change ONE field of one vehicle, and nothing else.

    Writes a single 32-byte value cell in place. The table's length never changes, which is what
    makes this safe where the text route was not: cfgp2pd cannot represent a comma inside a string,
    so 71 ostov_type fields of this very table come back truncated through it. Nothing here goes
    through that format.

    A string may only be replaced by one of the SAME LENGTH, because string bytes live in a pool
    that everything else points into - a longer or shorter string would move the pool. Numbers have
    no such problem: their cell is a fixed 32 bytes.
    """
    import struct
    p, blob, t = techn_load(install, archive)
    props, fields, subs = techn_vehicle(t, vehicle)
    if props is None:
        raise SystemExit("no vehicle called %s in %s" % (vehicle, os.path.basename(p)))
    hit = [f for f in fields if f[0] == field]
    if not hit:
        names = ", ".join(f[0] for f in fields[:14])
        raise SystemExit("%s has no field called %r. Some of what it does have: %s"
                         % (vehicle, field, names))
    key, letter, old, off = hit[0]
    buf = bytearray(blob)
    try:
        if letter == "f":
            struct.pack_into("<f", buf, off, float(value))
        elif letter == "s":
            old_b = old.encode("latin1") if isinstance(old, str) else b""
            new_b = str(value).encode("latin1")
            if len(new_b) != len(old_b):
                raise SystemExit("%s.%s is a string of %d characters; %r is %d. A different length"
                                 " would move the string pool everything else points into."
                                 % (vehicle, field, len(old_b), value, len(new_b)))
            ln, ptr = struct.unpack_from("<II", blob, off)
            buf[ptr:ptr + ln] = new_b
        elif letter == "u":
            struct.pack_into("<i", buf, off, int(value))
        elif letter == "b":
            struct.pack_into("<I", buf, off, 1 if str(value).lower() in ("1", "true", "yes") else 0)
        elif letter in ("v", "a"):
            parts = [x.strip() for x in str(value).split(",")]
            if len(parts) != 4:
                raise SystemExit("%s.%s takes four values separated by commas, got %d"
                                 % (vehicle, field, len(parts)))
            if letter == "v":
                for i, x in enumerate(parts):
                    struct.pack_into("<f", buf, off + i * 4, float(x))
            else:
                for i, x in enumerate(parts):
                    struct.pack_into("<I", buf, off + i * 4, int(x, 0))
        else:
            raise SystemExit("%s.%s is type %r, which this does not know how to write"
                             % (vehicle, field, letter))
    except ValueError as e:
        raise SystemExit("%s.%s takes a number: %s" % (vehicle, field, e))

    if bytes(buf) == blob:
        log("   %s.%s is already %s - nothing to do" % (vehicle, field, value))
        return False
    if len(buf) != len(blob):
        raise SystemExit("REFUSED - the table changed size, which must never happen")
    log("   %s.%s : %s -> %s" % (vehicle, field, _fmt_field(old), value))
    if dry:
        log("   DRY RUN - nothing written. The table would go back byte for byte the same length.")
        return True

    man = azcf.archive_records(p)
    off_in_archive, size, kind, loc = man["techn_base"]
    if size != len(blob):
        raise SystemExit("REFUSED - the archive's copy is %d bytes and ours is %d"
                         % (size, len(blob)))
    with open(p, "rb") as f:
        f.seek(off_in_archive)
        cur = f.read(size)
    if cur != blob:
        raise SystemExit("REFUSED - the archive has changed since it was read, so writing would"
                         " discard whatever changed it")
    backup = os.path.join(work_dir(install), "techn",
                          "techn_base_%s_%s_%d.bak" % (vehicle, field, off_in_archive))
    os.makedirs(os.path.dirname(backup), exist_ok=True)
    with open(backup, "wb") as f:
        f.write(cur)
    with open(p, "r+b") as f:
        f.seek(off_in_archive)
        f.write(bytes(buf))
    back = azcf.read_record(p, "techn_base")
    props2, fields2, _ = techn_vehicle(azcf.Table(back), vehicle)
    got = [f[2] for f in fields2 if f[0] == field]
    ok = len(back) == len(blob) and got and _fmt_field(got[0]) == _fmt_field(
        [f[2] for f in fields if f[0] == field][0:1] and _read_back(buf, letter, off))
    log("   written, backed up, and read back as %s - %s"
        % (_fmt_field(got[0]) if got else "?", "CONFIRMED" if ok else "CHECK IT"))
    return True


def _read_back(buf, letter, off):
    """The value as it now sits in the edited bytes, so the read-back can be compared."""
    import struct
    if letter == "f":
        return struct.unpack_from("<f", buf, off)[0]
    if letter == "u":
        return struct.unpack_from("<i", buf, off)[0]
    if letter == "b":
        return bool(struct.unpack_from("<I", buf, off)[0])
    if letter == "v":
        return tuple(struct.unpack_from("<4f", buf, off))
    if letter == "a":
        return tuple(struct.unpack_from("<4I", buf, off))
    ln, ptr = struct.unpack_from("<II", buf, off)
    return bytes(buf[ptr:ptr + ln]).decode("latin1")


def _table_work(install, table):
    """Scratch inside the game's own modwork folder.

    starter.exe runs with the game root as its working directory and takes paths relative to it,
    so the decompiler's files have to live inside the install. users/modwork is the game's own
    modding workspace and is where every earlier conversion left its scratch too.
    """
    import build
    d = os.path.join(build.work_dir(install), "config_text", table)
    os.makedirs(d, exist_ok=True)
    return d


def table_to_text(install, table, stock, log=print):
    """The repaired editable text for a compiled table, using the game's own cfgp2pd.

    cfgp2pd's output cannot be compiled as it comes out - indentation is written as NUL and
    spec-less blocks gain a stray '=' (notes/21, notes/43) - so cfgfix repairs it against the stock
    table as the oracle. Returns the path of the repaired text.
    """
    import build
    import subprocess
    import sys
    import textable
    here = os.path.dirname(os.path.abspath(__file__))
    d = _table_work(install, table)
    cfg = os.path.join(d, table + ".stock.config")
    with open(cfg, "wb") as f:
        f.write(stock)
    raw = os.path.join(d, table + ".cfgp2pd.engcfg2")
    if os.path.exists(raw):
        os.remove(raw)
    build.starter(install, "cfgp2pd,", build.rel(cfg, install) + ",",
                  build.rel(raw, install), expect=raw)
    fixed = os.path.join(d, table + ".loc_def.engcfg2")
    args = [sys.executable, os.path.join(here, "cfgfix.py"), cfg, raw, fixed]
    if table in textable.KEEP_DUPES:
        args.append("--keep-dupes")
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(fixed):
        raise SystemExit("cfgfix refused it (exit %d) %s"
                         % (r.returncode, (r.stdout or r.stderr or "").strip()[:120]))
    return fixed


def _crlf(b):
    """The line endings pd2cfgp needs, whatever editor the text has been through.

    This is not tidiness. pd2cfgp does NOT fail on text with bare LF: it compiles a complete,
    well-formed table containing NO BLOCKS AT ALL. Measured on cocpits - 60952 bytes of text with
    CRLF compiles to the stock 214792-byte table, and the same text with LF alone compiles to a
    193-byte AZCF header with nothing in it. An editor that saves Unix line endings would empty
    the table, quietly, and the result would look like a successful build.
    """
    CR, LF = bytes([13]), bytes([10])
    b = b.replace(CR + LF, LF).replace(CR, LF)
    return b.replace(LF, CR + LF)


def text_to_table(install, table, text_bytes, log=print):
    """Compiled bytes for a table's text, using the game's own pd2cfgp.

    The result is checked for blocks. If the text does not compile, pd2cfgp still writes a valid
    table header, so looking at the block count is the only thing standing between a bad edit and
    a table with nothing in it.
    """
    import struct
    import textable
    d = _table_work(install, table)
    src = os.path.join(d, "edited", table + ".engcfg2")
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with open(src, "wb") as f:
        f.write(_crlf(text_bytes))
    built = textable.compile_text(install, src, os.path.join(d, "edited", table + ".config"), log)
    if built[:4] != b"AZCF":
        raise SystemExit("the compiler did not produce a table at all (%d bytes)" % len(built))
    blocks = struct.unpack_from("<I", built, 0)[0] - 1
    if blocks < 1:
        raise SystemExit("the compiler produced a table with NO BLOCKS in it - the text did not"
                         " compile, and writing it would have emptied the table")
    return built


def config_text_out(workspace, install, log=print):
    """Every .azcf in a workspace out as editable text, with the round-trip gate enforced.

    Each table is decompiled, repaired, compiled back and COMPARED TO THE STOCK BYTES before its
    text is handed over. That is the gate, and it is the whole reason an edit can be trusted: if
    the text does not reproduce the table exactly, nothing edited from it means anything, so it is
    refused here rather than discovered later in a broken add-on.
    """
    got = []
    for table, kind, archive, rel in _manifest_rows(workspace):
        if kind not in ("config", "program"):
            continue
        stock = open(os.path.join(workspace, rel), "rb").read()
        try:
            fixed = table_to_text(install, table, stock, log)
            text = open(fixed, "rb").read()
            back = text_to_table(install, table, text, lambda t: None)
        except (SystemExit, Exception) as e:
            log("   %-24s REFUSED - %s" % (table, str(e)[:150]))
            continue
        if back != stock:
            log("   %-24s REFUSED - its own text compiles back to %d bytes, stock is %d"
                % (table, len(back), len(stock)))
            continue
        with open(os.path.join(workspace, rel + ".engcfg2"), "wb") as f:
            f.write(text)
        got.append(table)
        log("   %-24s %5d lines, compiles back to the stock bytes exactly"
            % (table, text.count(b"\n")))
    log("   %d table(s) out as text%s" % (len(got), "" if got else " - nothing here could be done"))
    if got:
        log("   edit the .engcfg2 files, then run configs-in")
    return got


def config_text_in(workspace, install, log=print):
    """Edited .engcfg2 text back into the .azcf records the manifest expects."""
    n = 0
    for table, kind, archive, rel in _manifest_rows(workspace):
        if kind not in ("config", "program"):
            continue
        text = os.path.join(workspace, rel + ".engcfg2")
        if not os.path.isfile(text):
            continue
        try:
            built = text_to_table(install, table, open(text, "rb").read(), lambda t: None)
        except (SystemExit, Exception) as e:
            log("   %-24s REFUSED - %s" % (table, str(e)[:150]))
            continue
        dest = os.path.join(workspace, rel)
        before = open(dest, "rb").read() if os.path.isfile(dest) else None
        if before is not None and len(built) != len(before):
            log("   %-24s REFUSED - the text compiles to %d bytes but the record is %d. Records go"
                " back in place at a fixed offset, so a different length cannot be written."
                % (table, len(built), len(before)))
            continue
        with open(dest, "wb") as f:
            f.write(built)
        log("   %-24s %7d bytes%s" % (table, len(built),
                                      " (unchanged)" if before == built else "  CHANGED"))
        n += 1
    log("   %d table(s) compiled back. Flat back will pick up the ones that changed." % n)
    return n


def _tex_stage(install):
    """Where a texture is staged for the game's own converters.

    atf2dds and dds2atf only recognise a file named <name>.<loc>.<kind> - the EXTENSION IS THE
    INTERFACE - and starter.exe takes paths relative to the game root, so the staging has to be
    inside the install. users/modwork is the game's own modding workspace.
    """
    d = os.path.join(install, "users", "modwork", "sabow_ext", "textures")
    os.makedirs(d, exist_ok=True)
    return d


def _tex_loc(archive, name, default="loc_def"):
    """The locale a record sits under, read from the archive rather than assumed."""
    try:
        for n, off, size, kind, loc in azcf.archive_entries(archive):
            if n == name:
                return loc or default
    except Exception:
        pass
    return default


def _manifest_rows(workspace):
    """[(name, kind, archive, rel)] from a workspace manifest."""
    man = os.path.join(workspace, "manifest.txt")
    if not os.path.isfile(man):
        raise SystemExit("no manifest.txt in %s - extract first" % workspace)
    out = []
    with open(man, encoding="utf-8") as f:
        for line in f.read().split(chr(10)):
            line = line.strip()
            if not line or line.startswith("#") or line.count(" | ") != 6:
                continue
            name, kind, archive, off, size, md5, rel = [x.strip() for x in line.split(" | ")]
            out.append((name, kind, archive, rel))
    return out


def _run(install, prog, src, dst, log):
    """One starter.exe call, and the log it leaves is what decides whether it worked.

    These programs print 'Converted!' AFTER an 'ERROR!' line, so their output cannot be trusted.
    The only thing that counts is whether the destination file exists and is not empty.
    """
    import build
    if os.path.isdir(dst):
        return False       # a folder is not a destination for these
    if os.path.exists(dst):
        os.remove(dst)
    try:
        build.starter(install, prog + ",", build.rel(src, install) + ",",
                      build.rel(dst, install), expect=dst, timeout=30)
    # 30s, not 120: a conversion of one of these takes about 2s, and a REFUSED format
    # never creates the file at all, so a long timeout is two minutes of nothing.
    except BaseException:
        pass
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return True
    return False


def textures_out(workspace, install, log=print):
    """Every texture in a workspace out as a .dds, using the GAME'S OWN atf2dds.

    This replaced a hand-written ATF1 decoder. The decoder was correct - it round-tripped DXT1 and
    DXT5 byte for byte - and unnecessary: Graviteam's own tool does the same job, for more formats,
    and the format listing in docs/modwork/modtools.pdf is the authority rather than my reading of
    the bytes.

    atf2dds handles DXT1, DXT5, A8, ARGB4 and ARGB8. It REFUSES ART8 - the armour maps - and says
    so in out/i_atf2dds.log; those go through tga2am instead, one way, from an authored TGA.
    Anything it will not convert is named and left alone.
    """
    stage = _tex_stage(install)
    n = left = 0
    for name, kind, archive, rel in _manifest_rows(workspace):
        if kind not in ("texture", "armor", "dig_map"):
            continue
        src = os.path.join(workspace, rel)
        if not os.path.isfile(src):
            continue
        loc = _tex_loc(archive, name)
        staged = os.path.join(stage, "%s.%s.texture" % (name, loc))
        with open(src, "rb") as f, open(staged, "wb") as g:
            g.write(f.read())
        out = os.path.join(stage, "%s.%s.dds" % (name, loc))
        if not _run(install, "atf2dds", staged, out, log):
            log("   %-34s the game's atf2dds would not convert it" % name)
            left += 1
            continue
        with open(out, "rb") as f:
            b = f.read()
        with open(os.path.join(workspace, name + ".dds"), "wb") as g:
            g.write(b)
        log("   %-34s %d bytes of dds" % (name, len(b)))
        n += 1
    log("   %d texture(s) out as .dds%s" % (n, ", %d left alone" % left if left else ""))
    log("   edit the .dds in Paint.NET or GIMP and save as DXT1 or DXT5, then run dds2atf")
    return n


def textures_in(workspace, install, log=print):
    """Edited .dds files back into the records, using the GAME'S OWN dds2atf."""
    stage = _tex_stage(install)
    n = 0
    for name, kind, archive, rel in _manifest_rows(workspace):
        if kind not in ("texture", "armor", "dig_map"):
            continue
        edited = os.path.join(workspace, name + ".dds")
        if not os.path.isfile(edited):
            continue
        loc = _tex_loc(archive, name)
        staged = os.path.join(stage, "%s.%s.dds" % (name, loc))
        with open(edited, "rb") as f, open(staged, "wb") as g:
            g.write(f.read())
        out = os.path.join(stage, "%s.%s.texture" % (name, loc))
        if not _run(install, "dds2atf", staged, out, log):
            log("   %-34s dds2atf would not convert it - is it saved as DXT1 or DXT5?" % name)
            continue
        with open(out, "rb") as f:
            b = f.read()
        dest = os.path.join(workspace, rel)
        before = open(dest, "rb").read() if os.path.isfile(dest) else None
        if before is not None and len(b) != len(before):
            log("   %-34s REFUSED - it converted to %d bytes and the record is %d. Records go back"
                " in place at a fixed offset, so a different length cannot be written."
                % (name, len(b), len(before)))
            continue
        with open(dest, "wb") as g:
            g.write(b)
        log("   %-34s %d bytes%s" % (name, len(b), " (unchanged)" if before == b else "  CHANGED"))
        n += 1
    log("   %d texture(s) back. Flat back will pick up the ones that changed." % n)
    return n


def write_index(out_dir, seen, what):
    """INDEX.txt - what came out, and what each kind of thing actually is.

    The extensions say what a file is. This says what to do with it, and is honest about the ones
    nothing here can open, because a folder of files nobody can identify is not a workspace.
    """
    lines = [what, ""]
    total_n = sum(v[0] for v in seen.values())
    total_b = sum(v[1] for v in seen.values())
    lines.append("%d record(s), %s" % (total_n, _mb(total_b)))
    lines.append("")
    for kind in sorted(seen, key=lambda k: -seen[k][1]):
        n, size = seen[kind]
        lines.append("  %-10s %-7s %6d file(s)  %12s" % (kind, kind_extension(kind), n, _mb(size)))
        note = KIND_NOTE.get(kind, "an unrecognised kind - left as .bin on purpose.")
        for i in range(0, len(note), 92):
            lines.append("        " + note[i:i + 92])
        lines.append("")
    lines += [
        "WHAT YOU CAN ACTUALLY EDIT BY HAND",
        "",
        "  Right now: .txt records, which are plain text, and .img, which is raw pixels.",
        "  Everything else comes out intact and goes back intact, but nothing in this tool",
        "  opens or converts it yet. That is not a limitation of the extraction - the bytes are",
        "  exactly what the game holds - it is the next piece of work.",
        "",
        "PUTTING THEM BACK",
        "",
        "  Edit anything you like, of any kind, as long as the LENGTH is unchanged. Flat back",
        "  compares md5 and only writes what actually changed, and it refuses a file whose size",
        "  changed because these go back in place at a recorded offset.",
        "",
    ]
    with open(os.path.join(out_dir, "INDEX.txt"), "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(chr(10).join(lines) + chr(10))




def find_archives(install, opstar=None, log=None):
    """Every AZP3 archive under the install, found by extension and then confirmed by its magic.

    Confirmed by magic rather than trusted by name, so a file that happens to be called .flatdata
    but is not one is never offered as if it were.
    """
    roots = [install]
    if opstar and os.path.abspath(opstar) != os.path.abspath(install):
        roots.append(opstar)
    out = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                if not fn.lower().endswith(ARCHIVE_EXT):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "rb") as f:
                        if f.read(4) != b"AZP3":
                            continue
                except OSError:
                    continue
                out.append(full)
    out.sort()
    if log:
        log("   %d archive(s) found" % len(out))
    return out


def archive_summary(path):
    """[(name, size, kind)] for an archive, biggest first - the shape of what is inside."""
    recs = azcf.archive_records(path)
    rows = [(n, r[1], r[2]) for n, r in recs.items()]
    rows.sort(key=lambda r: -r[1])
    return rows


def _mb(n):
    """A size a person can read."""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "bytes":
                return "%d bytes" % n
            return "%.1f %s" % (n, unit)
        n = n / 1024.0
    return "%d" % n


def _safe_name(name):
    """A record name as a filename. The mapping is kept in the manifest, so nothing is lost."""
    bad = "<>:" + chr(34) + "/" + chr(92) + "|?*"
    out = "".join(("_" if (c in bad or ord(c) < 32) else c) for c in name)
    return out.strip().rstrip(".") or "record"


def check_archive(path):
    """Is this an AZP3 archive, and does its directory agree with the file it lives in?

    The header says how many records there are and where the directory starts; each record says
    where it lives and how long it is. Where those disagree the archive is not safe to write into,
    so this says so BEFORE anything is touched rather than after.
    """
    import struct
    with open(path, "rb") as f:
        head = f.read(0x20)
    if head[:4] != b"AZP3":
        return False, "not an AZP3 archive - it starts with %r" % head[:4]
    count, = struct.unpack_from("<I", head, 0x04)
    end, = struct.unpack_from("<I", head, 0x10)
    size = os.path.getsize(path)
    base = end - count * azcf.ARCHIVE_ENTRY
    if count < 1 or base < 0 or end > size:
        return False, ("its header does not fit the file: %d records, directory ends at %d,"
                       " the file is %d" % (count, end, size))
    try:
        recs = azcf.archive_records(path)
    except Exception as exc:
        return False, "its directory cannot be read: %s" % exc
    if len(recs) != count:
        return False, "%d records in the header, %d named in the directory" % (count, len(recs))
    over = [(n, r) for n, r in recs.items() if r[0] + r[1] > size]
    if over:
        return False, ("%d record(s) claim to run past the end of the file, e.g. %s"
                       % (len(over), over[0][0]))
    return True, "%d record(s), %s" % (count, _mb(size))


def install_of(path):
    """The game root an archive lives under, so starter.exe can be given a relative path."""
    p = os.path.abspath(path)
    marker = os.sep + "data" + os.sep
    if marker in p:
        return p.split(marker)[0]
    marker = os.sep + "users" + os.sep
    if marker in p:
        return p.split(marker)[0]
    raise SystemExit("cannot tell which game %s belongs to" % path)


def _run_into(install, prog, src, folder, log):
    """A call whose output is a FOLDER, which is what unflat wants.

    Success cannot be judged by a destination file, so it is judged by whether the folder
    gained anything. These programs print 'Converted!' whatever happens, so their output is
    no guide to anything.
    """
    import build
    os.makedirs(folder, exist_ok=True)
    before = set(os.listdir(folder))
    try:
        build.starter(install, prog + ",", build.rel(src, install) + ",",
                      build.rel(folder, install))
    except BaseException:
        pass
    return sorted(set(os.listdir(folder)) - before)

def stage_archive(install, path):
    """A copy of an archive where starter.exe can see it.

    The game's unflat only takes paths relative to the game root, so an archive from anywhere
    else has to be copied in first. The copy is byte for byte, so every offset, size and md5
    taken from it is true of the original - and the manifest still points at the ORIGINAL,
    because flat back writes with ordinary file access and can reach anywhere. Staging is only
    ever needed to READ.
    """
    import shutil
    d = os.path.join(install, "users", "modwork", "sabow_ext", "unflat")
    os.makedirs(d, exist_ok=True)
    staged = os.path.join(d, os.path.basename(path))
    shutil.copy2(path, staged)
    return staged

def unflat(path, out_dir, install=None, log=print, only=None, limit=None):
    """Open an archive with the GAME'S OWN unflat, then write our manifest over the result.

    The official tool names every file <name>.<loc>.<kind> and leaves a .!flatlist beside them. The
    extension is the interface and the locale comes from the archive directory - the field the
    hand-written extractor read and threw away. It also does not collapse records that share a
    name, which the hand-written one did.

    Our manifest is still written on top of it, because the manifest is what makes a WRITE safe:
    archive, offset, size and md5 for every record, so the repack can put a changed file back in
    place and can refuse when the archive has moved on underneath it. The game's tool builds whole
    archives; it does not know how to be careful about one record, and that is our job.

    only / limit  choose which records get a manifest row. The game's tool has no such option and
                  unpacks everything, so the folder can hold more than the manifest mentions. That
                  is harmless: only manifest rows are ever written back.
    """
    import build
    import hashlib
    import datetime
    import settings
    here = None
    try:
        here = install_of(path)
    except SystemExit:
        here = None
    if install is None:
        install = here or settings.get("sandbox")
        if not install:
            raise SystemExit("cannot tell which game %s belongs to, and no game is configured"
                             " - pass install=" % path)
    # the game's tool can only read a file it can see from the game root
    source = path if here else stage_archive(install, path)
    if source != path:
        log("   %s is outside the game, so a copy was staged in users/modwork to read it"
            % os.path.basename(path))
    os.makedirs(out_dir, exist_ok=True)
    man_path = os.path.join(out_dir, "manifest.txt")
    if os.path.isfile(man_path):
        raise SystemExit("%s already holds a workspace - give unflat a fresh folder, so that one"
                         " archive never writes into another one's manifest" % out_dir)
    ok, why = check_archive(path)
    if not ok:
        raise SystemExit("%s cannot be unflattened: %s" % (os.path.basename(path), why))
    log("   unflattening %s with the game's own unflat" % os.path.basename(path))
    made = _run_into(install, "unflat", source, out_dir, log)
    if not made:
        raise SystemExit("the game's unflat produced nothing for %s - out/i_unflat.log says why"
                         % os.path.basename(path))

    entries = azcf.archive_entries(path)
    if only:
        entries = [e for e in entries if only.lower() in e[0].lower()]
    man = ["# %s - unflattened %s"
           % (path, datetime.datetime.now().isoformat(timespec="seconds")),
           "# name | kind | archive | offset | size | md5 | written-as", ""]
    seen = {}
    n = missed = 0
    for name, off, size, kind, loc in entries:
        rel = "%s.%s.%s" % (name, loc or "loc_def", kind)
        full = os.path.join(out_dir, rel)
        if not os.path.isfile(full):
            missed += 1
            continue
        with open(full, "rb") as f:
            b = f.read()
        man.append("%s | %s | %s | %d | %d | %s | %s"
                   % (name, kind, path, off, size, hashlib.md5(b).hexdigest(), rel))
        seen[kind] = (seen.get(kind, (0, 0))[0] + 1, seen.get(kind, (0, 0))[1] + size)
        n += 1
    with open(man_path, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(chr(10).join(man) + chr(10))
    write_index(out_dir, seen, "%s - what came out" % os.path.basename(path))
    readme = chr(10).join([
        "%s - unflattened by the game's own unflat." % os.path.basename(path),
        "",
        "files are named <name>.<locale>.<kind>, which is the game's own convention and the reason",
        "its tools recognise them. The .!flatlist is what the game's mkflat reads to rebuild an",
        "archive. manifest.txt is ours, and is what makes putting one file back safe.",
        "",
        "TO CHANGE ONE: edit it, then flat back. Only files whose md5 actually changed are written,",
        "each is backed up first, and a file whose SIZE changed is refused because these go back in",
        "place at a recorded offset.",
        "",
        "Nothing in the game has been changed by unflattening.",
    ])
    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(readme + chr(10))
    log("   %d record(s) in the manifest, %d file(s) the game's tool produced"
        % (n, len(made)))
    if missed:
        log("   %d record(s) are in the archive but not on disk - named oddly, or a name clash"
            % missed)
    return man_path


def check_build(install, opstar=gtos_opstar.OPSTAR, log=print):
    """WILL WHAT I HAVE NOW ACTUALLY BUILD? Every validator, current settings, nothing installed.

    A different question from check_tool(), and the one that stops you at the Build button.
    check_tool() answers "have the proven builds drifted?" - it rebuilds history and compares, which
    protects the past and says nothing about the next build. A green Check the tool meant exactly
    that, and nothing more, which is how three guards written for a single-vehicle world got through.

    Runs the whole pipeline to a throwaway zip: no version, no log entry, nothing installed, the game
    folder untouched. When it passes, Build will succeed.
    """
    log("")
    log("CHECKING THE BUILD - the whole pipeline against your current settings")
    log("   every validator, nothing installed, no version spent")
    log("")
    scratch = os.path.join(work_dir(install), "check_build.zip")
    try:
        build_ai(999, install, opstar, ADDON_VEHICLES, log=log, zip_path=scratch)
    except (SystemExit, Exception) as e:
        log("")
        log("BUILD WOULD STOP: %s" % e)
        log("")
        log("   That is where the Build button would have stopped too. Nothing was installed and no")
        log("   version was spent - this cost four minutes and nothing else.")
        return False
    finally:
        if os.path.isfile(scratch):
            os.remove(scratch)
    log("")
    log("BUILD IS CLEAN - every validator passed. Build now and it will succeed.")
    return True


def check_tool(install, opstar=gtos_opstar.OPSTAR, log=print):
    """Rebuild every proven build into a scratch zip and compare it part by part. True only if all match."""
    ok = True
    for version, proven, vehicles, options in PROVEN:
        if not os.path.isfile(proven):
            log("MISSING proven build %s" % proven)
            ok = False
            continue
        scratch = os.path.join(work_dir(install), "check_tool_v%03d.zip" % version)
        log("Rebuilding %s from scratch ..." % (LABEL % version))
        build_ai(version, install, opstar, vehicles, log=lambda s: None, zip_path=scratch, **options)
        # The spec is checked BEFORE the bytes, because it says WHY they differ. Without it a
        # drifted setting reads as "12 parts differ" and looks like a regression in the tool.
        for veh, eff in sorted(EFFECTIVE_SPECS.items()):
            if not check_proven_spec(version, veh, eff, log):
                ok = False
        a, b = zip_parts(proven), zip_parts(scratch)
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if diff:
            ok = False
            log("WRONG  %s: %d of %d parts differ: %s" % (LABEL % version, len(diff), len(set(a) | set(b)), ", ".join(diff)))
        else:
            log("RIGHT  %s: all %d parts identical to the proven build" % (LABEL % version, len(a)))
        os.remove(scratch)
    return ok


def events(log_path):
    import buildlog
    return [e for e in buildlog.rows(log_path) if re.match(r"^gtos_ww2 v\d+$", e["version"])]


def next_version(log_path):
    built = [int(e["version"].split("v")[-1]) for e in events(log_path) if e["what"] == "BUILT"]
    return (max(built) + 1) if built else 1


def lock(log_path):
    """(locked, reason) - one build, one look, one line: no new build while the newest has no GOOD/BAD."""
    ev = events(log_path)
    built = [e for e in ev if e["what"] == "BUILT"]
    if not built:
        return False, "no GTOS builds yet"
    last = built[-1]["version"]
    after = ev[ev.index(built[-1]) + 1:]
    if any(e["what"] in ("GOOD", "BAD") and e["version"] == last for e in after):
        return False, "%s has its result" % last
    return True, "%s has no GOOD or BAD line yet - install it, look, and write one line in 5" % last


def record(log_path, backup_root, version, vehicles, verdict, line, zpath):
    """murkz's one line as a GOOD/BAD row; a GOOD build is backed up and checked by md5. Returns a message."""
    import buildlog
    label = LABEL % version
    digest = hashlib.md5(open(zpath, "rb").read()).hexdigest()
    notes = "murkz: \"%s\". Zip %s md5 %s." % (line, zpath, digest)
    msg = "Saved: %s for %s." % (verdict, label)
    if verdict == "GOOD":
        folder = os.path.join(backup_root, BACKUP_NAME % (version, "_".join(v.upper() for v in vehicles)))
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, os.path.basename(zpath))
        shutil.copy2(zpath, dest)
        if hashlib.md5(open(dest, "rb").read()).hexdigest() != digest:
            raise SystemExit("the backup copy does not match - nothing was saved")
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("%s - %s\nmurkz: %s\nmd5 %s\n" % (label, ", ".join(vehicles), line, digest))
        notes += " Backed up to %s." % folder
        msg += " Backed up as proven."
    buildlog.append(log_path, verdict, label, notes)
    return msg


load_user_vehicles()          # murkz's own vehicles join VEHICLES / ADDON_VEHICLES on import


if __name__ == "__main__":
    import settings
    # every subcommand, so a new one cannot be added and then silently fall through to the
    # old build path - which is exactly what happened when techn-show was added.
    _CMDS = ("list", "extract", "repack", "archives", "contents", "unflat", "check-archive",
             "flatback", "atf2dds", "dds2atf", "configs-out", "configs-in",
             "techn-show", "techn-set", "techn-list")
    if len(sys.argv) > 1 and (sys.argv[1] in _CMDS or sys.argv[1] in ("-h", "--help")):
        raise SystemExit(main(sys.argv[1:]))
    # The older form, still here so any wrapper or habit keeps working:
    #   gtos_vehicle.py [install] [version]     - build that version
    _fresh = sys.argv[1] if len(sys.argv) > 1 else settings.get("sandbox")
    _ver = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    build_ai(_ver, _fresh, settings.get("opstar"))
