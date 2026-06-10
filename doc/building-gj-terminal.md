# GJ Terminal ビルド手順

GridWorld fork (gj-terminal) のローカルビルド＆サイドロード手順。

## 前提条件

| コンポーネント | 場所 | 備考 |
|---|---|---|
| Build Tools (UWP ワークロード付き) | `C:\BuildTools` | `C:\Program Files (x86)\...` 側は UWP 未対応 |
| Windows SDK 10.0.22621.0 | `C:\Program Files (x86)\Windows Kits\10` | |
| NuGet | `dep/nuget/nuget.exe` | リポジトリ同梱 |
| Python 3.10+ | PATH | gjwt-mcp ビルド用 |

> **注意**: `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools` は
> UWP/XAML ワークロード (`WindowsXaml`) が存在しないためビルド失敗する。
> 必ず `C:\BuildTools` を使うこと。

## ビルド手順

### 1. NuGet パッケージ復元

```cmd
C:\BuildTools\Common7\Tools\VsDevCmd.bat -arch=x64
dep\nuget\nuget.exe restore dep\nuget\packages.config -PackagesDirectory packages
```

> `OpenConsole.slnx` の nuget restore は slnx 形式非対応のためスキップ。
> `packages.config` のみ復元すれば十分。

### 2. MSBuild でビルド

```cmd
"C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe" OpenConsole.slnx ^
    /p:Configuration=Release /p:Platform=x64 ^
    /m /v:m /nologo
```

- `/m` — 並列ビルド（CPU コア数に応じて自動調整）
- `/v:m` — 最小ログ出力
- 初回ビルド時間: 約 20〜40 分（IPDB なしのフルコンパイル）

### 3. ワンライナー（cmd スクリプト）

`C:\Temp\build_wt2.cmd` に以下を保存して実行:

```cmd
call "C:\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64
"C:\claude_code\dev2\terminal\dep\nuget\nuget.exe" restore "C:\claude_code\dev2\terminal\dep\nuget\packages.config" -PackagesDirectory "C:\claude_code\dev2\terminal\packages"
"C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe" "C:\claude_code\dev2\terminal\OpenConsole.slnx" /p:Configuration=Release /p:Platform=x64 /m /v:m /nologo
```

## デプロイ（サイドロード）

ビルド完了後、MSIX パッケージを Windows に登録:

```powershell
# 既存パッケージを削除（初回は不要）
Get-AppxPackage -Name "WindowsTerminalDev" | Remove-AppxPackage

# サイドロード（C:\claude_code\dev2\terminal は junction → 実パスを使うこと）
Add-AppxPackage -Register "C:\claude_code\dev2\gj-terminal\src\cascadia\CascadiaPackage\bin\x64\Release\AppxManifest.xml"
```

### デスクトップショートカット作成

```powershell
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$env:USERPROFILE\Desktop\GJ Terminal.lnk")
$shortcut.TargetPath = "shell:AppsFolder\WindowsTerminalDev_8wekyb3d8bbwe!App"
$shortcut.Save()
```

## ビルド出力確認

| 成果物 | パス |
|---|---|
| wt.exe | `bin\x64\Release\wt.exe` |
| WindowsTerminal.exe | `bin\x64\Release\OpenConsole.exe` |
| CascadiaPackage | `src\cascadia\CascadiaPackage\bin\x64\Release\` |

## gjwt-mcp Python ツール

```powershell
# 開発用インストール（editable）— .exe ロック中は --no-scripts 付きで
pip install -e tools\wt-agent-harness
# または .exe がロックされている場合（MCP サーバー起動中）:
# .py の変更は editable install のため即反映済み、再インストール不要
```

## トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| `Microsoft.Windows.UI.Xaml.Cpp.targets が見つかりません` | `C:\Program Files (x86)\...BuildTools` を使用 | `C:\BuildTools` の VsDevCmd を使う |
| `gjwt-mcp.exe — 別プロセスが使用中` | MCP サーバー起動中に pip が .exe 上書き試行 | Claude Code を閉じてから再インストール、または editable install のまま使用 |
| `nuget: Invalid input 'OpenConsole.slnx'` | nuget が slnx 非対応 | `packages.config` のみ restore でよい |
| `0x800701C0: 信頼されていないマウントポイント` | `C:\claude_code\dev2\terminal` はジャンクション | 実パス `C:\claude_code\dev2\gj-terminal\...` を使う |

## GJ ブランディング変更点

GJ Terminal は上流の Windows Terminal から以下の名称変更を行っている。**git 管理対象。無断変更禁止。**

| 変更箇所 | 上流値 | GJ 値 | ファイル |
|---|---|---|---|
| 実行ファイル名 | `WindowsTerminal.exe` / `wt.exe` | `gjWindowsTerminal.exe` / `gjwt.exe` | `Package.appxmanifest`, `wt.vcxproj` など |
| 優先 PowerShell プロファイル名 | `PowerShell` | `gj-PowerShell` | `src/cascadia/TerminalSettingsModel/PowershellCoreProfileGenerator.cpp:25` |

### 注意: パッケージ再インストール後の settings.json

`Remove-AppxPackage` → `Add-AppxPackage -Register` でパッケージを再登録すると
`LocalState/settings.json` がリセットされる場合がある。
その際は以下で `gj-PowerShell` に戻すこと:

```powershell
$path = "$env:LOCALAPPDATA\Packages\WindowsTerminalDev_8wekyb3d8bbwe\LocalState\settings.json"
(Get-Content $path -Raw) -replace '"name": "PowerShell"', '"name": "gj-PowerShell"' |
    Set-Content $path -NoNewline
```
