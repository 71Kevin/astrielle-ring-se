"""Preview renders of the Astrielle Ring (Blender 4.3 + PyNifly).

blender --background --factory-startup --python render_ring.py -- <out_dir> <meshes_dir> <png_dir>
    <skeleton_female.nif> <femalehands_1.nif> <skeleton.nif> <malehands_1.nif> [<skeleton_female.hkx> <idle.hkx>]
Close-ups of the ground model with its PNG textures (EEVEE), then the worn models on the hands, both skinned on the
skeleton the way the game does it (bone transform x the shape's skin-to-bone), from the back of the hand, the thumb side
and the palm; with the HKX pair, the female hand again in the first frame of that clip.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
argv = sys.argv[sys.argv.index("--") + 1:]
out_dir, meshes, pngs, skel_f, hands_f, skel_m, hands_m = argv[:7]
idle = argv[7:9]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="io_scene_nifly")
import hl_nif  # noqa: E402
from finger_fit import posed  # noqa: E402

scn = bpy.context.scene
BONE = "NPC R Finger10 [RF10]"


def material(name, png, metallic, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(png)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    return m


def mesh_object(name, v, t, uv=None, mat=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(x) for x in np.asarray(v)], [], [tuple(int(i) for i in x) for x in np.asarray(t)])
    if uv is not None:
        layer = me.uv_layers.new()
        for loop in me.loops:
            u, w = uv[loop.vertex_index]
            layer.data[loop.index].uv = (u, 1 - w)
    for p in me.polygons:
        p.use_smooth = smooth
    o = bpy.data.objects.new(name, me)
    scn.collection.objects.link(o)
    if mat is not None:
        o.data.materials.append(mat)
    return o


def camera(target, direction, ortho):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho
    scn.collection.objects.link(cam)
    d = Vector(direction).normalized() * 60
    cam.location = Vector(target) + d
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
    return cam


def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return Vector([min(p[k] for p in pts) for k in range(3)]), Vector([max(p[k] for p in pts) for k in range(3)])


def render(path, target, direction, ortho):
    cam = camera(target, direction, ortho)
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)


metal = material("metal", os.path.join(pngs, "ring_d.png"), 1.0, 0.25)
gemm = material("gem", os.path.join(pngs, "gem_d.png"), 0.0, 0.08)
skin = bpy.data.materials.new("skin")
skin.use_nodes = True
skin.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.78, 0.6, 0.5, 1)
skin.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.37, 0.42, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.2
scn.world = world
light = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
light.data.energy = 4
light.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
scn.collection.objects.link(light)
scn.render.engine = "BLENDER_EEVEE_NEXT"
scn.render.resolution_x = scn.render.resolution_y = 640


def nif_objects(path, skel=None):
    objs = []
    for s in hl_nif.NifFile(path).shapes:
        d = hl_nif.read_shape(s)
        v = posed(d, skel) if skel is not None else d["v"] @ d["xf"][:3, :3].T + d["xf"][:3, 3]
        mat = skin if "Ring" not in d["name"] else (gemm if "Gem" in d["name"] else metal)
        objs.append(mesh_object(d["name"], v, d["t"], d["uv"], mat))
    return objs


ground = nif_objects(os.path.join(meshes, "AstrielleRingGO.nif"))
lo, hi = bbox(ground)
centre = (lo + hi) / 2
gem_obj = [o for o in ground if "Gem" in o.name][0]
glo, ghi = bbox([gem_obj])
setting = ((glo + ghi) / 2 - centre).normalized()
for name, d in (("top", (0, -0.35, 1)), ("side", (1, -0.2, 0.25)), ("front", (0.05, -1, 0.3)),
                ("setting", tuple(setting + Vector((0.15, -0.25, 0.2))))):
    target = centre if name != "setting" else (glo + ghi) / 2
    render(os.path.join(out_dir, "ring_%s.png" % name), target, d, max(hi - lo) * (1.35 if name != "setting" else 0.75))
for o in ground:
    o.hide_render = True


def worn_views(tag, skel, hand_nif, ring_nif):
    objs = nif_objects(hand_nif, skel) + nif_objects(ring_nif, skel)
    ring = [o for o in objs if "Ring" in o.name]
    lo, hi = bbox(ring)
    target = (lo + hi) / 2
    r = skel[BONE][:3, :3] / np.cbrt(np.linalg.det(skel[BONE][:3, :3]))
    back, thumb, along = r[:, 1], r[:, 0], r[:, 2]
    for name, d, ortho in (("back", back - 0.25 * along, 5), ("thumb", thumb + 0.3 * back, 5), ("palm", -back - 0.2 * along, 5),
                           ("wide", back + 0.4 * thumb - 0.6 * along, 14)):
        render(os.path.join(out_dir, "worn_%s_%s.png" % (tag, name)), target, tuple(d), ortho)
    for o in objs:
        o.hide_render = True


worn_views("female", hl_nif.skeleton_globals(skel_f), hands_f, os.path.join(meshes, "AstrielleRingF_1.nif"))
worn_views("male", hl_nif.skeleton_globals(skel_m), hands_m, os.path.join(meshes, "AstrielleRing_1.nif"))
if idle:
    from check_fit import clip_frames, load_skyrim_skeleton, posed_skeleton  # noqa: E402
    skel = hl_nif.skeleton_globals(skel_f)
    nif = hl_nif.NifFile(skel_f)
    parents = {n: (node.parent.name if node.parent is not None else None) for n, node in nif.nodes.items()}
    hk = load_skyrim_skeleton(idle[0])
    fingers = [b for b in hk.bones if b.startswith("NPC R Finger")]
    name, rots = next(clip_frames(hk, idle[1], fingers, 1))
    worn_views("female_idle", posed_skeleton(skel, parents, rots), hands_f, os.path.join(meshes, "AstrielleRingF_1.nif"))
print("RENDER done")
