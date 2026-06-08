import sys
import os
import json
import math
import FreeCAD as App
import Part
import Mesh


# ─────────────────────────────────────────────────────────────────────────────
# Z-COORDINATE CONTRACT
# ─────────────────────────────────────────────────────────────────────────────
# The ring band is a torus in the XZ plane; the finger hole runs along Y.
#
#   Z =  0           → ring geometric centre (equator)
#   Z = +outer_r     → top of the band   ← gallery base attaches here
#   Z = -outer_r     → bottom of the band
#
# Every component's z_offset parameter = the BASE (lowest Z) of that component.
# The gem shape is built with pavilion tip at Z=0, table at Z=height,
# then translated so the pavilion tip lands at z_offset.
# ─────────────────────────────────────────────────────────────────────────────


def create_gem_shape(cut, width, length, height):
    """
    Gem built from Z=0 (pavilion tip / base) to Z=height (table / top).
    Caller translates by z_offset to place the base at the correct world Z.
    """
    cut = cut.lower()
    r   = width / 2.0

    pavilion_h = height * 0.60
    girdle_h   = height * 0.08
    crown_h    = height * 0.32

    pavilion = Part.makeCone(0.05, r, pavilion_h,
                              App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    girdle   = Part.makeCylinder(r, girdle_h,
                                  App.Vector(0, 0, pavilion_h), App.Vector(0, 0, 1))
    crown    = Part.makeCone(r, r * 0.55, crown_h,
                              App.Vector(0, 0, pavilion_h + girdle_h), App.Vector(0, 0, 1))

    gem = pavilion.fuse(girdle).fuse(crown)

    if cut == "oval":
        scale_y = length / width if width > 0 else 1.0
        gem.scale(App.Vector(1.0, scale_y, 1.0))
    elif cut == "princess":
        w2, l2 = width / 2.0, length / 2.0
        pav  = Part.makeWedge(-w2, -l2, 0,  w2,  l2, pavilion_h,  0, 0, 0, 0, 0, 0)
        gird = Part.makeBox(width, length, girdle_h,
                             App.Vector(-w2, -l2, pavilion_h))
        crn  = Part.makeWedge(-w2, -l2, pavilion_h + girdle_h,
                                w2,  l2, pavilion_h + girdle_h + crown_h,
                               -w2*0.6, -l2*0.6, -w2*0.6, w2*0.6, l2*0.6, -w2*0.6)
        gem  = pav.fuse(gird).fuse(crn)
    elif cut == "cushion":
        scale_y = length / width if width > 0 else 1.0
        gem.scale(App.Vector(1.0, scale_y, 1.0))

    return gem


def create_band_shape(inner_radius, width, thickness, profile_type):
    """
    Ring band: torus in the XZ plane, finger hole along Y.
    Spans Y from -width/2 to +width/2.
    The metal ring cross-section sits in XZ; outer radius = inner_radius + thickness.
    """
    outer_radius = inner_radius + thickness
    outer_cyl = Part.makeCylinder(outer_radius, width,
                                   App.Vector(0, -width/2.0, 0), App.Vector(0, 1, 0))
    inner_cyl = Part.makeCylinder(inner_radius, width,
                                   App.Vector(0, -width/2.0, 0), App.Vector(0, 1, 0))
    band = outer_cyl.cut(inner_cyl)

    if profile_type == "court":
        outer_edges = []
        for edge in band.Edges:
            try:
                curve = edge.Curve
                if hasattr(curve, "Radius") and abs(curve.Radius - outer_radius) < 0.01:
                    outer_edges.append(edge)
            except:
                pass
        if len(outer_edges) >= 2:
            try:
                band = band.makeFillet(thickness * 0.25, outer_edges)
            except Exception as e:
                print(f"Fillet failed: {e}")
    return band


def create_gallery_shape(style, width, height, z_offset,
                          inner_radius=8.5, thickness=1.8, band_width=2.5):
    """
    Open-basket gallery connecting band top to stone seat.

    z_offset  = band outer_radius (= band top)
    z_offset + height = stone base

    The gallery MUST touch the band at z_offset.  To do this we build:
      • A tapered cone/frustum from (r=outer_radius, z=z_offset) narrowing
        to (r=gallery_r, z=z_offset+height) — this is the cathedral shoulder.
      • A stone-seat ring at the top.
    """
    outer_radius = inner_radius + thickness
    gallery_r    = width / 2.0          # radius of the stone seat ring

    # ── Stone seat ring at the top ─────────────────────────────────────────
    seat_h     = 0.5
    seat_top_z = z_offset + height
    seat_outer = Part.makeCylinder(gallery_r, seat_h,
                                    App.Vector(0, 0, seat_top_z - seat_h),
                                    App.Vector(0, 0, 1))
    seat_inner = Part.makeCylinder(gallery_r - 0.4, seat_h,
                                    App.Vector(0, 0, seat_top_z - seat_h),
                                    App.Vector(0, 0, 1))
    seat_ring  = seat_outer.cut(seat_inner)
    gallery    = seat_ring

    # ── Cathedral shoulders: tapered frustum from band edge to seat ────────
    # We build 4 thin tapered pillars at 45°/135°/225°/315° (prong positions)
    # This is more realistic than a solid cone and matches a solitaire basket.
    w_pillar = max(0.6, thickness * 0.35)

    for angle_deg in [45, 135, 225, 315]:
        angle  = math.radians(angle_deg)
        # Start point on the band top circle (XZ plane, at z=z_offset)
        x_bot  = outer_radius * math.cos(angle)
        z_bot  = outer_radius * math.sin(angle)   # <-- uses Z as "up"
        # Wait — the band top is the set of points (x,0,z) with x²+z²=outer_r²
        # and z > 0 specifically: the TOP of the band is at z = +outer_radius
        # That single point is (0, 0, outer_radius). The band top is a CIRCLE
        # in the XZ plane. We want to run pillars from the circumference of this
        # circle up to the seat ring.
        #
        # Since the seat ring is centred on the Z axis (small r = gallery_r ≈ 3.9mm)
        # and the band top circle has r = outer_radius ≈ 10.3mm, the pillars must
        # bridge from radius 10.3 DOWN to radius 3.9 — but they do so at different
        # XZ angles.  The pillar for angle=45° starts at:
        #   (outer_r * cos45, 0, outer_r * sin45) = (7.28, 0, 7.28) in XYZ
        # and ends at:
        #   (gallery_r * cos45, 0, z_offset + height) = (2.76, 0, 15.3)
        #
        # This works ONLY if z_offset = outer_radius AND the pillars truly start
        # at the band metal.  Let's verify: x_bot²+z_bot² = outer_r²  ✓
        # The pillar starts embedded in the band and rises to the seat.

        x_top  = gallery_r * math.cos(angle)
        z_top  = gallery_r * math.sin(angle)
        z_top_world = seat_top_z - seat_h   # top of pillar = bottom of seat

        # Build pillar as a lofted box approximation: a thin rectangular extrusion
        # from bottom point to top point in 3D
        dx = x_top - x_bot
        dz = z_top_world - z_bot
        length_3d = math.sqrt(dx*dx + dz*dz)
        if length_3d < 0.1:
            continue

        # Create a thin box along the Z axis and then rotate/translate it
        pillar = Part.makeBox(w_pillar, w_pillar, length_3d,
                               App.Vector(-w_pillar/2.0, -w_pillar/2.0, 0))

        # Rotate to point from (x_bot, 0, z_bot) toward (x_top, 0, z_top_world)
        angle_pitch = math.degrees(math.atan2(dx, dz))
        pillar.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), -angle_pitch)
        pillar.translate(App.Vector(x_bot, 0, z_bot))

        try:
            gallery = gallery.fuse(pillar)
        except Exception as e:
            print(f"Pillar fuse failed at {angle_deg}°: {e}")

    return gallery


