"""Fit of the ring to the fingers of the hands the game uses (system Python + numpy + PyNifly files).

python finger_fit.py <out_fit.json> <skeleton_female.nif> <skeleton.nif> <femalehands_1.nif> <malehands_1.nif> <malehands_0.nif>

The worn ring is rigid on NPC R Finger10 [RF10], like the vanilla rings, so it is placed in that bone's local frame: z
along the finger, +y the back of the hand (every finger bone of both hands follows this convention). Each hand is posed
on its skeleton the way the game skins it, cut by planes across the band's width, and the smallest circle around the
finger's contour gives the centre and the inner radius (+ CLEARANCE). Z0 sits just past the web between the fingers,
where the band's palm side clears it (checked over animation poses with check_fit.py). The bind written into the worn
NIFs is the hand's own RF10 skin-to-bone transform, so ring and finger follow the same bone the same way. Female: CBBE
3BA hands (the TBD hands are identical on the fingers, weights 0 and 1 too). Male: vanilla hands (SOS ships the same),
weight 0 and 1, for the weight slider.

"displays" fits the ring to the nine other fingers for Jewelry Limiter, which shows extra rings as art objects attached
to a finger bone (Ring_R1 = right middle ... Ring_L4 = left thumb); there Z0 = WEB_MARGIN past the point where the
finger's contour stops widening towards the hand, except where check_fit.py found the next joint's skin pushing through
the band in fist poses: DISPLAY_Z0 holds the position measured for those fingers.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import hl_nif  # noqa: E402
import ring_geometry as G  # noqa: E402

BONE = "NPC R Finger10 [RF10]"
CLEARANCE = 0.03
Z0 = {"female": 1.85, "male": 1.6}
GUESS = {"female": (0.1, -0.12), "male": (0.0, -0.17)}
WEB_MARGIN = 0.45
WEB_WIDENING = 1.12
DISPLAYS = {"Ring_R1.nif": "NPC R Finger20 [RF20]", "Ring_R2.nif": "NPC R Finger30 [RF30]",
            "Ring_R3.nif": "NPC R Finger40 [RF40]", "Ring_R4.nif": "NPC R Finger01 [RF01]",
            "Ring_L0.nif": "NPC L Finger10 [LF10]", "Ring_L1.nif": "NPC L Finger20 [LF20]",
            "Ring_L2.nif": "NPC L Finger30 [LF30]", "Ring_L3.nif": "NPC L Finger40 [LF40]",
            "Ring_L4.nif": "NPC L Finger01 [LF01]"}
DISPLAY_Z0 = {("male", "Ring_R3.nif"): 1.15, ("male", "Ring_L3.nif"): 1.15}


def child_of(bone):
    side, digit, joint = bone[4], bone[12], int(bone[13])
    return "NPC %s Finger%s%d [%sF%s%d]" % (side, digit, joint + 1, side, digit, joint + 1)


def web_z0(v, t, length, guess):
    """Z0 past the web: the contour's enclosing radius along the bone, compared with its narrowest value on the free
    part of the finger; the web ends where it is no longer WEB_WIDENING times wider."""
    zs = np.arange(0.2 * length, 0.95 * length, 0.05)
    radii = []
    for z in zs:
        loop = finger_contour(v, t, z, np.asarray(guess, dtype=float))
        radii.append(enclosing_circle(loop)[1] if loop is not None else np.inf)
    radii = np.array(radii)
    narrow = radii[zs >= 0.6 * length].min()
    wide = zs[radii > WEB_WIDENING * narrow]
    z_web = wide.max() if len(wide) else 0.2 * length
    return float(np.clip(z_web + WEB_MARGIN, 0.45 * length, 0.9 * length))


def posed(shape, skel):
    v = np.c_[shape["v"], np.ones(len(shape["v"]))]
    out = np.zeros((len(v), 3))
    for j, b in enumerate(shape["bones"]):
        out += shape["w"][:, j:j + 1] * (v @ (skel[b] @ shape["s2b"][j]).T)[:, :3]
    return out


def to_bone(points, skel, bone=BONE):
    return (np.c_[points, np.ones(len(points))] @ np.linalg.inv(skel[bone]).T)[:, :3]


def plane_loops(v, t, z0):
    """Closed contours of a triangle mesh cut by the plane z = z0, one 2D point set per connected contour."""
    above = v[:, 2] >= z0
    side = above[t]
    cross = t[side.any(1) & ~side.all(1)]
    adj, pos = {}, {}
    for tri in cross:
        ends = []
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if above[a] != above[b]:
                s = (z0 - v[a, 2]) / (v[b, 2] - v[a, 2])
                key = (min(a, b), max(a, b))
                pos[key] = v[a, :2] + s * (v[b, :2] - v[a, :2])
                ends.append(key)
        if len(ends) == 2:
            adj.setdefault(ends[0], []).append(ends[1])
            adj.setdefault(ends[1], []).append(ends[0])
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(pos[k])
            stack.extend(adj[k])
        loops.append(np.array(comp))
    return loops


def finger_contour(v, t, z, centre, reach=1.8):
    best = None
    for loop in plane_loops(v, t, z):
        if len(loop) < 6 or np.linalg.norm(loop - centre, axis=1).max() > reach:
            continue
        d = np.linalg.norm(loop.mean(0) - centre)
        if best is None or d < best[0]:
            best = (d, loop)
    return None if best is None else best[1]


def enclosing_circle(p, iters=600):
    c = p.mean(0)
    step = 0.1
    for _ in range(iters):
        far = p[np.argmax(np.linalg.norm(p - c, axis=1))]
        c = c + (far - c) * step
        step *= 0.985
    return c, float(np.linalg.norm(p - c, axis=1).max())


def half_width(theta, scale):
    return (G.BAND["hw0"] + (G.BAND["hw1"] - G.BAND["hw0"]) * G.closeness(theta)) * scale


def band_contour(v, t, z0, centre, scale, step=0.02):
    """Finger contour points that lie under the band (its half-width depends on the angle from the setting)."""
    pts = []
    top = half_width(0.0, scale)
    for z in np.arange(z0 - top, z0 + top + 1e-9, step):
        loop = finger_contour(v, t, z, centre)
        if loop is None:
            continue
        th = np.arctan2(loop[:, 0] - centre[0], loop[:, 1] - centre[1])
        keep = np.abs(z - z0) <= half_width(th, scale)
        pts.append(np.c_[loop[keep], np.full(keep.sum(), z)])
    return np.vstack(pts)


def fit(v, t, z0, guess):
    centre, scale = np.asarray(guess, dtype=float), 1.0
    for _ in range(3):
        pts = band_contour(v, t, z0, centre, scale)
        centre, r = enclosing_circle(pts[:, :2])
        scale = (r + CLEARANCE) / G.R_IN
    return centre, r + CLEARANCE, scale, pts


def hand_in_bone(hand_nif, skel_nif, bone=BONE):
    skel = hl_nif.skeleton_globals(skel_nif)
    shape = hl_nif.read_shape(hl_nif.NifFile(hand_nif).shapes[0])
    v = to_bone(posed(shape, skel), skel, bone)
    near = np.linalg.norm(v[shape["t"]][:, :, :2], axis=2).min(1) < 3.0
    s2b = shape["s2b"][shape["bones"].index(bone)]
    length = float(np.linalg.norm((np.linalg.inv(skel[bone]) @ skel[child_of(bone)])[:3, 3]))
    return v, shape["t"][near], s2b, length


def entry(name, bone, z0, v, t, guess, hand):
    centre, r_in, scale, pts = fit(v, t, z0, guess)
    r = np.linalg.norm(pts[:, :2] - centre, axis=1)
    e = {"bone": bone, "z0": round(z0, 4), "centre": [round(float(x), 5) for x in centre], "inner_radius": round(r_in, 5),
         "scale": round(scale, 5), "gap": [round(float(r_in - r.max()), 4), round(float(np.percentile(r_in - r, 90)), 4)],
         "hand": os.path.basename(hand)}
    print("%-22s %-24s z0 %.2f centre (%.3f, %.3f) inner radius %.3f scale %.3f gap min %.3f p90 %.3f" % (
        name, bone, z0, centre[0], centre[1], r_in, scale, *e["gap"]))
    return e


def main():
    out, skel_f, skel_m, hands_f, hands_m1, hands_m0 = sys.argv[1:7]
    worn = {}
    for name, gender, hand, skel in (("AstrielleRingF_1.nif", "female", hands_f, skel_f),
                                     ("AstrielleRing_1.nif", "male", hands_m1, skel_m),
                                     ("AstrielleRing_0.nif", "male", hands_m0, skel_m)):
        v, t, s2b, length = hand_in_bone(hand, skel)
        worn[name] = entry(name, BONE, Z0[gender], v, t, GUESS[gender], hand)
        worn[name]["skin_to_bone"] = s2b.round(6).tolist()
    s1, s0 = worn["AstrielleRing_1.nif"]["skin_to_bone"], worn["AstrielleRing_0.nif"]["skin_to_bone"]
    if not np.allclose(s1, s0, atol=1e-4):
        worn["AstrielleRing_0.nif"]["skin_to_bone"] = s1
        print("weight 0 and 1 hands bind RF10 differently; the weight-0 ring uses the weight-1 bind")
    displays = {}
    for gender, hand, skel in (("female", hands_f, skel_f), ("male", hands_m1, skel_m)):
        displays[gender] = {}
        for name, bone in DISPLAYS.items():
            v, t, s2b, length = hand_in_bone(hand, skel, bone)
            guess = (0.0, -0.1)
            z0 = DISPLAY_Z0.get((gender, name)) or web_z0(v, t, length, guess)
            displays[gender][name] = entry(gender + " " + name, bone, z0, v, t, guess, hand)
    json.dump({"worn": worn, "displays": displays}, open(out, "w"), indent=1)
    print("FIT", out)


if __name__ == "__main__":
    main()
