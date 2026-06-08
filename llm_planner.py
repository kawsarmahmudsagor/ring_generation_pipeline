import json
import logging
from llm_client import get_llm_client
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PLANNER_SYSTEM_PROMPT = """You are a jewelry CAD compilation planner. Your task is to output a sequence of 3D construction tool calls that build a jewelry ring based on the hierarchical context JSON provided.
You must output a raw JSON array containing dictionaries with keys "tool" and "params". Do not wrap the JSON in markdown code blocks.

The tool library specifications are:
1. "create_band"
   - inner_radius (float): radius of finger hole in mm.
   - width (float): thickness of band along finger axis in mm.
   - thickness (float): height of metal shell from inner to outer radius in mm.
   - profile_type (string): "court", "d_shape", or "flat".

2. "create_gallery"
   - style (string): "cathedral" or "solitaire" or "bypass".
   - width (float): outer width of the gallery in mm.
   - height (float): vertical span of gallery in mm.
   - z_offset (float): starting height of gallery floor in mm (usually starts at the outer_radius of the band).

3. "create_bridge"
   - height (float): vertical thickness of the bridge wire in mm.
   - z_offset (float): vertical offset of the bridge in mm (usually sits right around the band outer_radius).

4. "create_center_stone"
   - cut (string): "round", "oval", "cushion", "princess", "emerald", "pear", "marquise".
   - width (float): width (diameter) of center stone in mm.
   - length (float): length of center stone in mm (same as width for round/cushion/princess).
   - height (float): total thickness of center stone in mm.
   - z_offset (float): Z-coordinate of the center stone girdle in mm.

5. "create_prongs"
   - count (int): number of prongs (4, 6, 8).
   - radius (float): thickness radius of each prong wire in mm.
   - height (float): length of prong wires in mm.
   - radial_distance (float): distance from the ring center to the prongs in mm (must match center stone radius).
   - z_offset (float): starting height of the prongs in mm.

6. "create_halo"
   - stone_count (int): number of accent stones in the halo.
   - stone_size (float): diameter of individual halo stones in mm.
   - radial_distance (float): radius of the halo circle in mm.
   - z_offset (float): Z-coordinate of the halo plane.

7. "create_side_stones"
   - stone_size (float): diameter of individual pavé stones on the shoulders in mm.
   - stone_count (int): total number of pavé stones.

Example Output:
[
  {"tool": "create_band", "params": {"inner_radius": 8.5, "width": 2.5, "thickness": 1.8, "profile_type": "court"}},
  {"tool": "create_gallery", "params": {"style": "cathedral", "width": 6.4, "height": 4.2, "z_offset": 10.3}},
  {"tool": "create_bridge", "params": {"height": 1.2, "z_offset": 10.0}},
  {"tool": "create_center_stone", "params": {"cut": "round", "width": 6.0, "length": 6.0, "height": 3.8, "z_offset": 14.5}},
  {"tool": "create_prongs", "params": {"count": 4, "radius": 0.4, "height": 4.8, "radial_distance": 3.0, "z_offset": 14.0}},
  {"tool": "create_halo", "params": {"stone_count": 16, "stone_size": 1.2, "radial_distance": 4.2, "z_offset": 14.3}},
  {"tool": "create_side_stones", "params": {"stone_size": 1.3, "stone_count": 10}}
]

Output ONLY the JSON list of tool calls. Do not explain anything."""


def generate_rule_based_plan(context: dict) -> list:
    """Generates a tool call plan directly from the hierarchical context dictionary using rules."""
    logging.info("Generating rule-based tool call plan...")
    plan = []

    shank = context.get("shank", {})
    head = context.get("head", {})

    # 1. Band (Shank)
    band = shank.get("band", {})
    plan.append({
        "tool": "create_band",
        "params": {
            "inner_radius": float(band.get("inner_radius", 8.5)),
            "width": float(band.get("width", 2.5)),
            "thickness": float(band.get("thickness", 1.8)),
            "profile_type": str(band.get("profile_type", "court"))
        }
    })

    # 2. Side Stones (Shank)
    side_stones = shank.get("side_stones", {})
    if side_stones.get("enabled", False):
        plan.append({
            "tool": "create_side_stones",
            "params": {
                "stone_size": float(side_stones.get("stone_size", 1.3)),
                "stone_count": int(side_stones.get("stone_count", 10))
            }
        })

    # 3. Gallery (Head)
    gallery = head.get("gallery", {})
    if gallery.get("enabled", False):
        plan.append({
            "tool": "create_gallery",
            "params": {
                "style": str(gallery.get("style", "cathedral")),
                "width": float(gallery.get("width", 6.5)),
                "height": float(gallery.get("height", 3.0)),
                "z_offset": float(gallery.get("z_offset", 10.3))
            }
        })

    # 4. Bridge (Head)
    bridge = head.get("bridge", {})
    if bridge.get("enabled", False):
        plan.append({
            "tool": "create_bridge",
            "params": {
                "height": float(bridge.get("height", 1.2)),
                "z_offset": float(bridge.get("z_offset", 10.0))
            }
        })

    # 5. Center Stone (Head)
    stone = head.get("center_stone", {})
    plan.append({
        "tool": "create_center_stone",
        "params": {
            "cut": str(stone.get("cut", "round")),
            "width": float(stone.get("width", 6.0)),
            "length": float(stone.get("length") if stone.get("length", 0.0) > 0 else stone.get("width", 6.0)),
            "height": float(stone.get("height", 3.8)),
            "z_offset": float(stone.get("z_offset", 12.0))
        }
    })

    # 6. Prongs (Head)
    prongs = head.get("prongs", {})
    plan.append({
        "tool": "create_prongs",
        "params": {
            "count": int(prongs.get("count", 4)),
            "radius": float(prongs.get("radius", 0.4)),
            "height": float(prongs.get("height", 3.0)),
            "radial_distance": float(prongs.get("radial_distance", 3.0)),
            "z_offset": float(prongs.get("z_offset", 11.5))
        }
    })

    # 7. Halo (Head)
    halo = head.get("halo", {})
    if halo.get("enabled", False):
        plan.append({
            "tool": "create_halo",
            "params": {
                "stone_count": int(halo.get("stone_count", 16)),
                "stone_size": float(halo.get("stone_size", 1.2)),
                "radial_distance": float(halo.get("radial_distance", 4.2)),
                "z_offset": float(halo.get("z_offset", 12.0))
            }
        })

    return plan


def plan_tool_calls(context: dict) -> list:
    """
    Plans the tool calls for the CAD engine.
    Uses the configured LLM provider, or falls back to rule-based generation.
    """
    if config.LLM_PROVIDER == "rule_based":
        return generate_rule_based_plan(context)

    try:
        client = get_llm_client()
        prompt = f"System:\n{PLANNER_SYSTEM_PROMPT}\n\nUser Context:\n{json.dumps(context, indent=2)}\n\nGenerate the tool call plan JSON array:"
        logging.info(f"Querying tool plan via LLM provider: {config.LLM_PROVIDER}")
        response_text = client.query_text(prompt)

        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            first_newline = cleaned_text.find("\n")
            if first_newline != -1:
                cleaned_text = cleaned_text[first_newline:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

        plan = json.loads(cleaned_text)
        if isinstance(plan, list) and len(plan) > 0:
            logging.info(f"Successfully planned {len(plan)} tool calls via LLM.")
            return plan
        else:
            raise ValueError("LLM returned empty plan or invalid format.")
    except Exception as e:
        logging.error(f"Failed to plan tool calls via LLM: {e}. Falling back to rule-based plan.")
        return generate_rule_based_plan(context)
