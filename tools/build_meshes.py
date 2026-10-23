"""Astrielle Ring meshes (run in Blender 4.3 with PyNifly; bmesh builds the collision hull).

blender --background --factory-startup --python build_meshes.py -- <out_meshes_dir> <vanilla_dir> <fit.json>
Writes the worn models AstrielleRingF_1.nif (female), AstrielleRing_1.nif and AstrielleRing_0.nif (male, weight slider),
rigid on NPC R Finger10 [RF10] with partition 36, placed and bound as finger_fit.py measured on the hands, the
ground/inventory model AstrielleRingGO.nif (BSFadeNode, convex collision), and the Jewelry Limiter displays
JewelryLimiter\AstrielleRingF\Ring_*.nif and JewelryLimiter\AstrielleRing\Ring_*.nif: static art objects whose AttachT
puts the ring on another finger bone, in that bone's frame. The vanilla Gold Sapphire Ring meshes (read from
<vanilla_dir>) only give the ground model's frame and inventory marker and the shader settings; no geometry or texture
is taken from them.
"""
import json
import os
import sys

import bpy  # noqa: F401
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import hl_nif  # noqa: E402
import nif_attach  # noqa: E402
import nif_rigid_lib as rl  # noqa: E402
import ring_geometry as G  # noqa: E402

out_dir, vanilla_dir, fit_json = sys.argv[sys.argv.index("--") + 1:][:3]
VAN_GO = os.path.join(vanilla_dir, "goldringsapphirego.nif")
VAN_WORN = os.path.join(vanilla_dir, "goldringsapphire_1.nif")
TEX_DIR = "textures\\Tinesh\\AstrielleRing\\"
TEX = {
    "metal": {"Diffuse": TEX_DIR + "AstrielleRing_d.dds", "Normal": TEX_DIR + "AstrielleRing_n.dds",
              "EnvMap": r"textures\cubemaps\ore_silver_e.dds", "EnvMask": TEX_DIR + "AstrielleRing_m.dds"},
    "gem": {"Diffuse": TEX_DIR + "AstrielleGem_d.dds", "Normal": TEX_DIR + "AstrielleGem_n.dds",
            "EnvMap": r"textures\cubemaps\shinyglass_e.dds", "EnvMask": TEX_DIR + "AstrielleGem_m.dds"},
}
SHAPES = (("AstrielleRingMetal", ["band", "star", "claws"], "metal"), ("AstrielleRingGem", ["gem"], "gem"))


def circle(p):
    A = np.c_[2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))]
    sol = np.linalg.lstsq(A, (p ** 2).sum(1), rcond=None)[0]
    return sol[:2]


def frame(points, normals):
    """Ring frame of a ring mesh: (hole centre, hole axis, setting direction, outer radius, inner radius).
    Axis = least-variance direction; the hole is fitted on the inner surface (vertex normals pointing at the hole),
    which goes all the way round, so the setting's mass does not pull the centre. The setting carries most of the
    vertices, so it lies where the vertex centroid sits off the hole centre."""
    c = points.mean(0)
    w, vec = np.linalg.eigh(np.cov((points - c).T))
    axis, b1, b2 = vec[:, 0], vec[:, 2], vec[:, 1]
    p = np.c_[(points - c) @ b1, (points - c) @ b2]
    q = np.c_[normals @ b1, normals @ b2]
    cc = circle(p)
    for _ in range(3):
        d = p - cc
        inner = (q * d).sum(1) < -0.5 * np.linalg.norm(d, axis=1) * np.linalg.norm(q, axis=1)
        cc = circle(p[inner])
    rad = np.linalg.norm(p - cc, axis=1)
    r_in = float(np.median(rad[inner]))
    gem_dir = -cc / np.linalg.norm(cc)
    r_out = float(np.percentile(rad[~inner], 50))
    centre = c + b1 * cc[0] + b2 * cc[1]
    e1 = b1 * gem_dir[0] + b2 * gem_dir[1]
    return centre, axis, e1, r_out, r_in


def placement(points, normals):
    """4x4 matrix from the canonical ring frame (+Z axis, +Y setting) to the frame of a vanilla ring mesh."""
    centre, axis, e1, r_out, r_in = frame(points, normals)
    scale = r_in / G.R_IN
    x = np.cross(e1, axis)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = x * scale, e1 * scale, axis * scale
    m[:3, 3] = centre
    return m, {"vanilla_inner_radius": round(float(r_in), 3), "vanilla_outer_radius": round(float(r_out), 3),
               "scale": round(float(scale), 3)}


def transformed(parts, m):
    out = {}
    rot = m[:3, :3] / np.cbrt(np.linalg.det(m[:3, :3]))
    for k, (v, t, uv, n) in parts.items():
        out[k] = (v @ m[:3, :3].T + m[:3, 3], t, uv, n @ rot.T)
    return out


def merged(parts, names):
    vs, ts, uvs, ns, off = [], [], [], [], 0
    for k in names:
        v, t, uv, n = parts[k]
        vs.append(v)
        ts.append(t + off)
        uvs.append(uv)
        ns.append(n)
        off += len(v)
    return np.vstack(vs), np.vstack(ts), np.vstack(uvs), np.vstack(ns)