def create_bridge_shape(height, z_offset, inner_radius=8.5, band_width=2.5):
    """Bridge across the under-gallery, flush with the band."""
    w_bridge   = (inner_radius + 0.5) * 2.0
    block      = Part.makeBox(w_bridge, band_width, height,
                               App.Vector(-w_bridge/2.0, -band_width/2.0, z_offset))
    finger_cyl = Part.makeCylinder(inner_radius, band_width + 1.0,
                                    App.Vector(0, -band_width/2.0 - 0.5, 0),
                                    App.Vector(0, 1, 0))
    try:
        return block.cut(finger_cyl)
    except Exception as e:
        print(f"Bridge cut failed: {e}. Returning block.")
        return block


def _make_prong_shaft(radius, height, z_offset, x, y, orientation, placement_plane):
    """
    Build a single prong shaft cylinder placed at (x, y) in the correct plane.

    orientation     : "radial"   — prong radiates outward from stone in XY plane
                      "vertical" — prong is a pillar aligned with the Z axis
    placement_plane : "XY" — prong positions are given as (x, y, z_offset),
                              which is the standard top-view layout.
                      "XZ" — prong positions are in the ring's equatorial plane;
                              y=0 for all prongs, z position encodes the angle.
    """
    if placement_plane == "XZ":
        # Prong sits in the XZ plane (ring equator); it runs along Y
        shaft = Part.makeCylinder(radius, height,
                                   App.Vector(x, -height / 2.0, y),
                                   App.Vector(0, 1, 0))
    else:
        # Default XY plane — prong runs along Z (vertical)
        shaft = Part.makeCylinder(radius, height,
                                   App.Vector(x, y, z_offset),
                                   App.Vector(0, 0, 1))
    return shaft


