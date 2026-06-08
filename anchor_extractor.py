"""
anchor_extractor.py
────────────────────────────────────────────────────────────────────────────
Converts raw COCO segmentation/bbox data into a typed anchor graph.

Pipeline position:
    coco_parser → anchor_extractor → context_builder → support_solver → freecad_toolkit

Each anchor is NOT a raw pixel point.  It is a *semantic geometric role*
derived from the segmentation masks + view type + category semantics.

Output structure (AnchorGraph dict):
{
    "center_stone": { "center_2d": [cx, cy], "radius_2d": r, "depth_estimate": h },
    "prongs":       [ { "angle": deg, "position_2d": [x,y], "height_hint": h }, ... ],
    "gallery":      { "mode": "explicit"|"inferred", "support_points": [[x,y],...], "height": h },
    "band":         { "center": [0,0], "inner_radius": r, "outer_radius": R }
}

Missing components produce *inferred* anchors, never None.
"""

import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bbox_centroid(bbox) -> tuple:
    """Return (cx, cy) from a BBox object or dict."""
    if hasattr(bbox, "cx"):
        return bbox.cx, bbox.cy
    return bbox["cx"], bbox["cy"]


def _bbox_wh(bbox) -> tuple:
    if hasattr(bbox, "w"):
        return bbox.w, bbox.h
    return bbox["w"], bbox["h"]


def _poly_centroid(segmentation: list) -> Optional[tuple]:
    """
    Compute the centroid of the first polygon in a COCO segmentation list.
    Returns (cx, cy) or None if segmentation is empty / malformed.
    """
    if not segmentation or not segmentation[0]:
        return None
    flat = segmentation[0]
    if len(flat) < 6:
        return None
    xs = flat[0::2]
    ys = flat[1::2]
    return sum(xs) / len(xs), sum(ys) / len(ys)


# ─────────────────────────────────────────────────────────────────────────────
# Per-component anchor extractors
# ─────────────────────────────────────────────────────────────────────────────

def extract_center_stone_anchor(top_anns: list, side_anns: list,
                                 scale_top: float, scale_side: float) -> dict:
    """
    Returns the stone anchor — always present (uses defaults if not annotated).

    Fields:
        center_2d    : (cx, cy) in mm from ring centre, top-view projection
        radius_2d    : stone radius in mm (top-view)
        depth_estimate: stone height in mm (side-view)
        annotated    : bool — whether the stone was actually found in COCO
    """
    stone_anns = [a for a in top_anns if a["category"] == "center_stone"]
    stone_side  = [a for a in side_anns  if a["category"] == "center_stone"]

    if not stone_anns:
        logger.warning("No center_stone annotation found — using defaults.")
        return {
            "center_2d":     [0.0, 0.0],
            "radius_2d":     3.0,
            "depth_estimate": 3.8,
            "annotated":     False
        }

    # Use polygon centroid where available, else bbox centroid
    bbox = stone_anns[0]["bbox"]
    seg  = stone_anns[0].get("segmentation", [])
    cx_px, cy_px = _poly_centroid(seg) or _bbox_centroid(bbox)
    w_px, _      = _bbox_wh(bbox)

    radius_mm = (w_px / 2.0) * scale_top

    depth_mm = 3.8  # fallback
    if stone_side:
        _, h_px = _bbox_wh(stone_side[0]["bbox"])
        depth_mm = h_px * scale_side

    anchor = {
        "center_2d":      [cx_px * scale_top, cy_px * scale_top],
        "radius_2d":      radius_mm,
        "depth_estimate": max(1.0, depth_mm),
        "annotated":      True
    }
    logger.info(f"Center stone anchor: radius={radius_mm:.2f}mm, depth={depth_mm:.2f}mm")
    return anchor


def extract_prong_anchors(top_anns: list, side_anns: list,
                           stone_anchor: dict,
                           scale_top: float, scale_side: float) -> list:
    """
    Returns a list of prong anchor dicts — one per individual prong annotation.
    If individual prongs aren't resolvable, returns an empty list
    (context_builder will fall back to even distribution).

    Each dict:
        angle       : polar angle in degrees around stone centre
        position_2d : [x_mm, y_mm] offset from ring centre
        height_hint : prong height in mm from side view (or None)
    """
    prong_top  = [a for a in top_anns if a["category"] == "prongs"]
    prong_side = [a for a in side_anns  if a["category"] == "prongs"]

    if len(prong_top) < 2:
        logger.info("Fewer than 2 individual prong annotations — skipping per-prong anchors.")
        return []

    stone_cx_px = stone_anchor["center_2d"][0] / scale_top
    stone_cy_px = stone_anchor["center_2d"][1] / scale_top

    # Height hint from side view
    height_hint_mm = None
    if prong_side:
        _, h_px = _bbox_wh(prong_side[0]["bbox"])
        height_hint_mm = h_px * scale_side

    anchors = []
    for ann in prong_top:
        bbox = ann["bbox"]
        seg  = ann.get("segmentation", [])
        cx_px, cy_px = _poly_centroid(seg) or _bbox_centroid(bbox)

        dx = cx_px - stone_cx_px
        dy = cy_px - stone_cy_px
        angle_deg = math.degrees(math.atan2(dy, dx))

        anchors.append({
            "angle":       round(angle_deg, 1),
            "position_2d": [cx_px * scale_top, cy_px * scale_top],
            "height_hint": height_hint_mm
        })

    logger.info(f"Extracted {len(anchors)} prong anchors at angles: "
                f"{[a['angle'] for a in anchors]}")
    return anchors


