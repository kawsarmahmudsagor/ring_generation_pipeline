import json
import logging
import math
import os
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class BBox:
    """Helper class to represent a bounding box [x_min, y_min, width, height] in pixels."""
    def __init__(self, bbox_list):
        self.x = bbox_list[0]
        self.y = bbox_list[1]
        self.w = bbox_list[2]
        self.h = bbox_list[3]
        self.cx = self.x + self.w / 2.0
        self.cy = self.y + self.h / 2.0

    def to_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "cx": self.cx, "cy": self.cy}


def load_coco_annotations(json_path: str, target_image_id: int):
    """Loads COCO JSON file and returns a list of annotations for a specific image_id."""
    if not os.path.exists(json_path):
        logging.error(f"COCO file not found: {json_path}")
        return []
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read COCO JSON {json_path}: {e}")
        return []

    cat_map = {}
    for cat in data.get("categories", []):
        cat_map[cat["id"]] = cat["name"].lower()

    annotations = []
    for ann in data.get("annotations", []):
        if ann.get("image_id") != target_image_id:
            continue

        cat_id = ann.get("category_id")
        cat_name = cat_map.get(cat_id, "unknown")

        if cat_name in ["shank", "band", "ring_band"]:
            cat_name = "band"
        elif cat_name in ["void", "finger_hole"]:
            cat_name = "inner_band"
        elif cat_name in ["center_stone", "stone", "centerstone"]:
            cat_name = "center_stone"
        elif cat_name in ["prong", "prongs"]:
            cat_name = "prongs"
        elif cat_name in ["gallery", "undergallery"]:
            cat_name = "gallery"
        elif cat_name in ["bridge"]:
            cat_name = "bridge"
        elif cat_name in ["halo"]:
            cat_name = "halo"
        elif cat_name in ["shoulder", "shoulders"]:
            cat_name = "shoulder"
        elif cat_name in ["side_stones", "sidestones", "pave_shoulder"]:
            cat_name = "side_stones"

        annotations.append({
            "category": cat_name,
            "bbox": BBox(ann.get("bbox", [0, 0, 0, 0])),
            "segmentation": ann.get("segmentation", []),
            "area": ann.get("area", 0)
        })

    logging.info(f"Loaded {len(annotations)} annotations for image_id {target_image_id} from {json_path}")
    return annotations


def get_combined_bbox(anns, category):
    """Combines multiple annotations of the same category into a single enclosing BBox."""
    matching = [a for a in anns if a["category"] == category]
    if not matching:
        return None
    x_min = min(a["bbox"].x for a in matching)
    y_min = min(a["bbox"].y for a in matching)
    x_max = max(a["bbox"].x + a["bbox"].w for a in matching)
    y_max = max(a["bbox"].y + a["bbox"].h for a in matching)
    return BBox([x_min, y_min, x_max - x_min, y_max - y_min])


