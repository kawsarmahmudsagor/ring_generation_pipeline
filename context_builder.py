import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def build_context(geometry: dict, semantics: dict) -> dict:
    """
    Merges geometry dimensions and semantic attributes, and computes derived structural constraints.
    Returns a unified context dict structured into 'shank' and 'head'.
    """
    logging.info("Building unified ring design context...")

    # Extract component nodes, using empty dict as fallback
    shank_geom = geometry.get("shank", {})
    head_geom = geometry.get("head", {})

    band_geom = shank_geom.get("band", {})
    stone_geom = head_geom.get("center_stone", {})
    prong_geom = head_geom.get("prongs", {})
    halo_geom = head_geom.get("halo", {})
    gallery_geom = head_geom.get("gallery", {})
    bridge_geom = head_geom.get("bridge", {})
    shoulder_geom = shank_geom.get("shoulder", {})
    side_stones_geom = shank_geom.get("side_stones", {})

    # 1. Band parameters (Shank)
    inner_radius = band_geom.get("inner_radius", 8.5)
    width = band_geom.get("width", 2.5)
    thickness = band_geom.get("thickness", 1.8)
    outer_radius = inner_radius + thickness

    # 2. Center stone parameters (Head)
    stone_cut = semantics.get("center_stone_cut", "Round").lower()
    stone_width = stone_geom.get("width", 6.0)
    stone_length = stone_geom.get("length", 6.0)
    
    # Enforce round stone constraints (length must equal width to override noisy vertical annotations)
    if stone_cut == "round":
        stone_length = stone_width
        
    stone_height = stone_geom.get("height", 3.8)
    
    default_stone_z = outer_radius + 3.0
    stone_z = stone_geom.get("z_offset", default_stone_z)
    if stone_z < outer_radius:
        stone_z = outer_radius + 2.5

    # 3. Gallery constraints (Head)
    has_gallery = semantics.get("gallery", "Yes").lower() == "yes"
    gallery_h = gallery_geom.get("height", stone_z - outer_radius)
    if gallery_h <= 0:
        gallery_h = stone_z - outer_radius
    gallery_z = outer_radius

    # 4. Prong constraints (Head)
    prong_count = int(semantics.get("prong_count", 4))
    if prong_count not in [4, 6, 8]:
        prong_count = 4

    prong_rad = prong_geom.get("width", 0.8) / 2.0
    if prong_rad <= 0 or prong_rad > 1.5:
        prong_rad = 0.4

    prong_h = prong_geom.get("height", stone_height + 1.2)
    if prong_h < stone_height:
        prong_h = stone_height + 1.0
    prong_z = stone_z - 0.5  
    prong_radial_dist = (stone_width / 2.0)

    # 5. Halo constraints (Head)
    has_halo = semantics.get("halo", "No").lower() == "yes"
    halo_stone_sz = halo_geom.get("width", 1.2)
    if halo_stone_sz <= 0 or halo_stone_sz > 3.0:
        halo_stone_sz = 1.2

    halo_radial_dist = (stone_width / 2.0) + (halo_stone_sz / 2.0) + 0.3
    halo_z = stone_z
    halo_stone_count = int((2 * 3.14159 * halo_radial_dist) / (halo_stone_sz + 0.2))
    if halo_stone_count < 8:
        halo_stone_count = 12

    # 6. Bridge parameters (Head)
    # A bridge sits directly beneath the gallery to connect the shank sides and gallery bottom.
    has_bridge = "bridge" in head_geom or semantics.get("ring_style", "").lower() == "cathedral"
    bridge_h = bridge_geom.get("height", 1.2)
    bridge_z = outer_radius - 0.5  # sits slightly overlapping with the top of the band

    # 7. Shoulder & Side Stones (Shank)
    has_shoulder = "shoulder" in shank_geom
    has_side_stones = "side_stones" in shank_geom or semantics.get("shank_style", "").lower() == "pave"
    
    # If the parsed side stones region width is very large (e.g. spanning the whole band diameter > 3mm),
    # it represents the entire region bounding box, so we override it with a standard pavé stone size of 1.3mm.
    side_stone_size = side_stones_geom.get("width", 1.3)
    if side_stone_size <= 0 or side_stone_size > 3.0:
        side_stone_size = 1.3

    # Compile structured context
    context = {
        "shank": {
            "band": {
                "inner_radius": inner_radius,
                "width": width,
                "thickness": thickness,
                "outer_radius": outer_radius,
                "profile_type": "court"
            },
            "shoulder": {
                "enabled": has_shoulder,
                "style": semantics.get("shoulders", "Plain").lower()
            },
            "side_stones": {
                "enabled": has_side_stones,
                "stone_size": side_stone_size,
                "stone_count": 10  # default count per side
            }
        },
        "head": {
            "center_stone": {
                "cut": stone_cut,
                "width": stone_width,
                "length": stone_length,
                "height": stone_height,
                "z_offset": stone_z
            },
            "gallery": {
                "enabled": has_gallery,
                "style": semantics.get("ring_style", "Cathedral").lower(),
                "height": gallery_h,
                "width": stone_width + 0.4,
                "z_offset": gallery_z
            },
            "bridge": {
                "enabled": has_bridge,
                "height": bridge_h,
                "z_offset": bridge_z
            },
            "prongs": {
                "count": prong_count,
                "radius": prong_rad,
                "height": prong_h,
                "radial_distance": prong_radial_dist,
                "z_offset": prong_z
            },
            "halo": {
                "enabled": has_halo,
                "stone_count": halo_stone_count,
                "stone_size": halo_stone_sz,
                "radial_distance": halo_radial_dist,
                "z_offset": halo_z
            }
        },
        "style": semantics,
        "meta": geometry.get("meta", {})
    }

    logging.info(f"Built context successfully. Grouped by Head and Shank.")
    return context
