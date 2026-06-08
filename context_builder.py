import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def build_context(geometry: dict, semantics: dict) -> dict:
    """
    Merges geometry dimensions and semantic attributes into a unified design context.

    ANNOTATION-DRIVEN PRINCIPLE:
    ─────────────────────────────
    A component block is only built and included in the context when its category
    was present in the COCO annotation file.  If coco_parser found no 'gallery'
    bbox, there is no gallery block — we do not invent one.

    The only components that are always present are 'band' and 'center_stone',
    because every ring has those by definition.

    Z-COORDINATE CONVENTION:
    ─────────────────────────
    The FreeCAD world has the ring band as a torus in the XZ plane, finger-hole
    along Y.  Therefore:

        Z = 0           →  geometric centre of the band (ring's equator)
        Z = +outer_r    →  top of the band (where gallery/head attaches)
        Z = -outer_r    →  bottom of the band

    All z_offset values are the BASE (bottom) Z of the component.
    Vertical positions are derived from first principles using band geometry +
    component heights; we do NOT use coco_parser's pixel-derived z_offset directly.
    """
    logging.info("Building annotation-driven ring design context...")

    shank_geom       = geometry.get("shank", {})
    head_geom        = geometry.get("head",  {})
    band_geom        = shank_geom.get("band", {})
    stone_geom       = head_geom.get("center_stone", {})
    prong_geom       = head_geom.get("prongs",       {})
    halo_geom        = head_geom.get("halo",         {})
    gallery_geom     = head_geom.get("gallery",      {})
    bridge_geom      = head_geom.get("bridge",       {})
    shoulder_geom    = shank_geom.get("shoulder",    {})
    side_stones_geom = shank_geom.get("side_stones", {})

    # ── 1. Band (always present) ───────────────────────────────────────────────
    inner_radius = band_geom.get("inner_radius", 8.5)
    width        = band_geom.get("width",        2.5)
    thickness    = band_geom.get("thickness",    1.8)
    outer_radius = inner_radius + thickness

    # ── 2. Center stone (always present) ──────────────────────────────────────
    stone_cut    = semantics.get("center_stone_cut", "Round").lower()
    stone_width  = stone_geom.get("width",  6.0)
    stone_length = stone_geom.get("length", 6.0)
    stone_height = stone_geom.get("height", 3.8)

    if stone_cut == "round":
        stone_length = stone_width          # enforce circular footprint

    stone_width  = max(2.0, min(stone_width,  20.0))
    stone_height = max(1.0, min(stone_height, 15.0))

    # ── 3. Derive Z stack from first principles ────────────────────────────────
    # gallery_h is only used when gallery is annotated; otherwise stone sits
    # directly on the band top (with a minimal 1 mm seat).
    if gallery_geom:
        parsed_h = gallery_geom.get("height")
        gallery_h = parsed_h if (parsed_h and 0.5 < parsed_h < 20.0) else max(1.5, stone_height * 0.50)
    else:
        gallery_h = 0.0     # no gallery → stone base = band top

    gallery_z = outer_radius
    stone_z   = gallery_z + gallery_h
    prong_z   = stone_z - 0.5
    bridge_z  = outer_radius - 0.5
    halo_z    = stone_z

    logging.info(
        f"Z layout → band_top={outer_radius:.2f}  "
        f"{'gallery:['+str(round(gallery_z,2))+'→'+str(round(gallery_z+gallery_h,2))+']  ' if gallery_geom else ''}"
        f"stone_base={stone_z:.2f}  stone_top={stone_z+stone_height:.2f}"
    )

    # ── 4. Assemble context — annotation-gated blocks ──────────────────────────
    context = {
        "shank": {
            "band": {
                "inner_radius": inner_radius,
                "width":        width,
                "thickness":    thickness,
                "outer_radius": outer_radius,
                "profile_type": "court"
            }
        },
        "head": {
            "center_stone": {
                "cut":      stone_cut,
                "width":    stone_width,
                "length":   stone_length,
                "height":   stone_height,
                "z_offset": stone_z
            }
        },
        "style": semantics,
        "meta":  geometry.get("meta", {})
    }

    # ── Gallery — only if annotated ────────────────────────────────────────────
    if gallery_geom:
        context["head"]["gallery"] = {
            "style":    semantics.get("ring_style", "solitaire").lower(),
            "height":   gallery_h,
            "width":    stone_width + 0.4,
            "z_offset": gallery_z
        }

    # ── Bridge — only if annotated ─────────────────────────────────────────────
    if bridge_geom:
        bridge_h = max(0.8, bridge_geom.get("height", 1.2))
        context["head"]["bridge"] = {
            "height":   bridge_h,
            "z_offset": bridge_z
        }

    # ── Prongs — only if annotated ─────────────────────────────────────────────
    if prong_geom:
        prong_count = int(semantics.get("prong_count", 4))
        if prong_count not in (4, 6, 8):
            prong_count = 4
        prong_rad = prong_geom.get("width", 0.8) / 2.0
        if not (0.1 < prong_rad <= 1.5):
            prong_rad = 0.4

        # Annotation-derived placement geometry — these come from coco_parser
        # and are never hardcoded here.
        orientation     = prong_geom.get("orientation",     "radial")
        placement_plane = prong_geom.get("placement_plane", "XY")
        prong_angles    = prong_geom.get("prong_angles_deg", [])

        # If no per-prong angles were derived from the annotation (e.g. only a
        # combined prong bbox was present), distribute them evenly.
        if not prong_angles:
            step = 360.0 / prong_count
            if prong_count == 4:
                prong_angles = [45.0, 135.0, 225.0, 315.0]
            elif prong_count == 6:
                prong_angles = [30.0, 90.0, 150.0, 210.0, 270.0, 330.0]
            elif prong_count == 8:
                prong_angles = [i * step for i in range(prong_count)]
            else:
                prong_angles = [i * step for i in range(prong_count)]
            logging.info(
                f"No per-prong angles from annotation; using evenly distributed "
                f"angles for {prong_count} prongs: {prong_angles}"
            )

        context["head"]["prongs"] = {
            "count":           prong_count,
            "radius":          prong_rad,
            "height":          stone_height + 1.0,
            "radial_distance": stone_width / 2.0,
            "z_offset":        prong_z,
            # Semantic — drives tip shape in freecad_toolkit
            "prong_style":     semantics.get("prong_style", "claw"),
            # Annotation-derived — drives placement, never hardcoded
            "orientation":     orientation,
            "placement_plane": placement_plane,
            "angles_deg":      prong_angles,
        }

    # ── Halo — only if annotated ───────────────────────────────────────────────
    if halo_geom:
        halo_stone_sz = halo_geom.get("width", 1.2)
        if not (0.3 < halo_stone_sz <= 3.0):
            halo_stone_sz = 1.2
        halo_radial_dist = (stone_width / 2.0) + (halo_stone_sz / 2.0) + 0.3
        halo_stone_count = max(8, int((2 * 3.14159 * halo_radial_dist) / (halo_stone_sz + 0.2)))
        context["head"]["halo"] = {
            "stone_count":     halo_stone_count,
            "stone_size":      halo_stone_sz,
            "radial_distance": halo_radial_dist,
            "z_offset":        halo_z
        }

    # ── Shoulder — only if annotated ──────────────────────────────────────────
    if shoulder_geom:
        context["shank"]["shoulder"] = {
            "style": semantics.get("shoulders", "plain").lower()
        }

    # ── Side stones — only if annotated ───────────────────────────────────────
    if side_stones_geom:
        side_stone_size = side_stones_geom.get("width", 1.3)
        if not (0.3 < side_stone_size <= 3.0):
            side_stone_size = 1.3
        context["shank"]["side_stones"] = {
            "stone_size":  side_stone_size,
            "stone_count": 10
        }

    return context