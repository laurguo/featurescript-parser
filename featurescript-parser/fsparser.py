import yaml
import json
import os
import glob
import sys
from joblib import Parallel, delayed
import datetime
import time
import multiprocessing

"""
Parses input FeatureScript files (yaml) into DeepCAD format which is based on Fusion360 (json)
"""

def build_profile_sketch_mappings(features):
    """
    Track the most recent sketch ID and extract profile mappings from sketches.
    Returns (current_sketch_id, {profile_id: sketch_id}).
    """
    current_sketch_id = None
    profile_mappings = {}
    
    for feat in features:
        msg = feat["message"]
        ftype = msg.get("featureType")
        if ftype == "newSketch" or ftype == "sketch":
            current_sketch_id = msg.get("featureId")
            
            # Extract profile IDs from this sketch
            if "entities" in msg:
                profile_counter = 0
                for entity in msg["entities"]:
                    eid = entity["message"].get("entityId")
                    geom = entity["message"].get("geometry", {})
                    if eid and geom:
                        geom_type = geom.get("typeName")
                        if geom_type in ["BTCurveGeometryCircle", "BTCurveGeometryLine"]:
                            profile_id = f"JG{chr(65 + profile_counter)}"  # Generate JG1, JG2, etc.
                            profile_mappings[profile_id] = current_sketch_id
                            profile_counter += 1
    
    return current_sketch_id, profile_mappings



def get_axis_point_and_direction(axis_param, sketch_id, features):
    """
    Given the axis parameter and the parent sketch_id, extract the axis point and direction from the referenced line entity.
    Returns (axis_point, axis_dir) as lists.
    """
    axis_geom_id = None
    for q in axis_param.get("queries", []):
        axis_ids = q["message"].get("geometryIds", [])
        if axis_ids:
            axis_geom_id = axis_ids[0]
            break
    if axis_geom_id and sketch_id:
        # Find the parent sketch feature
        for sketch_feat in features:
            sketch_msg = sketch_feat["message"]
            if sketch_msg.get("featureId") == sketch_id and "entities" in sketch_msg:
                for entity in sketch_msg["entities"]:
                    if entity["message"].get("entityId") == axis_geom_id:
                        geom = entity["message"].get("geometry", {})
                        if geom.get("typeName") == "BTCurveGeometryLine":
                            msg = geom["message"]
                            if "pntX" in msg and "pntY" in msg and "dirX" in msg and "dirY" in msg:
                                axis_point = [
                                    msg.get("pntX", 0.0),
                                    msg.get("pntY", 0.0),
                                    0.0
                                ]
                                axis_dir = [
                                    msg.get("dirX", 0.0),
                                    msg.get("dirY", 0.0),
                                    0.0
                                ]
                                return axis_point, axis_dir
    # Fallback to default if not found
    return [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]

def extract_line_profile(geom, profile_id):
    """Extract line profile with proper coordinate extraction logic"""
    # Try different possible paths for coordinates in the YAML structure
    start_point = {"x": 0.0, "y": 0.0, "z": 0.0}
    end_point = {"x": 0.0, "y": 0.0, "z": 0.0}
    
    # Check if coordinates are directly in geom["message"]
    if "message" in geom:
        msg = geom["message"]
        # FeatureScript uses pntX, pntY for start point and dirX, dirY for direction
        if "pntX" in msg and "pntY" in msg:
            start_point["x"] = msg.get("pntX", 0.0)
            start_point["y"] = msg.get("pntY", 0.0)
            
            # Calculate end point using direction vectors
            if "dirX" in msg and "dirY" in msg:
                dir_x = msg.get("dirX", 0.0)
                dir_y = msg.get("dirY", 0.0)
                end_point["x"] = start_point["x"] + dir_x
                end_point["y"] = start_point["y"] + dir_y
    
    # Check if coordinates are in a different path (common in FeatureScript YAML)
    if "startPoint" in geom:
        start_pt = geom["startPoint"]
        if "message" in start_pt:
            start_msg = start_pt["message"]
            start_point["x"] = start_msg.get("x", 0.0)
            start_point["y"] = start_msg.get("y", 0.0)
            start_point["z"] = start_msg.get("z", 0.0)
    
    if "endPoint" in geom:
        end_pt = geom["endPoint"]
        if "message" in end_pt:
            end_msg = end_pt["message"]
            end_point["x"] = end_msg.get("x", 0.0)
            end_point["y"] = end_msg.get("y", 0.0)
            end_point["z"] = end_msg.get("z", 0.0)
    
    return {
        "loops": [
            {
                "is_outer": True,
                "profile_curves": [
                    {
                        "type": "Line3D",
                        "start_point": start_point,
                        "end_point": end_point,
                        "curve": profile_id
                    }
                ]
            }
        ],
        "properties": {}
    }

