# Contributing to NHMesh Producer

Thank you for your interest in contributing to NHMesh Producer! This document provides guidelines and instructions for contributors.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Building Binaries](#building-binaries)
- [Testing](#testing)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)
- [GitHub Actions](#github-actions)

## Getting Started

### Prerequisites

- Python 3.13+
- Poetry (for dependency management)
- Docker (for cross-platform builds)
- Git

### Development Setup

1. **Fork and clone the repository:**

   ```bash
   git clone https://github.com/your-username/nhmesh-producer.git
   cd nhmesh-producer
   ```

2. **Install dependencies:**

   ```bash
   poetry install --extras dev
   ```

3. **Set up pre-commit hooks (optional):**
   ```bash
   poetry run pre-commit install
   ```

## Development Setup

### Environment Variables

Create a `.env` file in the project root with your configuration:

```bash
# Copy the sample environment file
cp sample.env .env

# Edit with your settings
nano .env
```

### Running the Application

#### Using Poetry (Development)

```bash
# Run the producer
poetry run python -m nhmesh_producer.producer \
    --username your_username \
    --password your_password \
    --node-ip 192.168.1.100

# Run with debug logging
LOG_LEVEL=DEBUG poetry run python -m nhmesh_producer.producer \
    --username your_username \
    --password your_password \
    --node-ip 192.168.1.100
```

#### Using Docker (Production-like)

```bash
# Build the image
docker build -t nhmesh-producer .

# Run the container
docker run -d \
    --name nhmesh-producer \
    -e NODE_IP=192.168.1.100 \
    -e MQTT_USERNAME=your_username \
    -e MQTT_PASSWORD=your_password \
    -p 5001:5001 \
    nhmesh-producer
```

## Building Binaries

### Local Build

You can build binaries locally using the included build script:

```bash
# Build for current platform only
python3 build.py simple

# Build for all platforms (requires Docker)
python3 build.py docker

# Test existing binaries
python3 build.py test
```

### Supported Platforms

- **Linux x86_64** (Intel/AMD servers and desktops)
- **Linux ARM64** (Raspberry Pi, ARM servers)
- **macOS x86_64** (Intel Macs)
- **macOS ARM64** (Apple Silicon M1/M2)
- **macOS Native** (built on macOS runners)

### Build Output

Binaries are created in the `dist/` directory:

```
dist/
├── linux-x86_64/linux-x86_64/nhmesh-producer/nhmesh-producer
├── linux-aarch64/linux-aarch64/nhmesh-producer/nhmesh-producer
├── macos-x86_64/macos-x86_64/nhmesh-producer/nhmesh-producer
├── macos-arm64/macos-arm64/nhmesh-producer/nhmesh-producer
└── macos-native/nhmesh-producer/nhmesh-producer
```

## Testing

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=nhmesh_producer

# Run specific test file
poetry run pytest tests/test_connection_manager.py

# Run tests with verbose output
poetry run pytest -v
```

### Code Quality Checks

```bash
# Run linting with Ruff
poetry run ruff check .

# Run type checking with Pyright
poetry run pyright

# Run all quality checks
poetry run ruff check . && poetry run pyright
```

### Testing Binaries

```bash
# Test built binaries
python3 build.py test

# Test specific binary
./dist/macos-native/nhmesh-producer/nhmesh-producer --help
```

## Code Style

### Python Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check code style
poetry run ruff check .

# Format code
poetry run ruff format .

# Fix auto-fixable issues
poetry run ruff check --fix .
```

### Type Hints

All new code should include type hints:

```python
from typing import Optional, List, Dict

def process_message(message: str, metadata: Optional[Dict[str, str]] = None) -> bool:
    """Process a message with optional metadata."""
    pass
```

### Documentation

- Use docstrings for all public functions and classes
- Follow Google-style docstrings
- Include type information in docstrings

```python
def connect_to_node(node_ip: str, port: int = 4403) -> bool:
    """Connect to a Meshtastic node.

    Args:
        node_ip: IP address of the node
        port: TCP port (default: 4403)

    Returns:
        True if connection successful, False otherwise

    Raises:
        ConnectionError: If connection fails
    """
    pass
```

## Pull Request Process

### Before Submitting

1. **Ensure tests pass:**

   ```bash
   poetry run pytest
   poetry run ruff check .
   poetry run pyright
   ```

2. **Update documentation** if needed

3. **Test your changes** locally

4. **Follow the commit message format:**

   ```
   type(scope): description

   Optional body with more details
   ```

   Examples:

   - `feat(connection): add automatic reconnection`
   - `fix(mqtt): handle connection timeouts`
   - `docs(readme): update installation instructions`

### Pull Request Guidelines

1. **Create a feature branch:**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and commit them

3. **Push to your fork:**

   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request** with:
   - Clear description of changes
   - Link to related issues
   - Screenshots if UI changes
   - Test results

### Review Process

- All PRs require at least one review
- CI checks must pass
- Code coverage should not decrease
- Documentation should be updated

## Release Process

### Creating a Release

#### Option 1: Using the Release Script (Recommended)

```bash
# Create a release
./scripts/create-release.sh 1.0.0

# Dry run to see what would happen
./scripts/create-release.sh 1.0.0 --dry-run
```

#### Option 2: Manual Git Commands

```bash
# Create and push a tag
git tag v1.0.0
git push origin v1.0.0
```

#### Option 3: GitHub Actions UI

1. Go to Actions → Build and Release
2. Click "Run workflow"
3. Enter the version (e.g., `v1.0.0`)
4. Click "Run workflow"

### Release Checklist

- [ ] All tests pass
- [ ] Documentation is up to date
- [ ] Version is updated in `pyproject.toml`
- [ ] CHANGELOG.md is updated
- [ ] Release notes are prepared
- [ ] Binaries are tested locally

## GitHub Actions

### Workflows

The project includes several GitHub Actions workflows:

#### Build and Release (`build-and-release.yml`)

- **Triggers:** Tag pushes (`v*`), manual dispatch
- **Purpose:** Builds binaries for all platforms and creates releases
- **Jobs:**
  - Build cross-platform binaries using Docker
  - Build native binaries on runners
  - Create GitHub release with binaries
  - Package release assets
  - Test binaries

#### Test Build (`test-build.yml`)

- **Triggers:** Push to main, pull requests
- **Purpose:** Tests build process and code quality
- **Jobs:**
  - Test build script
  - Build simple binary
  - Test binary functionality
  - Test Docker build setup

### Monitoring Workflows

- **Actions Tab:** View all workflow runs
- **Releases Tab:** View created releases
- **Artifacts:** Download build artifacts

### Troubleshooting

#### Common Issues

1. **Build Failures:**

   - Check Poetry dependencies are up to date
   - Verify Python 3.13 is available
   - Check Docker is working for cross-compilation

2. **Release Failures:**

   - Ensure tag format is correct (`v*`)
   - Check repository permissions
   - Verify GitHub token has correct permissions

3. **Binary Issues:**
   - Test binaries locally first
   - Check platform compatibility
   - Verify all dependencies are included

### Local Testing

You can test the build process locally before pushing:

```bash
# Test simple build
python3 build.py simple

# Test Docker build (requires Docker)
python3 build.py docker

# Test binaries
python3 build.py test
```

## Getting Help

### Resources

- [GitHub Issues](https://github.com/nhmesh/nhmesh-producer/issues)
- [GitHub Discussions](https://github.com/nhmesh/nhmesh-producer/discussions)
- [Documentation](docs/)

### Questions

If you have questions about contributing:

1. Check existing issues and discussions
2. Search the documentation
3. Create a new discussion or issue
4. Join the community chat (if available)

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a welcoming and inclusive environment for all contributors.

## License

By contributing to NHMesh Producer, you agree that your contributions will be licensed under the [MIT License](LICENSE).
