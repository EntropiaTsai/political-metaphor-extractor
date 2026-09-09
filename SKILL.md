---
name: political-metaphor-extractor
description: 從政治文本語料中抽取概念性隱喻，建立 macro/mid/sub 三層來源域本體，並產生統計與可縮放的 circle packing 視覺化。採兩階段流程：先抽 Tenor/Vehicle/Ground 三元詞組，再獨立映射 domain。適用於使用者想從社群貼文、論壇留言、新聞或訪談逐字稿中做隱喻分析、批判論述分析、框架分析，或提到 conceptual metaphor、隱喻抽取、來源域、target domain、source domain、Tenor Vehicle Ground、CMT 時。
---

# 政治隱喻抽取

從一批政治文本中，抽出「用什麼概念在講政治」，並整理成可統計、可比較、可視覺化的三層結構。

**產出**：每則隱喻一列的 CSV（含原始例句）→ 三層來源域本體 → 頻率統計表 → 互動式視覺化。

## 方法核心

整套流程只有三個關鍵設計，其餘都是工程細節：

1. **抽取與分類分開做。** 第一階段只找 Tenor（本體）/ Vehicle（喻體）/ Ground（共同特徵），完全不碰 domain 分類；第二階段才在看不到原文的情況下，只根據這三個欄位指派 domain。合在一起做會讓模型看到 domain 清單就往上硬套，產生大量假陽性。

2. **標籤空間是白名單，而且注入 prompt 與事後驗證用同一份。** `taxonomy.yaml` 會被渲染進第二階段的 prompt，也會在寫檔前強制過濾。模型自創的標籤一律丟棄並回報，不會靜默混進統計。

3. **中層是人工策展層。** macro 由模型給，sub 就是原始 vehicle，**mid 由你自己寫規則**。沒被規則命中的會落進 `其他<macro>` 殘差桶並回報——那份回報就是你下一輪要補的規則清單。

## 兩種跑法

| | Agent 模式（預設） | 腳本模式 |
|---|---|---|
| 誰做標註 | 你（agent）直接讀 prompt 標註 | 腳本批次呼叫 LLM API |
| 需要 API key | **不需要** | 需要使用者自己的 key |
| 適合規模 | 數十到約兩百則 | 數百到數萬則 |

兩種模式的**輸出格式完全相同**，後段的三層彙總、統計、視覺化共用同一套腳本，而且那些腳本純本機運算，不碰網路也不需要 key。可以先用 agent 模式跑一小批確認 prompt 與 taxonomy 合用，再換腳本模式跑全量。

## 開始之前

下面的指令用 `<skill>` 代表這個 skill 目錄的實際路徑（專案安裝時是 `.cursor/skills/political-metaphor-extractor`），執行時請替換成真實路徑。腳本需要 Python 3.9 以上與 PyYAML，其餘都是標準函式庫。

先把設定檔複製到使用者的工作目錄，讓他可以自由修改而不動到 skill 本體：

```bash
mkdir -p metaphor && cd metaphor
cp -r <skill>/assets/* .
```

得到 `config.yaml`、`taxonomy.yaml`、`hierarchy_rules.yaml`、`prompts/`、`sample_corpus.jsonl`。

**每次改完這些檔案都要驗證一次**：

```bash
python3 <skill>/scripts/validate_config.py --config config.yaml --rules hierarchy_rules.yaml
```

它檢查的是那些不會當場報錯、只會讓資料靜默流失的矛盾：prompt 的 few-shot 範例教了白名單不接受的標籤、中層規則寫在一個永遠不會出現的 macro 底下、alias 折疊到白名單外的標籤、prompt 佔位符被刪掉。有 error 就先修完再往下跑，否則你會跑完幾千則才發現一整類映射都被丟掉了。

接著把使用者的語料整理成 JSONL，一行一則，**只有 `id` 和 `text` 是必要欄位**：

```json
{"id": "doc001", "period": "2014", "text": "這群立委根本就是政黨養的走狗……"}
```

