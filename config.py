import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# FreeCAD Path Configuration
# We run CAD generation in FreeCAD's built-in Python interpreter to avoid version conflicts.
FREECAD_PYTHON = r"C:\Program Files\FreeCAD 1.1\bin\python.exe"

# LLM Configuration
# Options: "ollama", "gemini", "rule_based"
LLM_PROVIDER = "ollama"

# Ollama Settings
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:31b-cloud"  # default vision-language model for Ollama

# Gemini Settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# Single COCO Annotation Configuration
COCO_FILE = os.path.join("inputs", "annotations.coco.json")
TOP_IMAGE_ID = 2
SIDE_IMAGE_ID = 0

# Directories
INPUT_DIR = "inputs"
OUTPUT_DIR = "outputs"

# Create directories if they do not exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Validation Parameters
VALIDATION_IOU_THRESHOLD = 0.85
VALIDATION_MAX_ERROR_MM = 0.5
REFINEMENT_MAX_ITERATIONS = 10

# Default geometric settings
DEFAULT_INNER_DIAMETER_MM = 17.0  # standard ring size (~6.5 US)
DEFAULT_BAND_WIDTH_MM = 2.5
DEFAULT_BAND_THICKNESS_MM = 1.8