def extract_band_anchor(top_anns: list, side_anns: list,
                         inner_radius_mm: float, outer_radius_mm: float) -> dict:
    """
    Band anchor — always present, describes the ring's base geometry.
    """
    return {
        "center":       [0.0, 0.0],
        "inner_radius": inner_radius_mm,
        "outer_radius": outer_radius_mm,
        "annotated":    bool([a for a in top_anns if a["category"] == "band"])
    }


def extract_gallery_anchor(top_anns: list, side_anns: list,
                            stone_anchor: dict, band_anchor: dict,
                            scale_top: float, scale_side: float) -> dict:
    """
    Gallery anchor — ALWAYS returns a valid dict, never None.

    mode = "explicit"  → gallery was annotated; derive from COCO
    mode = "inferred"  → no gallery annotation; derive fallback support points
                         from band top circumference at stone's angular position
    """
    gallery_top  = [a for a in top_anns  if a["category"] == "gallery"]
    gallery_side = [a for a in side_anns  if a["category"] == "gallery"]

    outer_r = band_anchor["outer_radius"]

    if gallery_top or gallery_side:
        # ── Explicit gallery ────────────────────────────────────────────────
        height_mm = 0.0
        if gallery_side:
            _, h_px = _bbox_wh(gallery_side[0]["bbox"])
            height_mm = h_px * scale_side

        # Support points: left/right of stone base in top view
        stone_r   = stone_anchor["radius_2d"]
        support_l = [-stone_r, 0.0]
        support_r = [ stone_r, 0.0]

        if gallery_top:
            bbox = gallery_top[0]["bbox"]
            cx, cy = _bbox_centroid(bbox)
            w, _   = _bbox_wh(bbox)
            support_l = [(cx - w / 2.0) * scale_top, cy * scale_top]
            support_r = [(cx + w / 2.0) * scale_top, cy * scale_top]

        anchor = {
            "mode":           "explicit",
            "height":         max(0.5, height_mm),
            "support_points": [support_l, support_r],
            "annotated":      True
        }
        logger.info(f"Gallery anchor (explicit): height={height_mm:.2f}mm")
        return anchor

    else:
        # ── Inferred gallery — use band top as support surface ──────────────
        # Generate 4 support points around the top of the band circle
        # at the same XZ radius, symmetrically around where the stone sits.
        support_points = []
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            support_points.append([
                outer_r * math.cos(rad),
                outer_r * math.sin(rad)
            ])

        anchor = {
            "mode":           "inferred",
            "height":         0.0,
            "support_points": support_points,
            "annotated":      False
        }
        logger.info("Gallery anchor (inferred): no gallery annotation — band top as support")
        return anchor


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_anchor_graph(geometry: dict, top_anns: list, side_anns: list) -> dict:
    """
    Master function — converts raw COCO geometry + annotation lists into
    a typed AnchorGraph dict consumed by context_builder and support_solver.

    Returns:
    {
        "center_stone" : { ... },
        "prongs"       : [ { ... }, ... ],
        "gallery"      : { ... },
        "band"         : { ... }
    }
    """
    meta       = geometry.get("meta", {})
    scale_top  = meta.get("scale_top",  0.05)
    scale_side = meta.get("scale_side", 0.05)
    band_geom  = geometry.get("shank", {}).get("band", {})

    inner_r = band_geom.get("inner_radius", 8.5)
    outer_r = band_geom.get("outer_radius", inner_r + 1.8)

    # 1. Band — always first (other anchors depend on it)
    band_anchor = extract_band_anchor(top_anns, side_anns, inner_r, outer_r)

    # 2. Center stone
    stone_anchor = extract_center_stone_anchor(top_anns, side_anns, scale_top, scale_side)

    # 3. Prongs — may be empty list
    prong_anchors = extract_prong_anchors(top_anns, side_anns, stone_anchor,
                                           scale_top, scale_side)

    # 4. Gallery — ALWAYS returns dict (explicit or inferred)
    gallery_anchor = extract_gallery_anchor(top_anns, side_anns, stone_anchor,
                                             band_anchor, scale_top, scale_side)

    graph = {
        "center_stone": stone_anchor,
        "prongs":        prong_anchors,
        "gallery":       gallery_anchor,
        "band":          band_anchor
    }

    logger.info(
        f"AnchorGraph built — stone_r={stone_anchor['radius_2d']:.2f}mm, "
        f"prong_count={len(prong_anchors)}, "
        f"gallery_mode={gallery_anchor['mode']}, "
        f"band_outer_r={outer_r:.2f}mm"
    )
    return graph