def handle_sketch(msg):
    feat_dict = {
        "type": "Sketch",
        "name": msg.get("name", "Sketch"),
        "points": {},
        "curves": {},
        "constraints": {},
        "profiles": {},
        "transform": {
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
            "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
            "y_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
            "z_axis": {"x": 0.0, "y": 0.0, "z": 1.0}
        },
        "reference_plane": {}
    }
    profiles = {}
    profile_counter = 0
    
    if "entities" in msg:
        for entity in msg["entities"]:
            eid = entity["message"].get("entityId")
            geom = entity["message"].get("geometry", {})
            if eid and geom:
                geom_type = geom.get("typeName")
                profile_id = f"JG{chr(65 + profile_counter)}"
                
                if geom_type == "BTCurveGeometryCircle":
                    profiles[profile_id] = {
                        "loops": [
                            {
                                "is_outer": True,
                                "profile_curves": [
                                    {
                                        "type": "Circle3D",
                                        "center_point": {
                                            "x": geom["message"].get("xCenter", 0.0),
                                            "y": geom["message"].get("yCenter", 0.0),
                                            "z": 0.0
                                        },
                                        "radius": geom["message"].get("radius", 0.0),
                                        "curve": profile_id,
                                        "normal": {"x": 0.0, "y": 0.0, "z": 1.0}
                                    }
                                ]
                            }
                        ],
                        "properties": {}
                    }
                    profile_counter += 1
                    
                elif geom_type == "BTCurveGeometryLine":
                    profiles[profile_id] = extract_line_profile(geom, profile_id)
                    profile_counter += 1
    
    feat_dict["profiles"] = profiles
    return feat_dict

def handle_extrude(msg, current_sketch_id, sketch_profiles, features):
    feat_dict = {"type": "ExtrudeFeature", "name": msg.get("name", "Extrude")}
    
    # Use the current sketch ID directly
    if not current_sketch_id:
        return None
    
    # Build profiles array from sketch profiles
    profiles = []
    if current_sketch_id and sketch_profiles:
        for profile_id, sketch_id in sketch_profiles.items():
            if sketch_id == current_sketch_id:
                profiles.append({
                    "profile": profile_id,
                    "sketch": sketch_id
                })
    feat_dict["profiles"] = profiles
    
    depth_val = None
    for p in msg.get("parameters", []):
        if p["message"]["parameterId"] == "depth":
            if "expression" in p["message"]:
                depth_val = p["message"]["expression"]
            elif "value" in p["message"]:
                depth_val = p["message"]["value"]
    feat_dict["extent_one"] = {
        "distance": {
            "type": "ModelParameter",
            "role": "AlongDistance",
            "name": "none",
            "value": float(depth_val.split("*")[0]) if depth_val and "*" in str(depth_val) else depth_val if depth_val else 0.0
        },
        "type": "DistanceExtentDefinition",
        "taper_angle": {
            "type": "ModelParameter",
            "role": "TaperAngle",
            "name": "none",
            "value": 0.0
        }
    }
    feat_dict["extent_two"] = {
        "distance": {
            "type": "ModelParameter",
            "role": "AgainstDistance",
            "name": "none",
            "value": 0.0
        },
        "type": "DistanceExtentDefinition",
        "taper_angle": {
            "type": "ModelParameter",
            "role": "Side2TaperAngle",
            "name": "none",
            "value": 0.0
        }
    }
    op_val = None
    for p in msg.get("parameters", []):
        if p["message"]["parameterId"] == "operationType":
            op_val = p["message"].get("value")
    feat_dict["operation"] = "NewBodyFeatureOperation" if op_val == "NEW" else op_val
    feat_dict["start_extent"] = {"type": "ProfilePlaneStartDefinition"}
    feat_dict["extent_type"] = "OneSideFeatureExtentType"
    return feat_dict

