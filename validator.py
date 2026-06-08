import json
import logging
import os
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def compute_iou(box1: dict, box2: dict) -> float:
    """Computes Intersection over Union (IoU) of two bounding boxes [x,y,w,h]."""
    x1_min, y1_min = box1["x"], box1["y"]
    x1_max, y1_max = x1_min + box1["w"], y1_min + box1["h"]
    x2_min, y2_min = box2["x"], box2["y"]
    x2_max, y2_max = x2_min + box2["w"], y2_min + box2["h"]

    inter_w = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
    inter_h = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))
    inter_area = inter_w * inter_h

    area1 = box1["w"] * box1["h"]
    area2 = box2["w"] * box2["h"]
    union_area = area1 + area2 - inter_area

    return 0.0 if union_area <= 0 else inter_area / union_area


def validate_projection(geometry: dict, cad_stats: dict, context: dict = None) -> dict:
    """
    Projects 3D CAD bounding boxes back to 2D pixel space and checks IoU and
    dimensional error against the original COCO annotations.

    All z_offset values (in both context and cad_stats) now represent the BASE Z
    of each component (fixed in coco_parser and freecad_toolkit).  This validator
    compares like for like.
    """
    logging.info("Validating generated CAD model projections...")

    meta        = geometry.get("meta", {})
    scale_top   = meta.get("scale_top",   0.05)
    scale_side  = meta.get("scale_side",  0.05)
    origin_top  = meta.get("origin_top",  {"x": 400.0, "y": 400.0})
    origin_side = meta.get("origin_side", {"x": 400.0, "y": 400.0})

    report = {"is_valid": True, "metrics": {}, "adjustments": {}}

    components_stats = cad_stats.get("components", {})
    band_stats       = components_stats.get("band", {})
    stone_stats      = components_stats.get("center_stone", {})

    shank_coco = geometry.get("shank", {})
    head_coco  = geometry.get("head",  {})

    # 1. Band validation
    band_coco = shank_coco.get("band", {})
    if band_stats and band_coco:
        cad_outer_diameter  = max(band_stats.get("Xlen", 0.0), band_stats.get("Zlen", 0.0))
        coco_outer_diameter = band_coco.get("outer_radius", 10.3) * 2.0
        dim_error_mm        = abs(cad_outer_diameter - coco_outer_diameter)

        report["metrics"]["band"] = {
            "cad_outer_diameter_mm":  cad_outer_diameter,
            "coco_outer_diameter_mm": coco_outer_diameter,
            "error_mm": dim_error_mm,
            "iou":      1.0 - min(1.0, dim_error_mm / max(coco_outer_diameter, 1e-6))
        }

        if dim_error_mm > config.VALIDATION_MAX_ERROR_MM:
            report["is_valid"] = False
            thickness_diff = (coco_outer_diameter - cad_outer_diameter) / 2.0
            report["adjustments"]["shank"] = {"band": {"thickness": thickness_diff}}

    # 2. Center-stone validation
    stone_coco = head_coco.get("center_stone", {})
    if stone_stats and stone_coco:
        bbox_top  = stone_coco.get("bbox_top")
        bbox_side = stone_coco.get("bbox_side")

        cad_w      = stone_stats.get("Xlen", 0.0)
        cad_l      = stone_stats.get("Ylen", 0.0)
        cad_h      = stone_stats.get("Zlen", 0.0)
        # After freecad_toolkit fix: Zmin == stone base (pavilion tip) == z_offset
        cad_base_z = stone_stats.get("Zmin", 0.0)

        report["metrics"]["center_stone"] = {}
        stone_adj = {}

        # Top view
        if bbox_top:
            coco_w_mm = stone_coco.get("width",  6.0)
            coco_l_mm = stone_coco.get("length", 6.0)

            stone_cut = "round"
            if context:
                stone_cut = context.get("head", {}).get("center_stone", {}).get("cut", "round").lower()

            if stone_cut in ["round", "princess", "cushion"]:
                coco_l_mm = coco_w_mm
                bbox_top  = dict(bbox_top)
                bbox_top["h"] = bbox_top["w"]
                bbox_top["y"] = bbox_top["cy"] - bbox_top["w"] / 2.0

            proj_w_px  = cad_w / scale_top
            proj_l_px  = cad_l / scale_top
            proj_cx_px = origin_top["x"] + (stone_coco.get("x_offset", 0.0) / scale_top)
            proj_cy_px = origin_top["y"] - (stone_coco.get("y_offset", 0.0) / scale_top)

            proj_box_top = {
                "x": proj_cx_px - proj_w_px / 2.0,
                "y": proj_cy_px - proj_l_px / 2.0,
                "w": proj_w_px,
                "h": proj_l_px
            }

            iou_top    = compute_iou(proj_box_top, bbox_top)
            w_error_mm = abs(cad_w - coco_w_mm)

            report["metrics"]["center_stone"]["iou_top"]        = iou_top
            report["metrics"]["center_stone"]["width_error_mm"] = w_error_mm

            if iou_top < config.VALIDATION_IOU_THRESHOLD or w_error_mm > config.VALIDATION_MAX_ERROR_MM:
                report["is_valid"]  = False
                stone_adj["width"]  = coco_w_mm - cad_w
                if stone_cut in ["round", "princess", "cushion"]:
                    stone_adj["length"] = coco_w_mm - cad_w
                else:
                    stone_adj["length"] = coco_l_mm - cad_l

        # Side view
        if bbox_side:
            coco_h_mm   = stone_coco.get("height",   3.8)
            # coco z_offset is now the stone BASE Z (fixed in coco_parser)
            coco_base_z = stone_coco.get("z_offset", 12.0)

            # Project stone centre for the visual bounding box
            cad_center_z = cad_base_z + cad_h / 2.0

            proj_w_side_px  = cad_w / scale_side
            proj_h_px       = cad_h / scale_side
            proj_cx_side_px = origin_side["x"] + (stone_coco.get("x_offset_side", 0.0) / scale_side)
            proj_cy_side_px = origin_side["y"] - (cad_center_z / scale_side)

            proj_box_side = {
                "x": proj_cx_side_px - proj_w_side_px / 2.0,
                "y": proj_cy_side_px - proj_h_px / 2.0,
                "w": proj_w_side_px,
                "h": proj_h_px
            }

            iou_side   = compute_iou(proj_box_side, bbox_side)
            h_error_mm = abs(cad_h      - coco_h_mm)
            z_error_mm = abs(cad_base_z - coco_base_z)

            report["metrics"]["center_stone"]["iou_side"]          = iou_side
            report["metrics"]["center_stone"]["height_error_mm"]   = h_error_mm
            report["metrics"]["center_stone"]["z_offset_error_mm"] = z_error_mm

            logging.info(
                f"Stone Z: cad_base={cad_base_z:.3f}mm  coco_base={coco_base_z:.3f}mm  "
                f"err={z_error_mm:.3f}mm | "
                f"cad_h={cad_h:.3f}mm  coco_h={coco_h_mm:.3f}mm  err={h_error_mm:.3f}mm | "
                f"iou_side={iou_side:.3f}"
            )

            if iou_side < config.VALIDATION_IOU_THRESHOLD or z_error_mm > config.VALIDATION_MAX_ERROR_MM:
                report["is_valid"]    = False
                stone_adj["height"]   = coco_h_mm   - cad_h
                stone_adj["z_offset"] = coco_base_z - cad_base_z

        if stone_adj:
            report["adjustments"]["head"] = {"center_stone": stone_adj}

    report_path = os.path.join(config.OUTPUT_DIR, "validation_report.json")
    try:
        with open(report_path, 'w') as rf:
            json.dump(report, rf, indent=2)
        logging.info(f"Saved validation report to {report_path}")
    except Exception as e:
        logging.error(f"Failed to save validation report: {e}")

    logging.info(f"Validation complete. Meets thresholds: {report['is_valid']}")
    return report