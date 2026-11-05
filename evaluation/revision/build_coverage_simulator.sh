#!/bin/bash
# Build a coverage-instrumented copy of the fixed simulator, for code_coverage.py
# (context/EVALUATION_METRICS.md, section 3.4).
#
# Copies the fixed ns-3 tree (default /tmp/ns3_fixtest, the build used for every Stage 7 run and
# for bug detection) without its build output, and builds afdx-demo with the compiler's
# --coverage flag. The source is identical; only the flag differs. ns-3's own --enable-gcov is
# not used because it requires the lcov package. Also installs gcovr in its own environment.
#
# Usage (in WSL): bash evaluation/revision/build_coverage_simulator.sh [FIXED_TREE] [COVERAGE_TREE]
set -e
SRC=${1:-/tmp/ns3_fixtest}
DST=${2:-/tmp/ns3_cov}
rm -rf "$DST"
mkdir -p "$DST"
(cd "$SRC" && tar --exclude=./build --exclude=./cmake-cache -cf - .) | (cd "$DST" && tar -xf -)
cd "$DST"
CXXFLAGS="--coverage" LDFLAGS="--coverage" ./ns3 configure --build-profile=default \
  --enable-examples --disable-tests --enable-modules='core;network;internet;csma;bridge' \
  > "$DST.configure.log" 2>&1
grep -E "^CMAKE_CXX_FLAGS:|^CMAKE_EXE_LINKER_FLAGS:" cmake-cache/CMakeCache.txt
./ns3 build afdx-demo > "$DST.build.log" 2>&1
tail -1 "$DST.build.log"
echo "instrumented AFDX files: $(find "$DST" -name '*.gcno' | grep -ci afdx)"
[ -x ~/cov_venv/bin/gcovr ] || { python3 -m venv ~/cov_venv && ~/cov_venv/bin/pip install -q gcovr; }
~/cov_venv/bin/gcovr --version | head -1