def _make_prong_tip(prong_style, radius, shaft_top_center):
    """
    Build the prong tip shape based on the semantic prong_style.

    prong_style options:
      "claw"        — hemisphere + inward-curving cone cap (tapers inward)
      "round_tip"   — simple sphere (ball tip)
      "flat"        — flat disc cap
      "double_claw" — two smaller hemispheres side-by-side (forked tip)

    shaft_top_center : App.Vector at the top centre of the shaft
    """
    x, y, z = shaft_top_center.x, shaft_top_center.y, shaft_top_center.z

    if prong_style == "round_tip":
        return Part.makeSphere(radius, shaft_top_center)

    elif prong_style == "flat":
        # Flat disc, slightly wider than the shaft
        disc_r = radius * 1.4
        disc_h = radius * 0.4
        return Part.makeCylinder(disc_r, disc_h,
                                  App.Vector(x - disc_r / 2.0, y - disc_r / 2.0, z),
                                  App.Vector(0, 0, 1))

    elif prong_style == "double_claw":
        # Two small spheres offset perpendicular to the stone radius
        offset = radius * 0.7
        tip1 = Part.makeSphere(radius * 0.75,
                                App.Vector(x + offset, y, z))
        tip2 = Part.makeSphere(radius * 0.75,
                                App.Vector(x - offset, y, z))
        return tip1.fuse(tip2)

    else:  # "claw" (default) — a small sphere + inward-curving cone cap
        sphere = Part.makeSphere(radius, shaft_top_center)
        # Cone that tapers inward: base radius = prong radius, tip = 0
        # oriented toward the stone centre (origin), so it points inward
        cone_h = radius * 1.5
        # Direction from prong tip toward ring centre (inward)
        toward_centre = App.Vector(-x, -y, 0)
        length = math.sqrt(x * x + y * y)
        if length > 0.001:
            toward_centre = App.Vector(
                toward_centre.x / length,
                toward_centre.y / length,
                0
            )
        else:
            toward_centre = App.Vector(0, 0, 1)
        cap = Part.makeCone(radius, 0, cone_h, shaft_top_center, toward_centre)
        return sphere.fuse(cap)


