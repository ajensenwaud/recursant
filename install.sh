#!/usr/bin/env bash
# Recursant installer: builds the single `recursant` binary from source and installs it
# with a starter configuration.
#
#   curl -fsSL https://raw.githubusercontent.com/ajensenwaud/recursant/main/install.sh | bash
#
# Environment (all optional):
#   RECURSANT_PREFIX    install prefix (default: $HOME/.local; binary in $PREFIX/bin)
#   RECURSANT_CONFIG    config directory (default: ${XDG_CONFIG_HOME:-$HOME/.config}/recursant)
#   RECURSANT_REF       git branch or tag to build (default: main)
#   RECURSANT_SRC       build from this local checkout instead of downloading
#   RECURSANT_NO_DEPS=1 never install system packages; fail with the command to run instead
#
# What it does: checks for a C compiler, CMake, pkg-config and four libraries
# (libmicrohttpd, libcurl, jansson, PCRE2); installs missing ones with your package manager
# (apt, dnf, pacman, zypper, apk or Homebrew; sudo when needed); downloads the source,
# builds a Release binary, installs it, writes a starter config if none exists, and
# validates it. Nothing runs as a service and nothing is sent anywhere.
set -euo pipefail

REPO="ajensenwaud/recursant"
REF="${RECURSANT_REF:-main}"
PREFIX="${RECURSANT_PREFIX:-$HOME/.local}"
CONFIG_DIR="${RECURSANT_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/recursant}"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif have sudo; then sudo "$@"
  else die "need root to install packages: run as root, install sudo, or set RECURSANT_NO_DEPS=1 and install them yourself"
  fi
}

PC_LIBS="libmicrohttpd libcurl jansson libpcre2-8"

missing_deps() {
  local m=""
  have cc || have gcc || have clang || m="$m compiler"
  have cmake || m="$m cmake"
  have pkg-config || m="$m pkg-config"
  if have pkg-config; then
    for lib in $PC_LIBS; do pkg-config --exists "$lib" || m="$m $lib"; done
  fi
  echo "$m"
}

install_deps() {
  local cmd
  if have apt-get; then
    cmd="apt-get install -y build-essential cmake pkg-config libmicrohttpd-dev libcurl4-openssl-dev libjansson-dev libpcre2-dev ca-certificates"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: sudo apt-get update && sudo $cmd"
    say "Installing build dependencies with apt"
    sudo_cmd apt-get update -qq && sudo_cmd env DEBIAN_FRONTEND=noninteractive $cmd
  elif have dnf; then
    cmd="dnf install -y gcc make cmake pkgconf-pkg-config libmicrohttpd-devel libcurl-devel jansson-devel pcre2-devel"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: sudo $cmd"
    say "Installing build dependencies with dnf"; sudo_cmd $cmd
  elif have pacman; then
    cmd="pacman -S --needed --noconfirm base-devel cmake pkgconf libmicrohttpd curl jansson pcre2"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: sudo $cmd"
    say "Installing build dependencies with pacman"; sudo_cmd $cmd
  elif have zypper; then
    cmd="zypper install -y gcc make cmake pkg-config libmicrohttpd-devel libcurl-devel libjansson-devel pcre2-devel"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: sudo $cmd"
    say "Installing build dependencies with zypper"; sudo_cmd $cmd
  elif have apk; then
    cmd="apk add build-base cmake pkgconf libmicrohttpd-dev curl-dev jansson-dev pcre2-dev"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: sudo $cmd"
    say "Installing build dependencies with apk"; sudo_cmd $cmd
  elif have brew; then
    cmd="brew install cmake pkg-config libmicrohttpd curl jansson pcre2"
    [ -n "${RECURSANT_NO_DEPS:-}" ] && die "missing:$(missing_deps). Install with: $cmd"
    say "Installing build dependencies with Homebrew"; $cmd
    export PKG_CONFIG_PATH="$(brew --prefix curl)/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
  else
    die "missing:$(missing_deps). No supported package manager found; install a C compiler, CMake, pkg-config, libmicrohttpd, libcurl, jansson and PCRE2, then rerun"
  fi
}

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) die "unsupported OS $(uname -s): Recursant builds on Linux and macOS" ;;
esac
have curl || [ -n "${RECURSANT_SRC:-}" ] || die "curl is required"
have tar  || [ -n "${RECURSANT_SRC:-}" ] || die "tar is required"

say "Checking build dependencies"
if [ -n "$(missing_deps)" ]; then
  install_deps
  [ -z "$(missing_deps)" ] || die "still missing:$(missing_deps)"
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/recursant-install.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if [ -n "${RECURSANT_SRC:-}" ]; then
  SRC="$(cd "$RECURSANT_SRC" && pwd)"
  say "Building from local source $SRC"
else
  say "Downloading $REPO ($REF)"
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" -o "$WORK/src.tar.gz" ||
    die "download failed: https://github.com/$REPO ($REF). Is the repository public and the ref correct?"
  mkdir "$WORK/src" && tar -xzf "$WORK/src.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
[ -f "$SRC/CMakeLists.txt" ] && [ -d "$SRC/core" ] || die "$SRC does not look like a Recursant checkout"

JOBS="$( (have nproc && nproc) || sysctl -n hw.ncpu 2>/dev/null || echo 2)"
say "Building (Release, $JOBS jobs)"
cmake -S "$SRC" -B "$WORK/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF >"$WORK/cmake.log" 2>&1 ||
  { cat "$WORK/cmake.log" >&2; die "cmake configure failed"; }
cmake --build "$WORK/build" --target recursant -j "$JOBS" >"$WORK/build.log" 2>&1 ||
  { tail -40 "$WORK/build.log" >&2; die "build failed"; }

say "Installing $PREFIX/bin/recursant"
mkdir -p "$PREFIX/bin"
install -m 0755 "$WORK/build/recursant" "$PREFIX/bin/recursant"

mkdir -p "$CONFIG_DIR"
CONFIG="$CONFIG_DIR/config.json"
if [ -e "$CONFIG" ]; then
  say "Keeping existing config $CONFIG"
else
  install -m 0600 "$SRC/config/recursant.quickstart.json" "$CONFIG"
  say "Wrote starter config $CONFIG"
fi

# Structure check only: distinct placeholder values (the keys must differ) stand in for
# your keys in this one subprocess.
if env RECURSANT_API_KEY=check-client OPENROUTER_API_KEY=check-public RECURSANT_SOURCE_KEY=check-source \
     "$PREFIX/bin/recursant" validate "$CONFIG" >/dev/null 2>&1; then
  say "Config is valid"
else
  warn "$CONFIG did not validate; run: recursant validate $CONFIG (with your keys exported)"
fi

case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) warn "$PREFIX/bin is not on your PATH; add: export PATH=\"$PREFIX/bin:\$PATH\"" ;; esac

cat <<EOF

Recursant is installed.

  1. Set three secrets (from your secret manager; never put them in the config):
       export OPENROUTER_API_KEY=...                 # public models
       export RECURSANT_API_KEY=\$(openssl rand -hex 24)   # what your agents use to call Recursant
       export RECURSANT_SOURCE_KEY=\$(openssl rand -hex 24) # for optional harness hints
  2. Point "local" in $CONFIG at your on-prem model (default: Ollama on :11434).
  3. Run it:
       recursant serve $CONFIG
  4. Point your agent at it: base URL http://127.0.0.1:8080/v1, API key \$RECURSANT_API_KEY,
     model "auto". Every step is routed; responses carry X-Recursant-Model and
     X-Recursant-Decision headers so you can see what happened.

Docs: https://github.com/$REPO
EOF
