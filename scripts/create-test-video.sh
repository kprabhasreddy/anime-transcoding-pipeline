#!/bin/bash
# Create test video clip for pipeline testing
# ============================================
# This script creates a short test video using FFmpeg
# for use in integration and end-to-end tests.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
OUTPUT_DIR="${1:-./test-fixtures}"
DURATION="${2:-5}"  # seconds
RESOLUTION="${3:-1920x1080}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test Video Generator${NC}"
echo -e "${GREEN}========================================${NC}"

# Check for FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: FFmpeg is not installed${NC}"
    echo "Please install FFmpeg:"
    echo "  macOS: brew install ffmpeg"
    echo "  Ubuntu: sudo apt-get install ffmpeg"
    exit 1
fi

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Parse resolution
WIDTH=$(echo "${RESOLUTION}" | cut -d'x' -f1)
HEIGHT=$(echo "${RESOLUTION}" | cut -d'x' -f2)

echo -e "\n${YELLOW}Generating test video...${NC}"
echo "  Duration: ${DURATION} seconds"
echo "  Resolution: ${WIDTH}x${HEIGHT}"
echo "  Output: ${OUTPUT_DIR}/"

# -----------------------------------------------------------------------------
# Generate Test Pattern Video
# -----------------------------------------------------------------------------

# Create a test pattern video with audio
# This creates a professional-looking test card similar to broadcast standards
ffmpeg -y \
    -f lavfi -i "testsrc2=duration=${DURATION}:size=${WIDTH}x${HEIGHT}:rate=24000/1001" \
    -f lavfi -i "sine=frequency=1000:duration=${DURATION}" \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -profile:v high \
    -level 4.2 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 192k \
    -ar 48000 \
    -ac 2 \
    -movflags +faststart \
    "${OUTPUT_DIR}/test-pattern-${WIDTH}x${HEIGHT}.mp4" \
    2>/dev/null

echo -e "${GREEN}  Created: test-pattern-${WIDTH}x${HEIGHT}.mp4${NC}"

# -----------------------------------------------------------------------------
# Generate Color Bars Video (Alternative)
# -----------------------------------------------------------------------------

ffmpeg -y \
    -f lavfi -i "smptebars=duration=${DURATION}:size=${WIDTH}x${HEIGHT}:rate=24000/1001" \
    -f lavfi -i "sine=frequency=440:duration=${DURATION}" \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -profile:v high \
    -level 4.2 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 192k \
    -ar 48000 \
    -ac 2 \
    -movflags +faststart \
    "${OUTPUT_DIR}/color-bars-${WIDTH}x${HEIGHT}.mp4" \
    2>/dev/null

echo -e "${GREEN}  Created: color-bars-${WIDTH}x${HEIGHT}.mp4${NC}"

# -----------------------------------------------------------------------------
# Generate Anime-style Test Video
# -----------------------------------------------------------------------------

# Create a stylized video with anime-like aesthetics
# Uses gradient background with animated text overlay
ffmpeg -y \
    -f lavfi -i "
        gradients=duration=${DURATION}:size=${WIDTH}x${HEIGHT}:rate=24000/1001:
        c0=#FF6B9D:c1=#4A90D9:x0=0:y0=0:x1=${WIDTH}:y1=${HEIGHT}:speed=0.5,
        drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:
        text='ANIME TRANSCODING TEST':
        fontcolor=white:fontsize=72:
        x=(w-text_w)/2:y=(h-text_h)/2:
        shadowcolor=black:shadowx=3:shadowy=3
    " \
    -f lavfi -i "sine=frequency=880:duration=${DURATION}" \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -profile:v high \
    -level 4.2 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 192k \
    -ar 48000 \
    -ac 2 \
    -movflags +faststart \
    "${OUTPUT_DIR}/anime-test-${WIDTH}x${HEIGHT}.mp4" \
    2>/dev/null || {
        # Fallback without text (for systems without Arial font)
        ffmpeg -y \
            -f lavfi -i "gradients=duration=${DURATION}:size=${WIDTH}x${HEIGHT}:rate=24000/1001:c0=#FF6B9D:c1=#4A90D9:speed=0.5" \
            -f lavfi -i "sine=frequency=880:duration=${DURATION}" \
            -c:v libx264 \
            -preset medium \
            -crf 18 \
            -profile:v high \
            -level 4.2 \
            -pix_fmt yuv420p \
            -c:a aac \
            -b:a 192k \
            -ar 48000 \
            -ac 2 \
            -movflags +faststart \
            "${OUTPUT_DIR}/anime-test-${WIDTH}x${HEIGHT}.mp4" \
            2>/dev/null
    }

