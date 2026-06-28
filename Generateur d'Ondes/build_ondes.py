#!/usr/bin/env python3
"""Generate Generateur d'Ondes Max for Live device (single flat patcher)."""

import json
import re
import struct
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent
FACTORY_AMXD = Path(
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Misc/Max Devices/Max Instrument.amxd"
)
M4L_TEMPLATE_AMXD = Path(
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Max/Max.app/Contents/Resources/C74/packages/BEAP/Examples/Synthesis Examples/Example M4L Instrument.amxd"
)

_id_counter = 0


def uid(prefix="obj"):
    global _id_counter
    _id_counter += 1
    return f"{prefix}-{_id_counter}"


def reset_ids():
    global _id_counter
    _id_counter = 0


APPVERSION = {
    "major": 8,
    "minor": 1,
    "revision": 2,
    "architecture": "x64",
    "modernui": 1,
}


def base_patcher(**overrides):
    p = {
        "fileversion": 1,
        "appversion": deepcopy(APPVERSION),
        "classnamespace": "box",
        "rect": [34.0, 89.0, 1100.0, 900.0],
        "openrect": [0.0, 0.0, 0.0, 0.0],
        "bglocked": 0,
        "openinpresentation": 0,
        "default_fontsize": 12.0,
        "default_fontface": 0,
        "default_fontname": "Arial",
        "gridonopen": 1,
        "gridsize": [15.0, 15.0],
        "gridsnaponopen": 1,
        "statusbarvisible": 2,
        "toolbarvisible": 1,
        "boxanimatetime": 200,
        "imprint": 0,
        "enablehscroll": 1,
        "enablevscroll": 1,
        "devicewidth": 600.0,
        "description": "",
        "digest": "",
        "tags": "",
        "boxes": [],
        "lines": [],
    }
    p.update(overrides)
    return p


class PatcherBuilder:
    """Flat Max for Live patcher builder with monotonic object ids."""

    def __init__(self, presentation=False, device_width=600.0):
        self.presentation = presentation
        self.patcher = base_patcher(
            openinpresentation=1 if presentation else 0,
            devicewidth=device_width,
        )
        self.boxes = {}
        self.lines = []

    def add(self, maxclass, text="", x=50, y=50, w=None, h=18, **extra):
        oid = extra.pop("id", uid())
        presentation = extra.pop("presentation", None)
        numinlets = extra.pop("numinlets", 1)
        outlettype = extra.pop("outlettype", [""])
        numoutlets = extra.pop("numoutlets", len(outlettype))

        if w is None:
            w = max(28, len(text) * 7 + 16)

        box_data = {
            "id": oid,
            "maxclass": maxclass,
            "numinlets": numinlets,
            "numoutlets": numoutlets,
            "patching_rect": [float(x), float(y), float(w), float(h)],
            **extra,
        }
        if outlettype is not None:
            box_data["outlettype"] = outlettype
        if text:
            box_data["text"] = text
        if maxclass == "newobj":
            box_data.setdefault("fontsize", 10.0)
            box_data.setdefault("fontname", "Arial Bold")
            box_data.setdefault("saved_object_attributes", {})

        box = {"box": box_data}
        if self.presentation and (maxclass.startswith("live.") or presentation):
            box["box"]["presentation"] = 1
            box["box"]["presentation_rect"] = [float(x), float(y), float(w), float(h)]
        self.boxes[oid] = box["box"]
        self.patcher["boxes"].append(box)
        return oid

    def connect(self, src, src_outlet, dst, dst_inlet, midpoints=None):
        line = {
            "patchline": {
                "source": [src, src_outlet],
                "destination": [dst, dst_inlet],
            }
        }
        if midpoints:
            line["patchline"]["midpoints"] = midpoints
        self.lines.append(line)

    def build(self):
        self.patcher["lines"] = self.lines
        return {"patcher": self.patcher}


def add_dial(b, x, y, longname, shortname, mmin, mmax, initial, unitstyle=0, steps=None):
    attrs = {
        "valueof": {
            "parameter_longname": longname,
            "parameter_shortname": shortname,
            "parameter_type": 0,
            "parameter_unitstyle": unitstyle,
            "parameter_mmin": float(mmin),
            "parameter_mmax": float(mmax),
            "parameter_initial_enable": 1,
            "parameter_initial": [float(initial)],
        }
    }
    if steps is not None:
        attrs["valueof"]["parameter_steps"] = steps
    return b.add(
        "live.dial",
        "",
        x,
        y,
        44,
        44,
        numinlets=1,
        numoutlets=2,
        outlettype=["", ""],
        parameter_enable=1,
        saved_attribute_attributes=attrs,
    )


def add_tab(b, x, y, w, longname, shortname, enum, initial=0, h=20):
    return b.add(
        "live.tab",
        "",
        x,
        y,
        w,
        h,
        numinlets=1,
        numoutlets=len(enum) + 1,
        outlettype=["int"] + [""] * len(enum),
        parameter_enable=1,
        saved_attribute_attributes={
            "valueof": {
                "parameter_longname": longname,
                "parameter_shortname": shortname,
                "parameter_type": 2,
                "parameter_enum": enum,
                "parameter_initial_enable": 1,
                "parameter_initial": [initial],
            }
        },
    )


def _build_ui(b):
    """Two compact presentation rows that fit Live's fixed device height.

    Live's device area is a fixed height (~168 px); anything taller is clipped
    and the lower controls become unreachable, so every control lives in two
    rows. live.dial/live.tab render their own name + value, so only the tab
    objects (which have no built-in label) get explicit comments.
    """
    c = SimpleNamespace()
    PANEL_X, PANEL_W = 8, 804

    def label(text, x, y, w=70, fontsize=9.0):
        b.add("live.comment", text, x, y, w, 14, presentation=1, fontsize=fontsize)

    # Row backgrounds live in the dedicated background layer (background:1) so
    # they always render behind the foreground controls.
    b.add(
        "panel", "", PANEL_X, 4, PANEL_W, 78, numinlets=1, numoutlets=0, outlettype=[],
        presentation=1, background=1, bgcolor=[0.22, 0.16, 0.13, 1.0],
        bordercolor=[0.46, 0.33, 0.26, 1.0], border=1, rounded=8,
    )
    b.add(
        "panel", "", PANEL_X, 86, PANEL_W, 78, numinlets=1, numoutlets=0, outlettype=[],
        presentation=1, background=1, bgcolor=[0.15, 0.17, 0.19, 1.0],
        bordercolor=[0.32, 0.37, 0.41, 1.0], border=1, rounded=8,
    )

    # Row 1: performance (uniform 56 px dial grid), grouped vib / trem / pitch.
    # Rate dials use the Hz unit style (3) and free-running Hz ranges -- never
    # tempo-synced -- so they can be smoothly swept by hand or MIDI CC.
    c.d_expr = add_dial(b, 16, 22, "Expression", "Expr", 0, 1, 0.85, unitstyle=1)
    c.d_expr_atk = add_dial(b, 72, 22, "Attack", "Atk", 0, 3000, 80, unitstyle=2)
    c.d_expr_rel = add_dial(b, 128, 22, "Release", "Rel", 0, 5000, 350, unitstyle=2)
    c.d_vib_depth = add_dial(b, 184, 22, "Vibrato Depth", "Vib Dp", 0, 1, 0.25, unitstyle=1)
    c.d_vib_rate = add_dial(b, 240, 22, "Vibrato Rate", "Vib Rt", 0.1, 12.0, 5.5, unitstyle=3)
    c.d_trem = add_dial(b, 296, 22, "Tremolo Depth", "Trem Dp", 0, 0.5, 0.08, unitstyle=1)
    c.d_trem_rate = add_dial(b, 352, 22, "Tremolo Rate", "Trem Rt", 0.1, 12.0, 4.0, unitstyle=3)
    c.d_glide = add_dial(b, 408, 22, "Glide Time", "Glide", 0, 500, 120, unitstyle=2)
    c.d_bend = add_dial(b, 464, 22, "Pitch Bend Range", "Bend", 0, 12, 2, unitstyle=7, steps=13)
    c.d_ribbon = add_dial(b, 520, 22, "Ribbon", "Ribbon", -2, 2, 0, unitstyle=7)
    c.d_intensity = add_dial(b, 576, 22, "Intensity", "Intens", 0, 1, 0, unitstyle=1)

    # --- Vintage engraved nameplate in the empty pocket right of row 1 ---
    # Plain `comment` objects (not parameters) carry the title so we can apply
    # the American Typewriter face + aged-ink colours locally, without touching
    # the default font used by every other control.
    INK = [0.91, 0.85, 0.69, 1.0]   # aged ivory
    BRASS = [0.69, 0.55, 0.34, 1.0]  # tarnished brass

    def title(text, x, y, w, h, size, color, face=1):
        b.add(
            "comment", text, x, y, w, h, numinlets=1, numoutlets=0, outlettype=[],
            presentation=1, fontname="American Typewriter", fontsize=float(size),
            fontface=face, textjustification=1, textcolor=color,
        )

    # Engraved plate sits behind the lettering (background layer).
    b.add(
        "panel", "", 626, 8, 184, 70, numinlets=1, numoutlets=0, outlettype=[],
        presentation=1, background=1, bgcolor=[0.18, 0.13, 0.10, 1.0],
        bordercolor=[0.60, 0.46, 0.30, 1.0], border=1, rounded=6,
    )
    title("Générateur", 630, 12, 176, 22, 16, INK)
    title("d'Ondes", 630, 33, 176, 22, 16, INK)
    b.add(  # hairline rule under the title
        "panel", "", 672, 57, 92, 1, numinlets=1, numoutlets=0, outlettype=[],
        presentation=1, background=1, bgcolor=BRASS, border=0, rounded=0,
    )
    title("— ONDES MUSICALES —", 630, 60, 176, 12, 7, BRASS, face=0)

    # Row 2: tone + master (tabs need explicit labels)
    label("Timbre", 16, 89, 56)
    c.d_timbre = add_tab(b, 16, 104, 150, "Timbre", "Timbre", ["O", "C", "G", "N", "8"], 0, h=22)
    label("Diffuseur", 174, 89, 90)
    c.d_diff = add_tab(
        b, 174, 104, 220, "Diffuseur", "Diff",
        ["Principal", "Metallique", "Palme", "Resonance"], 2, h=22,
    )
    c.d_cutoff = add_dial(b, 402, 104, "Filter Cutoff", "Cutoff", 200, 6000, 3200, unitstyle=3)
    c.d_res = add_dial(b, 458, 104, "Filter Resonance", "Res", 0, 0.4, 0.15, unitstyle=1)
    c.d_triode = add_dial(b, 514, 104, "Triode Drive", "Triode", 0, 1, 0.2, unitstyle=1)
    c.d_drift = add_dial(b, 570, 104, "Analog Drift", "Drift", 0, 1, 0, unitstyle=1)
    c.d_track = add_dial(b, 626, 104, "Expression to Cutoff", "Track", 0, 1, 0.2, unitstyle=1)
    c.d_gain = add_dial(b, 682, 104, "Master Gain", "Gain", -60, 0, -12, unitstyle=4)
    c.d_sat = add_dial(b, 738, 104, "Saturation", "Sat", 0, 0.3, 0.02, unitstyle=1)
    return c


