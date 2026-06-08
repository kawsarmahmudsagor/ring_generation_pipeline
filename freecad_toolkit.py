import sys
import os
import json
import math

import FreeCAD as App
import Part
import Mesh

def create_gem_shape(cut, width, length, height):
    """
    Creates a parametric 3D gemstone shape.
    Table/girdle is centered at (0,0,0).
    """
    cut = cut.lower()
    r = width / 2.0
    
    crown_h = height * 0.25
    girdle_h = height * 0.08
    pavilion_h = height * 0.67
    
    crown = Part.makeCone(r, r * 0.55, crown_h, App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    girdle = Part.makeCylinder(r, girdle_h, App.Vector(0, 0, -girdle_h), App.Vector(0, 0, 1))
    pavilion = Part.makeCone(0.05, r, pavilion_h, App.Vector(0, 0, -girdle_h - pavilion_h), App.Vector(0, 0, 1))
    
    gem_shape = crown.fuse(girdle).fuse(pavilion)
    
    if cut == "oval":
        scale_y = length / width if width > 0 else 1.0
        gem_shape.scale(App.Vector(1.0, scale_y, 1.0))
    elif cut in ["princess", "cushion", "emerald"]:
        if cut == "princess":
            w2 = width / 2.0
            l2 = length / 2.0
            crown_box = Part.makeWedge(-w2, -l2, 0, w2, l2, crown_h, -w2*0.6, -l2*0.6, -w2*0.6, w2*0.6, l2*0.6, -w2*0.6)
            girdle_box = Part.makeBox(width, length, girdle_h, App.Vector(-w2, -l2, -girdle_h))
            pavilion_pyr = Part.makeWedge(-w2, -l2, -girdle_h-pavilion_h, w2, l2, -girdle_h, 0, 0, 0, 0, 0, 0)
            gem_shape = crown_box.fuse(girdle_box).fuse(pavilion_pyr)
        elif cut == "cushion":
            scale_y = length / width if width > 0 else 1.0
            gem_shape.scale(App.Vector(1.0, scale_y, 1.0))
            
    return gem_shape


def create_band_shape(inner_radius, width, thickness, profile_type):
    """
    Creates the ring band centered at the origin along the Y-axis.
    """
    outer_radius = inner_radius + thickness
    outer_cyl = Part.makeCylinder(outer_radius, width, App.Vector(0, -width/2.0, 0), App.Vector(0, 1, 0))
    inner_cyl = Part.makeCylinder(inner_radius, width, App.Vector(0, -width/2.0, 0), App.Vector(0, 1, 0))
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
                fillet_rad = thickness * 0.25
                band = band.makeFillet(fillet_rad, outer_edges)
            except Exception as e:
                print(f"Fillet failed: {e}. Using flat band profile.")
                
    return band


def create_prongs_shape(count, radius, height, radial_distance, z_offset):
    """
    Creates prongs distributed around the center stone.
    """
    prongs_list = []
    
    if count == 4:
        angles = [45, 135, 225, 315]
    elif count == 6:
        angles = [30, 90, 150, 210, 270, 330]
    elif count == 8:
        angles = [0, 45, 90, 135, 180, 225, 270, 315]
    else:
        angles = [45, 135, 225, 315]
        
    for angle in angles:
        rad = math.radians(angle)
        x = radial_distance * math.cos(rad)
        y = radial_distance * math.sin(rad)
        
        post = Part.makeCylinder(radius, height, App.Vector(x, y, z_offset), App.Vector(0, 0, 1))
        tip = Part.makeSphere(radius, App.Vector(x, y, z_offset + height))
        prong = post.fuse(tip)
        prongs_list.append(prong)
        
    if prongs_list:
        fused = prongs_list[0]
        for p in prongs_list[1:]:
            fused = fused.fuse(p)
        return fused
    return None


def create_gallery_shape(style, width, height, z_offset, inner_radius=8.5, thickness=1.8, band_width=2.5):
    """
    Creates a realistic open-basket gallery underneath the center stone.
    If style is cathedral, adds sweeping shoulders rising from the band.
    """
    r_outer = width / 2.0
    r_inner = r_outer - 0.4
    
    # 1. Bezel collar / wire basket (top and bottom gallery wires)
    # Top wire ring
    top_h = 0.5
    top_outer = Part.makeCylinder(r_outer, top_h, App.Vector(0, 0, z_offset + height - top_h), App.Vector(0, 0, 1))
    top_inner = Part.makeCylinder(r_inner, top_h, App.Vector(0, 0, z_offset + height - top_h), App.Vector(0, 0, 1))
    top_ring = top_outer.cut(top_inner)
    
    # Bottom wire ring (slightly tapered inwards)
    bot_h = 0.4
    bot_outer = Part.makeCylinder(r_outer - 0.3, bot_h, App.Vector(0, 0, z_offset), App.Vector(0, 0, 1))
    bot_inner = Part.makeCylinder(r_inner - 0.3, bot_h, App.Vector(0, 0, z_offset), App.Vector(0, 0, 1))
    bottom_ring = bot_outer.cut(bot_inner)
    
    gallery = top_ring.fuse(bottom_ring)
    
    # 2. Cathedral arches
    if style == "cathedral":
        outer_radius = inner_radius + thickness
        
        # Arch start position on the band (at 60 degrees)
        angle = math.radians(60.0)
        x_start = outer_radius * math.cos(angle)
        z_start = outer_radius * math.sin(angle)
        
        # Arch start inner position (thickness displacement)
        x_start_in = inner_radius * math.cos(angle)
        z_start_in = inner_radius * math.sin(angle)
        
        # Arch end position at gallery bottom
        x_end = r_outer - 0.2
        z_end = z_offset + 0.2
        
        x_end_in = r_inner - 0.2
        z_end_in = z_offset
        
        # Create polygon points in XZ plane
        p1 = App.Vector(x_start, 0, z_start)
        p2 = App.Vector(x_end, 0, z_end)
        p3 = App.Vector(x_end_in, 0, z_end_in)
        p4 = App.Vector(x_start_in, 0, z_start_in)
        
        try:
            poly = Part.makePolygon([p1, p2, p3, p4, p1])
            face = Part.Face(poly)
            # Extrude along Y axis (slightly narrower than the band width)
            w_shoulder = band_width * 0.8
            arch_right = face.extrude(App.Vector(0, w_shoulder, 0))
            # Center it along Y
            arch_right.translate(App.Vector(0, -w_shoulder/2.0, 0))
            
            # Mirror to get the left arch
            arch_left = arch_right.mirror(App.Vector(0,0,0), App.Vector(1,0,0))
            
            # Fuse arches to the gallery rings
            gallery = gallery.fuse(arch_right).fuse(arch_left)
        except Exception as e:
            print(f"Cathedral arch creation failed: {e}. Falling back to simple pillars.")
            w_shoulder = 1.8
            
            pillar = Part.makeBox(0.8, w_shoulder, z_offset - z_start, App.Vector(x_start - 0.4, -w_shoulder/2.0, z_start))
            pillar_left = pillar.mirror(App.Vector(0,0,0), App.Vector(1,0,0))
            gallery = gallery.fuse(pillar).fuse(pillar_left)
            
    return gallery


def create_bridge_shape(height, z_offset, inner_radius=8.5, band_width=2.5):
    """
    Creates a metal bridge curving above the finger hole.
    """
    # Create a solid block that spans between the cathedral arches
    w_bridge = (inner_radius + 0.5) * 2.0
    block = Part.makeBox(w_bridge, band_width, height, App.Vector(-w_bridge/2.0, -band_width/2.0, z_offset))
    
    # Cut the bottom of the block with the finger hole cylinder so it curves flush
    # The finger hole is along Y-axis, centered at origin (0,0,0)
    finger_cyl = Part.makeCylinder(inner_radius, band_width + 1.0, App.Vector(0, -band_width/2.0 - 0.5, 0), App.Vector(0, 1, 0))
    
    try:
        bridge = block.cut(finger_cyl)
        return bridge
    except Exception as e:
        print(f"Bridge cut failed: {e}. Returning block.")
        return block


def create_side_stones_shape(stone_size, stone_count, inner_radius=8.5, thickness=1.8, band_width=2.5):
    """
    Creates small pavé stones distributed along the ring shoulders.
    Returns fused gems shape.
    """
    r_placement = inner_radius + thickness - 0.2  # place slightly embedded in metal
    gems_list = []
    gem_h = stone_size * 0.6
    
    # Distribute stones on the shoulders (e.g. from 45 to 80 degrees on right, 100 to 135 on left)
    half_count = max(1, stone_count // 2)
    
    # Angle ranges in degrees
    right_angles = [45 + i * (35.0 / half_count) for i in range(half_count)]
    left_angles = [100 + i * (35.0 / half_count) for i in range(half_count)]
    
    all_angles = right_angles + left_angles
    
    for angle in all_angles:
        rad = math.radians(angle)
        # In side view (XZ plane), the band circumference is in the XZ plane!
        # Remember the finger hole axis is Y, so the ring circumference lies in the XZ plane.
        x = r_placement * math.cos(rad)
        z = r_placement * math.sin(rad)
        y = 0.0  # centered along the band width
        
        gem = create_gem_shape("round", stone_size, stone_size, gem_h)
        
        # Rotate gem so it points outward radially
        # The default gem points along +Z. We want to rotate it around the Y axis by (angle - 90) degrees.
        rot_angle = angle - 90.0
        gem.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), rot_angle)
        
        # Translate to shoulder position
        gem.translate(App.Vector(x, y, z))
        gems_list.append(gem)
        
    if gems_list:
        fused = gems_list[0]
        for g in gems_list[1:]:
            fused = fused.fuse(g)
        return fused
    return None


