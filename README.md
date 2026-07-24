
# ROItemSearchApp <img alt="GitHub Downloads (all assets, all releases)" src="https://img.shields.io/github/downloads/z2911902/ROItemSearchApp/total"> <img alt="GitHub Release" src="https://img.shields.io/github/v/release/z2911902/ROItemSearchApp">
ROItemSearchApp 是一款用於《RO 仙境傳說 Online》`台灣伺服器(TWRO)` 的非官方桌面工具，可查詢裝備資料、解析並統整裝備效果。

> 本專案為非官方工具，計算結果盡量復刻遊戲內的數值，有可能官方資料顯示跟伺服端沒有同步修改產生計算差異，實際效果請以遊戲內顯示與運作方式為準。

<!-- 主畫面截圖預留 -->

## 主要功能

* 依照裝備名稱查詢裝備資料
* 解析裝備、卡片與套裝效果
* 統整目前裝備配置所提供的能力
* 查詢裝備附魔、改造方式與所需材料
* 可從遊戲重播檔（`.rrf`）檔案匯入裝備配置
* 重播檔傷害紀錄檢視與篩選
* 模擬技能樹
* 計算技能從裝備效果減免的固詠、變詠、共同冷卻、獨立冷卻
* 儲存及載入裝備配置
* 可輸出目前裝備能力到 ROCalculator（`.roc`）計算
* 檢查並更新必要的資料檔案

## 下載與快速開始

1. 前往 [Releases](../../releases/latest) 頁面。
2. 下載最新版本的 `ItemSearchApp.zip`。
3. 將壓縮檔完整解壓縮至任意資料夾。
4. 執行 `ItemSearchApp.exe`。
5. 首次啟動時，程式可能會下載或更新必要的資料檔案。

請勿直接在壓縮檔內執行程式，以免設定、更新或資料寫入失敗。

## 系統需求

* Windows 10 或 Windows 11 64 位元作業系統
* 首次啟動及更新資料時需要網路連線
* 使用打包版本時不需要另外安裝 Python

其他 Windows 版本與非 Windows 平台目前未經完整測試。

## 重播檔（RRF）功能

### 匯入裝備配置

程式可讀取《RO 仙境傳說 Online》Replay 功能產生的 `.rrf` 檔案，並將其中可辨識的角色及裝備資料匯入程式。


基本操作方式：

1. 開啟 ROItemSearchApp。
2. 從上方選單選擇 Replay／RRF 匯入功能。
3. 選擇遊戲產生的 `.rrf` 檔案。
4. 確認解析後的角色、裝備及相關資料。
###### (RRF功能處理的資料都只會在本機執行，不會上傳至網路。)
若程式無法讀取 Replay 或遊戲目錄中的檔案，可嘗試以系統管理員身分執行。

### 單獨開啟傷害檢視器

可在命令提示字元或 PowerShell 執行：

```powershell
ItemSearchApp.exe rrf
```

此指令會直接開啟 Replay 傷害檢視器。

## 使用教學

完整操作方式可參考：