def _build_midi_inputs(b, n):
    n.notein = b.add("newobj", "notein", 40, 180, 45, 22, numoutlets=2, outlettype=["int", "int"])
    n.bendin = b.add("newobj", "bendin", 120, 180, 45, 22, numoutlets=1, outlettype=["int"])
    n.ctlin = b.add("newobj", "ctlin 11", 200, 180, 55, 22, numoutlets=1, outlettype=["int"])
    n.vib_cc = b.add("newobj", "ctlin 1", 360, 180, 50, 22, numoutlets=1, outlettype=["int"])
    n.touchin = b.add("newobj", "touchin", 280, 180, 50, 22, numoutlets=1, outlettype=["int"])


def _build_pitch(b, n):
    """note + bend + ribbon -> mtof -> clamp -> line~ glide."""
    n.stripnote = b.add("newobj", "stripnote", 40, 230, 65, 22, numinlets=2, numoutlets=2, outlettype=["int", "int"])
    n.note_store = b.add("newobj", "f 60", 40, 270, 40, 22)
    n.bend_store = b.add("newobj", "f 64", 120, 230, 55, 22)
    n.bend_trig = b.add("newobj", "t b f", 120, 270, 40, 22, numinlets=1, numoutlets=2)
    n.bend_range_f = b.add("newobj", "f 2", 170, 230, 35, 22)
    n.ribbon_f = b.add("newobj", "f 0", 170, 270, 35, 22)
    n.ribbon_trig = b.add("newobj", "t b f", 170, 310, 40, 22, numinlets=1, numoutlets=2)
    n.bend_range_trig = b.add("newobj", "t b f", 220, 230, 40, 22, numinlets=1, numoutlets=2)
    n.pitch_expr = b.add("newobj", "expr $f1+(($f2-64.)/64.)*$f3+$f4", 280, 270, 210, 22, numinlets=4)
    n.pitch_bang = b.add("newobj", "t b b b b", 280, 230, 55, 22, numinlets=1, numoutlets=4)
    n.mtof = b.add("newobj", "mtof", 280, 310, 40, 22, numinlets=1)
    n.freq_clip_msg = b.add("newobj", "expr min(max($f1\\,20.)\\,4000.)", 280, 350, 170, 22, numinlets=1)
    n.freq_target = b.add("newobj", "f 440", 280, 390, 45, 22)
    n.glide_amt_f = b.add("newobj", "f 120", 340, 390, 45, 22)
    n.glide_pack = b.add("newobj", "pack f f", 340, 430, 55, 22, numinlets=2, numoutlets=1)
    n.freq_line = b.add("newobj", "line~", 340, 470, 45, 22, numinlets=2, outlettype=["signal"])
    n.pitch_init = b.add("newobj", "loadmess bang", 40, 310, 85, 22, numinlets=1, numoutlets=1)


def _build_modulation(b, n):
    """Analog drift, periodic vibrato, tremolo, and the intensity fan-out."""
    # Analog drift on frequency
    n.drift_f = b.add("newobj", "f 0", 420, 390, 35, 22)
    n.drift_sig = b.add("newobj", "sig~", 420, 430, 35, 22, outlettype=["signal"])
    n.drift_noise = b.add("newobj", "noise~", 480, 390, 50, 22, numinlets=1, outlettype=["signal"])
    n.drift_lpf = b.add("newobj", "onepole~ 0.999", 480, 430, 95, 22, numinlets=1, outlettype=["signal"])
    n.drift_scale = b.add("newobj", "*~ 3.", 480, 470, 50, 22, numinlets=2, outlettype=["signal"])
    n.freq_drift = b.add("newobj", "+~", 400, 510, 35, 22, numinlets=2, outlettype=["signal"])
    n.freq_clip_sig = b.add("newobj", "clip~ 20 4000", 400, 550, 90, 22, numinlets=1, outlettype=["signal"])

    # Vibrato (periodic pitch LFO, Greenwood-style hand vibrato). The rate is
    # smoothed through line~ so dial/CC sweeps of the frequency never zipper.
    n.vib_rate_f = b.add("newobj", "f 5.5", 520, 360, 45, 22)
    n.vib_rate_pack = b.add("newobj", "pack f 50", 520, 400, 60, 22, numinlets=2, numoutlets=1)
    n.vib_rate_line = b.add("newobj", "line~", 520, 440, 45, 22, numinlets=2, outlettype=["signal"])
    n.vib_lfo = b.add("newobj", "cycle~ 5.5", 560, 480, 75, 22, numinlets=2, outlettype=["signal"])
    n.vib_depth_f = b.add("newobj", "f 0.25", 620, 390, 45, 22)
    n.vib_wheel_scale = b.add("newobj", "/ 127.", 360, 230, 45, 22, numinlets=1)
    n.vib_depth_merge = b.add("newobj", "expr max($f1\\,max($f2\\,$f3))", 620, 430, 170, 22, numinlets=3)
    n.vib_note_t = b.add("newobj", "t f b", 40, 330, 40, 22, numinlets=1, numoutlets=2)
    n.vib_bloom_trig = b.add("newobj", "t b b", 620, 470, 40, 22, numinlets=1, numoutlets=2)
    n.vib_bloom_zero = b.add("newobj", "message 0", 580, 510, 65, 22, numinlets=2, numoutlets=1)
    n.vib_bloom_pack = b.add("newobj", "pack f 500", 660, 510, 65, 22, numinlets=2, numoutlets=1)
    n.vib_bloom_line = b.add("newobj", "line~ 0", 660, 550, 55, 22, numinlets=2, outlettype=["signal"])
    n.vib_depth_scale = b.add("newobj", "*~ 0.04", 660, 590, 60, 22, numinlets=2, outlettype=["signal"])
    n.vib_mod = b.add("newobj", "*~", 560, 550, 35, 22, numinlets=2, outlettype=["signal"])
    n.vib_one = b.add("newobj", "sig~ 1.", 520, 590, 55, 22, numinlets=0, outlettype=["signal"])
    n.vib_factor = b.add("newobj", "+~", 560, 590, 35, 22, numinlets=2, outlettype=["signal"])
    n.vib_apply = b.add("newobj", "*~", 480, 550, 35, 22, numinlets=2, outlettype=["signal"])

    # Tremolo (amplitude mod) — independent free-running LFO with its own
    # line~-smoothed rate, so vibrato and tremolo frequencies move separately.
    n.trem_rate_f = b.add("newobj", "f 4", 820, 360, 45, 22)
    n.trem_rate_pack = b.add("newobj", "pack f 50", 820, 400, 60, 22, numinlets=2, numoutlets=1)
    n.trem_rate_line = b.add("newobj", "line~", 820, 440, 45, 22, numinlets=2, outlettype=["signal"])
    n.trem_lfo = b.add("newobj", "cycle~ 4", 820, 480, 60, 22, numinlets=2, outlettype=["signal"])
    n.trem_depth_f = b.add("newobj", "f 0.08", 760, 470, 45, 22)
    n.trem_depth_sig = b.add("newobj", "sig~", 760, 510, 35, 22, outlettype=["signal"])
    n.trem_mod = b.add("newobj", "*~", 720, 550, 35, 22, numinlets=2, outlettype=["signal"])
    n.trem_factor = b.add("newobj", "+~ 1.", 720, 590, 45, 22, numinlets=2, outlettype=["signal"])
    n.trem_apply = b.add("newobj", "*~", 150, 1270, 35, 22, numinlets=2, outlettype=["signal"])

    # Intensity macro fan-out (vibrato + triode get a live recompute)
    n.intens_vib_tbf = b.add("newobj", "t b f", 700, 150, 45, 22, numinlets=1, numoutlets=2)
    n.intens_tri_tbf = b.add("newobj", "t b f", 760, 150, 45, 22, numinlets=1, numoutlets=2)


