#!/bin/bash
# 参照がすべて相対パスで実在し、移設しても壊れないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check references

echo "PASS"
