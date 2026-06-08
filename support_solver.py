"""
support_solver.py
────────────────────────────────────────────────────────────────────────────
Constraint-first assembly model.  Replaces the old "build components → fuse meshes"
approach with "define constraints → solve support surfaces → generate from anchors".

Core idea: ONLY this module decides where the stone sits in Z.
Everything else (prongs, gallery, bridge, halo) derives its Z from this solver.

Pipeline position:
    context_builder → support_solver → freecad_toolkit

Public API:
    resolve_stone_support(context, anchor_graph) → SupportResult dict
    apply_support_to_context(context, support)   → mutated context

SupportResult:
{
    "type":          "prong_support" | "gallery_support" | "direct_band_support",
    "stone_base_z":  float,   # BASE (pavilion tip) of the stone in world Z
    "anchor":        str,     # human-readable anchor description
    "prong_base_z":  float,   # where prong shafts start (≤ stone_base_z)
    "gallery_top_z": float,   # top of gallery (= stone_base_z when gallery used)
    "band_top_z":    float    # always = outer_radius
}
"""

import logging

logger = logging.getLogger(__name__)

# Minimum clearance above band top so the stone is never embedded in the band
_MIN_STONE_LIFT_MM = 0.5

# How far prong shafts sink below the stone girdle (embed depth)
_PRONG_EMBED_DEPTH_MM = 0.5


def resolve_stone_support(context: dict, anchor_graph: dict = None) -> dict:
    """
    ALWAYS returns a valid SupportResult.  Never returns None.

    Priority order:
      1. Prong support  — prongs annotated → prong tips define stone seat
      2. Gallery support — gallery annotated → gallery top defines stone seat
      3. Direct band support — fallback; stone sits on band top + minimal lift

    All Z coordinates follow the FreeCAD contract:
        Z = 0          → ring geometric centre (equator)
        Z = outer_r    → band top
        Z > outer_r    → above the band (head components)
    """
    shank      = context.get("shank", {})
    head       = context.get("head",  {})
    band       = shank.get("band", {})
    prong_ctx  = head.get("prongs",  None)
    gallery_ctx = head.get("gallery", None)

    outer_r    = float(band.get("outer_radius", 10.3))
    band_top_z = outer_r  # Z where band metal ends and head begins

    # ── 1. Prong support (highest priority) ──────────────────────────────────
    if prong_ctx:
        prong_h  = float(prong_ctx.get("height", 4.8))
        prong_z  = float(prong_ctx.get("z_offset", band_top_z))

        # Stone base = where prong tips land
        stone_base_z = prong_z + prong_h - _PRONG_EMBED_DEPTH_MM

        result = {
            "type":          "prong_support",
            "stone_base_z":  stone_base_z,
            "anchor":        "prong_tips",
            "prong_base_z":  prong_z,
            "gallery_top_z": stone_base_z,   # no separate gallery needed
            "band_top_z":    band_top_z
        }
        logger.info(
            f"Support solver → prong_support: "
            f"prong_base={prong_z:.2f}, stone_base={stone_base_z:.2f}"
        )
        return result

    # ── 2. Gallery support ────────────────────────────────────────────────────
    if gallery_ctx and gallery_ctx.get("mode", "none") == "explicit":
        gallery_z  = float(gallery_ctx.get("z_offset", band_top_z))
        gallery_h  = float(gallery_ctx.get("height",   2.0))
        stone_base_z = gallery_z + gallery_h

        result = {
            "type":          "gallery_support",
            "stone_base_z":  stone_base_z,
            "anchor":        "gallery_ring",
            "prong_base_z":  stone_base_z - _PRONG_EMBED_DEPTH_MM,
            "gallery_top_z": stone_base_z,
            "band_top_z":    band_top_z
        }
        logger.info(
            f"Support solver → gallery_support: "
            f"gallery=[{gallery_z:.2f}→{stone_base_z:.2f}], stone_base={stone_base_z:.2f}"
        )
        return result

    # ── 3. Direct band support (fallback) ─────────────────────────────────────
    stone_base_z = band_top_z + _MIN_STONE_LIFT_MM

    result = {
        "type":          "direct_band_support",
        "stone_base_z":  stone_base_z,
        "anchor":        "band_top_surface",
        "prong_base_z":  band_top_z,
        "gallery_top_z": stone_base_z,
        "band_top_z":    band_top_z
    }
    logger.info(
        f"Support solver → direct_band_support (fallback): "
        f"band_top={band_top_z:.2f}, stone_base={stone_base_z:.2f}"
    )
    return result


def apply_support_to_context(context: dict, support: dict) -> dict:
    """
    Mutates context in-place so ALL components derive their Z from
    the solved support result.  This is the universal Z fix:

        ❌ old: each component independently places itself
        ✅ new: support_solver is the single source of Z truth

    Rules applied:
      • center_stone.z_offset ← support["stone_base_z"]
      • prongs.z_offset       ← support["prong_base_z"]
      • gallery.z_offset      ← band_top_z  (gallery starts at band top)
      • halo.z_offset         ← stone_base_z  (halo rings stone at table level)
      • bridge.z_offset       ← band_top_z - small clearance
    """
    head       = context.get("head", {})
    shank      = context.get("shank", {})
    band       = shank.get("band", {})

    stone_base_z = support["stone_base_z"]
    prong_base_z = support["prong_base_z"]
    band_top_z   = support["band_top_z"]
    stone_height = float(head.get("center_stone", {}).get("height", 3.8))

    # ── Center stone ─────────────────────────────────────────────────────────
    if "center_stone" in head:
        old_z = head["center_stone"].get("z_offset", stone_base_z)
        head["center_stone"]["z_offset"] = stone_base_z
        if abs(old_z - stone_base_z) > 0.01:
            logger.info(f"  center_stone.z_offset: {old_z:.2f} → {stone_base_z:.2f}")

    # ── Prongs — derive from stone, not band ─────────────────────────────────
    if "prongs" in head:
        old_z = head["prongs"].get("z_offset", prong_base_z)
        head["prongs"]["z_offset"] = prong_base_z
        # Recalculate height so tips reach stone_base + embed_depth
        required_h = stone_base_z - prong_base_z + _PRONG_EMBED_DEPTH_MM
        head["prongs"]["height"] = max(required_h, head["prongs"].get("height", required_h))
        if abs(old_z - prong_base_z) > 0.01:
            logger.info(f"  prongs.z_offset: {old_z:.2f} → {prong_base_z:.2f}, "
                        f"height → {head['prongs']['height']:.2f}")

    # ── Gallery — base always at band top ─────────────────────────────────────
    if "gallery" in head:
        old_z = head["gallery"].get("z_offset", band_top_z)
        head["gallery"]["z_offset"] = band_top_z
        if abs(old_z - band_top_z) > 0.01:
            logger.info(f"  gallery.z_offset: {old_z:.2f} → {band_top_z:.2f}")

    # ── Bridge — just below band top ──────────────────────────────────────────
    if "bridge" in head:
        bridge_z = band_top_z - 0.5
        head["bridge"]["z_offset"] = max(0.0, bridge_z)

    # ── Halo — at stone top / table level ─────────────────────────────────────
    if "halo" in head:
        halo_z = stone_base_z + stone_height * 0.75  # near crown
        head["halo"]["z_offset"] = halo_z

    # Expose the support result in context for downstream diagnostics
    context["_support"] = support

    return context