def shader_from(path, flags2_clear=0x20):
    shape = hl_nif.NifFile(path).shapes[0]
    s = hl_nif.shader_settings(shape)
    s["Shader_Flags_2"] = int(s["Shader_Flags_2"]) & ~flags2_clear
    return s


def on_finger(fit):
    """Canonical ring scaled to the fitted inner radius, hole along the finger (bone +z), setting on the back of the
    hand (bone +y), in the finger bone's frame."""
    local = np.eye(4)
    local[:3, :3] *= fit["scale"]
    local[:3, 3] = [fit["centre"][0], fit["centre"][1], fit["z0"]]
    return local


def write_worn(parts, path, fit):
    """Vertices stored in the hand's skin space, bound with the hand's RF10 transform."""
    skin_to_bone = np.array(fit["skin_to_bone"])
    p = transformed(parts, np.linalg.inv(skin_to_bone) @ on_finger(fit))
    nif = hl_nif.new_nif(path, os.path.basename(path))
    shader = shader_from(VAN_WORN)
    bone = fit["bone"]
    for name, keys, tex in SHAPES:
        v, t, uv, n = merged(p, keys)
        hl_nif.add_skinned_shape(nif, name, v, t, uv, n, [bone], np.ones((len(v), 1)),
                                 {bone: np.linalg.inv(skin_to_bone)}, 36, shader, TEX[tex])
    nif.save()
    allv = np.vstack([x[0] for x in p.values()])
    return {"scale": fit["scale"], "inner_radius": fit["inner_radius"], "z0": fit["z0"], "centre": fit["centre"],
            "skin_bbox_min": allv.min(0).round(2).tolist(), "skin_bbox_max": allv.max(0).round(2).tolist()}


def write_ground(parts, path):
    vnif = hl_nif.NifFile(VAN_GO)
    van = hl_nif.read_shape(vnif.shapes[0])
    m, info = placement(np.asarray(van["v"]), np.asarray(van["n"]))
    p = transformed(parts, m)
    nif = hl_nif.NifFile()
    nif.initialize("SKYRIMSE", path, "BSFadeNode", "AstrielleRing")
    root = nif.rootNode
    rl.copy_root_extra_data(vnif.rootNode, nif, root)
    shader = shader_from(VAN_GO)
    for name, keys, tex in SHAPES:
        v, t, uv, n = merged(p, keys)
        hl_nif.add_static_shape(nif, name, v, t, uv, n, shader, TEX[tex], parent=root)
    allv = np.vstack([x[0] for x in p.values()])
    coll = rl.add_convex_collision(root, allv, vnif.rootNode.collision_object, 0.25, 1.0, 32)
    nif.save()
    info.update({"collision": coll, "bounds": rl.bounds(allv),
                 "setting_direction": (m[:3, 1] / np.linalg.norm(m[:3, 1])).round(3).tolist()})
    return info


def write_display(parts, path, fit):
    """Jewelry Limiter display: root with BSX and AttachT, one node whose children follow the finger bone."""
    p = transformed(parts, on_finger(fit))
    nif = hl_nif.NifFile()
    nif.initialize("SKYRIMSE", path, "BSFadeNode", "AstrielleRingDisplay")
    hl_nif.add_bsx(nif, 1)
    hl_nif.add_root_string(nif, "AttachT", "AttachT")
    node = nif.add_node("AstrielleRing", hl_nif.mat_to_xf(np.eye(4)), nif.rootNode)
    shader = shader_from(VAN_GO)
    for name, keys, tex in SHAPES:
        v, t, uv, n = merged(p, keys)
        hl_nif.add_static_shape(nif, name, v, t, uv, n, shader, TEX[tex], parent=node)
    nif.save()
    targets = nif_attach.attach(path, fit["bone"])
    return {"bone": fit["bone"], "attach": targets[0][2], "z0": fit["z0"], "inner_radius": fit["inner_radius"]}


os.makedirs(out_dir, exist_ok=True)
fits = json.load(open(fit_json))
parts = G.build()
displays = {}
for gender, folder in (("female", "AstrielleRingF"), ("male", "AstrielleRing")):
    os.makedirs(os.path.join(out_dir, "JewelryLimiter", folder), exist_ok=True)
    for name, fit in fits["displays"][gender].items():
        displays[folder + "\\" + name] = write_display(parts, os.path.join(out_dir, "JewelryLimiter", folder, name), fit)
report = {"worn": {name: write_worn(parts, os.path.join(out_dir, name), fit) for name, fit in fits["worn"].items()},
          "ground": write_ground(parts, os.path.join(out_dir, "AstrielleRingGO.nif")),
          "displays": displays,
          "counts": {k: [len(v[0]), len(v[1])] for k, v in parts.items()}}
json.dump(report, open(os.path.join(out_dir, "..", "meshes_report.json"), "w"), indent=1)
print("MESHES", json.dumps(report))
