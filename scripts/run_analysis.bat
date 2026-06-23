@echo off
rem Refresh progress.png, occam.png, and score_alignment.png from results.tsv
setlocal
cd /d "%~dp0\.."
jupyter nbconvert --to notebook --execute analysis.ipynb --output analysis.ipynb
if errorlevel 1 exit /b 1
echo Charts: progress.png, occam.png, score_alignment.png
