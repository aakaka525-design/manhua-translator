#!/bin/bash
# Clean up debug/temporary files from output directory
# Usage: ./scripts/clean_output.sh

OUTPUT_DIR="$(dirname "$0")/../output"

echo "Cleaning debug files from output directory..."

# Remove debug files (patterns that are not from Pipeline)
rm -f "$OUTPUT_DIR"/debug_*.png
rm -f "$OUTPUT_DIR"/ocr_*.jpg
rm -f "$OUTPUT_DIR"/final_*.png
rm -f "$OUTPUT_DIR"/*_inpainted.png

# Keep translated_*.png files (Pipeline output)

echo "Done. Remaining files:"
ls -la "$OUTPUT_DIR"