def _build_oscillators(b, n):
    """Heterodyne-inspired O/C/G/N/8 timbres feeding the timbre selector."""
    n.osc_o = b.add("newobj", "cycle~", 40, 620, 50, 22, numinlets=2, outlettype=["signal"])
    n.osc_c = b.add("newobj", "tri~", 120, 620, 40, 22, numinlets=2, outlettype=["signal"])
    n.creux_clip = b.add("newobj", "clip~ -0.6 0.6", 120, 660, 95, 22, numinlets=1, outlettype=["signal"])
    n.creux_norm = b.add("newobj", "*~ 0.85", 120, 700, 55, 22, numinlets=2, outlettype=["signal"])
    n.creux_lvl = b.add("newobj", "sig~ 1.", 180, 700, 45, 22, numinlets=0, outlettype=["signal"])
    n.osc_g = b.add("newobj", "rect~ 1 0.5", 220, 620, 70, 22, numinlets=3, outlettype=["signal"])
    n.osc_n = b.add("newobj", "rect~ 1 0.12", 300, 620, 75, 22, numinlets=3, outlettype=["signal"])
    n.osc_8_base = b.add("newobj", "cycle~", 340, 620, 50, 22, numinlets=2, outlettype=["signal"])
    n.oct_freq = b.add("newobj", "*~ 2", 400, 620, 40, 22, numinlets=2, outlettype=["signal"])
    n.oct_mul = b.add("newobj", "sig~ 2.", 450, 620, 45, 22, numinlets=0, outlettype=["signal"])
    n.osc_8_hi = b.add("newobj", "cycle~", 400, 660, 50, 22, numinlets=2, outlettype=["signal"])
    n.osc_8_lo = b.add("newobj", "*~ 0.6", 340, 700, 50, 22, numinlets=2, outlettype=["signal"])
    n.osc_8_hi_gain = b.add("newobj", "*~ 0.4", 440, 660, 50, 22, numinlets=2, outlettype=["signal"])
    n.osc_8_lvl = b.add("newobj", "sig~ 1.", 500, 660, 45, 22, numinlets=0, outlettype=["signal"])
    n.osc_8_mix = b.add("newobj", "+~", 380, 740, 35, 22, numinlets=2, outlettype=["signal"])
    n.timbre_inc = b.add("newobj", "+ 1", 40, 780, 35, 22, numinlets=1)
    n.timbre_sel = b.add(
        "newobj", "selector~ 5 1", 40, 820, 95, 22, numinlets=6, numoutlets=1, outlettype=["signal"]
    )


def _build_voice(b, n):
    """Triode coloration, voicing filter, and expression -> cutoff tracking."""
    # Triode coloration (drive into tanh, no DC offset)
    n.triode_amt = b.add("newobj", "expr 1.+($f1+$f2*0.5)*4.", 100, 870, 150, 22, numinlets=2)
    n.triode_amt_sig = b.add("newobj", "sig~", 100, 910, 35, 22, numinlets=0, outlettype=["signal"])
    n.triode_pre = b.add("newobj", "*~", 40, 950, 35, 22, numinlets=2, outlettype=["signal"])
    n.triode_shaper = b.add("newobj", "tanh~", 40, 990, 45, 22, numinlets=1, outlettype=["signal"])
    n.triode_out = b.add("newobj", "*~ 0.6", 40, 1030, 55, 22, numinlets=2, outlettype=["signal"])
    n.triode_init = b.add("newobj", "loadmess 0.2", 220, 870, 90, 22)

    # Voicing filter
    n.cutoff_f = b.add("newobj", "f 3200", 200, 870, 55, 22)
    n.cutoff_clip = b.add("newobj", "expr min(max($f1\\,200.)\\,6000.)", 200, 910, 180, 22, numinlets=1)
    n.cutoff_sig = b.add("newobj", "sig~", 200, 950, 35, 22, outlettype=["signal"])
    n.res_f = b.add("newobj", "f 0.15", 260, 870, 45, 22)
    n.res_clip = b.add("newobj", "expr min($f1\\,0.4)", 260, 910, 100, 22, numinlets=1)
    n.res_sig = b.add("newobj", "sig~", 260, 950, 35, 22, outlettype=["signal"])
    n.filt = b.add("newobj", "lores~", 200, 990, 50, 22, numinlets=3, outlettype=["signal"])
    n.filt_clip = b.add("newobj", "clip~ -1 1", 200, 1030, 65, 22, numinlets=1, outlettype=["signal"])
    n.cutoff_init = b.add("newobj", "loadmess 3200", 200, 830, 95, 22)
    n.res_init = b.add("newobj", "loadmess 0.15", 260, 830, 90, 22)

    # Expression -> cutoff tracking (+ Intensity macro opens the filter)
    n.track_f = b.add("newobj", "f 0.2", 320, 870, 45, 22)
    n.track_sig = b.add("newobj", "sig~", 320, 910, 35, 22, outlettype=["signal"])
    n.track_exprmul = b.add("newobj", "*~", 360, 950, 35, 22, numinlets=2, outlettype=["signal"])
    n.track_hz = b.add("newobj", "*~ 3000.", 360, 990, 65, 22, numinlets=2, outlettype=["signal"])
    n.intens_cut_f = b.add("newobj", "f 0", 440, 870, 35, 22)
    n.intens_cut_sig = b.add("newobj", "sig~", 440, 910, 35, 22, outlettype=["signal"])
    n.intens_cut_hz = b.add("newobj", "*~ 2500.", 440, 950, 65, 22, numinlets=2, outlettype=["signal"])
    n.cutoff_sum1 = b.add("newobj", "+~", 360, 1030, 35, 22, numinlets=2, outlettype=["signal"])
    n.cutoff_sum2 = b.add("newobj", "+~", 320, 1070, 35, 22, numinlets=2, outlettype=["signal"])
    n.cutoff_safe = b.add("newobj", "clip~ 100 7000", 320, 1110, 95, 22, numinlets=1, outlettype=["signal"])


