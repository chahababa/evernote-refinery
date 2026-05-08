# evernote-refinery

Evernote 舊資料煉油廠：把 Evernote 匯出的 `.enex` 檔案轉成乾淨、可搜尋、可再加工的 Markdown / JSON / CSV 資料。

## MVP 範圍

- 串流解析 `.enex`，避免大量筆記造成 OOM。
- 抽出 note metadata：title、created、updated、tags、content。
- 抽出 resource 附件 metadata 與二進位內容。
- 後續 Sprint 會加入 Evernote HTML 規範化、Markdown / JSON / CSV writer、checkpoint。

## 開發

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```
