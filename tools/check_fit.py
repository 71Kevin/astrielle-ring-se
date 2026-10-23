"""Check a built worn ring against a hand over real animation poses (system Python + numpy + PyNifly files).

python check_fit.py <ring.nif> <hands.nif> <skeleton.nif> <skeleton.hkx> <clip.hkx> [...] [--step 6]
The ring is read back from the NIF in its bone's frame (a worn ring rigid on one bone, or a Jewelry Limiter display
attached to a finger bone by AttachT). For each sampled frame the hand's finger bones take the clip's local rotations,
the hand is skinned as in game, and the ring's finger is cut by planes across the band: "through" is how far the
finger's skin reaches past the ring's inner surface (by side: back of the hand, +x and -x of the bone, palm; on the
right index +x is the thumb side), "gap" the 90th percentile of the space between them, and "fingers" the closest any
other finger's skin comes to the ring (0.300 = at least NEAR away). The bind pose comes first; a fitted ring reads 0
through there.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import hl_nif  # noqa: E402
import nif_attach  # noqa: E402
from finger_fit import finger_contour, posed  # noqa: E402

HKX = os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.3\scripts\addons\io_scene_nifly\hkx")
sys.path.insert(0, os.environ.get("HL_PYNIFLY_HKX", HKX))
from anim_skyrim import load_skyrim_animation, load_skyrim_skeleton  # noqa: E402

BARY = np.array([(i, j, 6 - i - j) for i in range(7) for j in range(7 - i)], dtype=float) / 6
SIDES = ("back", "side +x", "side -x", "palm")
NEAR = 0.3


def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def clip_frames(hkx_skel, path, bones, step):
    idx = {n: i for i, n in enumerate(hkx_skel.bones)}
    a = load_skyrim_animation(path)
    t2b = a.track_to_bone_indices or list(range(len(a.tracks)))
    trk = {b: t for t, b in enumerate(t2b)}
    nf = max(len(t.rotations) for t in a.tracks)
    for f in range(0, nf, step):
        rots = {}
        for b in bones:
            i = idx[b]
            if i in trk and trk[i] < len(a.tracks):
                tr = a.tracks[trk[i]]
                rots[b] = qmat(tr.rotations[min(f, len(tr.rotations) - 1)])
        yield "%s#%d" % (os.path.basename(path), f), rots


def posed_skeleton(skel, parents, rots):
    local = {n: (np.linalg.inv(skel[parents[n]]) @ skel[n] if parents.get(n) else skel[n]) for n in skel}
    for b, r in rots.items():
        s = np.cbrt(np.linalg.det(local[b][:3, :3]))
        local[b] = local[b].copy()
        local[b][:3, :3] = r * s
    out = {}

    def world(n):
        if n not in out:
            p = parents.get(n)
            out[n] = world(p) @ local[n] if p else local[n]
        return out[n]
    for n in skel:
        world(n)
    return out


def ring_in_bone(path):
    """Ring vertices in its bone's frame: a worn ring skinned to one bone, or a static art object whose AttachT names
    the bone (its shapes sit under nodes with identity transforms)."""
    nif = hl_nif.NifFile(path)
    pts, bone = [], None
    for s in nif.shapes:
        d = hl_nif.read_shape(s)
        if d["bones"]:
            assert len(d["bones"]) == 1, "rigid one-bone ring expected"
            bone = d["bones"][0]
            pts.append(((np.c_[d["v"], np.ones(len(d["v"]))] @ d["s2b"][0].T)[:, :3], d["name"]))
        else:
            bone = nif_attach.Nif(path).attach_targets()[0][2][0].split("&", 1)[1]
            pts.append(((np.c_[d["v"], np.ones(len(d["v"]))] @ d["xf"].T)[:, :3], d["name"]))
    metal = np.vstack([p for p, n in pts if "Metal" in n])
    allp = np.vstack([p for p, n in pts])
    c = metal[:, :2].mean(0)
    for _ in range(4):
        th = np.arctan2(metal[:, 0] - c[0], metal[:, 1] - c[1])
        bins = ((th + np.pi) / (2 * np.pi) * 72).astype(int) % 72
        rad = np.linalg.norm(metal[:, :2] - c, axis=1)
        inner = np.array([np.argmin(np.where(bins == k, rad, np.inf)) for k in range(72) if (bins == k).any()])
        A = np.c_[2 * metal[inner, 0], 2 * metal[inner, 1], np.ones(len(inner))]
        c = np.linalg.lstsq(A, (metal[inner, :2] ** 2).sum(1), rcond=None)[0][:2]
    th = np.arctan2(metal[:, 0] - c[0], metal[:, 1] - c[1])
    bins = ((th + np.pi) / (2 * np.pi) * 72).astype(int) % 72
    rad = np.linalg.norm(metal[:, :2] - c, axis=1)
    r_in = np.array([rad[bins == k].min() for k in range(72)])
    zlo = np.array([metal[(bins == k) & (rad < r_in[k] + 0.03), 2].min() for k in range(72)])
    zhi = np.array([metal[(bins == k) & (rad < r_in[k] + 0.03), 2].max() for k in range(72)])
    return bone, c, r_in, zlo, zhi, allp


def side_of(theta):
    a = np.degrees(theta)
    return np.where(np.abs(a) <= 45, 0, np.where(np.abs(a) >= 135, 3, np.where(a > 0, 1, 2)))


def main():
    args = sys.argv[1:]
    step = 6
    if "--step" in args:
        i = args.index("--step")
        step = int(args[i + 1])
        del args[i:i + 2]
    ring_path, hand_path, skel_nif, skel_hkx = args[:4]
    clips = args[4:]
    bone, c, r_in, zlo, zhi, ring_pts = ring_in_bone(ring_path)
    skel = hl_nif.skeleton_globals(skel_nif)
    nif = hl_nif.NifFile(skel_nif)
    parents = {n: (node.parent.name if node.parent is not None else None) for n, node in nif.nodes.items()}
    hk = load_skyrim_skeleton(skel_hkx)
    fingers = [b for b in hk.bones if b.startswith(("NPC R Finger", "NPC L Finger"))]
    hand = hl_nif.read_shape(hl_nif.NifFile(hand_path).shapes[0])
    inv = np.linalg.inv(skel[bone])
    rest = (np.c_[posed(hand, skel), np.ones(len(hand["v"]))] @ inv.T)[:, :3]
    z0 = (zlo.min() + zhi.max()) / 2
    near = ((np.abs(rest[hand["t"]][:, :, 2] - z0) < 1.2) & (np.linalg.norm(rest[hand["t"]][:, :, :2], axis=2) < 2.8)).any(1)
    chain = bone[:13]
    other = sum((hand["w"][:, j] for j, b in enumerate(hand["bones"])
                 if "Finger" in b and not b.startswith(chain)), np.zeros(len(rest)))
    t_near = hand["t"][near]
    t_other = hand["t"][near & (other[hand["t"]].mean(1) >= 0.5)]
    box_lo, box_hi = ring_pts.min(0) - 2 * NEAR, ring_pts.max(0) + 2 * NEAR
    frames = [("bind", {})]
    for clip in clips:
        frames += list(clip_frames(hk, clip, fingers, step))
    print("ring %s: bone %s, inner radius %.3f..%.3f, centre (%.3f, %.3f), band z %.2f..%.2f" % (
        os.path.basename(ring_path), bone, r_in.min(), r_in.max(), c[0], c[1], zlo.min(), zhi.max()))
    rows = []
    for name, rots in frames:
        fs = posed_skeleton(skel, parents, rots) if rots else skel
        pv = (np.c_[posed(hand, fs), np.ones(len(hand["v"]))] @ np.linalg.inv(fs[bone]).T)[:, :3]
        through = np.zeros(4)
        gaps = []
        for z in np.arange(zlo.min(), zhi.max() + 1e-9, 0.03):
            loop = finger_contour(pv, t_near, z, c)
            if loop is None:
                continue
            th = np.arctan2(loop[:, 0] - c[0], loop[:, 1] - c[1])
            k = ((th + np.pi) / (2 * np.pi) * 72).astype(int) % 72
            keep = (z >= zlo[k] + 0.02) & (z <= zhi[k] - 0.02)
            over = np.linalg.norm(loop - c, axis=1) - r_in[k]
            for s in range(4):
                sel = keep & (side_of(th) == s)
                if sel.any():
                    through[s] = max(through[s], over[sel].max())
            gaps.extend((-over[keep]).tolist())
        near_tri = ((pv[t_other] > box_lo) & (pv[t_other] < box_hi)).all(2).any(1)
        so = np.einsum("sk,tkd->tsd", BARY, pv[t_other[near_tri]]).reshape(-1, 3)
        so = so[((so > box_lo) & (so < box_hi)).all(1)]
        dmin = NEAR
        for i in range(0, len(so), 2000):
            dmin = min(dmin, float(np.linalg.norm(so[i:i + 2000, None, :] - ring_pts[None, :, :], axis=2).min()))
        rows.append((name, np.maximum(through, 0), float(np.percentile(gaps, 90)) if gaps else 0.0, dmin))
    by_clip = {}
    for name, th, gap, dmin in rows:
        k = name.split("#")[0].replace(".hkx", "")
        o = by_clip.get(k, (np.zeros(4), 0.0, 9.0))
        by_clip[k] = (np.maximum(o[0], th), max(o[1], gap), min(o[2], dmin))
    print("%-22s %s %8s %8s" % ("clip (max over frames)", " ".join("%18s" % s for s in SIDES), "gap p90", "fingers"))
    for k, (th, gap, dmin) in by_clip.items():
        print("%-22s %s %8.3f %8.3f" % (k, " ".join("%18.3f" % x for x in th), gap, dmin))
    allth = np.array([r[1] for r in rows])
    print("SUMMARY: %d frames; bind through %.3f; max through %.3f (back of hand %.3f); closest other finger %.3f" % (
        len(rows), rows[0][1].max(), allth.max(), allth[:, 0].max(), min(r[3] for r in rows)))


if __name__ == "__main__":
    main()