其他欄位（如上例的 `period`）可以用 `--carry-fields` 一路帶到最後，用來做分組比較。也接受 `.csv`（需有 `id`、`text` 欄）與 `.json`（陣列）。

**切分建議**：一則 = 一個分析單位。貼文和留言請拆成不同列，不要把整串討論塞進一個 `text`，否則 Tenor 會跨越不同發言者而失準。

## Agent 模式流程

複製這份清單並逐項追蹤：

```
- [ ] 1. 語料轉成 JSONL
- [ ] 2. 改寫 prompt 的語料脈絡區塊
- [ ] 3. 調整 taxonomy 標籤空間
- [ ] 4. 標註 Tenor/Vehicle/Ground → annotations.json
- [ ] 5. ingest 成 tvg.csv
- [ ] 6. 指派 domain → mappings.json
- [ ] 7. ingest 成 mapped.csv，處理被拒絕的標籤
- [ ] 8. 寫中層規則並建立三層本體
- [ ] 9. 檢查殘差桶，回頭補規則
- [ ] 10. 產生視覺化
```

### 步驟 2：改寫語料脈絡

`prompts/extract_system.md` 裡有一段用註解標記的區塊：

```
<!-- ==== 以下為語料脈絡，換語料時請整段改寫 ==== -->
```

裡面寫的是台灣 PTT 的陣營結構與在地黑話。**換語料一定要改這段**，寫清楚：來源與文體、語言、該場域的政治結構、常見的在地隱喻詞。這段是背景知識，不是必抓清單——prompt 裡已明確要求模型不得把它當觸發詞表。

其餘部分（五步驟推理、代稱排除規則、輸出格式）是通用的隱喻學鷹架，不要動。

若語料不是中文，把整份 prompt 翻成語料的語言，效果會明顯好於用中文 prompt 分析外語文本。

### 步驟 4：標註

讀 `prompts/extract_system.md`，**完整遵照裡面的五步驟與排除規則**，對語料每一則產生一筆結果，輸出成 `annotations.json`：

```json
{"results": [
  {"text_id": "doc001", "metaphors": [
    {"vehicle": "走狗", "vehicle_pos": "名詞", "semantic_focus": "政治人物的行為",
     "tenor": "立委", "tenor_pos": "名詞", "ground": "盲從聽命的追隨者",
     "rationale": "以受豢養的犬類映射對政黨的絕對服從。",
     "literal_anchor": "養、咬",
     "evidence_text": "這群立委根本就是政黨養的走狗。", "confidence": 0.95}
  ]},
  {"text_id": "doc003", "metaphors": []}
]}
```

**每一則都要有一筆**，沒有隱喻就給空陣列。漏掉的話分母會錯，比例統計全部失真。

資料多時分批處理，每批 10–20 則，分批寫成 `annotations.001.json`、`annotations.002.json`，最後分別 ingest 再合併也可以。

不要自己動手拼 CSV。中文例句裡的逗號與引號很容易把 CSV 弄壞，交給 ingest 腳本處理。

### 步驟 5：轉成 CSV

```bash
python3 <skill>/scripts/ingest_annotations.py --stage tvg \
    --corpus corpus.jsonl --input annotations.json \
    --output out/tvg.csv --carry-fields period
```

腳本會回報有哪些語料沒有對應的標註。有的話補齊再往下走。

### 步驟 6：指派 domain

讀 `prompts/map_system.md` 與 `taxonomy.yaml`。**只看 `tvg.csv` 的欄位，不要回頭看原文**——這個限制是刻意的，它讓分類決策可被獨立稽核，也避免用原文的其他線索合理化一個站不住腳的映射。

輸出 `mappings.json`：

```json
{"results": [
  {"record_id": "doc001::m1", "target_domain": "政治人物", "source_domain": "動物"}
]}
```

只能用 `taxonomy.yaml` 裡的標籤。真的沒有適用的就留空字串，不要自創，也不要輸出 `OTHER`。

