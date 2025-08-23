# FeatureScript Parser

A Python tool to convert Onshape FeatureScript model files into a standardized JSON format compatible with the [Fusion360GalleryDataset reconstruction format](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/reconstruction.md).

## Overview

This project extracts the construction sequence and geometric information from FeatureScript YAML files and outputs each model as a JSON file in the target format. The parser is designed for CAD model reconstruction and machine learning research applications.

## Features

- **Parse** Onshape FeatureScript YAML files
- **Extract** construction sequences, feature parameters, sketches, and geometry
- **Convert** to DeepCAD JSON format for reconstruction pipelines
- **Output** machine-readable JSON files ready for analysis or training

## Quick Start

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Installation

**Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Basic Usage

1. Place your FeatureScript YAML files in the working directory
2. Run `fsparser.py` to process the files
3. The script outputs a JSON file for each model in the target format

## Output Format

The parser generates JSON files following the DeepCAD reconstruction format:

```json
{
  "entities": {
    "<entity_id>": { ... }
  },
  "properties": { ... },
  "sequence": [
    { "index": 0, "type": "<FeatureType>", "entity": "<entity_id>" }
  ]
}
```

- **entities**: Dictionary mapping IDs to all model objects (sketches, features, geometry)
- **properties**: Global model properties (bounding box, metadata)
- **sequence**: Ordered list of construction steps

## Dependencies

The project requires the following Python packages (see `requirements.txt`):

- `pyyaml` - YAML file parsing
- `json` - JSON output (built-in)
- Additional dependencies as needed for your specific use case

## Next Steps

1. **Customize the parser** for your specific output file format
2. **Extend entity mapping** to support additional Onshape features. Only sketch, extrude, and revolve are currently supported
3. **Add validation** to ensure output JSON meets expected requirements. Currently there is no compatible visualizer to easily validate the output files
4. **Integrate** with your CAD reconstruction pipeline

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

- [Fusion360GalleryDataset Reconstruction Format](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/reconstruction.md)
- [Onshape FeatureScript Documentation](https://onshape.com/featurescript)
- [DeepCAD Dataset](https://github.com/ChrisWu1997/DeepCAD/)