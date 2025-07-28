#!/usr/bin/env python3
"""
NHMesh Producer Build Script
A unified build system for creating PyInstaller binaries across all platforms
"""

import os
import platform
import shutil
import subprocess
import sys

# Configuration
PROJECT_NAME = "nhmesh-producer"
MAIN_SCRIPT = "nhmesh_producer/producer.py"
SPEC_FILE = "nhmesh-producer.spec"

# Build configurations for different platforms
BUILD_CONFIGS = {
    "linux-x86_64": {
        "image": "python:3.13-slim",
        "platform": "linux/amd64",
        "target_arch": "x86_64",
    },
    "linux-aarch64": {
        "image": "python:3.13-slim",
        "platform": "linux/arm64",
        "target_arch": "aarch64",
    },
    "macos-x86_64": {
        "image": "python:3.13-slim",
        "platform": "linux/amd64",
        "target_arch": "x86_64",
    },
    "macos-arm64": {
        "image": "python:3.13-slim",
        "platform": "linux/arm64",
        "target_arch": "arm64",
    },
}


def run_command(cmd, cwd=None, env=None):
    """Run a command and return the result"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {result.stderr}")
        return False
    return True


def create_spec_file():
    """Create a PyInstaller spec file"""
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{MAIN_SCRIPT}'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Core dependencies
        'paho.mqtt.client',
        'paho.mqtt.publish',
        'paho.mqtt.subscribe',
        'paho.mqtt.auth',
        'paho.mqtt.callbacks',
        'paho.mqtt.properties',
        'paho.mqtt.reasoncodes',
        'paho.mqtt.subscribeoptions',

        # Meshtastic dependencies
        'meshtastic',
        'meshtastic.tcp_interface',
        'meshtastic.serial_interface',
        'meshtastic.protobuf',
        'meshtastic.protobuf.mesh_pb2',
        'meshtastic.protobuf.portnums_pb2',
        'meshtastic.protobuf.channel_pb2',
        'meshtastic.protobuf.config_pb2',
        'meshtastic.protobuf.localonly_pb2',
        'meshtastic.protobuf.module_config_pb2',
        'meshtastic.protobuf.telemetry_pb2',
        'meshtastic.protobuf.xmodem_pb2',
        'meshtastic.protobuf.api_pb2',
        'meshtastic.protobuf.connection_status_pb2',
        'meshtastic.protobuf.deviceonly_pb2',
        'meshtastic.protobuf.mqtt_pb2',
        'meshtastic.protobuf.nodeinfo_pb2',
        'meshtastic.protobuf.rtt_pb2',
        'meshtastic.protobuf.storeforward_pb2',

        # Google protobuf
        'google.protobuf',
        'google.protobuf.json_format',
        'google.protobuf.message',
        'google.protobuf.descriptor',
        'google.protobuf.descriptor_pb2',
        'google.protobuf.internal',
        'google.protobuf.internal.api_implementation',
        'google.protobuf.internal.containers',
        'google.protobuf.internal.decoder',
        'google.protobuf.internal.encoder',
        'google.protobuf.internal.enum_type_wrapper',
        'google.protobuf.internal.message_listener',
        'google.protobuf.internal.type_checkers',
        'google.protobuf.internal.wire_format',
        'google.protobuf.pyext',
        'google.protobuf.reflection',
        'google.protobuf.symbol_database',
        'google.protobuf.text_format',
        'google.protobuf.unknown_fields',
        'google.protobuf.well_known_types',

        # PubSub
        'pubsub',
        'pubsub.pub',
        'pubsub.core',
        'pubsub.core.listener',
        'pubsub.core.publisher',
        'pubsub.core.topic',
        'pubsub.core.topicdefnprovider',
        'pubsub.core.topicmgr',
        'pubsub.core.topicutils',
        'pubsub.core.weakmethod',
        'pubsub.core.weakref',

        # Local modules
        'nhmesh_producer.utils.connection_manager',
        'nhmesh_producer.utils.traceroute_manager',
        'nhmesh_producer.utils.node_cache',
        'nhmesh_producer.utils.deduplicated_queue',
        'nhmesh_producer.utils.envdefault',
        'nhmesh_producer.utils.number_utils',
        'utils.connection_manager',
        'utils.traceroute_manager',
        'utils.node_cache',
        'utils.deduplicated_queue',
        'utils.envdefault',
        'utils.number_utils',

        # Standard library modules
        'argparse',
        'atexit',
        'base64',
        'json',
        'logging',
        'os',
        'signal',
        'sys',
        'threading',
        'time',
        'typing',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{PROJECT_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{PROJECT_NAME}',
)
"""

    with open(SPEC_FILE, "w") as f:
        f.write(spec_content)

    return True


