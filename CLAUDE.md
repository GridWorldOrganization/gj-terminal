# gj-terminal プロジェクト ガイド

## ビルド生成物 exe の場所

**メイン実行ファイル:**
```
src/cascadia/CascadiaPackage/bin/x64/Release/gjWindowsTerminal.exe
```

`bin/x64/Release/` (リポジトリルート直下) は shim やテストツールのみ。本体は CascadiaPackage 配下。

**起動:**
```powershell
Start-Process "C:\claude_code\dev2\gj-terminal\src\cascadia\CascadiaPackage\bin\x64\Release\gjWindowsTerminal.exe"
```

## MCP / ApiServer

- デフォルトポート: 9551
- 疎通確認: `mcp__gjwt-mcp__ping`

## ビルドスクリプト

- `build_terminalapp.bat` — TerminalApp DLL ビルド用