def handle_revolve(msg, current_sketch_id, sketch_profiles, features):
    feat_dict = {"type": "RevolveFeature", "name": msg.get("name", "Revolve")}
    
    # Use the current sketch ID directly
    if not current_sketch_id:
        return None
    
    axis_point = [0.0, 0.0, 0.0]
    axis_dir = [0.0, 0.0, 1.0]
    body_type = None
    angle_one = 360.0
    angle_two = 0.0
    axis_param = None
    
    for p in msg.get("parameters", []):
        pid = p["message"]["parameterId"]
        pmsg = p["message"]
        if pid == "bodyType":
            body_type = pmsg.get("value")
        elif pid == "axis":
            axis_param = pmsg
        elif pid == "angleOne":
            if "expression" in pmsg:
                try:
                    angle_one = float(pmsg["expression"].replace("*degree", ""))
                except:
                    angle_one = 360.0
            elif "value" in pmsg:
                angle_one = pmsg["value"]
        elif pid == "angleTwo":
            if "expression" in pmsg:
                try:
                    angle_two = float(pmsg["expression"].replace("*degree", ""))
                except:
                    angle_two = 0.0
            elif "value" in pmsg:
                angle_two = pmsg["value"]
    
    if axis_param is not None:
        axis_point, axis_dir = get_axis_point_and_direction(axis_param, current_sketch_id, features)
    
    # Build profiles array from sketch profiles
    profiles = []
    if current_sketch_id and sketch_profiles:
        for profile_id, sketch_id in sketch_profiles.items():
            if sketch_id == current_sketch_id:
                profiles.append({
                    "profile": profile_id,
                    "sketch": sketch_id
                })
    feat_dict["profiles"] = profiles
    
    feat_dict["sketch_id"] = current_sketch_id
    feat_dict["parameters"] = {
        "bodyType": body_type,
        "axis": {
            "point": axis_point,
            "direction": axis_dir
        },
        "angleOne": angle_one,
        "angleTwo": angle_two
    }
    return feat_dict

def process_yaml_file(yaml_file_path):
    """Process a single YAML file and return its DeepCAD representation"""
    try:
        with open(yaml_file_path, "r") as f:
            data = yaml.safe_load(f)
        
        features = data.get("features", [])
        if not features:
            return None
        
        # Check for unsupported features during processing
        supported_types = {"sketch", "newSketch", "extrude", "revolve"}
        
        for feat in features:
            msg = feat.get("message")
            if not msg:
                continue
                
            ftype = msg.get("featureType")
            if ftype and ftype not in supported_types:
                print(f"Skipping {yaml_file_path}: contains unsupported feature: {ftype}")
                return None
        
        # Build profile to sketch mappings based on YAML order
        current_sketch_id, sketch_profiles = build_profile_sketch_mappings(features)
        
        output = {"entities": {}, "properties": {}, "sequence": []}
        idx = 0
        
        for feat in features:
            msg = feat["message"]
            ftype = msg.get("featureType")
            if ftype in {"sketch", "newSketch", "extrude", "revolve"}:
                feat_id = msg.get("featureId")
                if ftype == "sketch" or ftype == "newSketch":
                    feat_dict = handle_sketch(msg)
                elif ftype == "extrude":
                    feat_dict = handle_extrude(msg, current_sketch_id, sketch_profiles, features)
                elif ftype == "revolve":
                    feat_dict = handle_revolve(msg, current_sketch_id, sketch_profiles, features)
                else:
                    continue
                
                if feat_dict:
                    output["entities"][feat_id] = feat_dict
                    seq_entry = {"index": idx,
                               "type": feat_dict.get("type", ftype),
                               "entity": feat_id}
                    output["sequence"].append(seq_entry)
                    idx += 1
        
        if not output["entities"]:
            return None
        
        # Create organized output path
        base_name = os.path.splitext(os.path.basename(yaml_file_path))[0]
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file_path = os.path.join(output_dir, f"{base_name}.json")
        
        # Write output
        with open(output_file_path, "w") as f:
            json.dump(output, f, indent=2)
        
        return output_file_path
    except Exception as e:
        print(f"Error processing {yaml_file_path}: {e}")
        return None