def _build_diffuseurs(b, n):
    """Speaker emulations: Principal / Metallique / Palme / Resonance.

    res*-prefixed names belong to the voicing-filter resonance; the Resonance
    *diffuseur* uses the resd_ prefix to keep the two clearly distinct.
    """
    n.diff_inc = b.add("newobj", "+ 1", 400, 870, 35, 22, numinlets=1)
    n.diff_sel = b.add(
        "newobj", "selector~ 4 1", 400, 1030, 95, 22, numinlets=5, numoutlets=1, outlettype=["signal"]
    )

    # Principal: gentle HF rolloff
    n.principal = b.add("newobj", "onepole~ 8000", 400, 910, 95, 22, numinlets=1, outlettype=["signal"])

    # Metallique: inharmonic reson~ bank, dry/wet
    n.met_dry = b.add("newobj", "*~ 0.75", 500, 910, 55, 22, numinlets=2, outlettype=["signal"])
    n.met_wet = b.add("newobj", "+~", 500, 990, 35, 22, numinlets=2, outlettype=["signal"])
    n.met_r1 = b.add("newobj", "reson~ 0.5 900 12", 560, 910, 110, 22, numinlets=4, outlettype=["signal"])
    n.met_r2 = b.add("newobj", "reson~ 0.4 1370 14", 560, 950, 115, 22, numinlets=4, outlettype=["signal"])
    n.met_r3 = b.add("newobj", "reson~ 0.35 2100 16", 560, 990, 120, 22, numinlets=4, outlettype=["signal"])
    n.met_g1 = b.add("newobj", "*~ 0.12", 670, 910, 50, 22, numinlets=2, outlettype=["signal"])
    n.met_g2 = b.add("newobj", "*~ 0.10", 670, 950, 50, 22, numinlets=2, outlettype=["signal"])
    n.met_g3 = b.add("newobj", "*~ 0.08", 670, 990, 50, 22, numinlets=2, outlettype=["signal"])
    n.met_wet2 = b.add("newobj", "+~", 670, 1030, 35, 22, numinlets=2, outlettype=["signal"])
    n.met_lvl = b.add("newobj", "sig~ 1.", 730, 910, 45, 22, numinlets=0, outlettype=["signal"])
    n.met_wet_gain = b.add("newobj", "*~ 0.25", 500, 1030, 55, 22, numinlets=2, outlettype=["signal"])
    n.met_mix = b.add("newobj", "+~", 500, 1070, 35, 22, numinlets=2, outlettype=["signal"])
    n.met_safe = b.add("newobj", "lores~ 6000 0", 500, 1110, 90, 22, numinlets=3, outlettype=["signal"])
    n.met_clip = b.add("newobj", "clip~ -0.7 0.7", 500, 1150, 85, 22, numinlets=1, outlettype=["signal"])

    # Palme: harmonic reson~ bank, dry/wet
    n.pal_dry = b.add("newobj", "*~ 0.78", 820, 910, 55, 22, numinlets=2, outlettype=["signal"])
    n.pal_wet = b.add("newobj", "+~", 820, 990, 35, 22, numinlets=2, outlettype=["signal"])
    n.pal_r1 = b.add("newobj", "reson~ 0.5 220 16", 880, 910, 110, 22, numinlets=4, outlettype=["signal"])
    n.pal_r2 = b.add("newobj", "reson~ 0.45 440 18", 880, 950, 115, 22, numinlets=4, outlettype=["signal"])
    n.pal_r3 = b.add("newobj", "reson~ 0.4 660 18", 880, 990, 110, 22, numinlets=4, outlettype=["signal"])
    n.pal_g1 = b.add("newobj", "*~ 0.14", 990, 910, 50, 22, numinlets=2, outlettype=["signal"])
    n.pal_g2 = b.add("newobj", "*~ 0.12", 990, 950, 50, 22, numinlets=2, outlettype=["signal"])
    n.pal_g3 = b.add("newobj", "*~ 0.10", 990, 990, 50, 22, numinlets=2, outlettype=["signal"])
    n.pal_wet2 = b.add("newobj", "+~", 990, 1030, 35, 22, numinlets=2, outlettype=["signal"])
    n.pal_lvl = b.add("newobj", "sig~ 1.", 1050, 910, 45, 22, numinlets=0, outlettype=["signal"])
    n.pal_wet_gain = b.add("newobj", "*~ 0.22", 820, 1030, 55, 22, numinlets=2, outlettype=["signal"])
    n.pal_mix = b.add("newobj", "+~", 820, 1070, 35, 22, numinlets=2, outlettype=["signal"])
    n.pal_safe = b.add("newobj", "lores~ 5000 0", 820, 1110, 90, 22, numinlets=3, outlettype=["signal"])
    n.pal_clip = b.add("newobj", "clip~ -0.7 0.7", 820, 1150, 85, 22, numinlets=1, outlettype=["signal"])

    # Resonance diffuseur: spring-like modal mix
    n.resd_dry = b.add("newobj", "*~ 0.65", 1120, 910, 55, 22, numinlets=2, outlettype=["signal"])
    n.resd_wet = b.add("newobj", "+~", 1120, 990, 35, 22, numinlets=2, outlettype=["signal"])
    n.resd_r1 = b.add("newobj", "reson~ 0.5 120 8", 1180, 910, 110, 22, numinlets=4, outlettype=["signal"])
    n.resd_r2 = b.add("newobj", "reson~ 0.45 180 9", 1180, 950, 115, 22, numinlets=4, outlettype=["signal"])
    n.resd_r3 = b.add("newobj", "reson~ 0.4 240 10", 1180, 990, 110, 22, numinlets=4, outlettype=["signal"])
    n.resd_g1 = b.add("newobj", "*~ 0.18", 1290, 910, 50, 22, numinlets=2, outlettype=["signal"])
    n.resd_g2 = b.add("newobj", "*~ 0.14", 1290, 950, 50, 22, numinlets=2, outlettype=["signal"])
    n.resd_g3 = b.add("newobj", "*~ 0.10", 1290, 990, 50, 22, numinlets=2, outlettype=["signal"])
    n.resd_wet2 = b.add("newobj", "+~", 1290, 1030, 35, 22, numinlets=2, outlettype=["signal"])
    n.resd_lvl = b.add("newobj", "sig~ 1.", 1350, 910, 45, 22, numinlets=0, outlettype=["signal"])
    n.resd_wet_gain = b.add("newobj", "*~ 0.35", 1120, 1030, 55, 22, numinlets=2, outlettype=["signal"])
    n.resd_mix = b.add("newobj", "+~", 1120, 1070, 35, 22, numinlets=2, outlettype=["signal"])
    n.resd_safe = b.add("newobj", "lores~ 4500 0", 1120, 1110, 90, 22, numinlets=3, outlettype=["signal"])
    n.resd_clip = b.add("newobj", "clip~ -0.7 0.7", 1120, 1150, 85, 22, numinlets=1, outlettype=["signal"])

    n.diff_lvl = b.add("newobj", "sig~ 1.", 400, 1070, 45, 22, numinlets=0, outlettype=["signal"])
    n.diff_out_clip = b.add("newobj", "clip~ -1 1", 400, 1190, 65, 22, numinlets=1, outlettype=["signal"])


def _build_dynamics(b, n):
    """Amplitude gate envelope, legato detection, and the expression VCA."""
    # Amplitude (gate) envelope: count-driven target, Attack/Release ramp times
    n.gate_count_gt = b.add("newobj", "> 0", 40, 350, 35, 22, numinlets=1)
    n.gate_split = b.add("newobj", "t i i", 40, 390, 35, 22, numinlets=1, numoutlets=2, outlettype=["int", "int"])
    n.gate_timesel = b.add("newobj", "sel 1 0", 90, 390, 60, 22, numinlets=1, numoutlets=3)
    n.gate_atk_f = b.add("newobj", "f 80", 90, 430, 45, 22)
    n.gate_rel_f = b.add("newobj", "f 350", 140, 430, 50, 22)
    n.gate_pack = b.add("newobj", "pack f f", 40, 470, 55, 22, numinlets=2, numoutlets=1)
    n.gate_line = b.add("newobj", "line~", 40, 510, 45, 22, numinlets=2, outlettype=["signal"])

    # Legato detection: glide only when notes overlap
    n.leg_velgate = b.add("newobj", "> 0", 700, 230, 35, 22, numinlets=1)
    n.leg_onoff = b.add("newobj", "sel 1 0", 700, 270, 60, 22, numinlets=1, numoutlets=3)
    n.leg_on_seq = b.add("newobj", "t b b", 700, 310, 45, 22, numinlets=1, numoutlets=2)
    n.leg_on_one = b.add("message", "1", 760, 350, 32, 20, numinlets=2, numoutlets=1)
    n.leg_off_one = b.add("message", "-1", 800, 270, 32, 20, numinlets=2, numoutlets=1)
    n.leg_acc = b.add("newobj", "+ 0", 760, 390, 45, 22, numinlets=2)
    n.leg_clamp = b.add("newobj", "maximum 0", 760, 430, 75, 22, numinlets=2)
    n.leg_cur = b.add("newobj", "f 0", 700, 350, 35, 22)
    n.leg_test = b.add("newobj", ">= 2", 700, 390, 40, 22, numinlets=2)
    n.leg_timesel = b.add("newobj", "sel 1 0", 700, 430, 60, 22, numinlets=1, numoutlets=3)
    n.leg_zero = b.add("message", "0", 640, 470, 32, 20, numinlets=2, numoutlets=1)

    # Expression VCA (UI/CC11/aftertouch -> max -> smooth -> VCA)
    n.ui_expr_f = b.add("newobj", "f 0.85", 40, 460, 50, 22)
    n.cc_scale = b.add("newobj", "/ 127.", 200, 420, 45, 22, numinlets=1)
    n.cc_tbf = b.add("newobj", "t b f", 200, 460, 45, 22, numinlets=1, numoutlets=2)
    n.touch_scale = b.add("newobj", "/ 127.", 280, 420, 45, 22, numinlets=1)
    n.touch_tbf = b.add("newobj", "t b f", 280, 460, 45, 22, numinlets=1, numoutlets=2)
    n.expr_merge = b.add("newobj", "expr max($f1\\,max($f2\\,$f3))", 40, 500, 170, 22, numinlets=3)
    n.expr_smooth = b.add("newobj", "pack f 20", 40, 540, 60, 22, numinlets=2, numoutlets=1)
    n.expr_line = b.add("newobj", "line~ 0.85", 40, 580, 60, 22, numinlets=2, outlettype=["signal"])
    n.vca = b.add("newobj", "*~", 40, 1230, 35, 22, numinlets=2, outlettype=["signal"])
    n.vca_gate = b.add("newobj", "*~", 90, 1230, 35, 22, numinlets=2, outlettype=["signal"])


