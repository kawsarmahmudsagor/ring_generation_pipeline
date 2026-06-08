"""
context_builder.py
────────────────────────────────────────────────────────────────────────────
Merges geometry dimensions and semantic attributes into a unified design context.

CHANGES vs original:
  • Accepts optional anchor_graph (from anchor_extractor) for richer placement.
  • Gallery is ALWAYS represented as a structural node with a "mode" field:
        mode = "explicit"  → annotated, build real geometry
        mode = "inferred"  → not annotated, support_solver provides fallback
  • Does NOT set final Z positions — those are delegated to support_solver.
  • Prong z_offset is left as a provisional value; support_solver will correct it.

Z-COORDINATE CONVENTION (unchanged):
    Z = 0         → ring geometric centre (equator)
    Z = +outer_r  → top of the band  (head attaches here)
    Z = -outer_r  → bottom of the band
"""
import logging

logger = logging.getLogger(__name__)


def build_context(geometry: dict, semantics: dict,
                  anchor_graph: dict = None) -> dict:
    """
    Build the unified design context.

    Parameters
    ----------
    geometry     : output of coco_parser.parse_geometry()
    semantics    : output of semantic_extractor.extract_semantics()
    anchor_graph : (optional) output of anchor_extractor.build_anchor_graph()
                   When supplied, prong angles and stone radius come from here
                   instead of the raw bbox measurements.
    """
    logger.info("Building annotation-driven ring design context...")

    shank_geom       = geometry.get("shank", {})
    head_geom        = geometry.get("head",  {})
    band_geom        = shank_geom.get("band",        {})
    stone_geom       = head_geom.get("center_stone", {})
    prong_geom       = head_geom.get("prongs",        {})
    halo_geom        = head_geom.get("halo",          {})
    gallery_geom     = head_geom.get("gallery",       {})
    bridge_geom      = head_geom.get("bridge",        {})
    shoulder_geom    = shank_geom.get("shoulder",     {})
    side_stones_geom = shank_geom.get("side_stones",  {})

    # ── 1. Band ───────────────────────────────────────────────────────────────
    inner_radius = float(band_geom.get("inner_radius", 8.5))
    width        = float(band_geom.get("width",        2.5))
    thickness    = float(band_geom.get("thickness",    1.8))
    outer_radius = inner_radius + thickness

    # ── 2. Center stone ───────────────────────────────────────────────────────
    stone_cut    = semantics.get("center_stone_cut", "Round").lower()
    stone_width  = float(stone_geom.get("width",  6.0))
    stone_length = float(stone_geom.get("length", 6.0))
    stone_height = float(stone_geom.get("height", 3.8))

    # If anchor_graph has a better radius estimate, prefer it
    if anchor_graph and anchor_graph.get("center_stone", {}).get("annotated"):
        stone_radius_from_anchor = anchor_graph["center_stone"]["radius_2d"]
        # Only override if meaningfully different and in sane range
        if 1.0 < stone_radius_from_anchor < 15.0:
            stone_width  = stone_radius_from_anchor * 2.0
            stone_length = stone_width
        depth_from_anchor = anchor_graph["center_stone"].get("depth_estimate", 0)
        if 1.0 < depth_from_anchor < 15.0:
            stone_height = depth_from_anchor

    if stone_cut == "round":
        stone_length = stone_width
    stone_width  = max(2.0, min(stone_width,  20.0))
    stone_height = max(1.0, min(stone_height, 15.0))

    # ── 3. Provisional Z layout (support_solver will correct final values) ────
    # We still need a provisional stone_z so gallery/prong heights are sensible.
    if gallery_geom:
        parsed_h = gallery_geom.get("height")
        gallery_h = parsed_h if (parsed_h and 0.5 < parsed_h < 20.0) \
                    else max(1.5, stone_height * 0.50)
    else:
        gallery_h = 0.0

    gallery_z = outer_radius                   # gallery base always at band top
    stone_z   = gallery_z + gallery_h          # provisional — solver overrides
    prong_z   = stone_z - 0.5                  # provisional — solver overrides
    bridge_z  = outer_radius - 0.5
    halo_z    = stone_z

    logger.info(
        f"Provisional Z → band_top={outer_radius:.2f}  "
        f"{'gallery=[' + str(round(gallery_z,2)) + '→' + str(round(gallery_z+gallery_h,2)) + ']  ' if gallery_geom else ''}"
        f"stone_base={stone_z:.2f}  stone_top={stone_z+stone_height:.2f}"
    )

    # ── 4. Assemble context ───────────────────────────────────────────────────
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
                "z_offset": stone_z        # provisional; support_solver corrects
            }
        },
        "style": semantics,
        "meta":  geometry.get("meta", {})
    }

    # ── Gallery — ALWAYS included as structural node ──────────────────────────
    # mode = "explicit"  → was annotated; build real geometry
    # mode = "inferred"  → not annotated; support_solver supplies fallback anchor
    if gallery_geom:
        context["head"]["gallery"] = {
            "mode":     "explicit",
            "style":    semantics.get("ring_style", "solitaire").lower(),
            "height":   gallery_h,
            "width":    stone_width + 0.4,
            "z_offset": gallery_z           # corrected by support_solver
        }
        logger.info(f"Gallery: explicit, height={gallery_h:.2f}mm")
    else:
        # Inferred — no geometry will be built, but the structural role is recorded
        context["head"]["gallery"] = {
            "mode":     "inferred",
            "style":    "none",
            "height":   0.0,
            "width":    stone_width + 0.4,
            "z_offset": gallery_z
        }
        logger.info("Gallery: inferred (no annotation) — support_solver will resolve")

    # ── Bridge — only if annotated ─────────────────────────────────────────────
    if bridge_geom:
        bridge_h = max(0.8, float(bridge_geom.get("height", 1.2)))
        context["head"]["bridge"] = {
            "height":   bridge_h,
            "z_offset": bridge_z
        }

    # ── Prongs — only if annotated ─────────────────────────────────────────────
    if prong_geom:
        prong_count = int(semantics.get("prong_count", 4))
        if prong_count not in (4, 6, 8):
            prong_count = 4
        prong_rad = float(prong_geom.get("width", 0.8)) / 2.0
        if not (0.1 < prong_rad <= 1.5):
            prong_rad = 0.4

        # Prefer anchor_graph angles (polygon-centroid derived) over bbox angles
        if anchor_graph and anchor_graph.get("prongs"):
            prong_angles = [p["angle"] for p in anchor_graph["prongs"]]
            logger.info(f"Using anchor_graph prong angles: {prong_angles}")
        else:
            prong_angles = list(prong_geom.get("prong_angles_deg", []))

        orientation     = prong_geom.get("orientation",     "radial")
        placement_plane = prong_geom.get("placement_plane", "XY")

        if not prong_angles:
            step = 360.0 / prong_count
            if prong_count == 4:
                prong_angles = [45.0, 135.0, 225.0, 315.0]
            elif prong_count == 6:
                prong_angles = [30.0, 90.0, 150.0, 210.0, 270.0, 330.0]
            else:
                prong_angles = [i * step for i in range(prong_count)]
            logger.info(f"No per-prong angles from annotation; using evenly distributed "
                        f"angles for {prong_count} prongs: {prong_angles}")

        context["head"]["prongs"] = {
            "count":           prong_count,
            "radius":          prong_rad,
            "height":          stone_height + 1.0,   # provisional; solver corrects
            "radial_distance": stone_width / 2.0,
            "z_offset":        prong_z,              # provisional; solver corrects
            "prong_style":     semantics.get("prong_style", "claw"),
            "orientation":     orientation,
            "placement_plane": placement_plane,
            "angles_deg":      prong_angles,
        }

    # ── Halo — only if annotated ───────────────────────────────────────────────
    if halo_geom:
        halo_stone_sz = float(halo_geom.get("width", 1.2))
        if not (0.3 < halo_stone_sz <= 3.0):
            halo_stone_sz = 1.2
        halo_radial_dist = (stone_width / 2.0) + (halo_stone_sz / 2.0) + 0.3
        halo_stone_count = max(8, int((2 * 3.14159 * halo_radial_dist) / (halo_stone_sz + 0.2)))
        context["head"]["halo"] = {
            "stone_count":     halo_stone_count,
            "stone_size":      halo_stone_sz,
            "radial_distance": halo_radial_dist,
            "z_offset":        halo_z              # corrected by support_solver
        }

    # ── Shoulder — only if annotated ──────────────────────────────────────────
    if shoulder_geom:
        context["shank"]["shoulder"] = {
            "style": semantics.get("shoulders", "plain").lower()
        }

    # ── Side stones — only if annotated ───────────────────────────────────────
    if side_stones_geom:
        side_stone_size = float(side_stones_geom.get("width", 1.3))
        if not (0.3 < side_stone_size <= 3.0):
            side_stone_size = 1.3
        context["shank"]["side_stones"] = {
            "stone_size":  side_stone_size,
            "stone_count": 10
        }

    return context