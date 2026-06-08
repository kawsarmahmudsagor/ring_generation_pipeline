# Parametric Ring Generation Pipeline (COCO to 3D CAD)

This project implements an automated, visual-to-3D CAD pipeline for jewelry design. It ingests a 2D ring image and its corresponding COCO annotations (containing top and side views), extracts physical geometry and style semantics, compiles a parametric CAD construction plan, executes the plan inside FreeCAD 1.1, and validates the output 3D geometry against the input annotations using 2D projection overlap analysis.

---

## Architecture Flow
The pipeline runs the following stages:
1. **INPUT**: A design image and a single COCO JSON file with two images (top view and side view).
2. **GEOMETRY EXTRACTION (`coco_parser.py`)**: Reads the COCO annotations, identifies the ring shank and the center opening (`Void` / finger hole) to compute scale factors, and converts all component bounding boxes into millimeter dimensions.
3. **SEMANTIC EXTRACTION (`semantic_extractor.py`)**: Uses the configured LLM provider to extract high-level visual styling cues (ring setting type, gemstone cut, halo existence, shank pave details).
4. **CONTEXT COMPILATION (`context_builder.py`)**: Integrates physical measurements and styles, applying jewelry engineering constraints (e.g. prong heights to clamp stone depth, gallery height to seat girdle).
5. **PLANNING (`llm_planner.py`)**: Maps the hierarchical design context into a list of CAD tool calls (e.g., `create_band`, `create_center_stone`, `create_prongs`, `create_bridge`, `create_side_stones`).
6. **CAD EXECUTION (`execution_engine.py` & `freecad_toolkit.py`)**: Subprocesses FreeCAD 1.1's Python interpreter to construct parametric solid shapes and export to STL.
7. **PROJECTION VALIDATION (`validator.py`)**: Projects 3D bounds back to 2D pixel bounding boxes, computes Intersection over Union (IoU) and dimension errors.
8. **REFINEMENT LOOP (`pipeline.py`)**: If projection errors exceed tolerances, computes parameter offsets, updates the context, and recompiles the CAD geometry until it converges.

---

## Installation & Setup

### Prerequisites
1. **Python 3.14+** (for host orchestrator scripts)
2. **FreeCAD 1.1** (installed at `C:\Program Files\FreeCAD 1.1` on Windows)

### Installing Python Dependencies
Run the following command to install the required Python libraries for the orchestrator:
```bash
python -m pip install -r requirements.txt
```

---

## Configuration (`config.py`)
Open `config.py` to customize the pipeline:

### LLM Provider Selection
You can toggle between local Ollama models, Google's Gemini API, or deterministic rules:
```python
LLM_PROVIDER = "ollama"  # "ollama", "gemini", or "rule_based"
```

* **Ollama (Default)**: Requires a local Ollama instance running a vision-capable model (like `llava` or `llama3.2-vision`):
  ```python
  OLLAMA_HOST = "http://localhost:11434"
  OLLAMA_MODEL = "llava"
  ```
* **Gemini API**: Requires configuring your Google API key:
  ```python
  GEMINI_API_KEY = "AIzaSy..."
  GEMINI_MODEL = "gemini-2.5-flash"
  ```
* **Rule-Based**: Runs deterministically without any LLM network/local dependencies, using geometric rules for semantic defaults and tool compilation (highly recommended for rapid testing).

---

## How to Run & Verify

### Step 1: Generate Mock Inputs
To verify that the pipeline and FreeCAD integration work out-of-the-box, run the utility script. It will generate a placeholder image and a COCO annotation file containing top (`image_id = 2`) and side (`image_id = 0`) annotations:
```bash
python generate_sample_inputs.py
```
This creates:
- `inputs/ring.png` (a simple draw pattern)
- `inputs/annotations.coco.json` (containing custom categories like `Void`, `band`, `center_stone`, `Prong`, `gallery`, `halo`, `bridge`, `side_stones`).

### Step 2: Run the Main Pipeline
Execute the orchestrator:
```bash
python pipeline.py
```

You can customize the input file locations using arguments:
```bash
python pipeline.py --image inputs/ring.png --coco inputs/annotations.coco.json
```

---

## Outputs & Reports
When the pipeline executes, it writes all logs and shapes to the `outputs/` folder:
- **`ring.stl`**: The final combined 3D model (metal + gems).
- **`ring_metal.stl`**: The manufacturable 3D model containing only metal parts (band, prongs, gallery, bridge, halo base).
- **`ring_gems.stl`**: The 3D model containing gemstones (center stone, halo accents, shoulder pave).
- **`ring.FCstd`**: The native FreeCAD project file. Open this in FreeCAD Gui to inspect parametric history and parts!
- **`pipeline_execution.log`**: Detailed traceback of the orchestration and refinement iterations.
- **`validation_report.json`**: Score report containing projected IoUs and mm error bounds.