def _build_master(b, n):
    """Gain -> tanh saturation -> safety low-pass -> brickwall -> plugout~."""
    n.gain_f = b.add("newobj", "f -12", 200, 1230, 45, 22)
    n.dbtoa = b.add("newobj", "dbtoa", 200, 1270, 45, 22, numinlets=1)
    n.gain_sig = b.add("newobj", "sig~", 200, 1310, 35, 22, outlettype=["signal"])
    n.master_gain = b.add("newobj", "*~", 200, 1350, 35, 22, numinlets=2, outlettype=["signal"])
    n.sat_amt = b.add("newobj", "expr 1.+$f1*6.", 320, 1270, 110, 22, numinlets=1)
    n.sat_amt_sig = b.add("newobj", "sig~", 320, 1310, 35, 22, numinlets=0, outlettype=["signal"])
    n.sat_pre = b.add("newobj", "*~", 260, 1350, 35, 22, numinlets=2, outlettype=["signal"])
    n.sat_shaper = b.add("newobj", "tanh~", 260, 1390, 45, 22, numinlets=1, outlettype=["signal"])
    n.sat_makeup = b.add("newobj", "*~ 0.8", 260, 1430, 50, 22, numinlets=2, outlettype=["signal"])
    n.master_lpf = b.add("newobj", "onepole~ 12000", 260, 1470, 100, 22, numinlets=2, outlettype=["signal"])
    n.master_clip = b.add("newobj", "clip~ -1 1", 260, 1550, 70, 22, numinlets=1, outlettype=["signal"])
    n.plugout = b.add("newobj", "plugout~", 260, 1590, 55, 22, numinlets=2, outlettype=[])
    n.gain_init = b.add("newobj", "loadmess -12", 200, 1190, 85, 22)
    n.sat_init = b.add("newobj", "loadmess 0.02", 320, 1230, 90, 22)


def build_device():
    """Single flat Generateur d'Ondes instrument patcher (UI + DSP + wiring)."""
    b = PatcherBuilder(presentation=True, device_width=820.0)

    c = _build_ui(b)
    n = SimpleNamespace()
    _build_midi_inputs(b, n)
    _build_pitch(b, n)
    _build_modulation(b, n)
    _build_oscillators(b, n)
    _build_voice(b, n)
    _build_diffuseurs(b, n)
    _build_dynamics(b, n)
    _build_master(b, n)

    _wire_pitch(b, c, n)
    _wire_dynamics(b, c, n)
    _wire_modulation(b, c, n)
    _wire_oscillators(b, c, n)
    _wire_voice(b, c, n)
    _wire_diffuseurs(b, c, n)
    _wire_master(b, c, n)

    b.patcher["title"] = "Generateur d'Ondes"
    b.patcher["description"] = (
        "Monophonic Generateur d'Ondes — heterodyne-inspired sine core, authentic timbres, "
        "subtle resonant diffuseurs, hearing-safe output"
    )
    b.patcher["openrect"] = [0.0, 0.0, 0.0, 172.0]

    return b


def _wire_pitch(b, c, n):
    """MIDI note/bend/ribbon -> pitch expression -> mtof -> glide line~."""
    b.connect(n.notein, 0, n.stripnote, 0)
    b.connect(n.notein, 1, n.stripnote, 1)
    b.connect(n.stripnote, 0, n.vib_note_t, 0)
    b.connect(n.vib_note_t, 0, n.note_store, 0)
    b.connect(n.bendin, 0, n.bend_store, 0)
    b.connect(n.bendin, 0, n.bend_trig, 0)
    b.connect(n.bend_trig, 0, n.bend_store, 0)
    b.connect(n.bend_trig, 0, n.pitch_bang, 0)
    b.connect(c.d_bend, 0, n.bend_range_f, 0)
    b.connect(c.d_bend, 0, n.bend_range_trig, 0)
    b.connect(n.bend_range_trig, 0, n.bend_range_f, 0)
    b.connect(n.bend_range_trig, 0, n.pitch_bang, 0)
    b.connect(c.d_ribbon, 0, n.ribbon_f, 0)
    b.connect(c.d_ribbon, 0, n.ribbon_trig, 0)
    b.connect(n.ribbon_trig, 0, n.ribbon_f, 0)
    b.connect(n.ribbon_trig, 0, n.pitch_bang, 0)
    b.connect(n.pitch_init, 0, n.pitch_bang, 0)

    b.connect(n.pitch_bang, 0, n.note_store, 0)
    b.connect(n.pitch_bang, 1, n.bend_store, 0)
    b.connect(n.pitch_bang, 2, n.bend_range_f, 0)
    b.connect(n.pitch_bang, 3, n.ribbon_f, 0)
    b.connect(n.note_store, 0, n.pitch_expr, 0)
    b.connect(n.bend_store, 0, n.pitch_expr, 1)
    b.connect(n.bend_range_f, 0, n.pitch_expr, 2)
    b.connect(n.ribbon_f, 0, n.pitch_expr, 3)
    b.connect(n.pitch_expr, 0, n.mtof, 0)
    b.connect(n.mtof, 0, n.freq_clip_msg, 0)
    b.connect(n.freq_clip_msg, 0, n.freq_target, 0)
    b.connect(n.freq_target, 0, n.glide_pack, 0)
    b.connect(c.d_glide, 0, n.glide_amt_f, 1)
    b.connect(n.glide_pack, 0, n.freq_line, 0)


