import json
import os
import logging
from PIL import Image, ImageDraw
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_dummy_image(image_path: str):
    """Creates a simple placeholder ring design image for testing."""
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    # 800x800 image
    img = Image.new("RGB", (800, 800), color=(240, 240, 245))
    draw = ImageDraw.Draw(img)
    
    # Draw a simple ring drawing representation (top and side views)
    # Top View (center at 400, 400)
    draw.ellipse([250, 250, 550, 550], fill=None, outline=(150, 150, 150), width=15) # band
    draw.ellipse([300, 300, 500, 500], fill=(255, 255, 255), outline=(100, 100, 100), width=2) # finger hole
    draw.ellipse([340, 340, 460, 460], fill=(220, 230, 255), outline=(80, 120, 255), width=2) # center stone
    
    # Prongs
    for angle in [45, 135, 225, 315]:
        import math
        rad = math.radians(angle)
        cx = 400 + 62 * math.cos(rad)
        cy = 400 + 62 * math.sin(rad)
        draw.ellipse([cx-5, cy-5, cx+5, cy+5], fill=(120, 120, 120))

    img.save(image_path)
    logging.info(f"Created placeholder ring image at {image_path}")


def create_sample_coco(coco_path: str):
    """Creates a sample COCO annotation JSON matching the user's category list."""
    os.makedirs(os.path.dirname(coco_path), exist_ok=True)

    # Categories list matching user's spec
    categories = [
        {"id": 0, "name": "ring", "supercategory": "none"},
        {"id": 1, "name": "Full Ring", "supercategory": "ring"},
        {"id": 2, "name": "Head", "supercategory": "ring"},
        {"id": 3, "name": "Prong", "supercategory": "ring"},
        {"id": 4, "name": "Void", "supercategory": "ring"}, # maps to finger hole (inner band)
        {"id": 5, "name": "band", "supercategory": "ring"},
        {"id": 6, "name": "bridge", "supercategory": "ring"},
        {"id": 7, "name": "center_stone", "supercategory": "ring"},
        {"id": 8, "name": "gallery", "supercategory": "ring"},
        {"id": 9, "name": "halo", "supercategory": "ring"},
        {"id": 10, "name": "shank", "supercategory": "ring"},
        {"id": 11, "name": "shoulder", "supercategory": "ring"},
        {"id": 12, "name": "side_stones", "supercategory": "ring"}
    ]

    images = [
        {"id": 0, "width": 800, "height": 800, "file_name": "side_view.png"},
        {"id": 2, "width": 800, "height": 800, "file_name": "top_view.png"}
    ]

    # Annotations. Scale factor assumes:
    # 1mm = 20 pixels.
    # Inner diameter of Void (finger hole) = 17mm * 20px = 340 pixels width/height
    # Center = 400, 400. Finger hole box: x=230, y=230, w=340, h=340.
    # Outer band = 17mm + 2 * 1.8mm = 20.6mm * 20px = 412 pixels. Outer box: x=194, y=194, w=412, h=412.
    # Center stone = 6mm * 20px = 120 pixels. Box: x=340, y=340, w=120, h=120.
    
    annotations = [
        # === TOP VIEW (image_id = 2) ===
        # Void (Finger Hole)
        {
            "id": 101, "image_id": 2, "category_id": 4,
            "bbox": [230, 230, 340, 340], "area": 340*340, "iscrowd": 0
        },
        # Band
        {
            "id": 102, "image_id": 2, "category_id": 5,
            "bbox": [194, 194, 412, 412], "area": 412*412, "iscrowd": 0
        },
        # Center Stone
        {
            "id": 103, "image_id": 2, "category_id": 7,
            "bbox": [340, 340, 120, 120], "area": 120*120, "iscrowd": 0
        },
        # Prongs (approx outer envelope bounding box)
        {
            "id": 104, "image_id": 2, "category_id": 3,
            "bbox": [334, 334, 132, 132], "area": 132*132, "iscrowd": 0
        },
        # Halo
        {
            "id": 105, "image_id": 2, "category_id": 9,
            "bbox": [310, 310, 180, 180], "area": 180*180, "iscrowd": 0
        },

        # === SIDE VIEW (image_id = 0) ===
        # Void (Finger Hole)
        {
            "id": 201, "image_id": 0, "category_id": 4,
            "bbox": [230, 300, 340, 340], "area": 340*340, "iscrowd": 0
        },
        # Band (Shank outer circle in side view)
        {
            "id": 202, "image_id": 0, "category_id": 5,
            "bbox": [194, 264, 412, 412], "area": 412*412, "iscrowd": 0
        },
        # Center Stone (sits above the band)
        # band outer radius is 10.3mm (offset from center is 10.3mm * 20px = 206px)
        # Side view center of band is (400, 470)
        # Band outer top edge is at y = 470 - 206 = 264
        # Stone sits above this. Girdle Z offset = 12.0mm. So y_girdle = 470 - (12.0 * 20) = 470 - 240 = 230.
        # Stone height = 3.8mm * 20px = 76px.
        # Stone bbox y ranges from 230 - 76 = 154 to 230.
        # Bbox: [x = 400 - 60 = 340, y = 154, w = 120, h = 76]
        {
            "id": 203, "image_id": 0, "category_id": 7,
            "bbox": [340, 154, 120, 76], "area": 120*76, "iscrowd": 0
        },
        # Prongs (start at y=230 to 140)
        {
            "id": 204, "image_id": 0, "category_id": 3,
            "bbox": [334, 140, 132, 100], "area": 132*100, "iscrowd": 0
        },
        # Gallery (sits between band outer top edge at y=264 and stone girdle at y=230)
        # Bbox: [x=338, y=230, w=124, h=34]
        {
            "id": 205, "image_id": 0, "category_id": 8,
            "bbox": [338, 230, 124, 34], "area": 124*34, "iscrowd": 0
        },
        # Bridge
        {
            "id": 206, "image_id": 0, "category_id": 6,
            "bbox": [320, 255, 160, 20], "area": 160*20, "iscrowd": 0
        },
        # Side Stones (Pave) on shoulders (along side edges of band)
        {
            "id": 207, "image_id": 0, "category_id": 12,
            "bbox": [194, 264, 412, 120], "area": 412*120, "iscrowd": 0
        }
    ]

    coco_data = {
        "images": images,
        "categories": categories,
        "annotations": annotations
    }

    with open(coco_path, 'w') as f:
        json.dump(coco_data, f, indent=2)
    logging.info(f"Created sample COCO annotations file at {coco_path}")


def main():
    img_path = os.path.join(config.INPUT_DIR, "ring.png")
    coco_path = config.COCO_FILE
    
    create_dummy_image(img_path)
    create_sample_coco(coco_path)
    
    print("\nSample input generation successful!")
    print(f"Inputs generated in: {os.path.abspath(config.INPUT_DIR)}")
    print("You can now run the pipeline with: python pipeline.py")

if __name__ == "__main__":
    main()
