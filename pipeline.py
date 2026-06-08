import argparse
import json
import logging
import os
import sys

import config
from coco_parser import parse_geometry
from semantic_extractor import extract_semantics
from context_builder import build_context
from llm_planner import plan_tool_calls
from execution_engine import execute_cad_plan
from validator import validate_projection

os.makedirs(config.OUTPUT_DIR, exist_ok=True)
log_file_path = os.path.join(config.OUTPUT_DIR, "pipeline_execution.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_pipeline(image_path: str, coco_path: str) -> bool:
    """Runs the complete ring generation pipeline with iterative refinement."""
    logging.info("=========================================")
    logging.info("Starting Ring Generation CAD Pipeline")
    logging.info(f"Image Path: {image_path}")
    logging.info(f"COCO File Path: {coco_path}")
    logging.info(f"Configured Top Image ID: {config.TOP_IMAGE_ID}")
    logging.info(f"Configured Side Image ID: {config.SIDE_IMAGE_ID}")
    logging.info("=========================================")

    # Step 1: Geometry Extraction
    logging.info("[Step 1/5] Extracting geometry from COCO annotations...")
    try:
        geometry = parse_geometry(coco_path)
    except Exception as e:
        logging.critical(f"Failed to parse COCO geometry: {e}")
        return False

    # Step 2: Semantic Attribute Extraction
    logging.info("[Step 2/5] Extracting semantic style parameters from image...")
    try:
        semantics = extract_semantics(image_path)
        logging.info(f"Extracted Semantics: {json.dumps(semantics, indent=2)}")
    except Exception as e:
        logging.error(f"Failed to extract semantics: {e}. Using default style.")
        semantics = {}

    # Step 3: Context Builder
    logging.info("[Step 3/5] Building unified context and structural constraints...")
    try:
        context = build_context(geometry, semantics)
    except Exception as e:
        logging.critical(f"Failed to build design context: {e}")
        return False

    # Save initial design context
    with open(os.path.join(config.OUTPUT_DIR, "initial_context.json"), 'w') as f:
        json.dump(context, f, indent=2)

    # Step 4: Iterative Planning, Execution, and Validation Loop (Refinement)
    logging.info("[Step 4/5] Entering CAD Execution & Projection Refinement Loop...")
    
    iteration = 0
    success = False
    final_plan = []
    
    while iteration < config.REFINEMENT_MAX_ITERATIONS:
        iteration += 1
        logging.info(f"--- Refinement Loop Iteration {iteration}/{config.REFINEMENT_MAX_ITERATIONS} ---")

        # 4A: Planning
        logging.info("Step 4A: Generating tool call plan...")
        try:
            plan = plan_tool_calls(context)
            final_plan = plan
            logging.info(f"Plan steps count: {len(plan)}")
            logging.info(f"Plan details:\n{json.dumps(plan, indent=2)}")
        except Exception as e:
            logging.error(f"Planning failed on iteration {iteration}: {e}")
            break

        # 4B: Execution
        logging.info("Step 4B: Compiling 3D CAD model inside FreeCAD...")
        try:
            cad_stats = execute_cad_plan(plan, output_name="ring")
            if not cad_stats:
                raise RuntimeError("FreeCAD executed but returned empty bounding box stats.")
        except Exception as e:
            logging.error(f"FreeCAD CAD execution failed: {e}")
            break

        # 4C: Validation
        logging.info("Step 4C: Validating projected model geometry against COCO dimensions...")
        try:
            report = validate_projection(geometry, cad_stats, context)
        except Exception as e:
            logging.error(f"Projection validation failed: {e}")
            break

        # Check if validation succeeded
        if report["is_valid"]:
            logging.info(f"Validation succeeded on iteration {iteration}! Bounding boxes aligned within thresholds.")
            success = True
            break
        
        # 4D: Refinement (Apply adjustments)
        adjustments = report.get("adjustments", {})
        if not adjustments:
            logging.warning("Validation failed but no adjustment recommendations were generated. Stopping loop.")
            break
            
        logging.info(f"Validation failed. Applying corrective adjustments: {json.dumps(adjustments, indent=2)}")
        
        # Apply adjustments to hierarchical context dictionary
        for section, components in adjustments.items():  # 'shank' or 'head'
            if section in context:
                for component, params in components.items():
                    if component in context[section]:
                        for param, offset in params.items():
                            if param in context[section][component]:
                                old_val = context[section][component][param]
                                context[section][component][param] = old_val + offset
                                logging.info(f"Adjusted context.{section}.{component}.{param}: {old_val:.4f} -> {context[section][component][param]:.4f}")
                        
        # Save adjusted context
        with open(os.path.join(config.OUTPUT_DIR, f"context_iteration_{iteration}.json"), 'w') as f:
            json.dump(context, f, indent=2)

    # Step 5: Wrap Up and Output
    logging.info("[Step 5/5] Finalizing pipeline outputs...")
    
    # Save final plan and context
    with open(os.path.join(config.OUTPUT_DIR, "final_context.json"), 'w') as f:
        json.dump(context, f, indent=2)
    with open(os.path.join(config.OUTPUT_DIR, "final_plan.json"), 'w') as f:
        json.dump(final_plan, f, indent=2)

    if success:
        logging.info("=========================================")
        logging.info("Pipeline executed SUCCESSFULLY!")
        logging.info(f"Manufacturable 3D Model:  {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'ring.stl'))}")
        logging.info(f"Metal 3D Model (separate): {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'ring_metal.stl'))}")
        logging.info(f"Gems 3D Model (separate):  {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'ring_gems.stl'))}")
        logging.info(f"FreeCAD Source File:      {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'ring.FCstd'))}")
        logging.info(f"Execution Log File:       {os.path.abspath(log_file_path)}")
        logging.info(f"Validation Report:        {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'validation_report.json'))}")
        logging.info("=========================================")
        return True
    else:
        logging.warning("=========================================")
        logging.warning("Pipeline completed but failed validation thresholds.")
        logging.warning(f"FreeCAD Source File (Partial): {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'ring.FCstd'))}")
        logging.warning(f"Review the validation report at: {os.path.abspath(os.path.join(config.OUTPUT_DIR, 'validation_report.json'))}")
        logging.warning("=========================================")
        return False


def main():
    default_image = os.path.join(config.INPUT_DIR, "ring.png")
    # Fallback checks for common image extensions
    if not os.path.exists(default_image):
        for ext in [".jpg", ".jpeg", ".webp"]:
            fallback = os.path.join(config.INPUT_DIR, f"ring{ext}")
            if os.path.exists(fallback):
                default_image = fallback
                break

    parser = argparse.ArgumentParser(description="Iterative Ring Generation Pipeline (COCO to 3D CAD)")
    parser.add_argument(
        "--image", 
        default=default_image,
        help="Path to the input ring design image"
    )
    parser.add_argument(
        "--coco", 
        default=config.COCO_FILE,
        help="Path to the single COCO annotation JSON file containing top and side view images"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image) or not os.path.exists(args.coco):
        print(f"Error: Input files missing. Please ensure they exist:\n- {args.image}\n- {args.coco}")
        print("You can run 'python generate_sample_inputs.py' to generate dummy input files for testing.")
        sys.exit(1)

    result = run_pipeline(args.image, args.coco)
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()
