# evernote-refinery

Evernote 舊資料煉油廠：把 Evernote 匯出的 `.enex` 檔案轉成乾淨、可搜尋、可再加工的 Markdown / JSON / CSV 資料。

## 目前功能

- 串流解析 `.enex`，避免大量筆記造成 OOM。
- 抽出 note metadata：title、created、updated、tags、content。
- 抽出 resource 附件，寫入 `assets/`，並建立 hash 對應表。
- 規範化 Evernote ENML：`en-todo`、`en-media`、`en-crypt`。
- 轉出 Markdown、JSON metadata、CSV index。
- 支援 checkpoint / resume，重跑時可跳過已完成筆記。
- 產生 `summary.json` 對帳報告。
- 單篇 note 匯出失敗時，隔離到 `failed/failures.json`，不中斷後續筆記。
- 產生 JSONL 處理日誌 `export.log`。
- 可產生 synthetic ENEX 測試檔，供本機壓力測試與 smoke test 使用。
- 可建立 local-only SQLite/FTS inventory，支援本機全文搜尋、metadata filters、read-only source audit。

## 安裝與開發

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

## CLI 使用

計算 ENEX 內的筆記數：

```bash
evernote-refinery count path/to/evernote-export.enex
```

匯出 Markdown / JSON / CSV / assets：

```bash
evernote-refinery export path/to/evernote-export.enex --output output/
```

支援斷點續跑：

```bash
evernote-refinery export path/to/evernote-export.enex --output output/ --resume
```

建立本機 SQLite/FTS inventory（只讀取 canonical conversion output，SQLite 寫到指定本機路徑）：

```bash
uv run evernote-refinery inventory build \
  --aggregate-index /home/chahababa/evernote-backup-work/refinery-output-full-20260527-pr10/aggregate_index.csv \
  --canonical-root /home/chahababa/evernote-backup-work/refinery-output-full-20260527-pr10 \
  --output /home/chahababa/.hermes/user-data/evernote-search/evernote_refinery_index.sqlite \
  --read-only-source-check
```

查看 inventory 統計：

```bash
uv run evernote-refinery inventory stats \
  --index /home/chahababa/.hermes/user-data/evernote-search/evernote_refinery_index.sqlite
```

本機搜尋（預設排除 Trash、封存與 sensitive；需要時以 opt-in flag 放寬）：

```bash
uv run evernote-refinery search "客訴 牛肉" \
  --index /home/chahababa/.hermes/user-data/evernote-search/evernote_refinery_index.sqlite \
  --notebook-root HC_營運 \
  --limit 20 \
  --output paths
```

搜尋輸出可選 `paths`、`snippets`、`json`、`markdown`；`query_log` 只記錄 query/filter/result count，不存 note body。

指定處理日誌位置：

```bash
evernote-refinery export path/to/evernote-export.enex --output output/ --log-file output/logs/run.jsonl
```

產生 synthetic ENEX 測試檔：

```bash
evernote-refinery synthetic /tmp/stress.enex --notes 500 --attachments-per-note 1
```

產生 AI Vault v1 local-only prototype（讀取 canonical refinery output；只寫入指定本機輸出資料夾）：

```bash
evernote-refinery ai-vault \
  /home/chahababa/evernote-backup-work/refinery-output-full-20260527-pr10 \
  --output ai-vault-prototype-output \
  --sample-size 50
```

輸出 artifact：

```text
ai-vault-prototype-output/
  main_knowledge_map.json       # 非 Trash 內容的知識地圖（含 source traceability）
  trash_safety_map.json         # Trash 僅輸出 counts / risk categories，不重用內容或標題
  source_index.csv              # 全部來源列 traceability + main/trash_quarantined 狀態
  ai_vault_draft_sample.csv     # 12 欄、20-50 筆 review sample（會先做敏感資訊遮蔽）
  source_readonly_audit.json    # canonical aggregate 檔案 pre/post mtime + sha256
  prototype_summary.json        # 本次 prototype 摘要與安全政策
```

安全邊界：`ai-vault` 子命令不寫 Notion、不啟動 Telegram、不修改 canonical output；Trash 內容只做風險計數，不摘要、不匯入 sample。文字欄位會遮蔽常見 API key/token/JWT/connection string/email 型態，但 prototype 輸出仍需人工 review 後才可進下一階段。

再用同一套 export 流程做本機壓力 smoke test：

```bash
evernote-refinery export /tmp/stress.enex --output /tmp/stress-output --resume
```

## 輸出結構

```text
output/
  assets/                              # 附件
  notes/                               # Markdown 筆記
  metadata/                            # 每篇 note 的 JSON metadata / features
  failed/failures.json                 # 單篇匯出失敗報告；只有失敗時產生
  index.csv                            # 全部成功匯出筆記索引
  summary.json                         # 對帳摘要
  export.log                           # JSONL 處理日誌
  .evernote-refinery-checkpoint.json   # 使用 --resume 時產生
```

`summary.json` 範例：

```json
{
  "total_notes": 1,
  "exported_notes": 1,
  "failed_notes": 0,
  "skipped_notes": 0,
  "expected_attachments": 1,
  "written_attachments": 1,
  "failures": []
}
```

`export.log` 是一行一筆 JSON event，常見事件包含：

```text
export_started
note_exported
note_failed
export_finished
```

## 安全注意

- 原始 `.enex` 不會被修改或刪除。
- `en-crypt` 內容會被安全遮蔽，不輸出原始加密 payload。
- 附件檔名會經過 sanitize，並加上 hash prefix，避免路徑穿越與重名衝突。

## 壓力測試建議

本專案的 parser 使用 `lxml.iterparse` 串流處理 note，並在每篇 note 完成後清理 XML 節點，目標是避免大型 ENEX 一次載入整棵 XML tree。

建議先用 synthetic ENEX 在本機跑 smoke test：

```bash
SMOKE_DIR=$(mktemp -d /tmp/evernote-refinery-stress.XXXXXX)
evernote-refinery synthetic "$SMOKE_DIR/stress.enex" --notes 500 --attachments-per-note 1
evernote-refinery export "$SMOKE_DIR/stress.enex" --output "$SMOKE_DIR/out" --resume --log-file "$SMOKE_DIR/logs/run.jsonl"
python -m json.tool "$SMOKE_DIR/out/summary.json"
python -m json.tool --json-lines "$SMOKE_DIR/logs/run.jsonl" >/dev/null
```

壓力測試時請確認：

- `summary.json` 的 `total_notes`、`exported_notes`、`expected_attachments`、`written_attachments` 符合預期。
- `failed_notes` 為 `0`，或失敗內容有出現在 `failed/failures.json`。
- `export.log` 是合法 JSONL。
- 使用 `--resume` 重跑時，已完成筆記會被 checkpoint 跳過。
