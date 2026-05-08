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

指定處理日誌位置：

```bash
evernote-refinery export path/to/evernote-export.enex --output output/ --log-file output/logs/run.jsonl
```

產生 synthetic ENEX 測試檔：

```bash
evernote-refinery synthetic /tmp/stress.enex --notes 500 --attachments-per-note 1
```

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
