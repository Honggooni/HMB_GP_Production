@echo off
setlocal

tasklist /FI "IMAGENAME eq griptape-nodes-desktop.exe" /FO CSV /NH 2>NUL | find /I "griptape-nodes-desktop.exe" >NUL
if not errorlevel 1 (
    echo [HMB Agent] Close the running Griptape Desktop process, then run this launcher again.
    exit /b 1
)

set "HMB_AGENT_POLICY_PROCESS_BOOTSTRAP=1"
set "HMB_GRIPTAPE_EXE=%LOCALAPPDATA%\ai.griptape.nodes.desktop\current\griptape-nodes-desktop.exe"
if not exist "%HMB_GRIPTAPE_EXE%" (
    echo [HMB Agent] Griptape Desktop is not installed at the supported location.
    exit /b 2
)

for %%I in ("%HMB_GRIPTAPE_EXE%") do set "HMB_GRIPTAPE_DIR=%%~dpI"
pushd "%HMB_GRIPTAPE_DIR%" || exit /b 3
rem Run the Desktop executable directly from this command process. Using START
rem can delegate GUI activation through Explorer, which drops the one-process
rem policy bootstrap marker before the application engine is created.
"%HMB_GRIPTAPE_EXE%"
set "HMB_GRIPTAPE_EXIT=%ERRORLEVEL%"
popd
exit /b %HMB_GRIPTAPE_EXIT%
