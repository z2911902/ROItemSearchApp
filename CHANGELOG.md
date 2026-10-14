# ROItemSearchApp 更新紀錄

- [專案首頁](https://github.com/z2911902/ROItemSearchApp)
- [GitHub Releases](https://github.com/z2911902/ROItemSearchApp/releases)
- [BUG回報/建議提供](https://forum.gamer.com.tw/C.php?bsn=4212&snA=439281) 巴哈文章內留言/站內信/NOW

## 正式發布紀錄（最新至最早）

### [v0.8.21-261006](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.8.21-261006)

- 修改角色預設等級跟職業等級。
- 忽略windows UI的字體大小調整，只使用程式預設以防UI錯位。 
- 新增忍者符咒增傷。
- 傷害歷程UI更新，新增體種屬階之前 前後ATK/MATK的組成來源，增加增傷流程圖。
- 下載主程式更新使用Cloudflare CDN來源。


### [v0.8.14-260930](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.8.14-260930)

- 修正高階拳刃修煉的相乘位置。
- 傷害檢視器加入框選傷害範圍、可拖曳時間軸及小地圖。
- 同一 Lua 物品 ID 重複時，以最後一筆資料作為顯示內容。
- 加入深色／淺色 UI 設定。
- 修正取得 data 檔案時的大小寫問題。


### [v0.8.7-260911](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.8.7-260911)

- 修正 DP 站 API 怪物 JSON 的取得方式。
- 補足 RRF 轉換模組對部分普通攻擊封包的解析。
- 傷害檢視器新增左手普通攻擊傷害顯示。

### [v0.8.3-260906](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.8.3-260906)

- 移除 Selenium 模組。
- 將 RRF 轉換從外部 EXE 呼叫改為 Python 相容模組。
- 修正特殊增傷百分比顯示及物品查詢對自身技能的處理順序。
- 修正隱藏物理／魔法設定只影響效果展示、不影響最終計算。
- 擴充多裝備比較的總效果欄位。
- 部署 Web 介面。

**當版已知問題／限制：**
- 當版曾有部分普攻 ID 配對遺漏、DP API 怪物資料取得異常。

### [v0.7.19-260830](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.7.19-260830)

- 更新計算核心的破防公式。
- 修正裝備取得角色技能等級時能力數值被意外清空。

**當版已知問題／限制：**
- 當版仍有部分 GetSkillLevel 無法正確取得技能等級的問題。

### [v0.7.17-260816](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.7.17-260816)

- 將主程式計算核心分離為模組，改善 UI 回應速度。
- 優化 Git 檔案取得網址。

### [v0.5.10-260809](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.5.10-260809)

- 調整函數語法輸入視覺化及選取邏輯。
- 新增多專案裝備能力比較。
- 特性素質點數改採公式計算，而非固定清單。

### [v0.5.4-260803](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.5.4-260803)

- 自訂物品說明改為取代既有說明，而非略過。
- 新增附加能力附魔查詢。
- 補足函數選單中遺漏的項目。
- 更新主程式必要檔案檢查清單。

### [v0.4.4-260726](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.4.4-260726)

- 修正 HP/SP 基礎值取得的等級範圍。
- 調整部分輸入框變更的觸發條件。
- RRF 物品名稱及效果改由主程式提供給解析器。
- 新增「靈氣劍」增傷計算區段。
- 支援輸入人物面板 HP/SP 後反推基礎值。
- 新增目前物品連結至 DP 網站的按鈕。
- 可選擇載入 KRO 物品。

### [v0.3.22-260723](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.22-260723)

- 傷害檢視器加入攻擊方篩選及敵方狀態 ID。
- 新增天帝融合爆擊、溫暖風轉屬與跆拳加油／奇蹟／憎惡增傷判定。
- 修正 GRF 0x200 格式下可能因編譯環境造成的路徑解析失敗。

### [v0.3.18-260710](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.18-260710)

- 修正敵方 DEF／MDEF 為零時減傷比例異常超過 100%。
- 修正 RES、DEF 變更後未正確重算，以及種族物理運算子截斷。
- 附魔查詢工具與主程式連動，依已裝備物品顯示附魔按鈕。
- 修正依角色技能等級給予的能力被錯誤設為零。

### [v0.3.14-260707](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.14-260707)

- 新增可用語法關鍵字篩選的詞條輸入方式。
- 新增 UI 縮放設定。
- 調整載入 JSON 時清空 map 的先後順序。
- 修正傷害計算中屬性、種族、階級變動後不觸發更新。

### [v0.3.10-260630](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.10-260630)

- 改善減傷資訊的 UI 顯示。
- 技能公式支援覆寫敵方體型數值。
- 修正武器精煉 +16 以上的加成。
- 裝備階級下拉選單不再因滑鼠滾輪誤觸改值。

### [v0.3.5-260622](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.5-260622)

- 修正詠唱秒數計算公式。
- 更新鞭子對大型敵人的武器體型修正（50% → 75%）。
- 新增減傷分頁及初步減傷解析（當時屬測試功能）。

**當版已知問題／限制：**
- 當版終初技能「螺旋刺擊 Max」仍須手動調整敵方體型。

### [v0.3.3-260606](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.3-260606)

- 修正近傷計算時後遠傷值未初始化而導致計算中斷。

**當版已知問題／限制：**
- 當版仍記錄螺旋刺擊 Max、詠唱／延遲取整、部分 RRF 解析不完整等問題。

### [v0.3.1-260529](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.3.1-260529)

- 新增後遠傷區段判斷。
- RRF 角色名稱含特殊符號時，自動轉換為全形。

**當版已知問題／限制：**
- 當版近傷／後遠傷初始化仍有已知問題。

### [v0.2.8-260502](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.2.8-260502)

- 調整函數的物理、魔法排序。
- 函數清單新增取得角色裝備狀態。
- 修正儲存設定後的設定檔路徑錯誤。
- 更新 GRF 工具版本。

### [v0.2.5-260421](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.2.5-260421)

- 修正魔物技能同名時技能公式顯示錯誤。
- 右手裝備雙手武器時，自動清除並隱藏左手配置。
- 新增裝備分頁「快速定位」按鈕。
- 新增守護神盾可抵禦傷害計算。
- 調整料理轉換及 AGI 總值對應 temp 的邏輯。

### [v0.2.0-260412](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.2.0-260412)

- 新增傷害表／物品掉落檢視器。
- 修正附魔工具在指定升階時誤顯示隨機附魔材料。
- 主選單「遊戲資訊」改名為「工具」。

### [v0.1.54-260409](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.54-260409)

- RRF 匯入支援辨識角色現有 Buff、自動勾選並保存至 JSON。
- 新增敵方狀態「天怒」。
- 修正神威的計算位置。

### [v0.1.50-260402](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.50-260402)

- 修正左右手精煉欄位為空時造成計算中斷。
- 合併「檢查主程式更新」與「檢查物品職業技能資料更新」指令。

### [v0.1.48-260315](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.48-260315)

- 新增星座塔防禦星數／亡魂顆數減傷計算。
- 修正 EP19 符文物品敘述缺失導致無法選擇。

### [v0.1.46-260303](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.46-260303)

- 修正傷害最小值被最大值取代。
- 優化總效果清單顯示。

### [v0.1.45-260302](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.45-260302)

- 新增機甲被動技能對魔物屬性的增傷判斷。
- RRF 轉換支援四轉以下角色及角色 ID 顯示。
- 調整資料檔案過期判斷。
- 修正無視 RES 的破防上限。

### [v0.1.42-260227](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.42-260227)

- 新增技能半無視 DEF、無視 RES、砲彈 ATK 等判定選項。
- 新增傷害最大值／最小值顯示，以及砲彈 ATK 公式。

### [v0.1.39-260209](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.39-260209)

- 優化自動更新的版本判斷。
- 新增技能觸發時更改技能爆擊條件。
- 新增 GetPureJob 語法解析。

### [v0.1.38-260202](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.38-260202)

- 新增傷害歷程顯示。
- 修正怪物 API 的屬性套用問題。
- 更新 JobLv 60 加成點數及技能優化 4.1／4.2 資料。
- 修正部分技能爆擊判定。

### [v0.1.36-260127](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.36-260127)

- 修正物理種族破防公式。

### [v0.1.35-260126](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.35-260126)

- 修正部分技能沒有共同延遲時無法計算。
- 修正 GetEquipWeaponLv(部位) 的解析。

### [v0.1.33-260123](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.33-260123)

- 測試新增 DP 站怪物查詢 API（須 DP API Key）。
- 新增 ASPD 計算。
- 新增固定詠唱、變動詠唱、共同延遲、技能冷卻計算。

### [v0.1.30-260120](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.30-260120)

- 調整計算觸發流程。
- 新增武器浸透勁效果及等級 261–275 特性點數。
- 新增命中增傷相關詞條，須重新載入 EnchantName.lua。

**當版已知問題／限制：**
- 當版命中增傷與爆傷增傷僅能擇一判定。

### [v0.1.27-260117](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.27-260117)

- 調整計算邏輯。
- DEF／MDEF 顯示順序配合遊戲人物面板。

### [v0.1.26-260117](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.26-260117)

- 修正全種族／指定種族破防公式。
- 新增自動更新主程式功能。
- 優化計算資訊顯示。
- 新增命中增傷區段。

### [v0.1.22-260110](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.22-260110)

- 新增命中傷害增傷區段（當時台服尚未實裝）。
- RRF 匯入新增重複裝備區域提示。

### [v0.1.21-260105](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.21-260105)

- 依武器類型自動選擇近距離／遠距離傷害。
- 修正永恆斬、隕石術猛擊、新霜凍術、地面重力、念力連擊等技能特殊判定。

### [v0.1.20-251228](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.20-251228)

- 技能公式可依主動／被動狀態切換。
- 選取裝備時在說明下方顯示可觸發的套裝清單。
- 部分主動 Buff 移至增益技能／料理分頁。

### [v0.1.19-251223](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.19-251223)

- 新增心神凝聚對角色、裝備、被動素質加成的自動計算。

### [v0.1.18-251216](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.18-251216)

- 新增龍之氣息計算區段及各職業 201–260 級 HP/SP 基礎資料。
- 修正 RRF 匯入編碼造成的資料切割錯誤，並提示武器與盾牌 ID 相同的情況。
- 增益技能／料理清單優先顯示目前職業技能。
- 裝備搜尋支援以空白分隔的多關鍵字條件。

### [v0.1.16-251209](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.16-251209)

- 修正 CRI 顯示與 RRF 技能解譯。
- 更新技能編輯器遠傷選項及部分 Buff。
- 新增降低爆擊傷害的判斷。
- 新增 MHP／MSP 等數值對應 ROC 檔。
- 修正無視 RES 與 +18 天衣無縫貫穿相關計算。

### [v0.1.10-251201](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.10-251201)

- RRF Replay 檔案匯入裝備功能，修復大括號配對問題。

### [v0.1.9-251130](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.9-251130)

- 新增從 `.rrf` Replay 檔案匯入裝備。

### [v0.1.8-251130](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.8-251130)

- 新增從 `.rrf` Replay 檔案匯入裝備。

### [v0.1.2-251122](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.1.2-251122)

- 新增技能表及附魔查詢工具。

### [v0.0.1-251028](https://github.com/z2911902/ROItemSearchApp/releases/tag/v0.0.1-251028)

- 專案初次發布；提供初期打包版本（當時不含自動編譯資料）。

