import json
import logging
import os
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def compute_iou(box1: dict, box2: dict) -> float:
    """Computes Intersection over Union (IoU) of two bounding boxes in [x, y, w, h] format."""
    x1_min, y1_min, x1_max, y1_max = box1["x"], box1["y"], box1["x"] + box1["w"], box1["y"] + box1["h"]
    x2_min, y2_min, x2_max, y2_max = box2["x"], box2["y"], box2["x"] + box2["w"], box2["y"] + box2["h"]

    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    inter_w = max(0.0, inter_x_max - inter_x_min)
    inter_h = max(0.0, inter_y_max - inter_y_min)
    inter_area = inter_w * inter_h

    area1 = box1["w"] * box1["h"]
    area2 = box2["w"] * box2["h"]
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area


def validate_projection(geometry: dict, cad_stats: dict, context: dict = None) -> dict:
    """
    Validates the generated 3D CAD dimensions against original COCO annotations.
    Projects 3D CAD bounds back to 2D image pixels and calculates overlap metrics.
    Returns validation status, scores, and recommended parameter adjustments.
    """
    logging.info("Validating generated CAD model projections...")

    meta = geometry.get("meta", {})
    scale_top = meta.get("scale_top", 0.05)
    scale_side = meta.get("scale_side", 0.05)
    origin_top = meta.get("origin_top", {"x": 400.0, "y": 400.0})
    origin_side = meta.get("origin_side", {"x": 400.0, "y": 400.0})

    report = {
        "is_valid": True,
        "metrics": {},
        "adjustments": {}
    }

    components_stats = cad_stats.get("components", {})
    band_stats = components_stats.get("band", {})
    stone_stats = components_stats.get("center_stone", {})

    # Extract sections
    shank_coco = geometry.get("shank", {})
    head_coco = geometry.get("head", {})

    # 1. Validate Band (Shank)
    band_coco = shank_coco.get("band", {})
    if band_stats and band_coco:
        cad_outer_diameter = max(band_stats.get("Xlen", 0.0), band_stats.get("Ylen", 0.0))
        coco_outer_diameter = band_coco.get("outer_radius", 10.3) * 2.0
        
        dim_error_mm = abs(cad_outer_diameter - coco_outer_diameter)
        report["metrics"]["band"] = {
            "cad_outer_diameter_mm": cad_outer_diameter,
            "coco_outer_diameter_mm": coco_outer_diameter,
            "error_mm": dim_error_mm,
            "iou": 1.0 - min(1.0, dim_error_mm / coco_outer_diameter)
        }
        
        if dim_error_mm > config.VALIDATION_MAX_ERROR_MM:
            report["is_valid"] = False
            thickness_diff = (coco_outer_diameter - cad_outer_diameter) / 2.0
            report["adjustments"]["shank"] = {"band": {"thickness": thickness_diff}}

    # 2. Validate Center Stone (Head)
    stone_coco = head_coco.get("center_stone", {})
    if stone_stats and stone_coco:
        stone_bbox_top = stone_coco.get("bbox_top")
        stone_bbox_side = stone_coco.get("bbox_side")
        
        cad_stone_w = stone_stats.get("Xlen", 0.0)
        cad_stone_l = stone_stats.get("Ylen", 0.0)
        cad_stone_h = stone_stats.get("Zlen", 0.0)
        # Girdle plane of brilliant stone is at Zmin + 75% of stone height
        cad_stone_z = stone_stats.get("Zmin", 0.0) + cad_stone_h * 0.75
        
        report["metrics"]["center_stone"] = {}
        stone_adjustments = {}

        # Top view validation
        if stone_bbox_top:
            coco_w_mm = stone_coco.get("width", 6.0)
            coco_l_mm = stone_coco.get("length", 6.0)
            
            # Determine cut style to enforce circular/square constraints on the top-view 2D annotation
            stone_cut = "round"
            if context:
                stone_cut = context.get("head", {}).get("center_stone", {}).get("cut", "round").lower()

            if stone_cut in ["round", "princess", "cushion"]:
                coco_l_mm = coco_w_mm
                # Adjust noisy top-view annotation to be square based on its width
                stone_bbox_top["h"] = stone_bbox_top["w"]
                stone_bbox_top["y"] = stone_bbox_top["cy"] - stone_bbox_top["w"] / 2.0
            
            proj_w_px = cad_stone_w / scale_top
            proj_l_px = cad_stone_l / scale_top
            proj_cx_px = origin_top["x"] + (stone_coco.get("x_offset", 0.0) / scale_top)
            proj_cy_px = origin_top["y"] - (stone_coco.get("y_offset", 0.0) / scale_top)
            
            proj_box_top = {
                "x": proj_cx_px - proj_w_px / 2.0,
                "y": proj_cy_px - proj_l_px / 2.0,
                "w": proj_w_px,
                "h": proj_l_px
            }
            
            iou_top = compute_iou(proj_box_top, stone_bbox_top)
            w_error_mm = abs(cad_stone_w - coco_w_mm)
            
            report["metrics"]["center_stone"]["iou_top"] = iou_top
            report["metrics"]["center_stone"]["width_error_mm"] = w_error_mm
            
            if iou_top < config.VALIDATION_IOU_THRESHOLD or w_error_mm > config.VALIDATION_MAX_ERROR_MM:
                report["is_valid"] = False
                stone_adjustments["width"] = coco_w_mm - cad_stone_w
                # For round/square cuts, do not adjust length independently of width
                if stone_cut in ["round", "princess", "cushion"]:
                    stone_adjustments["length"] = coco_w_mm - cad_stone_w
                else:
                    stone_adjustments["length"] = coco_l_mm - cad_stone_l

        # Side view validation
        if stone_bbox_side:
            coco_h_mm = stone_coco.get("height", 3.8)
            coco_z_mm = stone_coco.get("z_offset", 12.0)
            
            # The center of the 3D bounding box along Z
            cad_stone_center_z = stone_stats.get("Zmin", 0.0) + cad_stone_h / 2.0
            
            proj_w_side_px = cad_stone_w / scale_side
            proj_h_px = cad_stone_h / scale_side
            proj_cx_side_px = origin_side["x"] + (stone_coco.get("x_offset_side", 0.0) / scale_side)
            proj_cy_side_px = origin_side["y"] - (cad_stone_center_z / scale_side)
            
            proj_box_side = {
                "x": proj_cx_side_px - proj_w_side_px / 2.0,
                "y": proj_cy_side_px - proj_h_px / 2.0,
                "w": proj_w_side_px,
                "h": proj_h_px
            }
            
            iou_side = compute_iou(proj_box_side, stone_bbox_side)
            h_error_mm = abs(cad_stone_h - coco_h_mm)
            z_error_mm = abs(cad_stone_z - coco_z_mm)
            
            report["metrics"]["center_stone"]["iou_side"] = iou_side
            report["metrics"]["center_stone"]["height_error_mm"] = h_error_mm
            report["metrics"]["center_stone"]["z_offset_error_mm"] = z_error_mm
            
            if iou_side < config.VALIDATION_IOU_THRESHOLD or z_error_mm > config.VALIDATION_MAX_ERROR_MM:
                report["is_valid"] = False
                stone_adjustments["height"] = coco_h_mm - cad_stone_h
                stone_adjustments["z_offset"] = coco_z_mm - cad_stone_z
                
        if stone_adjustments:
            report["adjustments"]["head"] = {"center_stone": stone_adjustments}

    # Save validation report JSON
    report_path = os.path.join(config.OUTPUT_DIR, "validation_report.json")
    try:
        with open(report_path, 'w') as rf:
            json.dump(report, rf, indent=2)
        logging.info(f"Saved validation report to {report_path}")
    except Exception as e:
        logging.error(f"Failed to save validation report: {e}")

    logging.info(f"Validation complete. Meets thresholds: {report['is_valid']}")
    return report
