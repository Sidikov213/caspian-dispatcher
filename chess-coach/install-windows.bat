@echo off
rem Chess Coach: install dependencies, build, and put a shortcut on the Desktop.
cd /d "%~dp0"
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Download it from https://nodejs.org and run this file again.
  pause
  exit /b 1
)
if not exist node_modules call npm install || goto :fail
call npm run build || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Chess Coach.lnk'));" ^
  "$s.TargetPath=(Join-Path $PWD 'node_modules\electron\dist\electron.exe');" ^
  "$s.Arguments='.'; $s.WorkingDirectory=\"$PWD\"; $s.Description='Chess Coach'; $s.Save()" || goto :fail
echo.
echo Done. The "Chess Coach" shortcut is on your Desktop.
pause
exit /b 0
:fail
echo.
echo Something went wrong - see the messages above.
pause
exit /b 1