def build_simple():
    """Build binary for current platform only"""
    print("Building for current platform...")

    # Install dev dependencies (including PyInstaller)
    print("Installing dev dependencies...")
    install_cmd = ["poetry", "install", "--extras", "dev"]
    if not run_command(install_cmd):
        print("Failed to install dev dependencies")
        return False

    # Create spec file
    if not create_spec_file():
        print("Failed to create spec file")
        return False

    # Build using Poetry
    build_cmd = [
        "poetry",
        "run",
        "python",
        "-m",
        "PyInstaller",
        "--clean",
        "-y",
        SPEC_FILE,
    ]

    if not run_command(build_cmd):
        print("Build failed")
        return False

    # Move to platform-specific directory
    current_platform = platform.system().lower()
    current_arch = platform.machine()
    output_dir = f"dist/{current_platform}-{current_arch}"

    # Remove existing directory if it exists
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(f"dist/{PROJECT_NAME}"):
        shutil.move(f"dist/{PROJECT_NAME}", output_dir)

    print(f"Successfully built binary: {output_dir}/{PROJECT_NAME}/{PROJECT_NAME}")
    return True


def create_dockerfile(config_name, config):
    """Create a Dockerfile for cross-compilation"""
    dockerfile_content = f"""FROM {config["image"]}

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    g++ \\
    make \\
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --only main --no-root

# Install PyInstaller
RUN pip install pyinstaller

# Copy source code
COPY . .

# Copy the PyInstaller spec file
COPY {SPEC_FILE} .

# Build the binary
RUN python -m PyInstaller --clean {SPEC_FILE}

# Create output directory structure
RUN mkdir -p /output/{config_name}

# Copy the built binary
RUN cp -r dist/{PROJECT_NAME} /output/{config_name}/

# Set permissions
RUN chmod +x /output/{config_name}/{PROJECT_NAME}/{PROJECT_NAME}
"""

    dockerfile_path = f"Dockerfile.{config_name}"
    with open(dockerfile_path, "w") as f:
        f.write(dockerfile_content)

    return dockerfile_path


def build_cross_platform():
    """Build binaries for all platforms using Docker"""
    print("Building for all platforms using Docker...")

    # Create spec file
    if not create_spec_file():
        print("Failed to create spec file")
        return False

    success_count = 0
    total_count = len(BUILD_CONFIGS)

    for config_name, config in BUILD_CONFIGS.items():
        print(f"\n{'=' * 60}")
        print(f"Building {config_name}")
        print(f"{'=' * 60}")

        # Create Dockerfile
        dockerfile_path = create_dockerfile(config_name, config)

        # Create output directory
        output_dir = f"dist/{config_name}"
        os.makedirs(output_dir, exist_ok=True)

        # Build Docker image
        image_name = f"{PROJECT_NAME}-build-{config_name}"
        build_cmd = [
            "docker",
            "build",
            "--platform",
            config["platform"],
            "-f",
            dockerfile_path,
            "-t",
            image_name,
            ".",
        ]

        if not run_command(build_cmd):
            print(f"Failed to build Docker image for {config_name}")
            continue

        # Create container and copy binary
        container_name = f"{PROJECT_NAME}-container-{config_name}"

        # Run container
        run_cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "--platform",
            config["platform"],
            image_name,
            "true",
        ]

        if not run_command(run_cmd):
            print(f"Failed to create container for {config_name}")
            continue

        # Copy binary from container
        cp_cmd = ["docker", "cp", f"{container_name}:/output/{config_name}", output_dir]

        if not run_command(cp_cmd):
            print(f"Failed to copy binary from container for {config_name}")
            continue

        # Clean up
        run_command(["docker", "rm", container_name])
        run_command(["docker", "rmi", image_name])
        os.remove(dockerfile_path)

        print(f"Successfully built {config_name}")
        success_count += 1

    # Build native macOS if on macOS
    if sys.platform == "darwin":
        print(f"\n{'=' * 60}")
        print("Building native macOS binary")
        print(f"{'=' * 60}")

        # Build using Poetry
        build_cmd = [
            "poetry",
            "run",
            "python",
            "-m",
            "PyInstaller",
            "--clean",
            SPEC_FILE,
        ]
        if run_command(build_cmd):
            output_dir = "dist/macos-native"
            os.makedirs(output_dir, exist_ok=True)
            if os.path.exists(f"dist/{PROJECT_NAME}"):
                shutil.move(f"dist/{PROJECT_NAME}", output_dir)
            print("Successfully built native macOS binary")
            success_count += 1
        total_count += 1

    # Clean up spec file
    if os.path.exists(SPEC_FILE):
        os.remove(SPEC_FILE)

    print(f"\n{'=' * 60}")
    print("BUILD SUMMARY")
    print(f"{'=' * 60}")
    print(f"Successfully built: {success_count}/{total_count} platforms")

    if success_count > 0:
        print("\nBinary locations:")
        for config_name in BUILD_CONFIGS.keys():
            binary_path = (
                f"dist/{config_name}/{config_name}/{PROJECT_NAME}/{PROJECT_NAME}"
            )
            if os.path.exists(binary_path):
                print(f"  {config_name}: {binary_path}")

        if sys.platform == "darwin":
            native_path = f"dist/macos-native/{PROJECT_NAME}/{PROJECT_NAME}"
            if os.path.exists(native_path):
                print(f"  macos-native: {native_path}")

    return success_count == total_count


