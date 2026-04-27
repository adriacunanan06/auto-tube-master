@echo off
echo ==============================================
echo 🚀 STARTING AUTO-TUBE INSTALLATION AND RUN
echo ==============================================
echo.

echo 1. Installing dependencies (This may take a minute)...
call npm install --no-fund --no-audit

echo.
echo 2. Running the pipeline...
call npm start "5 Money Habits Keeping You Poor"

echo.
echo ==============================================
echo ✅ PROCESS COMPLETE. Check your YouTube Studio!
echo ==============================================
pause