def create_prongs_shape(count, radius, height, radial_distance, z_offset,
                         prong_style="claw", orientation="radial",
                         placement_plane="XY", angles_deg=None):
    """
    Build all prong shapes.

    Parameters driven by COCO annotation geometry (never hardcoded here):
      angles_deg      — per-prong placement angles (degrees) derived from the
                        pixel positions of individual prong bboxes relative to
                        the stone centre in the top-view annotation.
                        If None, falls back to an even distribution.
      orientation     — "radial" | "vertical" (from bbox aspect-ratio analysis)
      placement_plane — "XY" | "XZ" (from which view prongs are visible)

    Parameters driven by semantic extraction:
      prong_style     — "claw" | "round_tip" | "flat" | "double_claw"
                        controls tip geometry, not placement.
    """
    # Build angle list — use annotation-derived angles when available,
    # otherwise distribute evenly (still no hardcoded assumptions about style).
    if angles_deg and len(angles_deg) >= count:
        angles = angles_deg[:count]
    elif angles_deg and len(angles_deg) > 0:
        # Annotation had fewer angles than expected count; use what we have
        # and fill the rest evenly from the last angle
        step = 360.0 / count
        start = angles_deg[-1] + step if angles_deg else 0.0
        extra = [start + i * step for i in range(count - len(angles_deg))]
        angles = list(angles_deg) + extra
    else:
        # No annotation angles at all — distribute evenly (no style assumptions)
        step = 360.0 / count
        angles = [i * step for i in range(count)]

    prongs_list = []
    for angle_deg in angles:
        rad = math.radians(angle_deg)
        x   = radial_distance * math.cos(rad)
        y   = radial_distance * math.sin(rad)

        shaft = _make_prong_shaft(radius, height, z_offset, x, y,
                                   orientation, placement_plane)

        # Compute the shaft tip centre for tip attachment
        if placement_plane == "XZ":
            tip_center = App.Vector(x, 0, y + height / 2.0)
        else:
            tip_center = App.Vector(x, y, z_offset + height)

        tip = _make_prong_tip(prong_style, radius, tip_center)

        prong = shaft.fuse(tip)
        prongs_list.append(prong)

    if not prongs_list:
        return None
    fused = prongs_list[0]
    for p in prongs_list[1:]:
        fused = fused.fuse(p)
    return fused


def create_side_stones_shape(stone_size, stone_count,
                               inner_radius=8.5, thickness=1.8, band_width=2.5):
    r_place    = inner_radius + thickness - 0.2
    gems_list  = []
    gem_h      = stone_size * 0.6
    half_count = max(1, stone_count // 2)
    right_a    = [45 + i * (35.0 / half_count) for i in range(half_count)]
    left_a     = [100 + i * (35.0 / half_count) for i in range(half_count)]

    for angle in right_a + left_a:
        rad = math.radians(angle)
        x   = r_place * math.cos(rad)
        z   = r_place * math.sin(rad)
        gem = create_gem_shape("round", stone_size, stone_size, gem_h)
        gem.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), angle - 90.0)
        gem.translate(App.Vector(x, 0.0, z))
        gems_list.append(gem)

    if not gems_list:
        return None
    fused = gems_list[0]
    for g in gems_list[1:]:
        fused = fused.fuse(g)
    return fused


def create_halo_shape(stone_count, stone_size, radial_distance, z_offset):
    w_base       = stone_size * 1.3
    h_base       = stone_size * 0.8
    r_outer      = radial_distance + w_base / 2.0
    r_inner      = radial_distance - w_base / 2.0
    outer_cyl    = Part.makeCylinder(r_outer, h_base,
                                      App.Vector(0, 0, z_offset - h_base), App.Vector(0, 0, 1))
    inner_cyl    = Part.makeCylinder(r_inner, h_base,
                                      App.Vector(0, 0, z_offset - h_base), App.Vector(0, 0, 1))
    metal_collar = outer_cyl.cut(inner_cyl)
    gems_list    = []
    gem_h        = stone_size * 0.6

    for i in range(stone_count):
        angle = i * (360.0 / stone_count)
        rad   = math.radians(angle)
        x, y  = radial_distance * math.cos(rad), radial_distance * math.sin(rad)
        gem   = create_gem_shape("round", stone_size, stone_size, gem_h)
        gem.translate(App.Vector(x, y, z_offset))
        gems_list.append(gem)
        cutter = Part.makeCylinder(stone_size / 2.0 + 0.1, h_base + 0.5,
                                    App.Vector(x, y, z_offset - h_base - 0.1),
                                    App.Vector(0, 0, 1))
        try:
            metal_collar = metal_collar.cut(cutter)
        except:
            pass

    fused_gems = gems_list[0]
    for g in gems_list[1:]:
        fused_gems = fused_gems.fuse(g)
    return metal_collar, fused_gems


