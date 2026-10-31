@echo off
rem Executa a coleta no CNES e, somente se ela der certo, gera o painel.
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo === 1/2 Coleta no CNES ===
python scraper.py
if errorlevel 1 (
    echo.
    echo Coleta falhou. O painel nao foi gerado. Veja scraper.log e egressos_erros.txt.
    pause
    exit /b 1
)

echo.
echo === 2/2 Geracao do painel ===
python dashboard_generator.py
if errorlevel 1 (
    echo.
    echo Falha ao gerar o painel.
    pause
    exit /b 1
)

echo.
echo === Auditoria dos dados ===
python auditoria.py
if errorlevel 1 echo Atencao: a auditoria encontrou divergencia entre o painel e os dados. Veja auditoriauditoria.html.

echo.
echo Pronto. Abra dashboard_final.html. A auditoria fica em auditoriauditoria.html (nao publicar).
pause