def test_binaries():
    """Test existing binaries"""
    print("Testing existing binaries...")

    # Find binaries that can run on current platform
    binary_paths = []
    current_platform = platform.system().lower()
    current_arch = platform.machine()

    # Only test binaries for current platform
    if current_platform == "darwin":
        # Test native macOS binary only (cross-compiled ones are actually Linux binaries)
        native_path = f"dist/macos-native/{PROJECT_NAME}/{PROJECT_NAME}"
        if os.path.exists(native_path):
            binary_paths.append(native_path)

    elif current_platform == "linux":
        # Test cross-compiled Linux binaries
        for config_name in ["linux-x86_64", "linux-aarch64"]:
            binary_path = (
                f"dist/{config_name}/{config_name}/{PROJECT_NAME}/{PROJECT_NAME}"
            )
            if os.path.exists(binary_path):
                binary_paths.append(binary_path)

    if not binary_paths:
        print("No compatible binaries found for current platform.")
        print(f"Current platform: {current_platform}-{current_arch}")
        print("Run a build first:")
        print("  python3 build.py simple")
        print("  python3 build.py docker")
        return False

    print(f"Found {len(binary_paths)} compatible binary(ies) to test:")
    for path in binary_paths:
        print(f"  - {path}")

    # Test each binary
    all_passed = True
    for binary_path in binary_paths:
        print(f"\nTesting: {binary_path}")

        # Test help command
        test_cmd = [binary_path, "--help"]
        if run_command(test_cmd):
            print("✓ Help command works")
        else:
            print("✗ Help command failed")
            all_passed = False

    if all_passed:
        print("\n✓ All compatible binaries passed tests!")
    else:
        print("\n✗ Some binaries failed tests.")

    return all_passed


def print_usage():
    """Print usage information"""
    print("""
NHMesh Producer Build Script

Usage:
  python3 build.py [option]

Options:
  simple      - Build for current platform only (recommended for beginners)
  docker      - Build for all platforms using Docker (requires Docker)
  test        - Test existing binaries
  help        - Show this help message

Examples:
  python3 build.py simple      # Build for your current platform
  python3 build.py docker      # Build for Linux, ARM64, and macOS
  python3 build.py test        # Test existing binaries

Supported platforms:
  - Linux x86_64 (Intel/AMD servers and desktops)
  - Linux ARM64 (Raspberry Pi, ARM servers)
  - macOS x86_64 (Intel Macs)
  - macOS ARM64 (Apple Silicon M1/M2)
""")


def main():
    """Main build function"""
    if len(sys.argv) != 2:
        print_usage()
        sys.exit(1)

    option = sys.argv[1].lower()

    # Check if we're in the right directory
    if not os.path.exists(MAIN_SCRIPT):
        print(
            f"Error: {MAIN_SCRIPT} not found. Please run this script from the nhmesh-producer directory."
        )
        sys.exit(1)

    # Clean previous builds
    print("Cleaning previous builds...")
    for path in ["build", SPEC_FILE]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    if option == "help":
        print_usage()
        sys.exit(0)
    elif option == "simple":
        success = build_simple()
    elif option == "docker":
        # Check if Docker is available
        if not run_command(["docker", "--version"]):
            print("Docker is not available. Please install Docker to use this option.")
            print("Use 'python3 build.py simple' for current platform only.")
            sys.exit(1)
        success = build_cross_platform()
    elif option == "test":
        success = test_binaries()
    else:
        print(f"Unknown option: {option}")
        print_usage()
        sys.exit(1)

    if success:
        print("\n✓ Build completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Build failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
