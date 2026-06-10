---
name: gjwt-control
description: gj-terminal (gjWindowsTerminal) を外部制御するスキル。MCP ツール gjwt-mcp__*
  で send_text/get_buffer/list_tabs/タブ色/ウィンドウ操作を行う。RPC は 127.0.0.1:9551 の
  ApiServer。port=0 で全ウィンドウscan。
---

# gjwt-control — gj-terminal 外部制御スキル

このスキルは、gj-terminal フォーク（gjWindowsTerminal）に組み込まれた外部制御 API を
Claude Code から MCP 経由で操作する手順をまとめたもの。

## 前提
- gj-terminal がビルド済みで、MCP サーバ `gjwt-mcp` が接続されていること
- ApiServer がポート **9551** で起動していること（多重起動時は +1 ずつ繰り上がり）

## 概要
gjwt-control は以下の MCP ツール群を提供する:
- send_text, get_buffer, get_viewport, get_selection
- list_tabs, new_tab, close_tab, focus_tab, rename_tab
- list_windows, focus_window, window_action（最大化/最小化/復元）
- get_scroll_state, get_font_size, set_font_size, get_tab_color, set_bar_color
- get_window_rect, set_window_rect, ping

## アーキテクチャ
- **ApiServer** … `TerminalApp.dll` 内の TCP JSON-RPC サーバ。`127.0.0.1:<port>` で 1 行 1 JSON。
  リクエスト `{"id":N,"method":"...","params":{...}}` → レスポンス `{"id":N,"result":...}`
  または `{"id":N,"error":"..."}`。
- **ポート** … 既定 9551。バインド失敗時は +1 ずつ +15 までフォールバック。
  「タブを新ウィンドウへ移動」で生成された 2 つ目のウィンドウは 9552 を取る、という具合に
  各ウィンドウが自前のポートを持つ（`SO_EXCLUSIVEADDRUSE` で横取り防止）。
- **UI スレッド実行** … バッファ読取やタブ操作は CoreDispatcher 経由で UI スレッドに
  ディスパッチされる（`_RunOnUI`）。`_stop` 連動ポーリングで shutdown 時もデッドロックしない。

## 接続確認
- `ping(host=127.0.0.1, port=9551)` → `{ok: bool, detail: ...}`。
  `ok:true` なら ApiServer 到達可能（`detail` に未知メソッド応答が入っても疎通は OK の証拠）。

## タブの指定方法
ほとんどのツールは対象タブを取る:
- `tab`（数値インデックス, 0 始まり）
- `tab_name`（タブ名）… 指定時は名前解決が優先。add/close でインデックスがずれても
  安定して同じタブを指せる。

## ツールリファレンス

### テキスト I/O
- `send_text(tab, text)` … タブの端末へ文字列を送信（常に Enter 付与）。
- `get_buffer(tab, lines=50)` … スクロールバック全体から末尾 `lines` 行を取得。
  `{lines:[...], total_rows:N}`。孤立サロゲートは除去して UTF-8 化。
- `get_viewport(tab)` … 現在の可視範囲のみ取得 `{lines, scroll_offset, view_height, ...}`。
- `get_selection(tab, trim=true)` … 選択テキスト `{has_selection, text}`。

### スクロール / フォント
- `get_scroll_state(tab)` … `{scroll_offset, view_height, buffer_height, at_bottom,
  scrolled_back_rows}`。
- `get_font_size(tab)` / `set_font_size(tab, size)` … フォントサイズ取得・設定（pt）。

### タブ操作
- `list_tabs(port=0)` … **port=0（既定）で全ウィンドウ横断**。
  `{tabs:[{port, index, title}, ...]}`。各エントリにポートが付くので対象ウィンドウを特定可能。
  `port=N` で単一ウィンドウのみ `{count, tabs:[{index, title}]}`。
- `new_tab()` … 新規タブ。
- `close_tab(tab)` … タブを閉じる（tab>=0 か tab_name 必須）。
- `focus_tab(tab)` … タブを選択（tab>=0 か tab_name 必須）。
- `rename_tab(tab, title)` … タブ名を変更。
- `get_tab_color(tab)` / `set_bar_color(tab, color)` … タブ色取得・タブバー色設定（hex）。

### ウィンドウ操作
- `list_windows()` … ポート走査で全 gj-terminal ウィンドウを列挙。
- `focus_window()` … ウィンドウを前面化（Summon）。
- `window_action(action)` … `maximize` / `minimize` / `restore` / `normal`。
- `get_window_rect()` … `{x, y, width, height, maximized, minimized}`。
- `set_window_rect(x, y, width, height)` … ウィンドウの位置・サイズ変更。

## マルチウィンドウ
- 既定の `list_tabs`（port=0）は 9551〜9566 を走査して全ウィンドウのタブを返す。
- 特定ウィンドウだけ操作したい場合は、`list_tabs` 結果の `port` を各ツールに渡す。

## 起動（重要）
`gjWindowsTerminal.exe` は `Windows.FullTrustApplication`。**exe 直叩き厳禁**
（パッケージアイデンティティ欠如で起動直後に `0xC0000409` クラッシュ）。MSIX 経由で起動:
```powershell
Start-Process "shell:AppsFolder\WindowsTerminalDev_8wekyb3d8bbwe!App"
```
詳細は リポジトリ直下 `CLAUDE.md` / `doc/building-gj-terminal.md`、調査記録は
GridWorldOrganization/gj-terminal#6 を参照。

## トラブルシューティング
- `ping` が `ok:false` … ApiServer 未起動。MSIX 経由で gj-terminal を起動し直す。
- `list_tabs` が空 … ウィンドウ未起動、またはポートが 9551〜9566 の外。
- 操作が無反応 … 対象 `tab` のインデックスがずれている可能性。`tab_name` で指定し直す。
