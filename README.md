# 北科選課助手（雛形）＋ 先搶先贏選課代理人模擬

資料來源：[北科課程好朋友](https://ntut-course.gnehs.net/) 的爬蟲資料
（[gnehs/ntut-course-crawler-node](https://github.com/gnehs/ntut-course-crawler-node)，gh-pages 分支）。

## 快速開始
```bash
python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' ortools numpy pandas pytest httpx
scripts/fetch_data.sh 115 1 114 2 114 1 113 2 113 1 112 2 112 1 111 2 111 1 110 2 110 1   # 取得資料（含 5 年歷史）
.venv/bin/python -m backend.sim.calibrate --year 115 --sem 1   # 校準課程吸引力 α
.venv/bin/python -m backend.sim.run --seeds 10 --out reports/sim_115_1.json
.venv/bin/python -m backend.sim.run --seeds 10 --mechanism fcfs --out reports/sim_115_1_fcfs.json
.venv/bin/python -m backend.sim.sensitivity               # 本系優先 × 加簽 × 名額 × 跨系成本
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

## 北科選課制度（模擬器預設，`backend/sim/mechanisms/ntut.py`）
- 第 1 週：本系開的課只有本系生能選；通識/博雅第一天全校開放。第 2 週：全校開放。共 14 天。
- 先到先得；滿額可申請加簽（老師同意後 1–3 天生效，上限 名額×1.23）；有人退選才釋出名額，其他人要回來刷。
- 學生拿到更喜歡的課時會退掉較不喜歡的課（內生退選）。
- 純搶課對照：`--mechanism fcfs`。關掉本系優先/回訪/加簽時，北科模型重現純 FCFS（已驗證）。

## 名額（無法向教務處取得時）
優先序：教師在系統回報 → 備註「限N人」→ 近 5 年同課同師的重複天花板（÷ 偏誤係數 1.093，
由備註上限的課交叉校正）→ 教室/歷史最大人數（低可信度）。

**資料證據**：113-1～115-1 有備註上限的 673 門課中，57% 達到上限，達到者多數超額，
超額中位數為上限的 22.7% → 加簽很普遍；模擬的加簽上限即取此值。（備註有上限的課可能不具代表性。）

## 模型假設（請批判性閱讀）
1. 母體：只有大學部本班學生（約 5,400 人）；研究所、進修部、跨校生未模擬。
2. 必修預排；博雅課（資料標為 △）視為可自由選擇的通識；`people==0` 的課視為停開。
3. 效用：`U = α_c + 系所興趣 − 跨系成本 + 年級相符 − 早八/夜間厭惡 + 英語偏好 + Gumbel`。
   **跨系成本 1.5 是無資料可估的先驗**；0/1.5/3 的敏感度分析顯示結論方向一致。
4. α 以歷史人數校準（滿額課右設限）。歷史人數已被名額截斷，模型**低估競爭**。
5. 驗證：預測各課人數明顯輸給「沿用上學期人數」（MAE 17.3 vs 10.2）→ 只用於比較制度的方向。

## 主要發現（115-1，10 seeds）
- 本系優先一週幾乎消除「手速」對結果的影響（ρ：純搶課 −0.14 → 北科 −0.02）。
- 代價：想修他系課的學生效用略降（99.5% → 98.9%），且前 10% 學生需登入約 20 次刷退選名額（純搶課 1 次）。
- 加簽同意率越高，外系生的損失越小。
- 各情境效用差距都很小（零點幾個百分點），請看方向而非幅度。

## Windows 本機執行（最簡單）
1. 安裝 Python 3.11–3.13：https://www.python.org/downloads/ （安裝時勾選 **Add python.exe to PATH**）。
2. 在 GitHub 頁面按綠色 **Code → Download ZIP**，解壓縮。
3. 雙擊資料夾裡的 **`start.bat`**。第一次會自動安裝套件（1–3 分鐘），完成後瀏覽器會打開 http://localhost:8000 。
4. 要停止網站，關掉那個黑色視窗即可。

不需要 Node.js（前端已預先建置在 `frontend/dist/`），也不需要下載原始資料：
`data/snapshot/115_1.json.gz` 內含 115-1 全部課程（已推估名額），`reports/` 內含預先算好的模擬結果。
只有要重新校準或重跑模擬時，才需要用 Git Bash 執行 `scripts/fetch_data.sh` 取得完整資料，
之後 `python -m scripts.build_snapshot 115 1` 可更新快照。

## 下一步
- 用加退選期間的時間序列（若可取得）估計未截斷需求，改善競爭程度的低估。
- 志願序＋抽籤、Course Match 等機制比較。
- LLM 代理人：實作 `backend/sim/agents.py::LLMAgent.wishlist()`。
- 教師回報名額目前無身分驗證；正式上線需接學校 SSO。
