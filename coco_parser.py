import json
import logging
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

    # Map category ID to category name
    cat_map = {}
    for cat in data.get("categories", []):
        cat_map[cat["id"]] = cat["name"].lower()

    annotations = []
    for ann in data.get("annotations", []):
        if ann.get("image_id") != target_image_id:
            continue

        cat_id = ann.get("category_id")
        cat_name = cat_map.get(cat_id, "unknown")
        
        # Standardize category names according to user's schema
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
    Filters by top_image_id and side_image_id and groups them into head and shank components.
    """
    if top_image_id is None:
        top_image_id = config.TOP_IMAGE_ID
    if side_image_id is None:
        side_image_id = config.SIDE_IMAGE_ID

    top_anns = load_coco_annotations(coco_path, top_image_id)
    side_anns = load_coco_annotations(coco_path, side_image_id)

    # 1. Find Band and Inner Band (Void) in Top/Side views using combined bounding boxes
    top_band_ann = get_combined_bbox(top_anns, "band")
    top_inner_ann = get_combined_bbox(top_anns, "inner_band")

    side_band_ann = get_combined_bbox(side_anns, "band")
    side_inner_ann = get_combined_bbox(side_anns, "inner_band")

    # Base scale calculation (px to mm)
    inner_diameter_mm = config.DEFAULT_INNER_DIAMETER_MM
    outer_diameter_mm = inner_diameter_mm + 2 * config.DEFAULT_BAND_THICKNESS_MM

    # Determine Top view scale
    if top_inner_ann:
        inner_px_top = top_inner_ann.w
        scale_top = inner_diameter_mm / inner_px_top
        cx_top = top_inner_ann.cx
        cy_top = top_inner_ann.cy
        logging.info(f"Top scale calculated from 'Void' (inner_band): {scale_top:.4f} mm/px")
    elif top_band_ann:
        outer_px_top = top_band_ann.w
        scale_top = outer_diameter_mm / outer_px_top
        cx_top = top_band_ann.cx
        cy_top = top_band_ann.cy
        logging.info(f"Top scale calculated from outer band: {scale_top:.4f} mm/px")
    else:
        scale_top = 0.05
        cx_top = 400.0
        cy_top = 400.0
        logging.warning(f"No band or Void found in top view. Using default scale: {scale_top} mm/px")

    # Determine Side view scale
    if side_inner_ann:
        inner_px_side = (side_inner_ann.w + side_inner_ann.h) / 2.0
        scale_side = inner_diameter_mm / inner_px_side
        cx_side = side_inner_ann.cx
        cy_side = side_inner_ann.cy
        logging.info(f"Side scale calculated from 'Void' (inner_band): {scale_side:.4f} mm/px")
    elif side_band_ann:
        outer_px_side = side_band_ann.w
        scale_side = outer_diameter_mm / outer_px_side
        cx_side = side_band_ann.cx
        cy_side = side_band_ann.cy
        logging.info(f"Side scale calculated from band outer width: {scale_side:.4f} mm/px")
    else:
        scale_side = 0.05
        cx_side = 400.0
        cy_side = 400.0
        logging.warning(f"No band or Void found in side view. Using default scale: {scale_side} mm/px")

    # Store geometry details
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

    # Extract Band Geometry (part of Shank)
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

    # Helper function to convert a bounding box to physical metrics
    def get_physical_dims(bbox_top, bbox_side, category=None):
        dims = {}
        if bbox_top:
            dims["width"] = bbox_top.w * scale_top
            dims["length"] = bbox_top.h * scale_top
            dims["x_offset"] = (bbox_top.cx - cx_top) * scale_top
            dims["y_offset"] = (cy_top - bbox_top.cy) * scale_top
        if bbox_side:
            if "width" not in dims:
                dims["width"] = bbox_side.w * scale_side
            dims["height"] = bbox_side.h * scale_side
            dims["x_offset_side"] = (bbox_side.cx - cx_side) * scale_side
            
            center_z = (cy_side - bbox_side.cy) * scale_side
            if category == "center_stone":
                # Girdle plane is at 75% height from bottom (or 25% from top), so we add 25% of height to the center Z
                dims["z_offset"] = center_z + (bbox_side.h * scale_side) * 0.25
            else:
                dims["z_offset"] = center_z
        return dims

    # Process Head components
    head_categories = ["center_stone", "prongs", "gallery", "bridge", "halo"]
    for category in head_categories:
        bbox_top = get_combined_bbox(top_anns, category)
        bbox_side = get_combined_bbox(side_anns, category)

        if bbox_top or bbox_side:
            geometry["head"][category] = get_physical_dims(bbox_top, bbox_side, category)
            geometry["head"][category]["bbox_top"] = bbox_top.to_dict() if bbox_top else None
            geometry["head"][category]["bbox_side"] = bbox_side.to_dict() if bbox_side else None

    # Process Shank components
    shank_categories = ["shoulder", "side_stones"]
    for category in shank_categories:
        bbox_top = get_combined_bbox(top_anns, category)
        bbox_side = get_combined_bbox(side_anns, category)

        if bbox_top or bbox_side:
            geometry["shank"][category] = get_physical_dims(bbox_top, bbox_side, category)
            geometry["shank"][category]["bbox_top"] = bbox_top.to_dict() if bbox_top else None
            geometry["shank"][category]["bbox_side"] = bbox_side.to_dict() if bbox_side else None

    return geometry
