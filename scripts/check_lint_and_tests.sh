#!/usr/bin/env bash
set -e

echo "==================================================="
echo " Running BidGuard Comprehensive Verification"
echo "==================================================="

echo "[1/3] Checking Git Diff for whitespace / formatting errors..."
git diff --check

echo "[2/3] Running Backend Pytest Suite..."
cd backend
pytest -v --ignore=sample_data
cd ..

echo "[3/3] Running Frontend Production Build..."
cd frontend
npm run build
cd ..

echo "==================================================="
echo " All checks passed successfully!"
echo "==================================================="
