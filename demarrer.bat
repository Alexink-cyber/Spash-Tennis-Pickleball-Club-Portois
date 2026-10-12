@echo off
rem Lance Spash Club sur l'ordinateur du club (Windows).
rem Double-cliquez sur ce fichier. Laissez la fenêtre ouverte pendant l'utilisation.
cd /d "%~dp0"
chcp 65001 >nul

where python >nul 2>nul
if errorlevel 1 (
  echo Python est introuvable. Installez Python 3.11 ou plus recent depuis https://www.python.org/downloads/
  echo et cochez "Add python.exe to PATH" pendant l'installation.
  pause
  exit /b 1
)

if not exist .venv (
  echo Premiere installation, patientez...
  python -m venv .venv || goto :erreur
)
call .venv\Scripts\activate.bat
python -m pip install --disable-pip-version-check -q -r requirements.txt || goto :erreur

if not exist config.toml (
  copy config.exemple.toml config.toml >nul
  echo Un fichier config.toml a ete cree : ouvrez-le pour indiquer l'adresse de votre camera.
  notepad config.toml
)

python -m spash --config config.toml
pause
exit /b 0

:erreur
echo Une erreur est survenue pendant l'installation.
pause
exit /b 1
