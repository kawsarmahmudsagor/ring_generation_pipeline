"""
support_solver.py
────────────────────────────────────────────────────────────────────────────
Single-source constraint solver for ALL vertical assembly.

CORE RULE:
    The solver defines ONE invariant:
        → stone_support_z (stone seat plane)

Everything else attaches to it.

No component is allowed to redefine Z.
"""

import logging

logger = logging.getLogger(__name__)

_MIN_STONE_LIFT_MM = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def resolve_stone_support(context: dict, anchor_graph: dict = None) -> dict:
    """
    Returns a single canonical support plane for the entire ring.

    Output:
    {
        "type": "prong_support" | "gallery_support" | "band_support",
        "stone_support_z": float,   # SINGLE truth
        "band_top_z": float,
        "anchor": str
    }
    """

    shank = context.get("shank", {})
    head = context.get("head", {})
    band = shank.get("band", {})

    outer_r = float(band.get("outer_radius", 10.3))
    band_top_z = outer_r

    prongs = head.get("prongs")
    gallery = head.get("gallery")

    # ─────────────────────────────────────────────────────────────
    # 1. PRONG SUPPORT (if prongs exist, they ATTACH, not define)
    # ─────────────────────────────────────────────────────────────
    if prongs:
        prong_h = float(prongs.get("height", 4.0))

        # IMPORTANT FIX:
        # Do NOT compute stone position from prongs.
        # Instead define a stable support plane above prongs.
        stone_support_z = band_top_z + max(2.0, prong_h * 0.4)

        return {
            "type": "prong_support",
            "stone_support_z": stone_support_z,
            "band_top_z": band_top_z,
            "anchor": "prongs_attach_to_support_plane"
        }

    # ─────────────────────────────────────────────────────────────
    # 2. GALLERY SUPPORT (if exists)
    # ─────────────────────────────────────────────────────────────
    if gallery:
        gallery_h = float(gallery.get("height", 2.0))

        # SAFE fallback even if gallery is malformed
        base_z = band_top_z + gallery_h

        stone_support_z = max(base_z, band_top_z + _MIN_STONE_LIFT_MM)

        return {
            "type": "gallery_support",
            "stone_support_z": stone_support_z,
            "band_top_z": band_top_z,
            "anchor": "gallery_top_surface"
        }

    # ─────────────────────────────────────────────────────────────
    # 3. BAND SUPPORT (fallback universal floor)
    # ─────────────────────────────────────────────────────────────
    stone_support_z = band_top_z + _MIN_STONE_LIFT_MM

    return {
        "type": "band_support",
        "stone_support_z": stone_support_z,
        "band_top_z": band_top_z,
        "anchor": "band_top_surface"
    }


# ─────────────────────────────────────────────────────────────────────────────
# APPLY FUNCTION (CRITICAL FIX)
# ─────────────────────────────────────────────────────────────────────────────

def apply_support_to_context(context: dict, support: dict) -> dict:
    """
    UNIVERSAL RULE:
        All components must align to stone_support_z.

    We enforce:
        - center_stone → sits exactly at support plane
        - prongs → extend UPWARD into stone (not define position)
        - gallery → supports from below if exists
        - halo → centered on stone_support_z
        - bridge → below support plane
    """

    head = context.get("head", {})
    shank = context.get("shank", {})
    band = shank.get("band", {})

    band_top_z = support["band_top_z"]
    stone_z = support["stone_support_z"]

    stone = head.get("center_stone", {})
    prongs = head.get("prongs", {})
    gallery = head.get("gallery", {})
    halo = head.get("halo", {})
    bridge = head.get("bridge", {})

    stone_height = float(stone.get("height", 3.8))

    # ─────────────────────────────
    # CENTER STONE (fixed anchor)
    # ─────────────────────────────
    if stone:
        stone["z_offset"] = stone_z

    # ─────────────────────────────
    # PRONGS (ATTACH TO SUPPORT)
    # ─────────────────────────────
    if prongs:
        prong_base = band_top_z

        prongs["z_offset"] = prong_base

        # CRITICAL FIX:
        # Prongs MUST reach support plane, not define it
        prong_height_needed = (stone_z - prong_base) + 1.0
        prongs["height"] = max(prongs.get("height", prong_height_needed),
                               prong_height_needed)

    # ─────────────────────────────
    # GALLERY (optional support)
    # ─────────────────────────────
    if gallery:
        gallery["z_offset"] = band_top_z

    # ─────────────────────────────
    # HALO (centered on stone plane)
    # ─────────────────────────────
    if halo:
        halo["z_offset"] = stone_z + stone_height * 0.3

    # ─────────────────────────────
    # BRIDGE (below structure)
    # ─────────────────────────────
    if bridge:
        bridge["z_offset"] = band_top_z - 0.5

    context["_support"] = support
    return context