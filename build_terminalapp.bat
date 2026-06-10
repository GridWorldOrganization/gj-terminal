@echo off
call "C:\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64
set MSB="C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe"

echo [1/3] Building Settings.Model...
%MSB% "C:\claude_code\dev2\gj-terminal\src\cascadia\TerminalSettingsModel\dll\Microsoft.Terminal.Settings.Model.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:SolutionDir="C:\claude_code\dev2\gj-terminal\\" /v:m /nologo
if errorlevel 1 echo WARNING: Settings.Model had errors, continuing...

echo [2/3] Building TerminalAppLib...
%MSB% "C:\claude_code\dev2\gj-terminal\src\cascadia\TerminalApp\TerminalAppLib.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:SolutionDir="C:\claude_code\dev2\gj-terminal\\" /v:m /nologo
if errorlevel 1 goto :fail

echo [3/3] Building TerminalApp DLL...
%MSB% "C:\claude_code\dev2\gj-terminal\src\cascadia\TerminalApp\dll\TerminalApp.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:SolutionDir="C:\claude_code\dev2\gj-terminal\\" /v:m /nologo
if errorlevel 1 goto :fail

echo SUCCESS
goto :end
:fail
echo FAILED
exit /b 1
:end
