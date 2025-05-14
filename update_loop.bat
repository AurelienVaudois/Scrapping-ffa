@echo off
:: active l’environnement virtuel
call %~dp0venv\\Scripts\\activate.bat
:: lance la boucle avec log horodaté
python %~dp0update_athletes.py --loop --delay 600 >> %~dp0logs\\update.log 2>&1
