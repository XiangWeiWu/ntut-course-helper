# 北科選課助手（雛形）＋ 先搶先贏選課代理人模擬

資料來源：[北科課程好朋友](https://ntut-course.gnehs.net/) 的爬蟲資料
（[gnehs/ntut-course-crawler-node](https://github.com/gnehs/ntut-course-crawler-node)，gh-pages 分支）。

## 快速開始
```bash
python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' ortools numpy pandas pytest httpx
scripts/fetch_data.sh 115 1 114 2 114 1 113 2 113 1     # git sparse checkout 取得資料
.venv/bin/python -m backend.sim.calibrate --year 115 --sem 1   # 校準課程吸引力 α
.venv/bin/python -m backend.sim.run --seeds 10 --out reports/sim_115_1.json
.venv/bin/python -m backend.sim.sensitivity               # 吞吐量 × 名額 敏感度
.venv/bin/python -m backend.sim.validate                  # 114-1 校準 → 115-1 hold-out 驗證
(cd frontend && npm install && npm run build)
.venv/bin/uvicorn backend.api.main:app --port 8000        # http://localhost:8000
.venv/bin/python -m pytest -q tests
```

## 架構
| 路徑 | 內容 |
|---|---|
| `backend/ingest/load.py` | 讀取資料、班級解析、**名額推估** |
| `backend/domain/` | 節次位元遮罩（衝堂 = `a & b`）、課程類別 |
| `backend/recommend/solver.py` | CP-SAT 自動排課（不衝堂、學分範圍、必修、k 組解） |
| `backend/sim/` | 母體、隨機效用、代理人介面、FCFS 離散事件、指標、校準、驗證 |
| `backend/api/main.py` | FastAPI |
| `frontend/` | React：學生查課排課／教授需求預測與必修節次熱圖／模擬儀表板 |

## 已用真實資料查證的事項
- 節次值：`1 2 3 4 N 5 6 7 8 9 A B C D`（115-1 全部課程統計）。
- **沒有人數上限欄位**（115-1 全部 2444 門課的欄位皆已列舉，`extras` 為空）。`people` = 選課人數。
- courseType：○ 部訂共同必修、△ 校訂共同必修、☆ 共同選修、● 部訂專業必修、▲ 校訂專業必修、★ 專業選修
  （由 `standard.json` 的學分欄位與實例交叉比對）。
- 課綱檔含教師 email，本系統**不讀取也不顯示**。

## 模型假設（請批判性閱讀）
1. **名額**：備註「限N人」(120 門) → 教室歷史最大人數 → 同課號歷史最大 → 預設。後兩者可能高估。
2. **母體**：只有大學部「本班」學生（約 5,400 人，由必修課人數中位數推得）；研究所、進修部、跨校生未模擬，
   但他們占用的名額也算在觀察人數中 → 模擬需求偏低。
3. **必修預排**，只有選修進入搶課；`people==0` 的課視為停開排除。
4. **效用**：`U = α_c + 系所興趣 + 年級相符 − 早八/夜間厭惡 + 英語偏好 + Gumbel`；β 為先驗設定、未估計。
5. **α 校準**：對數差收縮映射；已滿的課只往上推（右設限）。但因觀察值本身受名額截斷，
   校準後的需求幾乎貼著名額 → 模擬中的競爭程度很可能**低估**（基準效用達成率 99.5% 應這樣解讀）。
6. **FCFS**：對數常態到達、k 個 worker 的 FIFO 伺服器、逾時重送、學生看得到「已滿」不送出。
7. 北科實際選課規則（是否 FCFS、優先順序）**未查證**；機制以介面抽換。

## 目前結果（115-1，10 seeds）
- 第一志願取得率 73.5%（95% 區間 72.6–74.5%），到達時間與效用 Spearman ρ = −0.19。
- 敏感度：伺服器吞吐越低，大量逾時重送使結果近似隨機，ρ 趨近 0（「當機反而比較公平」，但代價是巨量逾時）；
  名額 ×0.8 時 ρ 降到 −0.35，手速影響變大。
- Hold-out 驗證：模擬 MAE 11.35 / ρ 0.715 vs 「沿用上學期人數」基準 MAE 11.69 / ρ 0.716 → **預測力與天真基準持平**。
  本模型的價值是反事實的機制比較，不是人數預測。

## 下一步
- 名額：向教務處取得真實上限，或爬選課系統的「人數上限」。
- 用加退選期間的時間序列（若可取得）估計需求，而非截斷後人數。
- 機制：志願序＋抽籤、點數競標、Course Match（A-CEEI），在同一批代理人上比較。
- LLM 代理人：實作 `backend/sim/agents.py::LLMAgent.wishlist()`，抽樣比較與效用模型的志願分布差異。
