@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: MediCare AI — Script khoi dong (Windows)
:: Chay tu thu muc medical-rag/
:: ============================================================

if "%1"=="help" goto :show_help
if "%1"==""     goto :show_help

:: ── install ─────────────────────────────────────────────────
if "%1"=="install" (
    echo [1/2] Installing backend dependencies...
    cd backend
    pip install -r requirements.txt
    if errorlevel 1 ( echo [ERROR] Backend install failed && exit /b 1 )
    cd ..

    echo [2/2] Installing frontend dependencies...
    cd frontend
    npm install
    if errorlevel 1 ( echo [ERROR] Frontend install failed && exit /b 1 )
    cd ..

    echo [OK] All dependencies installed.
    goto :end
)

:: ── migrate ──────────────────────────────────────────────────
if "%1"=="migrate" (
    echo Running database migrations...
    cd backend
    python -m alembic upgrade head
    if errorlevel 1 ( echo [ERROR] Migration failed && exit /b 1 )
    cd ..
    echo [OK] Migration complete.
    goto :end
)

:: ── ingest ───────────────────────────────────────────────────
if "%1"=="ingest" (
    echo Ingesting PDF documents into Qdrant...
    cd backend
    python scripts/ingest_pdf.py --folder ./data/pdfs
    if errorlevel 1 ( echo [ERROR] Ingest failed && exit /b 1 )
    cd ..
    echo [OK] Ingest complete.
    goto :end
)

:: ── backend ──────────────────────────────────────────────────
if "%1"=="backend" (
    echo Starting backend server on port 8000...
    cd backend
    python -m uvicorn main:app --reload --port 8000
    goto :end
)

:: ── frontend ─────────────────────────────────────────────────
if "%1"=="frontend" (
    echo Starting frontend server on port 4000...
    cd frontend
    ng serve --port 4000
    goto :end
)

:: ── test ─────────────────────────────────────────────────────
if "%1"=="test" (
    echo Running test suite...
    cd backend
    python -m pytest tests/ -v
    set EXIT_CODE=!errorlevel!
    cd ..
    if !EXIT_CODE! neq 0 (
        echo [FAIL] Some tests failed.
        exit /b !EXIT_CODE!
    )
    echo [OK] All tests passed.
    goto :end
)

:: ── test-cov ─────────────────────────────────────────────────
if "%1"=="test-cov" (
    echo Running tests with coverage report...
    cd backend
    python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html:coverage_html
    set EXIT_CODE=!errorlevel!
    cd ..
    if !EXIT_CODE! neq 0 (
        echo [FAIL] Some tests failed.
        exit /b !EXIT_CODE!
    )
    echo [OK] Coverage report: backend/coverage_html/index.html
    goto :end
)

:: ── check-qdrant ─────────────────────────────────────────────
if "%1"=="check-qdrant" (
    echo Checking Qdrant status...
    cd backend
    python scripts/check_qdrant.py
    cd ..
    goto :end
)

:: ── dev (backend + frontend concurrently) ────────────────────
if "%1"=="dev" (
    echo Starting backend and frontend in separate windows...
    start "MediCare Backend" cmd /k "cd backend && python -m uvicorn main:app --reload --port 8000"
    start "MediCare Frontend" cmd /k "cd frontend && ng serve --port 4000"
    echo [OK] Both servers starting. Backend: http://localhost:8000 | Frontend: http://localhost:4000
    goto :end
)

:: ── Unknown command ───────────────────────────────────────────
echo [ERROR] Unknown command: %1

:show_help
echo.
echo  MediCare AI — Available commands:
echo  ─────────────────────────────────────────────────────────
echo   start.bat install      - Cai dat tat ca dependencies (pip + npm)
echo   start.bat migrate      - Chay Alembic migration (can PostgreSQL)
echo   start.bat ingest       - Ingest PDF vao Qdrant vector DB
echo   start.bat backend      - Khoi dong backend FastAPI (port 8000)
echo   start.bat frontend     - Khoi dong frontend Angular (port 4000)
echo   start.bat dev          - Khoi dong ca backend lan frontend
echo   start.bat test         - Chay pytest test suite
echo   start.bat test-cov     - Chay test voi coverage HTML report
echo   start.bat check-qdrant - Kiem tra Qdrant collection status
echo   start.bat help         - Hien thi help nay
echo.
echo  Requirements:
echo    - Python 3.11+  (backend)
echo    - Node.js 18+   (frontend)
echo    - PostgreSQL     (production DB)
echo    - Qdrant         (vector DB, port 6333)
echo    - .env file tai medical-rag/ (xem README.md)
echo.

:end
endlocal