def main():
    if len(sys.argv) < 3:
        params_path   = os.path.join("outputs", "temp_plan.json")
        output_prefix = os.path.join("outputs", "ring")
        print("No command-line arguments. Using defaults:")
        print(f"  params_path:   {params_path}")
        print(f"  output_prefix: {output_prefix}")
    else:
        params_path   = sys.argv[1]
        output_prefix = sys.argv[2]

    if not os.path.exists(params_path):
        print(f"Error: {params_path} not found")
        sys.exit(1)

    with open(params_path, 'r') as f:
        plan = json.load(f)

    print(f"Starting FreeCAD generation with {len(plan)} tool calls...")

    doc = App.newDocument("RingModel")

    metal_shapes = []
    gem_shapes   = []

    # First pass: read band parameters for downstream components
    band_inner_radius = 8.5
    band_width        = 2.5
    band_thickness    = 1.8
    for call in plan:
        if call.get("tool") == "create_band":
            p = call.get("params", {})
            band_inner_radius = p.get("inner_radius", 8.5)
            band_width        = p.get("width",        2.5)
            band_thickness    = p.get("thickness",    1.8)
            break

    component_shapes = {}

    for idx, call in enumerate(plan):
        tool   = call.get("tool")
        params = call.get("params", {})
        print(f"Executing step {idx+1}: {tool} with params {params}")

        try:
            if tool == "create_band":
                shape = create_band_shape(
                    inner_radius = band_inner_radius,
                    width        = band_width,
                    thickness    = band_thickness,
                    profile_type = params.get("profile_type", "court")
                )
                metal_shapes.append(shape)
                component_shapes["band"] = shape

            elif tool == "create_gallery":
                shape = create_gallery_shape(
                    style        = params.get("style",    "cathedral"),
                    width        = params.get("width",    6.5),
                    height       = params.get("height",   3.0),
                    z_offset     = params.get("z_offset", 10.3),
                    inner_radius = band_inner_radius,
                    thickness    = band_thickness,
                    band_width   = band_width
                )
                metal_shapes.append(shape)
                component_shapes["gallery"] = shape

            elif tool == "create_bridge":
                shape = create_bridge_shape(
                    height       = params.get("height",   1.2),
                    z_offset     = params.get("z_offset", 10.0),
                    inner_radius = band_inner_radius,
                    band_width   = band_width
                )
                metal_shapes.append(shape)
                component_shapes["bridge"] = shape

            elif tool == "create_center_stone":
                z_off  = params.get("z_offset", 12.0)
                height = params.get("height",   3.8)
                shape  = create_gem_shape(
                    cut    = params.get("cut",    "round"),
                    width  = params.get("width",  6.0),
                    length = params.get("length", 6.0),
                    height = height
                )
                # Gem pavilion tip is at Z=0; translate so it sits at z_offset
                shape.translate(App.Vector(0, 0, z_off))
                gem_shapes.append(shape)
                component_shapes["center_stone"] = shape

            elif tool == "create_prongs":
                shape = create_prongs_shape(
                    count           = params.get("count",           4),
                    radius          = params.get("radius",          0.4),
                    height          = params.get("height",          3.0),
                    radial_distance = params.get("radial_distance", 3.0),
                    z_offset        = params.get("z_offset",        11.5),
                    prong_style     = params.get("prong_style",     "claw"),
                    orientation     = params.get("orientation",     "radial"),
                    placement_plane = params.get("placement_plane", "XY"),
                    angles_deg      = params.get("angles_deg",      None),
                )
                if shape:
                    metal_shapes.append(shape)
                    component_shapes["prongs"] = shape

            elif tool == "create_halo":
                metal_h, gem_h_shape = create_halo_shape(
                    stone_count     = params.get("stone_count",     16),
                    stone_size      = params.get("stone_size",      1.2),
                    radial_distance = params.get("radial_distance", 4.2),
                    z_offset        = params.get("z_offset",        12.0)
                )
                metal_shapes.append(metal_h)
                gem_shapes.append(gem_h_shape)
                try:
                    component_shapes["halo"] = metal_h.fuse(gem_h_shape)
                except:
                    component_shapes["halo"] = metal_h

            elif tool == "create_side_stones":
                shape = create_side_stones_shape(
                    stone_size   = params.get("stone_size",  1.3),
                    stone_count  = params.get("stone_count", 10),
                    inner_radius = band_inner_radius,
                    thickness    = band_thickness,
                    band_width   = band_width
                )
                if shape:
                    gem_shapes.append(shape)
                    component_shapes["side_stones"] = shape

            else:
                print(f"Unknown tool: {tool}")

        except Exception as err:
            print(f"Step {idx+1} ({tool}) failed: {err}")
            import traceback; traceback.print_exc()

    print("Fusing CAD components...")

    metal_fused = None
    if metal_shapes:
        metal_fused = metal_shapes[0]
        for s in metal_shapes[1:]:
            try:
                metal_fused = metal_fused.fuse(s)
            except Exception as e:
                print(f"Metal fuse error: {e}")

    gem_fused = None
    if gem_shapes:
        gem_fused = gem_shapes[0]
        for s in gem_shapes[1:]:
            try:
                gem_fused = gem_fused.fuse(s)
            except Exception as e:
                print(f"Gem fuse error: {e}")

    doc_objs = []
    if metal_fused:
        metal_obj = doc.addObject("Part::Feature", "RingMetal")
        metal_obj.Shape = metal_fused
        doc_objs.append(metal_obj)
    if gem_fused:
        gem_obj = doc.addObject("Part::Feature", "RingGems")
        gem_obj.Shape = gem_fused
        doc_objs.append(gem_obj)

    doc.recompute()

    fcstd_path = f"{output_prefix}.FCstd"
    doc.saveAs(fcstd_path)
    print(f"Saved FreeCAD project to {fcstd_path}")

    if metal_fused:
        Mesh.export([metal_obj], f"{output_prefix}_metal.stl")
        print(f"Exported metal STL to {output_prefix}_metal.stl")
    if gem_fused:
        Mesh.export([gem_obj], f"{output_prefix}_gems.stl")
        print(f"Exported gems STL to {output_prefix}_gems.stl")
    if doc_objs:
        Mesh.export(doc_objs, f"{output_prefix}.stl")
        print(f"Exported combined STL to {output_prefix}.stl")

    # ── Stats ──────────────────────────────────────────────────────────────────
    stats = {"components": {}}
    for obj in doc_objs:
        bbox = obj.Shape.BoundBox
        stats[obj.Name] = {
            "Xmin": bbox.XMin, "Xmax": bbox.XMax,
            "Ymin": bbox.YMin, "Ymax": bbox.YMax,
            "Zmin": bbox.ZMin, "Zmax": bbox.ZMax,
            "Xlen": bbox.XLength, "Ylen": bbox.YLength, "Zlen": bbox.ZLength
        }

    for name, shape in component_shapes.items():
        if not shape:
            continue
        if name == "band":
            true_outer_r = band_inner_radius + band_thickness
            stats["components"]["band"] = {
                "Xmin": -true_outer_r, "Xmax":  true_outer_r,
                "Ymin": -band_width/2, "Ymax":  band_width/2,
                "Zmin": -true_outer_r, "Zmax":  true_outer_r,
                "Xlen": 2*true_outer_r, "Ylen": band_width, "Zlen": 2*true_outer_r
            }
        else:
            bbox = shape.BoundBox
            stats["components"][name] = {
                "Xmin": bbox.XMin, "Xmax": bbox.XMax,
                "Ymin": bbox.YMin, "Ymax": bbox.YMax,
                "Zmin": bbox.ZMin, "Zmax": bbox.ZMax,
                "Xlen": bbox.XLength, "Ylen": bbox.YLength, "Zlen": bbox.ZLength
            }

    stats_path = f"{output_prefix}_stats.json"
    with open(stats_path, 'w') as sf:
        json.dump(stats, sf, indent=2)
    print(f"Saved model bounds stats to {stats_path}")
    print("FreeCAD generation complete!")


if __name__ == "__main__":
    main()