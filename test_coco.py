import json

with open("inputs/annotations.coco.json", "r") as f:
    d = json.load(f)

cats = {c["id"]: c["name"] for c in d["categories"]}

print("=== Images ===")
for im in d.get("images", []):
    print(f"ID {im['id']}: {im['file_name']} (w={im['width']}, h={im['height']})")

print("\n=== Annotations ===")
# Group by image ID
grouped = {}
for a in d.get("annotations", []):
    img_id = a["image_id"]
    if img_id not in grouped:
        grouped[img_id] = []
    grouped[img_id].append(a)

for img_id, anns in sorted(grouped.items()):
    print(f"\nImage ID {img_id}:")
    for a in anns:
        name = cats.get(a["category_id"], "unknown")
        print(f"  Category '{name}': bbox={a['bbox']}, area={a.get('area', 0)}")