def create_manifest(output_files, manifest_path="output/manifest.json"):
    """Create a manifest file listing all successfully processed files"""
    manifest = {
        "total_processed": len(output_files),
        "files": output_files,
        "timestamp": str(datetime.datetime.now()),
        "format": "DeepCAD/Fusion360"
    }
    
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    return manifest_path

def process_with_progress(yaml_files, batch_size=100):
    """Process files with progress tracking"""
    total_files = len(yaml_files)
    successful_outputs = []
    
    # Optimize number of jobs based on system
    n_jobs = min(multiprocessing.cpu_count(), 8)  # Cap at 8 to avoid memory issues
    
    print(f"Processing {total_files} files in batches of {batch_size}...")
    print(f"Using {n_jobs} parallel workers")
    
    start_time = time.time()
    
    for i in range(0, total_files, batch_size):
        batch = yaml_files[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total_files + batch_size - 1) // batch_size
        
        batch_start_time = time.time()
        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} files)")
        
        # Process batch in parallel
        results = Parallel(n_jobs=n_jobs, verbose=0, backend='loky')(delayed(process_yaml_file)(f) for f in batch)
        
        # Filter successful results
        batch_successful = [r for r in results if r is not None]
        successful_outputs.extend(batch_successful)
        
        # Progress update
        processed_so_far = i + len(batch)
        success_rate = len(successful_outputs) / processed_so_far * 100 if processed_so_far > 0 else 0
        batch_time = time.time() - batch_start_time
        files_per_second = len(batch) / batch_time if batch_time > 0 else 0
        
        print(f"  ✓ Processed: {processed_so_far}/{total_files} ({processed_so_far/total_files*100:.1f}%)")
        print(f"  ✓ Successful: {len(successful_outputs)} ({success_rate:.1f}% success rate)")
        print(f"  ⏱️  Batch time: {batch_time:.1f}s ({files_per_second:.1f} files/sec)")
    
    total_time = time.time() - start_time
    overall_files_per_second = total_files / total_time if total_time > 0 else 0
    
    print(f"\n⏱️  Total processing time: {total_time:.1f}s ({overall_files_per_second:.1f} files/sec)")
    
    return successful_outputs

def main():
    # Get directory path from command line argument or use current directory
    if len(sys.argv) > 1:
        directory_path = sys.argv[1]
        if not os.path.isdir(directory_path):
            print(f"Error: {directory_path} is not a valid directory.")
            return
    else:
        directory_path = "."
    
    # Get all YAML files in the directory (recursively)
    yaml_pattern = os.path.join(directory_path, "**", "*.yml")
    yaml_files = glob.glob(yaml_pattern, recursive=True)
    
    if not yaml_files:
        print(f"No YAML files found in {directory_path}.")
        return
    
    print(f"Found {len(yaml_files)} YAML files to process.")
    
    # Process files in parallel
    successful_outputs = process_with_progress(yaml_files)
    
    # Create manifest file
    manifest_path = create_manifest(successful_outputs)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"PROCESSING SUMMARY")
    print(f"{'='*50}")
    print(f"Total files found: {len(yaml_files)}")
    print(f"Successfully processed: {len(successful_outputs)}")
    print(f"Failed/Skipped: {len(yaml_files) - len(successful_outputs)}")
    print(f"Success rate: {len(successful_outputs)/len(yaml_files)*100:.1f}%")
    print(f"Output directory: output/")
    print(f"Manifest file: {manifest_path}")
    
    if successful_outputs:
        print(f"\nSuccessfully processed files:")
        for output_file in successful_outputs[:10]:  # Show first 10
            print(f"  - {os.path.basename(output_file)}")
        if len(successful_outputs) > 10:
            print(f"  ... and {len(successful_outputs) - 10} more")
    else:
        print("No files were successfully processed.")

if __name__ == "__main__":
    main()
