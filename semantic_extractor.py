import json
import logging
import os
from llm_client import get_llm_client
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Only truly semantic fields — things that cannot be determined from COCO geometry.
# Presence/absence of components (gallery, halo, bridge, etc.) is determined solely
# by whether that category exists in the annotation file.
SEMANTIC_PROMPT = """You are a professional jewelry design assistant. Analyze the provided ring image and extract its semantic design parameters.
Respond with a raw JSON object only. Do not wrap it in markdown code blocks. The JSON must follow this exact schema:
{
  "ring_style": "Solitaire" | "Cathedral" | "Halo" | "Three-Stone" | "Bypass" | "Cluster",
  "setting_type": "Prong" | "Bezel" | "Tension" | "Channel" | "Flush" | "Pave",
  "center_stone_cut": "Round" | "Cushion" | "Princess" | "Oval" | "Pear" | "Marquise" | "Emerald" | "Radiant" | "None",
  "shank_style": "Pave" | "Plain" | "Split-Shank" | "Bypass" | "Tapered",
  "shoulders": "Pave" | "Plain" | "Cathedral",
  "prong_count": 4 | 6 | 8,
  "symmetry": "Bilateral" | "Radial" | "Asymmetrical"
}

Rules:
- Do NOT include halo, gallery, bridge, or any structural component fields — those come from geometry annotations.
- prong_count must be one of 4, 6, or 8.
- Provide your best estimate based on the visual details.
- Respond with valid JSON only. Do not explain or write anything else."""


def extract_semantics(image_path: str) -> dict:
    """
    Extracts purely semantic ring design parameters from the input image.
    Does NOT include structural presence/absence flags (halo, gallery, bridge) —
    those are determined by the COCO annotation file, not the LLM.
    """
    default_semantics = {
        "ring_style":        "Solitaire",
        "setting_type":      "Prong",
        "center_stone_cut":  "Round",
        "shank_style":       "Plain",
        "shoulders":         "Plain",
        "prong_count":       4,
        "symmetry":          "Bilateral"
    }

    if config.LLM_PROVIDER == "rule_based" or not image_path or not os.path.exists(image_path):
        logging.info("Using default/rule-based semantic parameters.")
        return default_semantics

    try:
        client = get_llm_client()
        logging.info(f"Querying semantic parameters via LLM provider: {config.LLM_PROVIDER}")
        response_text = client.query_vision(SEMANTIC_PROMPT, image_path)

        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            first_newline = cleaned_text.find("\n")
            if first_newline != -1:
                cleaned_text = cleaned_text[first_newline:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

        parsed = json.loads(cleaned_text)
        logging.info("Successfully parsed semantic attributes from LLM.")

        # Drop any structural keys the LLM hallucinated back in
        for banned in ("halo", "gallery", "bridge", "side_stones"):
            parsed.pop(banned, None)

        # Fill missing keys with defaults; validate prong_count
        for k, v in default_semantics.items():
            if k not in parsed:
                parsed[k] = v
        if parsed.get("prong_count") not in (4, 6, 8):
            parsed["prong_count"] = default_semantics["prong_count"]

        return parsed

    except Exception as e:
        logging.error(f"Failed to extract semantic parameters from LLM: {e}. Falling back to defaults.")
        return default_semantics