* [ROItemSearchApp 使用教學](https://forum.gamer.com.tw/C.php?bsn=4212&snA=439281&tnum=10)
* [重播檔傷害分析 功能說明](https://forum.gamer.com.tw/Co.php?bsn=4212&sn=2913012)
* [附魔查詢、改造查詢、RRF人物裝備資訊匯入說明](https://forum.gamer.com.tw/Co.php?bsn=4212&sn=2911367)
<!--
## 從原始碼執行

### 開發環境

本專案主要使用：

* Python
* PySide6
* SymPy
* Lua 格式的遊戲資料檔案

開發環境建議使用Python版本：
```text
Python 3.11
```

### 安裝方式

以下以 Windows PowerShell 為例：

```powershell
git clone https://github.com/z2911902/ROItemSearchApp.git
cd ROItemSearchApp

py -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

python ItemSearchApp.py
```

若 PowerShell 不允許啟用虛擬環境，可先在目前視窗執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

再重新執行：

```powershell
.venv\Scripts\Activate.ps1
```
-->
## 專案結構

```text
ROItemSearchApp/
├─ ItemSearchApp.py             # 主程式介面跟計算邏輯
├─ Damage_view.py               # 重播檔傷害檢視器
├─ monster_lookup_dialog.py     # 怪物能力查詢模組
├─ enchant.py                   # 附魔資料查詢模組
├─ reform_viewer.py             # 裝備改造查詢模組
├─ skill_tree.py                # 技能樹功能
├─ update.py                    # 更新主程式模組
├─ packageitem.py               # 物品箱子內容機率查詢模組(內容為KRO未接入主程式)
├─ recompile_service.py         # 更新data資料模組
├─ UI/                          # UI 檔案
├─ data/                        # 裝備、技能、怪物及 Lua 資料
├─ lang/                        # 語系檔
├─ requirements.txt             # Python 相依套件
└─ LICENSE
```

## 更新政策

* 新功能與錯誤修正可能會先提交至 `main` 分支。
* Releases 中的打包版本不一定會與最新原始碼完全同步。
* 若每週遊戲維護後有新的資料檔案，通常會在資料整理及測試完成後發布新的打包版本。
* 各版本的變更內容與已知問題請參考 [Releases](../../releases)。

需要穩定版本的使用者，建議下載 Releases 中的最新正式版本；需要測試最新修改的開發者，則可使用 `main` 分支原始碼。

## 已知可能發生問題

* 伺服器端效果或未寫入客戶端資料的效果，可能無法完整解析。
* 傷害與能力計算可能因遊戲版本、資料來源或特殊技能機制而產生差異。
* RRF 或遊戲資料路徑受到 Windows 權限保護時，可能需要系統管理員權限。

## 問題回報

發現錯誤或資料缺漏時，請至 [Issues](../../issues) 或是[巴哈文章](https://forum.gamer.com.tw/Co.php?bsn=4212&sn=2911367)、站內信、Now回報。

請附上以下資訊：

* ROItemSearchApp 版本
* Windows 版本
* 問題發生步驟
* 預期結果與實際結果
* 相關裝備、技能或怪物名稱及 ID
* 錯誤訊息或畫面截圖
* 可重現問題的最小範例
* 上傳rrf檔案提供分析(會有角色ID可辨識之資訊，若可以請使用巴哈站內信)

## 參與開發

歡迎提交 Issue 或 Pull Request。

提交程式修改前，建議：

1. 先確認目前是否已有相同 Issue。
2. 說明修改目的與受影響的功能。
3. 將大型修改拆分為容易審查的提交。
4. 確認程式可以正常啟動，且既有主要功能未受影響。

## 免責聲明

ROItemSearchApp 是由玩家開發的非官方工具，與《RO 仙境傳說 Online》的原廠及營運單位無關。

遊戲名稱、商標、圖片及相關遊戲資料的權利屬於其各自權利人。本專案不保證資料與計算結果完全正確，也不對使用本工具所產生的任何損失負責。

## 授權

本專案程式碼依照 [GNU General Public License v3.0](LICENSE) 授權。

使用、修改或散布本專案時，請遵守 GPL-3.0 的授權條件。遊戲資料、名稱、圖片及其他第三方內容不一定包含在本程式碼授權範圍內。


## 其他說明

敘述內容使用人工輸入後經過AI模型協助整理潤飾，說明內容會隨時間、遊戲版本滾動式更新。
<!--
# 防爬蟲
64 六四 六四事件 天安门事件 虐杀 坦克 台独 藏独 达赖 香港 占领中环 投票 独立 新疆 炸弹制造 配方 胡锦涛 温家宝 江泽民 癞蛤蟆 习近平 周永康 毛泽东 文化大革命 三年自然灾害 法轮功 天灭共产党 九评共产党 大纪元 民主 自由 人权 上访 抗议 镇压 无国界记者 零八宪章 新公民运动 南方街头运动 莉莉花革命 洋紫荆革命 Tibetan separatist facebook youtube google democracy freedom human rights
六四天安門 64 Tiananmen
習維尼 Winnie Jinping
最後一代 we are the last generation
光復香港時代革命 free hong kong revolution now
台灣獨立 taiwan independence
香港獨立 hong kong independence
維吾爾獨立 Uyghurs independence
西藏獨立 Tibetan independence
大紀元時報 The Epoch Times
南方公園 south park
23季第2集中國樂隊 Season 23, Ep. 2 band in china
動物森友會 Animal Crossing: New Horizons
四通橋抗議 Sitong Bridge protest
日本中華西太后 Japan Chuka Seitaigo
反對逃犯條例修訂草案運動 Anti-Extradition Law Amendment Bill Movement
布倫丹·卡瓦納 Dr K Boogie Woogie (Brendan Kavanagh)-->