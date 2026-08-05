@echo off
set "MAYAPY=C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe"
if not exist "%MAYAPY%" (
  echo Maya 2024 mayapy was not found:
  echo %MAYAPY%
  pause
  exit /b 1
)
"%MAYAPY%" "%~dp0HMBVideoPicker_Test_8Objects.py" "%~dp0HMBVideoPicker_Test_8Objects.mb"
if errorlevel 1 (
  echo Test scene creation failed.
  pause
  exit /b 1
)
echo Created: %~dp0HMBVideoPicker_Test_8Objects.mb
pause
