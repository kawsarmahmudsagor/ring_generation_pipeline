import base64
import json
import logging
import requests
from PIL import Image
from io import BytesIO
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class LLMClient:
    """Base class for LLM client providers."""
    def query_vision(self, prompt: str, image_path: str) -> str:
        """Sends a query containing a prompt and an image, returning the string response."""
        raise NotImplementedError

    def query_text(self, prompt: str) -> str:
        """Sends a text-only query, returning the string response."""
        raise NotImplementedError


class OllamaClient(LLMClient):
    """Client for querying local Ollama instance."""
    def __init__(self, host: str, model: str):
        self.host = host.rstrip('/')
        self.model = model
        logging.info(f"OllamaClient initialized with host: {self.host}, model: {self.model}")

    def _get_image_base64(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logging.error(f"Error encoding image to base64: {e}")
            raise

    def query_vision(self, prompt: str, image_path: str) -> str:
        url = f"{self.host}/api/generate"
        try:
            img_b64 = self._get_image_base64(image_path)
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "format": "json"
            }
            logging.info(f"Sending vision request to Ollama: {self.model}")
            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logging.error(f"Ollama vision request failed: {e}. Ensure Ollama is running and '{self.model}' is pulled.")
            # Graceful fallback to rule-based mock
            return self._mock_fallback(prompt)

    def query_text(self, prompt: str) -> str:
        url = f"{self.host}/api/generate"
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
            logging.info(f"Sending text request to Ollama: {self.model}")
            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logging.error(f"Ollama text request failed: {e}. Ensure Ollama is running.")
            return self._mock_fallback(prompt)

    def _mock_fallback(self, prompt: str) -> str:
        logging.warning("Using mock LLM response fallback due to Ollama connection error.")
        if "semantic" in prompt.lower() or "style" in prompt.lower():
            return json.dumps({
                "ring_style": "Cathedral",
                "setting_type": "Prong",
                "center_stone_cut": "Round",
                "halo": "Yes",
                "gallery": "Yes",
                "shank_style": "Pave",
                "shoulders": "Pave",
                "prong_count": 4,
                "symmetry": "Bilateral"
            })
        else:
            # Planner prompt fallback
            return json.dumps([
                {"tool": "create_band", "params": {"inner_radius": 8.5, "width": 2.5, "thickness": 1.8, "profile_type": "court"}},
                {"tool": "create_gallery", "params": {"style": "cathedral", "width": 6.5, "height": 4.5, "z_offset": 8.5}},
                {"tool": "create_center_stone", "params": {"cut": "round", "width": 6.0, "height": 3.8, "z_offset": 12.0}},
                {"tool": "create_prongs", "params": {"count": 4, "radius": 0.4, "height": 3.0, "z_offset": 11.5}},
                {"tool": "create_halo", "params": {"stone_count": 16, "stone_size": 1.2, "radial_distance": 4.2, "z_offset": 11.8}}
            ])


class GeminiClient(LLMClient):
    """Client for querying Google Gemini API."""
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model_name = model
        self.initialized = False
        if not api_key:
            logging.warning("GEMINI_API_KEY is not set. Gemini API calls will fallback to mock replies unless configured.")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model)
            self.initialized = True
            logging.info(f"GeminiClient initialized with model: {self.model_name}")
        except Exception as e:
            logging.error(f"Failed to initialize Gemini SDK: {e}")

    def query_vision(self, prompt: str, image_path: str) -> str:
        if not self.initialized:
            logging.error("Gemini SDK not initialized.")
            return self._mock_fallback(prompt)
        try:
            img = Image.open(image_path)
            logging.info(f"Sending vision request to Gemini: {self.model_name}")
            response = self.model.generate_content(
                [prompt, img],
                generation_config={"response_mime_type": "application/json"}
            )
            return response.text
        except Exception as e:
            logging.error(f"Gemini vision query failed: {e}")
            return self._mock_fallback(prompt)

    def query_text(self, prompt: str) -> str:
        if not self.initialized:
            logging.error("Gemini SDK not initialized.")
            return self._mock_fallback(prompt)
        try:
            logging.info(f"Sending text request to Gemini: {self.model_name}")
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return response.text
        except Exception as e:
            logging.error(f"Gemini text query failed: {e}")
            return self._mock_fallback(prompt)

    def _mock_fallback(self, prompt: str) -> str:
        logging.warning("Using mock LLM response fallback due to Gemini SDK/key configuration issues.")
        if "semantic" in prompt.lower() or "style" in prompt.lower():
            return json.dumps({
                "ring_style": "Cathedral",
                "setting_type": "Prong",
                "center_stone_cut": "Round",
                "halo": "Yes",
                "gallery": "Yes",
                "shank_style": "Pave",
                "shoulders": "Pave",
                "prong_count": 4,
                "symmetry": "Bilateral"
            })
        else:
            return json.dumps([
                {"tool": "create_band", "params": {"inner_radius": 8.5, "width": 2.5, "thickness": 1.8, "profile_type": "court"}},
                {"tool": "create_gallery", "params": {"style": "cathedral", "width": 6.5, "height": 4.5, "z_offset": 8.5}},
                {"tool": "create_center_stone", "params": {"cut": "round", "width": 6.0, "height": 3.8, "z_offset": 12.0}},
                {"tool": "create_prongs", "params": {"count": 4, "radius": 0.4, "height": 3.0, "z_offset": 11.5}},
                {"tool": "create_halo", "params": {"stone_count": 16, "stone_size": 1.2, "radial_distance": 4.2, "z_offset": 11.8}}
            ])


def get_llm_client() -> LLMClient:
    """Factory function returning the configured LLMClient based on config.py."""
    if config.LLM_PROVIDER.lower() == "gemini":
        return GeminiClient(config.GEMINI_API_KEY, config.GEMINI_MODEL)
    elif config.LLM_PROVIDER.lower() == "ollama":
        return OllamaClient(config.OLLAMA_HOST, config.OLLAMA_MODEL)
    else:
        # Fallback dummy class that returns mock data
        class RuleBasedClient(LLMClient):
            def query_vision(self, prompt: str, image_path: str) -> str:
                return self._mock_fallback(prompt)
            def query_text(self, prompt: str) -> str:
                return self._mock_fallback(prompt)
            def _mock_fallback(self, prompt: str) -> str:
                if "semantic" in prompt.lower() or "style" in prompt.lower():
                    return json.dumps({
                        "ring_style": "Cathedral",
                        "setting_type": "Prong",
                        "center_stone_cut": "Round",
                        "halo": "Yes",
                        "gallery": "Yes",
                        "shank_style": "Pave",
                        "shoulders": "Pave",
                        "prong_count": 4,
                        "symmetry": "Bilateral"
                    })
                else:
                    return json.dumps([])
        return RuleBasedClient()
