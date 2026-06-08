import json
import logging
import os
import subprocess
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def execute_cad_plan(plan: list, output_name: str = "ring") -> dict:
    """
    Executes the planned CAD tool calls inside FreeCAD.
    Writes the plan to a temp JSON file, runs freecad_toolkit.py in a subprocess,
    and returns the bounding box stats of the generated shapes.
    """
    # 1. Prepare file paths
    temp_plan_path = os.path.join(config.OUTPUT_DIR, "temp_plan.json")
    output_prefix = os.path.join(config.OUTPUT_DIR, output_name)
    stats_path = f"{output_prefix}_stats.json"

    # Ensure output directory exists
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # 2. Write plan to JSON
    try:
        with open(temp_plan_path, 'w') as f:
            json.dump(plan, f, indent=2)
        logging.info(f"Wrote temporary plan parameters to {temp_plan_path}")
    except Exception as e:
        logging.error(f"Failed to write temporary plan file: {e}")
        return {}

    # 3. Formulate subcommand
    # Run the script using FreeCAD's built-in python.exe
    freecad_python = config.FREECAD_PYTHON
    toolkit_script = "freecad_toolkit.py"
    
    if not os.path.exists(freecad_python):
        logging.error(f"FreeCAD Python interpreter not found at: {freecad_python}. Please check config.py.")
        raise FileNotFoundError(f"FreeCAD Python interpreter not found at {freecad_python}")

    # We omit passing the JSON path on the command line to prevent freecadcmd.exe
    # from trying to import the JSON file as a CAD mesh.
    # freecad_toolkit.py defaults to reading "outputs/temp_plan.json".
    cmd = [freecad_python, toolkit_script]
    
    logging.info(f"Executing command: {' '.join(cmd)}")

    # 4. Invoke subprocess
    try:
        # We run the command with cwd set to the project root directory
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120  # fail-safe timeout
        )
        
        # Log outputs
        if process.stdout:
            logging.info("--- FreeCAD Stdout ---")
            for line in process.stdout.splitlines():
                logging.info(f"FreeCAD: {line}")
        if process.stderr:
            logging.warning("--- FreeCAD Stderr ---")
            for line in process.stderr.splitlines():
                logging.warning(f"FreeCAD-Err: {line}")

        if process.returncode != 0:
            logging.error(f"FreeCAD process exited with error code {process.returncode}")
            raise RuntimeError(f"FreeCAD execution failed: {process.stderr}")

    except subprocess.TimeoutExpired:
        logging.error("FreeCAD subprocess execution timed out (exceeded 120s).")
        raise
    except Exception as e:
        logging.error(f"Subprocess execution error: {e}")
        raise
    finally:
        # Clean up temp file
        if os.path.exists(temp_plan_path):
            try:
                os.remove(temp_plan_path)
            except Exception as e:
                logging.warning(f"Failed to remove temp file {temp_plan_path}: {e}")

    # 5. Read and return the output stats (containing physical bounding boxes in mm)
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r') as f:
                stats = json.load(f)
            logging.info("Successfully loaded generated model bounding box stats.")
            return stats
        except Exception as e:
            logging.error(f"Failed to read output stats JSON {stats_path}: {e}")
            return {}
    else:
        logging.error(f"Stats file was not generated at {stats_path}")
        return {}
