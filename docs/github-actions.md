# GitHub Actions Workflows

This document describes the GitHub Actions workflows used in the NHMesh Producer project.

## Overview

The project includes two main workflows:

1. **Build and Release** (`build-and-release.yml`) - Creates releases with binaries
2. **Test Build** (`test-build.yml`) - Tests the build process on PRs and pushes

## Workflows

### Build and Release (`build-and-release.yml`)

This workflow automatically builds binaries and creates GitHub releases when you push a tag.

#### Triggers

- Push to tags matching `v*` (e.g., `v1.0.0`)
- Manual workflow dispatch (for testing)

#### Jobs

1. **Build Cross-Platform Binaries**

   - Runs on `ubuntu-latest`
   - Builds for: `linux-x86_64`, `linux-aarch64`, `macos-x86_64`, `macos-arm64`
   - Uses Docker for cross-compilation
   - Uploads artifacts for each platform

2. **Build Native Binaries**

   - Runs on `ubuntu-latest` and `macos-latest`
   - Builds native binaries for the runner's platform
   - Uses Poetry for dependency management

3. **Create Release**

   - Creates GitHub release with all binaries
   - Generates release notes
   - Uploads binary files

4. **Package Release Assets**

   - Creates `.tar.gz` packages for each platform
   - Uploads packaged releases as artifacts

5. **Test Binaries**
   - Tests binaries on compatible platforms
   - Verifies binaries work correctly

#### Output

The workflow creates:

- GitHub release with version tag
- Binary files for each platform
- Packaged `.tar.gz` files for easy distribution

### Test Build (`test-build.yml`)

This workflow tests the build process on pull requests and pushes to main.

#### Triggers

- Push to `main` branch
- Pull requests to `main` branch

#### Jobs

1. **Test Build Process**

   - Tests the build script
   - Builds a simple binary
   - Tests the binary works
   - Uploads build artifacts

2. **Test Docker Build** (PRs only)
   - Tests Docker build setup
   - Verifies cross-compilation works
   - Runs quickly to keep PR builds fast

## Usage

### Creating a Release

1. **Automatic Release** (recommended):

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Manual Release**:
   - Go to GitHub Actions tab
   - Select "Build and Release"
   - Click "Run workflow"
   - Enter version (e.g., `v1.0.0`)
   - Click "Run workflow"

### Monitoring Builds

- **Actions Tab**: View all workflow runs
- **Releases Tab**: View created releases
- **Artifacts**: Download build artifacts

### Troubleshooting

#### Common Issues

1. **Build Failures**:

   - Check Poetry dependencies are up to date
   - Verify Python 3.13 is available
   - Check Docker is working for cross-compilation

2. **Release Failures**:

   - Ensure tag format is correct (`v*`)
   - Check repository permissions
   - Verify GitHub token has correct permissions

3. **Binary Issues**:
   - Test binaries locally first
   - Check platform compatibility
   - Verify all dependencies are included

#### Debugging

- Enable debug logging in workflows
- Check workflow logs for specific errors
- Test build process locally first

## Configuration

### Environment Variables

The workflows use these environment variables:

- `GITHUB_TOKEN`: Automatically provided by GitHub
- `RELEASE_PAT`: For release-please integration (if used)

### Dependencies

The workflows require:

- Python 3.13
- Poetry (latest)
- Docker (for cross-compilation)
- GitHub Actions runners with Docker support

## Integration with Release-Please

The project also includes a `release-please.yml` workflow that:

- Automatically creates PRs for releases
- Updates version numbers
- Generates changelogs

This works alongside the build and release workflow to provide automated version management.

## Security

- Workflows use minimal required permissions
- Secrets are properly managed
- Build artifacts are cleaned up automatically
- No sensitive data is logged

## Performance

- Builds are cached where possible
- Dependencies are cached between runs
- Cross-compilation uses Docker for efficiency
- PR builds are optimized for speed
