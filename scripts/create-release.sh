#!/bin/bash

# NHMesh Producer Release Script
# This script helps create a new release by tagging and pushing to GitHub

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 <version> [options]"
    echo ""
    echo "Arguments:"
    echo "  version    Version to release (e.g., 1.0.0)"
    echo ""
    echo "Options:"
    echo "  --dry-run  Show what would be done without actually doing it"
    echo "  --help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 1.0.0"
    echo "  $0 1.0.0 --dry-run"
    echo ""
    echo "This script will:"
    echo "  1. Check if you're on the main branch"
    echo "  2. Check if the working directory is clean"
    echo "  3. Create and push a tag (v<version>)"
    echo "  4. Trigger GitHub Actions to build and release"
}

# Parse arguments
VERSION=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        -*)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            if [[ -z "$VERSION" ]]; then
                VERSION="$1"
            else
                print_error "Multiple versions specified: $VERSION and $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if version is provided
if [[ -z "$VERSION" ]]; then
    print_error "Version is required"
    show_usage
    exit 1
fi

# Validate version format (simple check)
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    print_error "Invalid version format. Expected format: X.Y.Z (e.g., 1.0.0)"
    exit 1
fi

TAG="v$VERSION"

print_status "Preparing to release version $VERSION (tag: $TAG)"

if [[ "$DRY_RUN" == "true" ]]; then
    print_warning "DRY RUN MODE - No changes will be made"
fi

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Not in a git repository"
    exit 1
fi

# Check if we're on the main branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    print_warning "You're not on the main branch (currently on: $CURRENT_BRANCH)"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Aborted"
        exit 1
    fi
fi

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    print_error "Working directory is not clean. Please commit or stash your changes."
    git status --short
    exit 1
fi

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    print_error "Tag $TAG already exists"
    exit 1
fi

# Check if remote exists
if ! git remote get-url origin >/dev/null 2>&1; then
    print_error "No remote 'origin' found"
    exit 1
fi

print_status "All checks passed!"

if [[ "$DRY_RUN" == "true" ]]; then
    print_status "Would create tag: $TAG"
    print_status "Would push tag to origin"
    print_status "Would trigger GitHub Actions build and release"
else
    # Create and push the tag
    print_status "Creating tag $TAG..."
    git tag "$TAG"
    
    print_status "Pushing tag to origin..."
    git push origin "$TAG"
    
    print_success "Release tag $TAG has been pushed!"
    print_status "GitHub Actions will now build and create a release automatically."
    print_status "You can monitor progress at: https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^/]*\/[^/]*\).*/\1/')/actions"
fi

print_success "Release process completed!" 