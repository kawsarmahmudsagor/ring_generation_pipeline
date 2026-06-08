import json
import logging
import os
from llm_client import get_llm_client
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SEMANTIC_PROMPT = """You are a professional jewelry design assistant. Analyze the provided ring image and extract its semantic design parameters.
Respond with a raw JSON object only. Do not wrap it in markdown code blocks. The JSON must follow this exact schema:
{
  "ring_style": "Solitaire" | "Cathedral" | "Halo" | "Three-Stone" | "Bypass" | "Cluster",
  "setting_type": "Prong" | "Bezel" | "Tension" | "Channel" | "Flush" | "Pavé",
  "center_stone_cut": "Round" | "Cushion" | "Princess" | "Oval" | "Pear" | "Marquise" | "Emerald" | "Radiant" | "None",
  "halo": "Yes" | "No",
  "gallery": "Yes" | "No",
  "shank_style": "Pave" | "Plain" | "Split-Shank" | "Bypass" | "Tapered",
  "shoulders": "Pave" | "Plain" | "Cathedral",
  "prong_count": int,
  "symmetry": "Bilateral" | "Radial" | "Asymmetrical"
}

Provide your best estimate based on the visual details. Ensure your response is valid JSON only. Do not explain or write anything else."""


def extract_semantics(image_path: str) -> dict:
    """
    Extracts semantic ring design parameters from the input image.
    Uses the configured LLM provider or falls back to standard defaults.
    """
    default_semantics = {
        "ring_style": "Cathedral",
        "setting_type": "Prong",
        "center_stone_cut": "Round",
        "halo": "Yes",
        "gallery": "Yes",
        "shank_style": "Pave",
        "shoulders": "Pave",
        "prong_count": 4,
        "symmetry": "Bilateral"
    }

    if config.LLM_PROVIDER == "rule_based" or not image_path or not os.path.exists(image_path):
        logging.info("Using default/rule-based semantic parameters.")
        return default_semantics

    try:
        client = get_llm_client()
        logging.info(f"Querying semantic parameters via LLM provider: {config.LLM_PROVIDER}")
        response_text = client.query_vision(SEMANTIC_PROMPT, image_path)
        
        # Clean response text in case LLM wrapped it in markdown code block
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```"):
            # strip start ```json or ```
            first_newline = cleaned_text.find("\n")
            if first_newline != -1:
                cleaned_text = cleaned_text[first_newline:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

        parsed = json.loads(cleaned_text)
        logging.info("Successfully parsed semantic attributes from LLM.")
        
        # Ensure default keys exist
        for k, v in default_semantics.items():
            if k not in parsed:
                parsed[k] = v
        
        return parsed
    except Exception as e:
        logging.error(f"Failed to extract semantic parameters from LLM: {e}. Falling back to default parameters.")
        return default_semantics