def create_halo_shape(stone_count, stone_size, radial_distance, z_offset):
    """
    Creates a halo of small stones and its metal mounting collar.
    Returns (metal_shape, gem_shape).
    """
    w_base = stone_size * 1.3
    h_base = stone_size * 0.8
    r_outer = radial_distance + w_base/2.0
    r_inner = radial_distance - w_base/2.0
    
    outer_cyl = Part.makeCylinder(r_outer, h_base, App.Vector(0, 0, z_offset - h_base), App.Vector(0, 0, 1))
    inner_cyl = Part.makeCylinder(r_inner, h_base, App.Vector(0, 0, z_offset - h_base), App.Vector(0, 0, 1))
    metal_collar = outer_cyl.cut(inner_cyl)
    
    gems_list = []
    gem_h = stone_size * 0.6
    cutters_list = []
    
    for i in range(stone_count):
        angle = i * (360.0 / stone_count)
        rad = math.radians(angle)
        x = radial_distance * math.cos(rad)
        y = radial_distance * math.sin(rad)
        
        gem = create_gem_shape("round", stone_size, stone_size, gem_h)
        gem.translate(App.Vector(x, y, z_offset))
        gems_list.append(gem)
        
        cutter = Part.makeCylinder(stone_size/2.0 + 0.1, h_base + 0.5, App.Vector(x, y, z_offset - h_base - 0.1), App.Vector(0, 0, 1))
        cutters_list.append(cutter)
        
    for cutter in cutters_list:
        try:
            metal_collar = metal_collar.cut(cutter)
        except:
            pass
            
    fused_gems = gems_list[0]
    for g in gems_list[1:]:
        fused_gems = fused_gems.fuse(g)
        
    return metal_collar, fused_gems


