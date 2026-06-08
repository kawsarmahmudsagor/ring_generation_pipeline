import json
from coco_parser import parse_geometry
from validator import compute_iou
import config

geom = parse_geometry("inputs/annotations.coco.json")
with open("outputs/ring_stats.json") as f:
    stats = json.load(f)

meta = geom.get("meta", {})
scale_top = meta.get("scale_top", 0.05)
scale_side = meta.get("scale_side", 0.05)
origin_top = meta.get("origin_top", {"x": 400.0, "y": 400.0})
origin_side = meta.get("origin_side", {"x": 400.0, "y": 400.0})

stone_coco = geom.get("head", {}).get("center_stone", {})
stone_stats = stats.get("components", {}).get("center_stone", {})

cad_stone_w = stone_stats.get("Xlen", 0.0)
cad_stone_l = stone_stats.get("Ylen", 0.0)
cad_stone_h = stone_stats.get("Zlen", 0.0)
cad_stone_center_z = stone_stats.get("Zmin", 0.0) + cad_stone_h / 2.0

stone_bbox_side = stone_coco.get("bbox_side")
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

print("stone_bbox_side:", json.dumps(stone_bbox_side, indent=2))
print("proj_box_side:", json.dumps(proj_box_side, indent=2))
print("iou_side:", compute_iou(proj_box_side, stone_bbox_side))
