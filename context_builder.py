import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def build_context(geometry: dict, semantics: dict) -> dict:
    """
    Merges geometry dimensions and semantic attributes into a unified design context.

    Z-COORDINATE CONVENTION (single source of truth):
    ─────────────────────────────────────────────────
    The FreeCAD world has the ring band as a torus in the XZ plane, finger-hole
    along Y.  Therefore:

        Z = 0           →  geometric centre of the band (ring's equator)
        Z = +outer_r    →  top of the band (where gallery attaches)
        Z = -outer_r    →  bottom of the band

    ALL z_offset values stored in this context are the BASE (bottom) Z of the
    component in that world frame.

    CRITICALLY: we do NOT trust the coco_parser's pixel-derived z_offset for
    vertical placement.  A 2D side-view image provides no absolute Z anchor —
    pixel-Y can only tell us relative heights, not where Z=0 sits.  We therefore
    derive every vertical position from first principles using the band geometry
    and the stone's physical height (which IS reliably measured from pixels via
    scale_side).
    """
    logging.info("Building unified ring design context...")

    shank_geom       = geometry.get("shank", {})
    head_geom        = geometry.get("head",  {})
    band_geom        = shank_geom.get("band", {})
    stone_geom       = head_geom.get("center_stone", {})
    prong_geom       = head_geom.get("prongs", {})
    halo_geom        = head_geom.get("halo",  {})
    gallery_geom     = head_geom.get("gallery", {})
    bridge_geom      = head_geom.get("bridge", {})
    shoulder_geom    = shank_geom.get("shoulder", {})
    side_stones_geom = shank_geom.get("side_stones", {})

    # ── 1. Band ────────────────────────────────────────────────────────────────
    inner_radius = band_geom.get("inner_radius", 8.5)
    width        = band_geom.get("width",        2.5)
    thickness    = band_geom.get("thickness",    1.8)
    outer_radius = inner_radius + thickness       # e.g. 10.3 mm

    # ── 2. Center stone (XY dimensions only from COCO; Z from geometry) ───────
    stone_cut    = semantics.get("center_stone_cut", "Round").lower()
    stone_width  = stone_geom.get("width",  6.0)
    stone_length = stone_geom.get("length", 6.0)
    stone_height = stone_geom.get("height", 3.8)

    if stone_cut == "round":
        stone_length = stone_width   # enforce circular constraint

    # Clamp absurdly small/large values from noisy annotations
    stone_width  = max(2.0, min(stone_width,  20.0))
    stone_height = max(1.0, min(stone_height, 15.0))

    # ── 3. Gallery height (from COCO if available, else from stone geometry) ──
    # Gallery spans from the band top (outer_radius) up to where the stone sits.
    # A typical solitaire gallery is 40-60 % of the stone height.
    parsed_gallery_h = gallery_geom.get("height", None)
    if parsed_gallery_h and 0.5 < parsed_gallery_h < 20.0:
        gallery_h = parsed_gallery_h
    else:
        gallery_h = max(1.5, stone_height * 0.50)   # sensible default

    # ── 4. Derive all Z offsets from first principles ─────────────────────────
    #
    #   gallery_z  = outer_radius          (gallery sits on top of the band)
    #   stone_z    = gallery_z + gallery_h (stone base is on top of gallery)
    #   prong_z    = stone_z  - 0.5        (prongs wrap around girdle)
    #   bridge_z   = outer_radius - 0.5    (bridge just below band top)
    #   halo_z     = stone_z               (halo at stone base level)

    gallery_z = outer_radius
    stone_z   = gallery_z + gallery_h
    prong_z   = stone_z   - 0.5
    bridge_z  = outer_radius - 0.5
    halo_z    = stone_z

    logging.info(
        f"Z layout → band_top={outer_radius:.2f}  gallery:[{gallery_z:.2f}→{gallery_z+gallery_h:.2f}]  "
        f"stone_base={stone_z:.2f}  stone_top={stone_z+stone_height:.2f}"
    )

    # ── 5. Prongs ──────────────────────────────────────────────────────────────
    prong_count = int(semantics.get("prong_count", 4))
    if prong_count not in [4, 6, 8]:
        prong_count = 4

    prong_rad = prong_geom.get("width", 0.8) / 2.0
    if not (0.1 < prong_rad <= 1.5):
        prong_rad = 0.4

    # Prong height: must reach from prong_z to at least stone top + 0.5 mm tip
    prong_h = stone_height + 1.0
    prong_radial_dist = stone_width / 2.0

    # ── 6. Halo ────────────────────────────────────────────────────────────────
    has_halo      = semantics.get("halo", "No").lower() == "yes"
    halo_stone_sz = halo_geom.get("width", 1.2)
    if not (0.3 < halo_stone_sz <= 3.0):
        halo_stone_sz = 1.2
    halo_radial_dist  = (stone_width / 2.0) + (halo_stone_sz / 2.0) + 0.3
    halo_stone_count  = max(8, int((2 * 3.14159 * halo_radial_dist) / (halo_stone_sz + 0.2)))

    # ── 7. Bridge ──────────────────────────────────────────────────────────────
    has_bridge = "bridge" in head_geom or semantics.get("ring_style", "").lower() == "cathedral"
    bridge_h   = max(0.8, bridge_geom.get("height", 1.2))

    # ── 8. Shoulder / side stones ─────────────────────────────────────────────
    has_shoulder    = "shoulder" in shank_geom
    has_side_stones = (
        "side_stones" in shank_geom
        or semantics.get("shank_style", "").lower() == "pave"
    )
    side_stone_size = side_stones_geom.get("width", 1.3)
    if not (0.3 < side_stone_size <= 3.0):
        side_stone_size = 1.3

    # ── Compile ────────────────────────────────────────────────────────────────
    context = {
        "shank": {
            "band": {
                "inner_radius": inner_radius,
                "width":        width,
                "thickness":    thickness,
                "outer_radius": outer_radius,
                "profile_type": "court"
            },
            "shoulder": {
                "enabled": has_shoulder,
                "style":   semantics.get("shoulders", "Plain").lower()
            },
            "side_stones": {
                "enabled":     has_side_stones,
                "stone_size":  side_stone_size,
                "stone_count": 10
            }
        },
        "head": {
            "center_stone": {
                "cut":      stone_cut,
                "width":    stone_width,
                "length":   stone_length,
                "height":   stone_height,
                "z_offset": stone_z       # base Z of stone, derived from geometry
            },
            "gallery": {
                "enabled":  True,
                "style":    semantics.get("ring_style", "cathedral").lower(),
                "height":   gallery_h,
                "width":    stone_width + 0.4,
                "z_offset": gallery_z     # = outer_radius, the band top
            },
            "bridge": {
                "enabled":  has_bridge,
                "height":   bridge_h,
                "z_offset": bridge_z
            },
            "prongs": {
                "count":           prong_count,
                "radius":          prong_rad,
                "height":          prong_h,
                "radial_distance": prong_radial_dist,
                "z_offset":        prong_z
            },
            "halo": {
                "enabled":         has_halo,
                "stone_count":     halo_stone_count,
                "stone_size":      halo_stone_sz,
                "radial_distance": halo_radial_dist,
                "z_offset":        halo_z
            }
        },
        "style": semantics,
        "meta":  geometry.get("meta", {})
    }

    return context