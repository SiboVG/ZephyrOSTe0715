#!/bin/sh
# Build and install the pinned cppcheck into a prefix (default ~/.local/cppcheck-<version>).
# CI caches the prefix; locally `brew install cppcheck` is usually enough.
# Usage: install-cppcheck.sh [version] [prefix]
set -eu

version=${1:-2.22.0}
prefix=${2:-"$HOME/.local/cppcheck-$version"}

if [ -x "$prefix/bin/cppcheck" ]; then
    "$prefix/bin/cppcheck" --version
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone --quiet --depth 1 --branch "$version" https://github.com/danmar/cppcheck.git "$work/src"
cmake -S "$work/src" -B "$work/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DFILESDIR="$prefix/share/Cppcheck" \
    -DUSE_MATCHCOMPILER=ON \
    -DBUILD_GUI=OFF -DBUILD_TESTS=OFF -DHAVE_RULES=OFF
cmake --build "$work/build"
cmake --install "$work/build"
"$prefix/bin/cppcheck" --version
