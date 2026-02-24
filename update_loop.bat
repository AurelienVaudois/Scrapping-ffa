@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\update.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "VENV_ACTIVATE=%SCRIPT_DIR%venv\Scripts\activate.bat"
if not exist "%VENV_ACTIVATE%" set "VENV_ACTIVATE=%SCRIPT_DIR%..\.venv\Scripts\activate.bat"

if not exist "%VENV_ACTIVATE%" (
	echo [ERREUR] Environnement virtuel introuvable.>> "%LOG_FILE%"
	echo Cherche: "%SCRIPT_DIR%venv" puis "%SCRIPT_DIR%..\.venv"
	exit /b 1
)

call "%VENV_ACTIVATE%"
if errorlevel 1 (
	echo [ERREUR] Impossible d'activer l'environnement virtuel.>> "%LOG_FILE%"
	exit /b 1
)

echo [INFO] ===== Debut update %date% %time% =====>> "%LOG_FILE%"
python "%SCRIPT_DIR%update_athletes.py" --loop --delay 600 --batch 10 >> "%LOG_FILE%" 2>&1
echo [INFO] ===== Fin update %date% %time% =====>> "%LOG_FILE%"

endlocal