def main():
    # Use default paths if no arguments are provided (e.g. running inside freecadcmd.exe)
    if len(sys.argv) < 3:
        params_path = os.path.join("outputs", "temp_plan.json")
        output_prefix = os.path.join("outputs", "ring")
        print("No command-line arguments specified. Using default paths:")
        print(f"- params_path: {params_path}")
        print(f"- output_prefix: {output_prefix}")
    else:
        params_path = sys.argv[1]
        output_prefix = sys.argv[2]
    
    if not os.path.exists(params_path):
        print(f"Error: JSON file not found at {params_path}")
        sys.exit(1)
        
    try:
        with open(params_path, 'r') as f:
            plan = json.load(f)
    except Exception as e:
        print(f"Error reading plan: {e}")
        sys.exit(1)
        
    print(f"Starting FreeCAD generation with {len(plan)} tool calls...")
    
    doc_name = "RingModel"
    doc = App.newDocument(doc_name)
    
    metal_shapes = []
    gem_shapes = []
    
    # Store band inner radius & width to pass to sub-component functions
    band_inner_radius = 8.5
    band_width = 2.5
    band_thickness = 1.8
    
    # First pass: find band parameters
    for call in plan:
        if call.get("tool") == "create_band":
            params = call.get("params", {})
            band_inner_radius = params.get("inner_radius", 8.5)
            band_width = params.get("width", 2.5)
            band_thickness = params.get("thickness", 1.8)
            break
            
    component_shapes = {}

    for idx, call in enumerate(plan):
        tool = call.get("tool")
        params = call.get("params", {})
        print(f"Executing step {idx+1}: {tool} with params {params}")
        
        try:
            if tool == "create_band":
                shape = create_band_shape(
                    inner_radius=band_inner_radius,
                    width=band_width,
                    thickness=band_thickness,
                    profile_type=params.get("profile_type", "court")
                )
                metal_shapes.append(shape)
                component_shapes["band"] = shape
                
            elif tool == "create_gallery":
                shape = create_gallery_shape(
                    style=params.get("style", "cathedral"),
                    width=params.get("width", 6.5),
                    height=params.get("height", 3.0),
                    z_offset=params.get("z_offset", 10.3),
                    inner_radius=band_inner_radius,
                    thickness=band_thickness,
                    band_width=band_width
                )
                metal_shapes.append(shape)
                component_shapes["gallery"] = shape
                
            elif tool == "create_bridge":
                shape = create_bridge_shape(
                    height=params.get("height", 1.2),
                    z_offset=params.get("z_offset", 10.0),
                    inner_radius=band_inner_radius,
                    band_width=band_width
                )
                metal_shapes.append(shape)
                component_shapes["bridge"] = shape
                
            elif tool == "create_center_stone":
                shape = create_gem_shape(
                    cut=params.get("cut", "round"),
                    width=params.get("width", 6.0),
                    length=params.get("length", 6.0),
                    height=params.get("height", 3.8)
                )
                shape.translate(App.Vector(0, 0, params.get("z_offset", 12.0)))
                gem_shapes.append(shape)
                component_shapes["center_stone"] = shape
                
            elif tool == "create_prongs":
                shape = create_prongs_shape(
                    count=params.get("count", 4),
                    radius=params.get("radius", 0.4),
                    height=params.get("height", 3.0),
                    radial_distance=params.get("radial_distance", 3.0),
                    z_offset=params.get("z_offset", 11.5)
                )
                if shape:
                    metal_shapes.append(shape)
                    component_shapes["prongs"] = shape
                
            elif tool == "create_halo":
                metal_h, gem_h = create_halo_shape(
                    stone_count=params.get("stone_count", 16),
                    stone_size=params.get("stone_size", 1.2),
                    radial_distance=params.get("radial_distance", 4.2),
                    z_offset=params.get("z_offset", 12.0)
                )
                metal_shapes.append(metal_h)
                gem_shapes.append(gem_h)
                try:
                    component_shapes["halo"] = metal_h.fuse(gem_h)
                except:
                    component_shapes["halo"] = metal_h
                
            elif tool == "create_side_stones":
                shape = create_side_stones_shape(
                    stone_size=params.get("stone_size", 1.3),
                    stone_count=params.get("stone_count", 10),
                    inner_radius=band_inner_radius,
                    thickness=band_thickness,
                    band_width=band_width
                )
                if shape:
                    gem_shapes.append(shape)
                    component_shapes["side_stones"] = shape
                
            else:
                print(f"Unknown tool call: {tool}")
                
        except Exception as err:
            print(f"Step {idx+1} failed: {err}")
            
    print("Fusing CAD components...")
    
    metal_fused = None
    if metal_shapes:
        metal_fused = metal_shapes[0]
        for s in metal_shapes[1:]:
            try:
                metal_fused = metal_fused.fuse(s)
            except Exception as e:
                print(f"Failed to fuse metal components: {e}. Adding individually.")
        
    gem_fused = None
    if gem_shapes:
        gem_fused = gem_shapes[0]
        for s in gem_shapes[1:]:
            try:
                gem_fused = gem_fused.fuse(s)
            except Exception as e:
                print(f"Failed to fuse gem components: {e}.")
                
    doc_objs_to_export = []
    
    if metal_fused:
        metal_obj = doc.addObject("Part::Feature", "RingMetal")
        metal_obj.Shape = metal_fused
        doc_objs_to_export.append(metal_obj)
        
    if gem_fused:
        gem_obj = doc.addObject("Part::Feature", "RingGems")
        gem_obj.Shape = gem_fused
        doc_objs_to_export.append(gem_obj)
        
    doc.recompute()
    
    fcstd_path = f"{output_prefix}.FCstd"
    doc.saveAs(fcstd_path)
    print(f"Saved FreeCAD project to {fcstd_path}")
    
    metal_stl = f"{output_prefix}_metal.stl"
    gem_stl = f"{output_prefix}_gems.stl"
    combined_stl = f"{output_prefix}.stl"
    
    if metal_fused:
        Mesh.export([metal_obj], metal_stl)
        print(f"Exported metal STL to {metal_stl}")
        
    if gem_fused:
        Mesh.export([gem_obj], gem_stl)
        print(f"Exported gems STL to {gem_stl}")
        
    if doc_objs_to_export:
        Mesh.export(doc_objs_to_export, combined_stl)
        print(f"Exported combined STL to {combined_stl}")
        
    stats = {
        "components": {}
    }
    
    # Save overall group bounds
    for obj in doc_objs_to_export:
        bbox = obj.Shape.BoundBox
        stats[obj.Name] = {
            "Xmin": bbox.XMin, "Xmax": bbox.XMax,
            "Ymin": bbox.YMin, "Ymax": bbox.YMax,
            "Zmin": bbox.ZMin, "Zmax": bbox.ZMax,
            "Xlen": bbox.XLength, "Ylen": bbox.YLength, "Zlen": bbox.ZLength
        }
        
    # Save individual component bounds
    for name, shape in component_shapes.items():
        if shape:
            if name == "band":
                # Override with exact mathematical dimensions to bypass OpenCASCADE fillet bounding box calculation bug
                true_outer_r = band_inner_radius + band_thickness
                stats["components"][name] = {
                    "Xmin": -true_outer_r, "Xmax": true_outer_r,
                    "Ymin": -band_width/2.0, "Ymax": band_width/2.0,
                    "Zmin": -true_outer_r, "Zmax": true_outer_r,
                    "Xlen": 2.0 * true_outer_r, "Ylen": band_width, "Zlen": 2.0 * true_outer_r
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
