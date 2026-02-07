#!/bin/bash
# Manual Docker build workaround for GitHub Actions billing failure
# Usage: ./manual-docker-build.sh <image-name> <version> <dockerfile-path>

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 2 ]; then
    echo -e "${RED}Error: Missing required arguments${NC}"
    echo "Usage: $0 <image-name> <version> [dockerfile-path] [build-context]"
    echo ""
    echo "Examples:"
    echo "  $0 ardenone/mcp-gfz 0.1.9"
    echo "  $0 ardenone/botburrow-hub latest Dockerfile ./src"
    exit 1
fi

IMAGE_NAME="$1"
VERSION="$2"
DOCKERFILE="${3:-Dockerfile}"
BUILD_CONTEXT="${4:-.}"

REGISTRY="${IMAGE_NAME%%/*}"  # Extract registry/org from image name
IMAGE_BASE="${IMAGE_NAME##*/}" # Extract image base name

echo -e "${GREEN}=== Manual Docker Build ===${NC}"
echo "Image: ${IMAGE_NAME}"
echo "Version: ${VERSION}"
echo "Dockerfile: ${DOCKERFILE}"
echo "Context: ${BUILD_CONTEXT}"
echo ""

# Check if Dockerfile exists
if [ ! -f "${BUILD_CONTEXT}/${DOCKERFILE}" ]; then
    echo -e "${RED}Error: Dockerfile not found at ${BUILD_CONTEXT}/${DOCKERFILE}${NC}"
    exit 1
fi

# Build image with version and latest tags
echo -e "${YELLOW}Building ${IMAGE_NAME}:${VERSION}...${NC}"
docker build \
    -t "${IMAGE_NAME}:${VERSION}" \
    -t "${IMAGE_NAME}:latest" \
    -f "${BUILD_CONTEXT}/${DOCKERFILE}" \
    "${BUILD_CONTEXT}"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Build successful${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi

# Show image size
echo ""
echo -e "${GREEN}Built images:${NC}"
docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Prompt for push
echo ""
read -p "Push to registry? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${VERSION}...${NC}"
    docker push "${IMAGE_NAME}:${VERSION}"

    echo -e "${YELLOW}Pushing ${IMAGE_NAME}:latest...${NC}"
    docker push "${IMAGE_NAME}:latest"

    echo -e "${GREEN}✓ Push complete${NC}"
    echo ""
    echo "Image available at:"
    echo "  - ${IMAGE_NAME}:${VERSION}"
    echo "  - ${IMAGE_NAME}:latest"
else
    echo "Push skipped. Images built locally only."
fi

echo ""
echo -e "${GREEN}=== Build Complete ===${NC}"
