# lock-screen justfile

default:
    @just --list

# Install the project in development mode
install:
    uv sync

# Run the lock screen
run *ARGS:
    uv run lock-screen {{ ARGS }}

# Run with custom icon
run-icon ICON:
    uv run lock-screen --icon {{ ICON }}

# Lint with ruff
lint:
    uv run ruff check src/

# Format with ruff
fmt:
    uv run ruff format src/

# Check formatting without writing
fmt-check:
    uv run ruff format --check src/

# Lint and format
check: lint fmt-check

# Fix lint issues automatically
fix:
    uv run ruff check --fix src/
    uv run ruff format src/

# Build the package
build:
    uv build

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
