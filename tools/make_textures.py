"""Procedural textures for the Astrielle Ring (PNG sources; textures.sh converts them to BC7 DDS with mips).

Metal atlas 4096 x 2048: left half = band (u around the ring, v around the section; outer face at v = 0.5), blackened
silver with a row of six-point stars along the outer face (drawn in model units, so they are not stretched by the
band's UV, which is much tighter around the ring than across it) and two grooves near the edges, both inlaid with gold;
right half = star plate (top projection, centre (0.75, 0.5)) and claws, warm gold with rays and a ring line in black
enamel. Gem 2048 x 2048: star ruby, deep blood red with a six-ray asterism. Outputs: <out>/ring_d.png, ring_h.png
(height for the normal map), ring_m.png (environment mask), gem_d.png, gem_m.png (constant, 256 x 256).

make_textures.py <out_dir>
"""
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ring_geometry as G  # noqa: E402

W, H = 4096, 2048
GEM = 2048
STAR_R = (0.075, 0.03)
rng = np.random.default_rng(7)

BLACK_SILVER = np.array([0.115, 0.110, 0.128])
INNER = np.array([0.165, 0.160, 0.178])
INLAY_GOLD = np.array([0.86, 0.65, 0.28])
PLATE_GOLD = np.array([0.82, 0.61, 0.25])
ENAMEL = np.array([0.075, 0.060, 0.065])


def star_mask(x, y, cx, cy, r_out, r_in, soft):
    """Distance-like mask of a six-point star centred at (cx, cy) (1 inside, 0 outside), in the units of x and y."""
    dx, dy = x - cx, y - cy
    ang = np.arctan2(dx, dy)
    rad = np.hypot(dx, dy)
    k = np.abs(((ang / (np.pi / 3)) % 1.0) - 0.5) * 2
    edge = r_in + (r_out - r_in) * k
    return np.clip((edge - rad) / soft, 0, 1)


def brushed():
    """Brushing along the band at the 1024 px scale, upsampled, plus fine grain at full size."""
    coarse = rng.normal(0, 1, (H // 4, W // 4))
    for _ in range(3):
        coarse = (coarse + np.roll(coarse, 1, axis=1) + np.roll(coarse, -1, axis=1)) / 3
    coarse = cv2.resize(coarse.astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    fine = cv2.blur(rng.normal(0, 1, (H, W)).astype(np.float32), (13, 1))
    b = coarse + 0.35 * fine / (np.abs(fine).max() + 1e-9) * np.abs(coarse).max()
    return (b - b.min()) / (np.ptp(b) + 1e-9) - 0.5


def metal():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = x / W, y / H
    band = u < 0.5
    plate = ~band
    grain = brushed()
    outer = np.abs(v - 0.5)
    groove = np.exp(-((outer - 0.17) / 0.008) ** 2) * band
    n_stars = 18
    cx = (np.floor(u * 2 * n_stars) + 0.5) / (2 * n_stars) * W
    theta = 4 * np.pi * np.minimum(u, 0.5)
    c = G.closeness(theta)
    thick = G.BAND["t0"] + (G.BAND["t1"] - G.BAND["t0"]) * c
    half = G.BAND["hw0"] + (G.BAND["hw1"] - G.BAND["hw0"]) * c
    px_x = 0.5 * W / (2 * np.pi * (G.R_IN + thick))
    px_y = 0.98 * H / (2 * np.pi * half)
    stars = star_mask((x - cx) / px_x, (y - 0.5 * H) / px_y, 0, 0, STAR_R[0], STAR_R[1], 1.2 / px_y) * band
    pu, pv = (u - 0.75) / 0.22, (v - 0.5) / 0.44
    ang = np.arctan2(pu, pv)
    rad = np.hypot(pu, pv)
    rays = np.exp(-((np.abs(((ang / (np.pi / 3)) + 0.5) % 1.0 - 0.5)) / 0.025) ** 2) * (rad > 0.18) * (rad < 0.95) * plate
    ring_line = np.exp(-((rad - 0.42) / 0.012) ** 2) * plate
    inlay = np.clip(np.maximum(groove * 1.4, stars), 0, 1)
    enamel = np.clip(np.maximum(rays, ring_line), 0, 1)

    height = -0.45 * groove - 0.35 * stars - 0.5 * rays - 0.4 * ring_line
    inside = np.clip((outer - 0.30) / 0.06, 0, 1)[..., None]
    band_col = BLACK_SILVER + (INNER - BLACK_SILVER) * inside
    base = np.where(band[..., None], band_col, PLATE_GOLD)
    base = base + (INLAY_GOLD - base) * inlay[..., None]
    base = base + (ENAMEL - base) * enamel[..., None]
    sheen = np.where(band, 0.10, 0.06)[..., None]
    shade = 1 + sheen * grain[..., None] - 0.25 * np.clip(-height, 0, 1)[..., None] * (1 - inlay[..., None])
    diffuse = np.clip(base * shade, 0, 1)
    mask = np.where(band, 0.62, 0.66)
    mask = mask + (0.78 - mask) * inlay
    mask = mask + (0.30 - mask) * enamel
    return diffuse, height, mask


def gem():
    n = GEM
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    pu, pv = (x - n / 2) / (n * 0.48), (y - n / 2) / (n * 0.48)
    rad = np.hypot(pu, pv)
    deep, light = np.array([0.20, 0.008, 0.030]), np.array([0.84, 0.10, 0.15])
    body = deep + (light - deep) * np.clip(1 - rad, 0, 1)[..., None] ** 1.7
    silk = rng.normal(0, 1, (512, 512))
    for _ in range(4):
        silk = (silk + np.roll(silk, 1, 0) + np.roll(silk, -1, 0) + np.roll(silk, 1, 1) + np.roll(silk, -1, 1)) / 5
    silk = cv2.resize((silk / (np.abs(silk).max() + 1e-9)).astype(np.float32), (n, n), interpolation=cv2.INTER_CUBIC)
    star = np.zeros((n, n), dtype=np.float32)
    for a in (0, np.pi / 3, 2 * np.pi / 3):
        d = np.abs(pu * math.cos(a) - pv * math.sin(a))
        star += np.exp(-(d / 0.03) ** 2) * np.clip(1 - rad / 0.95, 0, 1) ** 0.7
    star = np.clip(star, 0, 1.2)
    glow = np.exp(-(rad / 0.16) ** 2) * 0.35
    col = body * (1 + 0.06 * silk[..., None]) + (star * 0.42)[..., None] * np.array([1.0, 0.80, 0.84]) \
        + (glow * 0.7)[..., None] * np.array([1.0, 0.42, 0.46])
    return np.clip(col, 0, 1), np.full((256, 256), 0.85)


def save(a, path):
    if a.ndim == 2:
        Image.fromarray(np.rint(np.clip(a, 0, 1) * 255).astype("uint8"), "L").convert("RGB").save(path)
    else:
        Image.fromarray(np.rint(np.clip(a, 0, 1) * 255).astype("uint8"), "RGB").save(path)


def main(out):
    os.makedirs(out, exist_ok=True)
    d, h, m = metal()
    save(d, os.path.join(out, "ring_d.png"))
    save((h - h.min()) / (np.ptp(h) + 1e-9), os.path.join(out, "ring_h.png"))
    save(m, os.path.join(out, "ring_m.png"))
    gd, gm = gem()
    save(gd, os.path.join(out, "gem_d.png"))
    save(gm, os.path.join(out, "gem_m.png"))
    print("textures written to", out)


if __name__ == "__main__":
    main(sys.argv[1])