def _wire_dynamics(b, c, n):
    """Legato held-key counter, count-driven gate envelope, expression VCA."""
    # Legato: count held keys; glide time = Glide on overlap, else 0 (instant)
    b.connect(n.notein, 1, n.leg_velgate, 0)
    b.connect(n.leg_velgate, 0, n.leg_onoff, 0)
    b.connect(n.leg_onoff, 0, n.leg_on_seq, 0)
    b.connect(n.leg_onoff, 1, n.leg_off_one, 0)
    b.connect(n.leg_on_seq, 1, n.leg_on_one, 0)
    b.connect(n.leg_on_one, 0, n.leg_acc, 0)
    b.connect(n.leg_off_one, 0, n.leg_acc, 0)
    b.connect(n.leg_acc, 0, n.leg_clamp, 0)
    b.connect(n.leg_clamp, 0, n.leg_acc, 1)
    b.connect(n.leg_clamp, 0, n.leg_cur, 1)
    b.connect(n.leg_on_seq, 0, n.leg_cur, 0)
    b.connect(n.leg_cur, 0, n.leg_test, 0)
    b.connect(n.leg_test, 0, n.leg_timesel, 0)
    b.connect(n.leg_timesel, 0, n.glide_amt_f, 0)
    b.connect(n.leg_timesel, 1, n.leg_zero, 0)
    b.connect(n.glide_amt_f, 0, n.glide_pack, 1)
    b.connect(n.leg_zero, 0, n.glide_pack, 1)

    # Amp envelope: held-count>0 -> target 0/1; Attack rising, Release falling
    b.connect(n.leg_clamp, 0, n.gate_count_gt, 0)
    b.connect(n.gate_count_gt, 0, n.gate_split, 0)
    b.connect(n.gate_split, 1, n.gate_timesel, 0)
    b.connect(n.gate_timesel, 0, n.gate_atk_f, 0)
    b.connect(n.gate_timesel, 1, n.gate_rel_f, 0)
    b.connect(n.gate_atk_f, 0, n.gate_pack, 1)
    b.connect(n.gate_rel_f, 0, n.gate_pack, 1)
    b.connect(n.gate_split, 0, n.gate_pack, 0)
    b.connect(n.gate_pack, 0, n.gate_line, 0)
    b.connect(c.d_expr_atk, 0, n.gate_atk_f, 1)
    b.connect(c.d_expr_rel, 0, n.gate_rel_f, 1)

    # Expression VCA — UI/CC11/aftertouch all trigger a recompute (live response)
    b.connect(c.d_expr, 0, n.ui_expr_f, 0)
    b.connect(n.ui_expr_f, 0, n.expr_merge, 0)
    b.connect(n.ctlin, 0, n.cc_scale, 0)
    b.connect(n.cc_scale, 0, n.cc_tbf, 0)
    b.connect(n.cc_tbf, 1, n.expr_merge, 1)
    b.connect(n.cc_tbf, 0, n.expr_merge, 0)
    b.connect(n.touchin, 0, n.touch_scale, 0)
    b.connect(n.touch_scale, 0, n.touch_tbf, 0)
    b.connect(n.touch_tbf, 1, n.expr_merge, 2)
    b.connect(n.touch_tbf, 0, n.expr_merge, 0)
    b.connect(n.expr_merge, 0, n.expr_smooth, 0)
    b.connect(n.expr_smooth, 0, n.expr_line, 0)
    b.connect(n.diff_out_clip, 0, n.vca, 0)
    b.connect(n.expr_line, 0, n.vca, 1)
    b.connect(n.vca, 0, n.vca_gate, 0)
    b.connect(n.gate_line, 0, n.vca_gate, 1)


def _wire_modulation(b, c, n):
    """Drift, vibrato, tremolo, and the intensity macro."""
    # Drift
    b.connect(c.d_drift, 0, n.drift_f, 0)
    b.connect(n.drift_f, 0, n.drift_sig, 0)
    b.connect(n.drift_noise, 0, n.drift_lpf, 0)
    b.connect(n.drift_lpf, 0, n.drift_scale, 0)
    b.connect(n.drift_sig, 0, n.drift_scale, 1)
    b.connect(n.freq_line, 0, n.freq_drift, 0)
    b.connect(n.drift_scale, 0, n.freq_drift, 1)
    b.connect(n.freq_drift, 0, n.vib_apply, 0)
    b.connect(n.vib_factor, 0, n.vib_apply, 1)
    b.connect(n.vib_apply, 0, n.freq_clip_sig, 0)

    # Vibrato (rate smoothed via line~ for clean dial/CC sweeps)
    b.connect(c.d_vib_rate, 0, n.vib_rate_f, 0)
    b.connect(n.vib_rate_f, 0, n.vib_rate_pack, 0)
    b.connect(n.vib_rate_pack, 0, n.vib_rate_line, 0)
    b.connect(n.vib_rate_line, 0, n.vib_lfo, 0)
    b.connect(c.d_vib_depth, 0, n.vib_depth_f, 0)
    b.connect(n.vib_depth_f, 0, n.vib_depth_merge, 0)
    b.connect(n.vib_cc, 0, n.vib_wheel_scale, 0)
    b.connect(n.vib_wheel_scale, 0, n.vib_depth_merge, 1)
    b.connect(n.vib_depth_merge, 0, n.vib_bloom_pack, 0)
    b.connect(n.vib_note_t, 1, n.vib_bloom_trig, 0)
    b.connect(n.vib_bloom_trig, 0, n.vib_bloom_zero, 0)
    b.connect(n.vib_bloom_zero, 0, n.vib_bloom_line, 0)
    b.connect(n.vib_bloom_trig, 1, n.vib_depth_f, 1)
    b.connect(n.vib_bloom_pack, 0, n.vib_bloom_line, 0)
    b.connect(n.vib_lfo, 0, n.vib_mod, 0)
    b.connect(n.vib_bloom_line, 0, n.vib_depth_scale, 0)
    b.connect(n.vib_depth_scale, 0, n.vib_mod, 1)
    b.connect(n.vib_mod, 0, n.vib_factor, 0)
    b.connect(n.vib_one, 0, n.vib_factor, 1)

    # Tremolo (own free-running LFO; rate smoothed via line~)
    b.connect(c.d_trem_rate, 0, n.trem_rate_f, 0)
    b.connect(n.trem_rate_f, 0, n.trem_rate_pack, 0)
    b.connect(n.trem_rate_pack, 0, n.trem_rate_line, 0)
    b.connect(n.trem_rate_line, 0, n.trem_lfo, 0)
    b.connect(c.d_trem, 0, n.trem_depth_f, 0)
    b.connect(n.trem_depth_f, 0, n.trem_depth_sig, 0)
    b.connect(n.trem_lfo, 0, n.trem_mod, 0)
    b.connect(n.trem_depth_sig, 0, n.trem_mod, 1)
    b.connect(n.trem_mod, 0, n.trem_factor, 0)

    # Intensity macro: bring vibrato depth in live (max with dial/wheel)
    b.connect(c.d_intensity, 0, n.intens_vib_tbf, 0)
    b.connect(n.intens_vib_tbf, 1, n.vib_depth_merge, 2)
    b.connect(n.intens_vib_tbf, 0, n.vib_depth_merge, 0)


def _wire_oscillators(b, c, n):
    """Drive each timbre from the modulated frequency into the selector."""
    b.connect(n.freq_clip_sig, 0, n.osc_o, 0)
    b.connect(n.freq_clip_sig, 0, n.osc_c, 0)
    b.connect(n.freq_clip_sig, 0, n.osc_g, 0)
    b.connect(n.freq_clip_sig, 0, n.osc_n, 0)
    b.connect(n.freq_clip_sig, 0, n.osc_8_base, 0)
    b.connect(n.osc_8_base, 0, n.osc_8_lo, 0)
    b.connect(n.freq_clip_sig, 0, n.oct_freq, 0)
    b.connect(n.oct_mul, 0, n.oct_freq, 1)
    b.connect(n.oct_freq, 0, n.osc_8_hi, 0)
    b.connect(n.osc_c, 0, n.creux_clip, 0)
    b.connect(n.creux_clip, 0, n.creux_norm, 0)
    b.connect(n.creux_lvl, 0, n.creux_norm, 1)
    b.connect(n.osc_8_lo, 0, n.osc_8_mix, 0)
    b.connect(n.osc_8_hi, 0, n.osc_8_hi_gain, 0)
    b.connect(n.osc_8_lvl, 0, n.osc_8_hi_gain, 1)
    b.connect(n.osc_8_hi_gain, 0, n.osc_8_mix, 1)
    b.connect(c.d_timbre, 0, n.timbre_inc, 0)
    b.connect(n.timbre_inc, 0, n.timbre_sel, 0)
    b.connect(n.osc_o, 0, n.timbre_sel, 1)
    b.connect(n.creux_norm, 0, n.timbre_sel, 2)
    b.connect(n.osc_g, 0, n.timbre_sel, 3)
    b.connect(n.osc_n, 0, n.timbre_sel, 4)
    b.connect(n.osc_8_mix, 0, n.timbre_sel, 5)


