@echo off
echo ===================================================
echo  Running BidGuard Comprehensive Verification
echo ===================================================

echo [1/3] Checking Git Diff for unintended changes...
git diff --check
if %ERRORLEVEL% neq 0 (
    echo Git diff check failed!
    exit /b %ERRORLEVEL%
)

echo [2/3] Running Backend Pytest Suite...
cd backend
pytest -v --ignore=sample_data
if %ERRORLEVEL% neq 0 (
    echo Backend tests failed!
    cd ..
    exit /b %ERRORLEVEL%
)
cd ..

echo [3/3] Running Frontend Production Build...
cd frontend
call npm run build
if %ERRORLEVEL% neq 0 (
    echo Frontend build failed!
    cd ..
    exit /b %ERRORLEVEL%
)
cd ..

echo ===================================================
echo  All checks passed successfully!
echo ===================================================