def parse_geometry(coco_path: str, top_image_id: int = None, side_image_id: int = None) -> dict:
    """
    Parses a single COCO annotation file to extract physical 3D dimensions of the ring.
    """
    if top_image_id is None:
        top_image_id = config.TOP_IMAGE_ID
    if side_image_id is None:
        side_image_id = config.SIDE_IMAGE_ID

    top_anns = load_coco_annotations(coco_path, top_image_id)
    side_anns = load_coco_annotations(coco_path, side_image_id)

    top_band_ann = get_combined_bbox(top_anns, "band")
    top_inner_ann = get_combined_bbox(top_anns, "inner_band")
    side_band_ann = get_combined_bbox(side_anns, "band")
    side_inner_ann = get_combined_bbox(side_anns, "inner_band")

    inner_diameter_mm = config.DEFAULT_INNER_DIAMETER_MM
    outer_diameter_mm = inner_diameter_mm + 2 * config.DEFAULT_BAND_THICKNESS_MM

    # --- Top view scale & origin ---
    if top_inner_ann:
        inner_px_top = top_inner_ann.w
        scale_top = inner_diameter_mm / inner_px_top
        cx_top = top_inner_ann.cx
        cy_top = top_inner_ann.cy
        logging.info(f"Top scale from 'Void': {scale_top:.4f} mm/px")
    elif top_band_ann:
        outer_px_top = top_band_ann.w
        scale_top = outer_diameter_mm / outer_px_top
        cx_top = top_band_ann.cx
        cy_top = top_band_ann.cy
        logging.info(f"Top scale from outer band: {scale_top:.4f} mm/px")
    else:
        scale_top = 0.05
        cx_top = 400.0
        cy_top = 400.0
        logging.warning(f"No band or Void found in top view. Using default scale.")

    # --- Side view scale & origin ---
    # The side-view origin (cx_side, cy_side) is the ring centre in pixel space.
    # In the side view the ring is oriented so the finger hole is horizontal;
    # the band bottom is at the bottom of the image.  We use the *band* annotation
    # to locate the ring centre so that Z=0 aligns with the ring's geometric centre.
    if side_band_ann:
        outer_px_side = side_band_ann.w
        scale_side = outer_diameter_mm / outer_px_side
        cx_side = side_band_ann.cx
        # Place the Z=0 origin at the geometric centre of the band in the side view.
        # The band in the side view is a circle; its centre pixel IS the ring centre.
        cy_side = side_band_ann.cy
        logging.info(f"Side scale from band: {scale_side:.4f} mm/px, origin=({cx_side:.1f},{cy_side:.1f})")
    elif side_inner_ann:
        inner_px_side = (side_inner_ann.w + side_inner_ann.h) / 2.0
        scale_side = inner_diameter_mm / inner_px_side
        cx_side = side_inner_ann.cx
        cy_side = side_inner_ann.cy
        logging.info(f"Side scale from 'Void': {scale_side:.4f} mm/px")
    else:
        scale_side = 0.05
        cx_side = 400.0
        cy_side = 400.0
        logging.warning(f"No band or Void found in side view. Using default scale.")

    geometry = {
        "meta": {
            "scale_top": scale_top,
            "scale_side": scale_side,
            "origin_top": {"x": cx_top, "y": cy_top},
            "origin_side": {"x": cx_side, "y": cy_side}
        },
        "shank": {},
        "head": {}
    }

    # --- Band geometry ---
    band_width_mm = config.DEFAULT_BAND_WIDTH_MM
    band_thickness_mm = config.DEFAULT_BAND_THICKNESS_MM
    if top_band_ann and top_inner_ann:
        band_thickness_mm = ((top_band_ann.w - top_inner_ann.w) / 2.0) * scale_top

    geometry["shank"]["band"] = {
        "inner_radius": inner_diameter_mm / 2.0,
        "width": band_width_mm,
        "thickness": band_thickness_mm,
        "outer_radius": (inner_diameter_mm / 2.0) + band_thickness_mm
    }

    # Helper: convert pixel bounding box to physical mm dimensions
    def get_physical_dims(bbox_top, bbox_side, category=None):
        dims = {}

        if bbox_top:
            dims["width"]    = bbox_top.w * scale_top
            dims["length"]   = bbox_top.h * scale_top
            dims["x_offset"] = (bbox_top.cx - cx_top) * scale_top
            dims["y_offset"] = (cy_top - bbox_top.cy) * scale_top

        if bbox_side:
            if "width" not in dims:
                dims["width"] = bbox_side.w * scale_side
            dims["height"] = bbox_side.h * scale_side
            dims["x_offset_side"] = (bbox_side.cx - cx_side) * scale_side

            # FIX: The side-view coordinate system has Y pointing DOWN in pixels,
            # so "higher on ring" = smaller pixel Y = larger Z in world space.
            # cy_side is the ring centre pixel (Z=0 in world space = centre of band).
            # A component whose pixel centre is ABOVE cy_side has positive world Z.
            #
            # component_center_z = (cy_side - bbox_side.cy) * scale_side
            #
            # context/freecad z_offset means the BASE (bottom) of the component.
            # base_z = center_z - half_height
            #
            # The old code used:  center_z + 0.25 * height   <-- WRONG
            # That formula shifted the z_offset 0.75 * height above the actual
            # base, landing near the girdle. This made the stone float far too high
            # and was the root cause of the head/band gap in the render.

            component_h_mm = bbox_side.h * scale_side
            center_z = (cy_side - bbox_side.cy) * scale_side
            dims["z_offset"] = center_z - component_h_mm / 2.0  # base = center - half_height

        return dims

    # --- Head components ---
    for category in ["center_stone", "prongs", "gallery", "bridge", "halo"]:
        bbox_top  = get_combined_bbox(top_anns,  category)
        bbox_side = get_combined_bbox(side_anns, category)
        if bbox_top or bbox_side:
            geometry["head"][category] = get_physical_dims(bbox_top, bbox_side, category)
            geometry["head"][category]["bbox_top"]  = bbox_top.to_dict()  if bbox_top  else None
            geometry["head"][category]["bbox_side"] = bbox_side.to_dict() if bbox_side else None

    # --- Derive prong geometry from individual prong annotations ---
    # Instead of treating all prong bboxes as a single merged region, inspect
    # each individual prong annotation to derive:
    #   - orientation: "radial" (prongs spread in XY from stone centre, top-view)
    #                  "vertical" (prongs are tall pillars aligned with Z axis)
    #   - placement_plane: "XY" (prongs radiate outward when viewed from top)
    #                      "XZ" (prongs lie in the ring's equatorial plane)
    #   - prong_angles_deg: list of per-prong angles derived from their pixel
    #                       positions relative to the ring/stone centre in the
    #                       top-view annotation.  If individual bboxes are not
    #                       available the angles are evenly distributed.
    individual_prong_anns = [a for a in top_anns if a["category"] == "prongs"]
    stone_top = get_combined_bbox(top_anns, "center_stone")

    if len(individual_prong_anns) > 1 and stone_top:
        # Each prong's centroid relative to the stone centre gives its angle.
        prong_angles = []
        for ann in individual_prong_anns:
            dx = ann["bbox"].cx - stone_top.cx
            dy = ann["bbox"].cy - stone_top.cy
            angle_deg = math.degrees(math.atan2(dy, dx))
            prong_angles.append(round(angle_deg, 1))

        # Determine orientation from individual prong aspect ratios.
        # A prong whose bbox is taller than wide (in the top view) is likely a
        # thin radial feature pointing toward the stone — i.e. "radial".
        # A prong whose bbox is wider than tall is more likely a flat cap —
        # i.e. "vertical" (pillar aligned with Z, appearing square from above).
        avg_aspect = sum(
            a["bbox"].h / a["bbox"].w if a["bbox"].w > 0 else 1.0
            for a in individual_prong_anns
        ) / len(individual_prong_anns)

        if avg_aspect > 1.1:
            # Tall & narrow in top view → pointed radially at the stone
            orientation = "radial"
        else:
            # Square / wide in top view → vertical pillars (seen from above)
            orientation = "vertical"

        placement_plane = "XY"  # individual prongs visible from top → XY plane

        logging.info(
            f"Derived prong orientation='{orientation}', "
            f"plane='{placement_plane}', angles={prong_angles}"
        )
    else:
        # Fall back: use the combined side-view prong bbox to infer orientation.
        prong_combined_side = get_combined_bbox(side_anns, "prongs")
        if prong_combined_side:
            side_aspect = (
                prong_combined_side.h / prong_combined_side.w
                if prong_combined_side.w > 0 else 1.0
            )
            # In the side view a "vertical" prong cluster is tall & narrow;
            # a "radial" cluster (spread around the stone) appears roughly square.
            orientation = "vertical" if side_aspect > 1.3 else "radial"
        else:
            orientation = "radial"
        placement_plane = "XY"
        prong_angles = []   # will be evenly distributed by context_builder
        logging.info(
            f"Derived prong orientation='{orientation}' from side-view bbox aspect ratio. "
            f"Per-prong angles not available — will be evenly distributed."
        )

    if "prongs" in geometry["head"]:
        geometry["head"]["prongs"]["orientation"]     = orientation
        geometry["head"]["prongs"]["placement_plane"] = placement_plane
        geometry["head"]["prongs"]["prong_angles_deg"] = prong_angles

    # --- Shank components ---
    for category in ["shoulder", "side_stones"]:
        bbox_top  = get_combined_bbox(top_anns,  category)
        bbox_side = get_combined_bbox(side_anns, category)
        if bbox_top or bbox_side:
            geometry["shank"][category] = get_physical_dims(bbox_top, bbox_side, category)
            geometry["shank"][category]["bbox_top"]  = bbox_top.to_dict()  if bbox_top  else None
            geometry["shank"][category]["bbox_side"] = bbox_side.to_dict() if bbox_side else None

    return geometry