def _wire_voice(b, c, n):
    """Triode coloration, voicing filter, and expression -> cutoff tracking."""
    # Triode: signal * (1 + (drive + intensity*0.5)*4) -> tanh -> makeup
    b.connect(c.d_triode, 0, n.triode_amt, 0)
    b.connect(n.triode_init, 0, n.triode_amt, 0)
    b.connect(c.d_intensity, 0, n.intens_tri_tbf, 0)
    b.connect(n.intens_tri_tbf, 1, n.triode_amt, 1)
    b.connect(n.intens_tri_tbf, 0, n.triode_amt, 0)
    b.connect(n.triode_amt, 0, n.triode_amt_sig, 0)
    b.connect(n.timbre_sel, 0, n.triode_pre, 0)
    b.connect(n.triode_amt_sig, 0, n.triode_pre, 1)
    b.connect(n.triode_pre, 0, n.triode_shaper, 0)
    b.connect(n.triode_shaper, 0, n.triode_out, 0)

    # Filter
    b.connect(n.cutoff_init, 0, n.cutoff_f, 0)
    b.connect(n.res_init, 0, n.res_f, 0)
    b.connect(c.d_cutoff, 0, n.cutoff_f, 0)
    b.connect(n.cutoff_f, 0, n.cutoff_clip, 0)
    b.connect(n.cutoff_clip, 0, n.cutoff_sig, 0)
    b.connect(c.d_res, 0, n.res_f, 0)
    b.connect(n.res_f, 0, n.res_clip, 0)
    b.connect(n.res_clip, 0, n.res_sig, 0)
    b.connect(n.triode_out, 0, n.filt, 0)

    # Expression -> cutoff tracking (+ Intensity), clamped to a safe range
    b.connect(c.d_track, 0, n.track_f, 0)
    b.connect(n.track_f, 0, n.track_sig, 0)
    b.connect(n.expr_line, 0, n.track_exprmul, 0)
    b.connect(n.track_sig, 0, n.track_exprmul, 1)
    b.connect(n.track_exprmul, 0, n.track_hz, 0)
    b.connect(c.d_intensity, 0, n.intens_cut_f, 0)
    b.connect(n.intens_cut_f, 0, n.intens_cut_sig, 0)
    b.connect(n.intens_cut_sig, 0, n.intens_cut_hz, 0)
    b.connect(n.track_hz, 0, n.cutoff_sum1, 0)
    b.connect(n.intens_cut_hz, 0, n.cutoff_sum1, 1)
    b.connect(n.cutoff_sig, 0, n.cutoff_sum2, 0)
    b.connect(n.cutoff_sum1, 0, n.cutoff_sum2, 1)
    b.connect(n.cutoff_sum2, 0, n.cutoff_safe, 0)
    b.connect(n.cutoff_safe, 0, n.filt, 1)
    b.connect(n.res_sig, 0, n.filt, 2)
    b.connect(n.filt, 0, n.filt_clip, 0)


def _wire_diffuseurs(b, c, n):
    """Filter output fans into all diffuseurs; selector picks one."""
    b.connect(n.filt_clip, 0, n.principal, 0)

    # Metallique
    b.connect(n.filt_clip, 0, n.met_dry, 0)
    b.connect(n.diff_lvl, 0, n.met_dry, 1)
    b.connect(n.filt_clip, 0, n.met_r1, 0)
    b.connect(n.filt_clip, 0, n.met_r2, 0)
    b.connect(n.filt_clip, 0, n.met_r3, 0)
    b.connect(n.met_r1, 0, n.met_g1, 0)
    b.connect(n.met_lvl, 0, n.met_g1, 1)
    b.connect(n.met_r2, 0, n.met_g2, 0)
    b.connect(n.met_lvl, 0, n.met_g2, 1)
    b.connect(n.met_r3, 0, n.met_g3, 0)
    b.connect(n.met_lvl, 0, n.met_g3, 1)
    b.connect(n.met_g1, 0, n.met_wet, 0)
    b.connect(n.met_g2, 0, n.met_wet, 1)
    b.connect(n.met_wet, 0, n.met_wet2, 0)
    b.connect(n.met_g3, 0, n.met_wet2, 1)
    b.connect(n.met_wet2, 0, n.met_wet_gain, 0)
    b.connect(n.met_lvl, 0, n.met_wet_gain, 1)
    b.connect(n.met_dry, 0, n.met_mix, 0)
    b.connect(n.met_wet_gain, 0, n.met_mix, 1)
    b.connect(n.met_mix, 0, n.met_safe, 0)
    b.connect(n.met_safe, 0, n.met_clip, 0)

    # Palme
    b.connect(n.filt_clip, 0, n.pal_dry, 0)
    b.connect(n.diff_lvl, 0, n.pal_dry, 1)
    b.connect(n.filt_clip, 0, n.pal_r1, 0)
    b.connect(n.filt_clip, 0, n.pal_r2, 0)
    b.connect(n.filt_clip, 0, n.pal_r3, 0)
    b.connect(n.pal_r1, 0, n.pal_g1, 0)
    b.connect(n.pal_lvl, 0, n.pal_g1, 1)
    b.connect(n.pal_r2, 0, n.pal_g2, 0)
    b.connect(n.pal_lvl, 0, n.pal_g2, 1)
    b.connect(n.pal_r3, 0, n.pal_g3, 0)
    b.connect(n.pal_lvl, 0, n.pal_g3, 1)
    b.connect(n.pal_g1, 0, n.pal_wet, 0)
    b.connect(n.pal_g2, 0, n.pal_wet, 1)
    b.connect(n.pal_wet, 0, n.pal_wet2, 0)
    b.connect(n.pal_g3, 0, n.pal_wet2, 1)
    b.connect(n.pal_wet2, 0, n.pal_wet_gain, 0)
    b.connect(n.pal_lvl, 0, n.pal_wet_gain, 1)
    b.connect(n.pal_dry, 0, n.pal_mix, 0)
    b.connect(n.pal_wet_gain, 0, n.pal_mix, 1)
    b.connect(n.pal_mix, 0, n.pal_safe, 0)
    b.connect(n.pal_safe, 0, n.pal_clip, 0)

    # Resonance diffuseur
    b.connect(n.filt_clip, 0, n.resd_dry, 0)
    b.connect(n.diff_lvl, 0, n.resd_dry, 1)
    b.connect(n.filt_clip, 0, n.resd_r1, 0)
    b.connect(n.filt_clip, 0, n.resd_r2, 0)
    b.connect(n.filt_clip, 0, n.resd_r3, 0)
    b.connect(n.resd_r1, 0, n.resd_g1, 0)
    b.connect(n.resd_lvl, 0, n.resd_g1, 1)
    b.connect(n.resd_r2, 0, n.resd_g2, 0)
    b.connect(n.resd_lvl, 0, n.resd_g2, 1)
    b.connect(n.resd_r3, 0, n.resd_g3, 0)
    b.connect(n.resd_lvl, 0, n.resd_g3, 1)
    b.connect(n.resd_g1, 0, n.resd_wet, 0)
    b.connect(n.resd_g2, 0, n.resd_wet, 1)
    b.connect(n.resd_wet, 0, n.resd_wet2, 0)
    b.connect(n.resd_g3, 0, n.resd_wet2, 1)
    b.connect(n.resd_wet2, 0, n.resd_wet_gain, 0)
    b.connect(n.resd_lvl, 0, n.resd_wet_gain, 1)
    b.connect(n.resd_dry, 0, n.resd_mix, 0)
    b.connect(n.resd_wet_gain, 0, n.resd_mix, 1)
    b.connect(n.resd_mix, 0, n.resd_safe, 0)
    b.connect(n.resd_safe, 0, n.resd_clip, 0)

    # Selector + output clamp
    b.connect(c.d_diff, 0, n.diff_inc, 0)
    b.connect(n.diff_inc, 0, n.diff_sel, 0)
    b.connect(n.principal, 0, n.diff_sel, 1)
    b.connect(n.met_clip, 0, n.diff_sel, 2)
    b.connect(n.pal_clip, 0, n.diff_sel, 3)
    b.connect(n.resd_clip, 0, n.diff_sel, 4)
    b.connect(n.diff_sel, 0, n.diff_out_clip, 0)


def _wire_master(b, c, n):
    """Gain -> tanh saturation (drive, no DC) -> safety LP -> brickwall."""
    b.connect(n.gain_init, 0, n.gain_f, 0)
    b.connect(c.d_gain, 0, n.gain_f, 0)
    b.connect(n.gain_f, 0, n.dbtoa, 0)
    b.connect(n.dbtoa, 0, n.gain_sig, 0)
    b.connect(n.vca_gate, 0, n.trem_apply, 0)
    b.connect(n.trem_factor, 0, n.trem_apply, 1)
    b.connect(n.trem_apply, 0, n.master_gain, 0)
    b.connect(n.gain_sig, 0, n.master_gain, 1)
    b.connect(n.sat_init, 0, n.sat_amt, 0)
    b.connect(c.d_sat, 0, n.sat_amt, 0)
    b.connect(n.sat_amt, 0, n.sat_amt_sig, 0)
    b.connect(n.master_gain, 0, n.sat_pre, 0)
    b.connect(n.sat_amt_sig, 0, n.sat_pre, 1)
    b.connect(n.sat_pre, 0, n.sat_shaper, 0)
    b.connect(n.sat_shaper, 0, n.sat_makeup, 0)
    b.connect(n.sat_makeup, 0, n.master_lpf, 0)
    b.connect(n.master_lpf, 0, n.master_clip, 0)
    b.connect(n.master_clip, 0, n.plugout, 0)
    b.connect(n.master_clip, 0, n.plugout, 1)