echo -e "${GREEN}  Created: anime-test-${WIDTH}x${HEIGHT}.mp4${NC}"

# -----------------------------------------------------------------------------
# Generate ProRes Mezzanine (High Quality Source)
# -----------------------------------------------------------------------------

echo -e "\n${YELLOW}Generating mezzanine file (ProRes)...${NC}"

ffmpeg -y \
    -f lavfi -i "testsrc2=duration=${DURATION}:size=${WIDTH}x${HEIGHT}:rate=24000/1001" \
    -f lavfi -i "sine=frequency=1000:duration=${DURATION}" \
    -f lavfi -i "sine=frequency=440:duration=${DURATION}" \
    -filter_complex "[1:a][2:a]amerge=inputs=2[aout]" \
    -map 0:v \
    -map "[aout]" \
    -c:v prores_ks \
    -profile:v 3 \
    -pix_fmt yuv422p10le \
    -c:a pcm_s24le \
    -ar 48000 \
    "${OUTPUT_DIR}/mezzanine-${WIDTH}x${HEIGHT}.mov" \
    2>/dev/null

echo -e "${GREEN}  Created: mezzanine-${WIDTH}x${HEIGHT}.mov${NC}"

# -----------------------------------------------------------------------------
# Generate Different Resolutions
# -----------------------------------------------------------------------------

echo -e "\n${YELLOW}Generating additional resolutions...${NC}"

# 720p
ffmpeg -y \
    -f lavfi -i "testsrc2=duration=${DURATION}:size=1280x720:rate=24000/1001" \
    -f lavfi -i "sine=frequency=1000:duration=${DURATION}" \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -profile:v high \
    -level 4.0 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 192k \
    -movflags +faststart \
    "${OUTPUT_DIR}/test-pattern-1280x720.mp4" \
    2>/dev/null

echo -e "${GREEN}  Created: test-pattern-1280x720.mp4${NC}"

# 480p
ffmpeg -y \
    -f lavfi -i "testsrc2=duration=${DURATION}:size=854x480:rate=24000/1001" \
    -f lavfi -i "sine=frequency=1000:duration=${DURATION}" \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -profile:v main \
    -level 3.1 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 128k \
    -movflags +faststart \
    "${OUTPUT_DIR}/test-pattern-854x480.mp4" \
    2>/dev/null

echo -e "${GREEN}  Created: test-pattern-854x480.mp4${NC}"

# -----------------------------------------------------------------------------
# Calculate Checksums
# -----------------------------------------------------------------------------

echo -e "\n${YELLOW}Calculating checksums...${NC}"

cd "${OUTPUT_DIR}"
for file in *.mp4 *.mov; do
    if [ -f "$file" ]; then
        MD5=$(md5sum "$file" 2>/dev/null || md5 -q "$file" 2>/dev/null || echo "N/A")
        SIZE=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "N/A")
        echo "  $file"
        echo "    MD5: ${MD5%% *}"
        echo "    Size: ${SIZE} bytes"
    fi
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Test Video Generation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Generated files in ${OUTPUT_DIR}:"
ls -la "${OUTPUT_DIR}"/*.mp4 "${OUTPUT_DIR}"/*.mov 2>/dev/null || true
echo ""
echo "To use these files in tests:"
echo "  1. Upload to S3: aws s3 cp ${OUTPUT_DIR}/mezzanine-${WIDTH}x${HEIGHT}.mov s3://bucket/mezzanines/"
echo "  2. Update test fixtures with the checksums above"
echo "  3. Run pipeline: make test-e2e"
