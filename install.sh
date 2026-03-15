#!/bin/sh
set -e

REPO="https://github.com/anej-soniox/soniox-cli"
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
RESET="\033[0m"

info() { printf "${BOLD}${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$1"; }
error() { printf "${BOLD}${RED}error${RESET}: %s\n" "$1" >&2; exit 1; }

# Check for uv, install if missing
if command -v uv >/dev/null 2>&1; then
    info "Found uv: $(uv --version)"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || error "Failed to install uv"
    info "Installed uv: $(uv --version)"
fi

# Install soniox-cli
info "Installing soniox-cli..."
uv tool install "soniox-cli @ git+${REPO}"

info "Done! Run 'soniox' to get started."