def load_amxd_json(path):
    data = path.read_bytes()
    idx = data.find(b"ptch")
    payload = data[idx + 8 : idx + 8 + struct.unpack("<I", data[idx + 4 : idx + 8])[0]]
    depth = 0
    for i, byte in enumerate(payload):
        if byte == ord("{"):
            depth += 1
        elif byte == ord("}"):
            depth -= 1
            if depth == 0:
                return json.loads(payload[: i + 1])
    raise ValueError(f"invalid amxd json in {path}")


M4L_FORBIDDEN_OBJECTS = re.compile(
    r'"maxclass"\s*:\s*"(inlet~|outlet~|expr~|gen~)"|'
    r'"text"\s*:\s*"(inlet~|outlet~|expr~|gen~|p |svf~)',
    re.I,
)
M4L_FORBIDDEN_EFFECTS = re.compile(
    r"reverb~|freeverb~|room~|gizmo~|delay~|tapin~|tapout~|"
    r"chorus~|flanger~|phaser~|width~|pan2~|rotate~|omx\.peaklim~",
    re.I,
)


def _audit_patchlines(patcher, errors):
    boxes = {box["box"]["id"]: box["box"] for box in patcher.get("boxes", [])}
    ids = [box["box"]["id"] for box in patcher.get("boxes", [])]
    if len(ids) != len(set(ids)):
        errors.append("duplicate object ids")

    for line in patcher.get("lines", []):
        src_id, _so = line["patchline"]["source"]
        dst_id, _di = line["patchline"]["destination"]
        if src_id not in boxes or dst_id not in boxes:
            errors.append(f"dangling patchline {src_id}->{dst_id}")


def _detect_signal_cycles(patcher, errors):
    """A feedback loop in the signal graph causes Max 'infinite recursion'."""
    boxes = {box["box"]["id"]: box["box"] for box in patcher.get("boxes", [])}
    adj = {}
    for line in patcher.get("lines", []):
        src, so = line["patchline"]["source"]
        dst, _di = line["patchline"]["destination"]
        sb = boxes.get(src)
        if not sb:
            continue
        ot = sb.get("outlettype", [])
        if so < len(ot) and ot[so] == "signal":
            adj.setdefault(src, set()).add(dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}
    stack = []

    def label(i):
        return boxes[i].get("text", i)

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for v in adj.get(u, ()):
            c = color.get(v, WHITE)
            if c == GRAY:
                idx = stack.index(v)
                names = " -> ".join(label(i) for i in stack[idx:] + [v])
                errors.append(f"signal feedback cycle: {names}")
                return True
            if c == WHITE and dfs(v):
                return True
        stack.pop()
        color[u] = BLACK
        return False

    for node in list(adj.keys()):
        if color.get(node, WHITE) == WHITE:
            if dfs(node):
                break


def verify_device(amxd_path):
    errors = []
    raw = amxd_path.read_bytes().decode("utf-8", "ignore")

    if M4L_FORBIDDEN_OBJECTS.search(raw):
        errors.append("contains M4L-forbidden objects (inlet~/outlet~/expr~/gen~/external p/svf~)")
    if M4L_FORBIDDEN_EFFECTS.search(raw):
        errors.append("contains forbidden production effects")

    device = load_amxd_json(amxd_path)
    patcher = device["patcher"]

    if patcher.get("project", {}).get("name") != "Generateur d'Ondes":
        errors.append("missing or wrong project name")

    embeds = [b["box"] for b in patcher["boxes"] if "patcher" in b["box"]]
    if embeds:
        errors.append(f"expected flat patcher, found {len(embeds)} embedded subpatchers")

    texts = [b["box"].get("text", "") for b in patcher["boxes"]]
    plugouts = [t for t in texts if t == "plugout~"]
    if len(plugouts) != 1:
        errors.append(f"expected 1 plugout~, found {len(plugouts)}")
    if "notein" not in texts:
        errors.append("missing notein")

    timbre_sels = [t for t in texts if t == "selector~ 5 1"]
    diff_sels = [t for t in texts if t == "selector~ 4 1"]
    if len(timbre_sels) != 1:
        errors.append(f"expected 1 timbre selector~ 5, found {len(timbre_sels)}")
    if len(diff_sels) != 1:
        errors.append(f"expected 1 diffuseur selector~ 4, found {len(diff_sels)}")

    master_clips = [b["box"]["id"] for b in patcher["boxes"] if b["box"].get("text") == "clip~ -1 1"]
    plugout_id = next(b["box"]["id"] for b in patcher["boxes"] if b["box"].get("text") == "plugout~")
    if master_clips:
        clip_id = master_clips[-1]
        wired = any(
            line["patchline"]["source"][0] == clip_id
            and line["patchline"]["destination"][0] == plugout_id
            for line in patcher["lines"]
        )
        if not wired:
            errors.append("final clip~ -1 1 not wired to plugout~")
    else:
        errors.append("missing master clip~ -1 1 before output")

    if "line~" not in texts:
        errors.append("missing line~ glide/envelope")
    if "tanh~" not in texts:
        errors.append("missing tanh~ triode coloration")

    _check_filter_stability(patcher, texts, errors)
    _audit_patchlines(patcher, errors)
    _detect_signal_cycles(patcher, errors)
    return errors


def _fnum(tok):
    try:
        return float(tok)
    except ValueError:
        return None


def _check_filter_stability(patcher, texts, errors):
    """Catch self-oscillation and mis-ordered resonant-filter args."""
    boxes = {b["box"]["id"]: b["box"] for b in patcher.get("boxes", [])}

    for t in texts:
        toks = t.split()
        if not toks:
            continue
        if toks[0] == "lores~" and len(toks) >= 3:
            res = _fnum(toks[2])
            if res is not None and res >= 0.99:
                errors.append(f"lores~ resonance {res} can self-oscillate: '{t}'")
        if toks[0] == "reson~" and len(toks) >= 3:
            # reson~ <gain> <centerfreq> <Q>: freq must be audio-range
            freq = _fnum(toks[2])
            gain = _fnum(toks[1])
            if freq is not None and freq < 20:
                errors.append(f"reson~ center freq {freq} too low (args mis-ordered?): '{t}'")
            if gain is not None and gain > 4:
                errors.append(f"reson~ gain {gain} dangerously high: '{t}'")

    # A sig~ feeding a lores~/reson~ resonance/Q inlet at >= 1.0 also self-oscillates.
    for line in patcher.get("lines", []):
        src, _so = line["patchline"]["source"]
        dst, di = line["patchline"]["destination"]
        sb, db = boxes.get(src), boxes.get(dst)
        if not sb or not db:
            continue
        dtext = db.get("text", "")
        if dtext.startswith("lores~") and di == 2:
            stoks = sb.get("text", "").split()
            if len(stoks) >= 2 and stoks[0] == "sig~":
                val = _fnum(stoks[1])
                if val is not None and val >= 0.99:
                    errors.append(f"sig~ {val} drives lores~ resonance inlet -> self-oscillation")


def write_amxd(path, device_json):
    """Write amxd using an M4L template shell (project dict, parameters, metadata)."""
    template_path = M4L_TEMPLATE_AMXD if M4L_TEMPLATE_AMXD.exists() else FACTORY_AMXD
    if template_path.exists():
        template = load_amxd_json(template_path)
        patcher = template["patcher"]
        ours = device_json["patcher"]
        for key in ("boxes", "lines", "parameters", "dependency_cache"):
            if key in ours:
                patcher[key] = ours[key]
        for key in ("title", "description", "devicewidth", "openinpresentation", "openrect"):
            if key in ours:
                patcher[key] = ours[key]
        patcher["title"] = "Generateur d'Ondes"
        if "project" in patcher:
            patcher["project"]["name"] = "Generateur d'Ondes"
        device_json = template

    payload = json.dumps(device_json, ensure_ascii=False, indent="\t").encode("utf-8")
    data = (
        b"ampf"
        + struct.pack("<I", 4)
        + b"iiii"
        + b"meta"
        + struct.pack("<I", 4)
        + b"\x00\x00\x00\x00"
        + b"ptch"
        + struct.pack("<I", len(payload))
        + payload
    )
    path.write_bytes(data)


def main():
    reset_ids()
    device = build_device().build()
    amxd_path = ROOT / "Generateur d'Ondes.amxd"
    write_amxd(amxd_path, device)
    print(f"Wrote {amxd_path}")

    verify_errors = verify_device(amxd_path)
    if verify_errors:
        print("Device verification FAILED:")
        for err in verify_errors:
            print(f"  - {err}")
        raise SystemExit(1)
    print("Device verification: PASS")
    print("Done.")


if __name__ == "__main__":
    main()
