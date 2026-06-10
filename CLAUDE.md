# gj-terminal プロジェクト ガイド

## ビルド生成物 exe の場所

**メイン実行ファイル:**
```
src/cascadia/CascadiaPackage/bin/x64/Release/gjWindowsTerminal.exe
```

`bin/x64/Release/` (リポジトリルート直下) は shim やテストツールのみ。本体は CascadiaPackage 配下。

**起動 (MSIX アクティベーション経由 — exe 直叩き厳禁):**
```powershell
Start-Process "shell:AppsFolder\WindowsTerminalDev_8wekyb3d8bbwe!App"
```

`gjWindowsTerminal.exe` は `Windows.FullTrustApplication`。パッケージアイデンティティ必須。
exe を直接 `Start-Process` するとアイデンティティ欠如で起動 3〜5 秒後に `0xC0000409`
(STATUS_STACK_BUFFER_OVERRUN / FAST_FAIL → `terminate`) でクラッシュする。
必ず AppsFolder アクティベーション経由で起動すること。
- PackageFamilyName: `WindowsTerminalDev_8wekyb3d8bbwe`
- AppId: `App`
- パッケージ未登録時: `Add-AppxPackage -Register "...\CascadiaPackage\bin\x64\Release\AppxManifest.xml"`

## MCP / ApiServer

- デフォルトポート: 9551
- 疎通確認: `mcp__gjwt-mcp__ping`

## ビルドスクリプト

- `build_terminalapp.bat` — TerminalApp DLL ビルド用