### 步驟 7：套用 taxonomy

```bash
python3 <skill>/scripts/ingest_annotations.py --stage map \
    --tvg out/tvg.csv --taxonomy taxonomy.yaml \
    --input mappings.json --output out/mapped.csv
```

腳本會列出被拒絕的標籤，例如：

```
  labels rejected as outside the taxonomy:
    source=植物 ×1
```

這時要判斷：是標註該改用既有標籤，還是這個概念在語料裡夠常見、值得正式加進 `taxonomy.yaml`。**兩種都是正當的**，但要有意識地選，不能放著不管——被拒絕的那筆會變成無效映射，不進統計。

### 步驟 8–9：三層本體

編輯 `hierarchy_rules.yaml` 的 `mid_source`，為每個夠大的 macro domain 寫中層規則：

```yaml
mid_source:
  動物:
    狗: ["走狗", "馬狗", "狗"]
    鳥: ["青鳥", "鳥"]
```

比對方式是拿關鍵詞去 `vehicle + ground` 做子字串比對，**長詞優先**，所以 `走狗` 會正確落在「狗」而不會被更短的規則搶走。沒寫規則的 macro domain 會直接用自己當中層標籤。

```bash
python3 <skill>/scripts/build_hierarchy.py --input out/mapped.csv \
    --rules hierarchy_rules.yaml --outdir out/ --group-field period
```

產生 `hierarchy.csv`、`stats_macro.csv`、`stats_mid.csv`，並印出殘差桶：

```
  clean mid (excluding '其他*' residuals): 454 (76.8%)
  residual buckets — these are your cue to add mid-level rules:
    其他動物: 8
```

殘差比例高就回頭補規則再跑一次。這一步會迭代好幾輪，很正常。

### 步驟 10：視覺化

```bash
python3 <skill>/scripts/make_circle_packing.py --input out/hierarchy.csv \
    --output out/hierarchy.html --group-field period \
    --title "政治隱喻來源域"
```

單一 HTML 檔，點圓圈往下鑽一層，點背景往上退，第三層列出原始例句。`--group-field` 會生出切換鈕做跨組比較（如不同年份）。

離線展示時用 `--d3-src ./d3.v7.min.js` 指向本機 d3，預設走 CDN。

## 腳本模式

語料上千則時改用這條路。使用者需要自己的 API key，寫進自己的 `.env`（**不要提交到版控**）：

```bash
echo 'GEMINI_API_KEY=你的金鑰' >> .env
```

`config.yaml` 裡只記錄要去哪個環境變數找 key，不存金鑰本身。任何 OpenAI 相容端點都可以，改 `base_url` 與 `api_key_env` 即可。

```bash
S=<skill>/scripts

# 先 dry-run 確認讀檔與設定正確，不會送出請求
python3 $S/extract_tvg.py --config config.yaml --input corpus.jsonl \
    --output out/tvg.csv --carry-fields period --dry-run

python3 $S/extract_tvg.py --config config.yaml --input corpus.jsonl \
    --output out/tvg.csv --carry-fields period

python3 $S/map_domains.py --config config.yaml \
    --input out/tvg.csv --output out/mapped.csv
```

之後的 `build_hierarchy.py` 與 `make_circle_packing.py` 完全相同。

**`temperature` 保持 0**。這是標註任務不是寫作任務，要的是可重現。

長時間跑用 `--resume` 續跑，已完成的語料會跳過。批次解析失敗時腳本會自動對切重試，單則仍失敗才放棄並記錄，不會整批陣亡。若看到 `hit max_tokens and was truncated`，把 `llm.max_tokens` 調高或把該階段的 `batch_size` 調低。

## 適用範圍

這套流程**針對政治語料**。換國家、換語言、換平台都沒問題，那正是語料脈絡區塊的用途；但**換領域不行**。

兩份 prompt 的政治假設不只在標記區塊裡，也寫進了推理步驟本身：抽取階段要求語意焦點落在政治層面、Tenor 必須是政治對象、驗證時要能與政治語境建立映射；映射階段的第一條核心原則直接禁止把非政治對象標成 target。

