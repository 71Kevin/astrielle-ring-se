"""Astrielle Ring geometry in a canonical frame: hole axis +Z, setting toward +Y, centre at the origin.

Parts: band (blackened silver, widens and thickens toward the setting), six-point star plate (gold) with six claws,
cabochon star ruby. Each part returns vertices, triangles, per-vertex UVs and normals. The metal parts share one atlas
(band on the left half, star and claws on the right half); the gem has its own texture (top projection).
"""
import math

import numpy as np

R_IN = 0.95
BAND = dict(t0=0.16, t1=0.26, hw0=0.20, hw1=0.36, power=3.0)
STAR = dict(r_out=0.52, r_in=0.25, thick=0.12, lift=0.02, bevel=0.78)
GEM = dict(r=0.22, height=0.20, base=0.03)
CLAW = dict(r=0.035, height=0.16)
SEG = 96
PROFILE = 16


def smooth_normals(v, t):
    n = np.zeros_like(v)
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def orient(v, t, inside):
    """Flip triangles whose normal points toward inside(face centroid) (a point known to be inside the part)."""
    c = v[t].mean(1)
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    bad = (fn * (c - inside(c))).sum(1) < 0
    t = t.copy()
    t[bad] = t[bad][:, [0, 2, 1]]
    return t


def flat(v, t, uv):
    """Unshared vertices per triangle (hard edges), flat normals."""
    fv, fuv = v[t].reshape(-1, 3), uv[t].reshape(-1, 2)
    ft = np.arange(len(fv)).reshape(-1, 3)
    fn = np.cross(fv[ft[:, 1]] - fv[ft[:, 0]], fv[ft[:, 2]] - fv[ft[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True)
    return fv, ft, fuv, np.repeat(fn, 3, axis=0)


def closeness(theta):
    return ((1 + np.cos(theta)) / 2) ** BAND["power"]


def band():
    """Swept rounded section around +Z; theta = 0 at +Y (under the setting). The inner face is flatter (comfort fit).
    The section starts and ends at the middle of the inner face, so both UV seams (v and u) sit against the finger;
    the outer face runs through v = 0.5."""
    cols = PROFILE + 1
    s = np.linspace(np.pi, 3 * np.pi, cols)
    rows, uvs = [], []
    for i in range(SEG + 1):
        th = 2 * np.pi * i / SEG
        c = closeness(th)
        t = BAND["t0"] + (BAND["t1"] - BAND["t0"]) * c
        hw = BAND["hw0"] + (BAND["hw1"] - BAND["hw0"]) * c
        rc = R_IN + t / 2
        pr = np.cos(s) * t / 2
        pr = np.where(pr < 0, pr * 0.35 - t / 2 * 0.65, pr)
        r = rc + pr
        d = np.array([math.sin(th), math.cos(th)])
        rows.append(np.stack([r * d[0], r * d[1], np.sin(s) * hw], 1))
        uvs.append(np.stack([np.full(cols, 0.5 * i / SEG), (s - np.pi) / (2 * np.pi) * 0.98 + 0.01], 1))
    v, uv = np.vstack(rows), np.vstack(uvs)
    tris = []
    for i in range(SEG):
        for j in range(PROFILE):
            a, b = i * cols + j, i * cols + j + 1
            tris += [(a, a + cols, b), (b, a + cols, b + cols)]
    t = np.array(tris)

    def inside(c):
        rad = np.linalg.norm(c[:, :2], axis=1, keepdims=True)
        ring_pt = c[:, :2] / rad * (R_IN + 0.1)
        return np.c_[ring_pt, np.zeros(len(c))]

    t = orient(v, t, inside)
    n = smooth_normals(v, t)
    first, last = np.arange(cols), np.arange(SEG * cols, (SEG + 1) * cols)
    n[first] = n[last] = (n[first] + n[last]) / 2
    starts, ends = np.arange(0, len(v), cols), np.arange(cols - 1, len(v), cols)
    n[starts] = n[ends] = (n[starts] + n[ends]) / 2
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return v, t, uv, n


def top_y():
    return R_IN + BAND["t1"] + STAR["lift"]


def star_outline():
    a = np.arange(12) * np.pi / 6
    r = np.where(np.arange(12) % 2 == 0, STAR["r_out"], STAR["r_in"])
    return np.stack([r * np.sin(a), r * np.cos(a)], 1)


def star():
    """Six-point star plate in the X-Z plane on top of the band, bevelled top edge, hard edges."""
    out = star_outline()
    y0, y1 = top_y() - 0.05, top_y() + STAR["thick"]
    rings = [(out, y0), (out, y1 - 0.03), (out * STAR["bevel"], y1)]
    v, uv = [], []
    for pts, y in rings:
        for x, z in pts:
            v.append((x, y, z))
            uv.append((0.75 + 0.22 * x / STAR["r_out"], 0.5 + 0.44 * z / STAR["r_out"]))
    v.append((0, y1 + 0.01, 0))
    uv.append((0.75, 0.5))
    v, uv = np.array(v), np.array(uv)
    t = []
    for k in range(2):
        for j in range(12):
            a, b = k * 12 + j, k * 12 + (j + 1) % 12
            t += [(a, b, a + 12), (b, b + 12, a + 12)]
    for j in range(12):
        t.append((24 + j, 24 + (j + 1) % 12, len(v) - 1))
    t = np.array(t)
    mid = (y0 + y1) / 2
    t = orient(v, t, lambda c: np.c_[c[:, 0] * 0.2, np.full(len(c), mid - 0.2), c[:, 2] * 0.2])
    return flat(v, t, uv)


def claws():
    """Six small claws from the star's inner corners up and over the gem's edge."""
    inner = star_outline()[1::2] * 0.92
    y_base = top_y() + STAR["thick"] - 0.01
    vs, ts, uvs = [], [], []
    ring = 8
    for x, z in inner:
        d = np.array([x, 0.0, z]) / math.hypot(x, z)
        p0 = np.array([x, y_base, z])
        p1 = p0 + np.array([0, CLAW["height"], 0]) - d * 0.05
        ax = (p1 - p0) / np.linalg.norm(p1 - p0)
        u = np.cross(ax, d)
        u /= np.linalg.norm(u)
        w = np.cross(ax, u)
        base = len(vs)
        for h, p, rr in ((0, p0, CLAW["r"]), (1, p1, CLAW["r"] * 0.7)):
            for k in range(ring):
                a = 2 * np.pi * k / ring
                vs.append(p + rr * (np.cos(a) * u + np.sin(a) * w))
                uvs.append((0.52 + 0.02 * k / ring, 0.05 + 0.05 * h))
        vs.append(p1 + ax * CLAW["r"] * 0.7)
        uvs.append((0.53, 0.12))
        for k in range(ring):
            a, b = base + k, base + (k + 1) % ring
            ts += [(a, b, a + ring), (b, b + ring, a + ring), (a + ring, b + ring, base + 2 * ring)]
    v, t = np.array(vs), np.array(ts)
    axis_pts = []
    for x, z in inner:
        axis_pts.append((x, z))

    def inside(c):
        best = np.array([min(inner, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[2]) ** 2) for p in c])
        return np.c_[best[:, 0], c[:, 1], best[:, 1]] - np.c_[np.zeros(len(c)), np.full(len(c), 0.0), np.zeros(len(c))]

    t = orient(v, t, inside)
    return v, t, np.array(uvs), smooth_normals(v, t)


def gem():
    """Cabochon: squashed dome over a round base, set on the star; top-projected UVs; pole vertex at the top."""
    y_base = top_y() + STAR["thick"] - 0.005
    rings, seg = 12, 48
    v, uv = [], []
    for i in range(rings):
        phi = (np.pi / 2) * i / rings
        r = GEM["r"] * math.cos(phi)
        y = y_base + GEM["base"] + GEM["height"] * math.sin(phi)
        for k in range(seg):
            a = 2 * np.pi * k / seg
            x, z = r * math.sin(a), r * math.cos(a)
            v.append((x, y, z))
            uv.append((0.5 + 0.48 * x / GEM["r"], 0.5 + 0.48 * z / GEM["r"]))
    pole = len(v)
    v.append((0, y_base + GEM["base"] + GEM["height"], 0))
    uv.append((0.5, 0.5))
    bottom = len(v)
    v.append((0, y_base, 0))
    uv.append((0.5, 0.5))
    v, uv = np.array(v), np.array(uv)
    t = []
    for i in range(rings - 1):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            t += [(a, b, a + seg), (b, b + seg, a + seg)]
    last = (rings - 1) * seg
    for k in range(seg):
        t.append((last + k, last + (k + 1) % seg, pole))
        t.append((k, (k + 1) % seg, bottom))
    t = np.array(t)
    centre = np.array([0, y_base + GEM["height"] * 0.3, 0])
    t = orient(v, t, lambda c: np.tile(centre, (len(c), 1)))
    return v, t, uv, smooth_normals(v, t)


def build():
    return {"band": band(), "star": star(), "claws": claws(), "gem": gem()}


if __name__ == "__main__":
    parts = build()
    allv = np.vstack([p[0] for p in parts.values()])
    for k, (v, t, uv, n) in parts.items():
        print("%-6s verts %5d tris %5d  bbox %s %s" % (k, len(v), len(t), v.min(0).round(2), v.max(0).round(2)))
    print("all bbox", allv.min(0).round(2), allv.max(0).round(2))