實際後果是**會被規則主動排除，而不是抽得比較差**。拿醫療語料進來，「癌細胞入侵器官」這種標準的 ILLNESS IS WAR 隱喻會被驗證步驟擋掉，因為 Tenor 是疾病不是政治對象。

要用在非政治領域，得改的不只是語料脈絡區塊，而是兩份 prompt 裡所有把 target 限定為政治的條款，加上整份 `allowed_target_domains`。來源域清單（戰爭、動物、商業、宗教、戲劇、家庭、階層、自然物）本來就是通用的 CMT 來源域，那部分可以留著。所有腳本也完全不含領域知識，可以照用。

## 換一批政治語料要改的四個檔案

| 檔案 | 改什麼 | 不改會怎樣 |
|---|---|---|
| `prompts/extract_system.md` | 語料脈絡區塊 | 模型用台灣政治框架讀你的語料 |
| `taxonomy.yaml` | 兩份 allowed 清單 | 你的領域概念全被當成越界標籤丟掉 |
| `hierarchy_rules.yaml` | `mid_source` 規則 | 中層等於 macro 層，三層退化成兩層 |
| `config.yaml` | `base_url`、`model` | 指向錯的供應商 |

改完跑 `validate_config.py`。這四個檔案彼此高度耦合——例如 taxonomy 的 alias 會把「黑道」這類人物 vehicle 折成 `犯罪者`，中層規則若把「黑道」寫在 `犯罪` 底下就永遠不會命中——驗證器就是為了抓這種跨檔案的矛盾。

## 品質控管

**穩定性不等於準確率。** `stability_check.py` 對同一批樣本重跑多次，量測 domain pair 的 Jaccard 一致性：

```bash
python3 <skill>/scripts/stability_check.py --config config.yaml \
    --input corpus.jsonl --sample 40 --runs 3 --outdir out/stability
```

它只告訴你「其他條件不變時輸出會晃多少」。要主張準確率，必須人工逐筆看過一定規模的樣本，且要在論文裡分別報告這兩個數字，不要混為一談。

**一定要人工抽查。** 至少隨機抽 50 筆讀過。重點看三件事：Ground 是否真的支撐跨域映射、Tenor 是否與該則的語意焦點一致、以及有沒有把代稱當成隱喻。

## 常見陷阱

**代稱不是隱喻。** 綽號、媒體慣用稱呼若只有指稱功能、沒有新的跨域屬性映射，不該抽出來。這是最常見的假陽性來源。

**角色層級與場域層級要分清楚。** Vehicle 是「人」（黑道、流氓）時取角色類 `犯罪者`；是「行為/事件」（作案、犯案）時才取活動類 `犯罪`。混用會讓層級結構垮掉，統計時 `犯罪者` 會錯誤地跟 `犯罪` 平起平坐。**不要把角色類標籤放進 `allowed_target_domains`**，它是 source 側的下層概念。

**過度正規化會抹掉政治意義。** `走狗` 不能簡化成 `狗`，`青鳥` 不能簡化成 `鳥`——修飾語承載了陣營指涉。只有在修飾語不改變來源概念時才移除（`那隻狗` → `狗`）。

**不要把整串討論當一個分析單位。** Tenor 會跨越不同發言者。

**跨組比較要看比例不要看絕對數。** 兩組語料的規模通常不同，`stats_*.csv` 的 `ratio` 欄已經算好組內佔比。

## 進一步說明

- prompt 各段落的作用與改寫方式，見 [references/prompt-design.md](references/prompt-design.md)
- taxonomy 標籤空間怎麼設計、粒度怎麼抓，見 [references/taxonomy-guide.md](references/taxonomy-guide.md)
- 人工後審流程與可報告的統計口徑，見 [references/review-workflow.md](references/review-workflow.md)
- 各 CSV 的完整欄位定義，見 [references/data-schema.md](references/data-schema.md)
