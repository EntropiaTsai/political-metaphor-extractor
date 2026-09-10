---
name: political-metaphor-extractor
description: 從政治文本語料中抽取概念性隱喻，建立 macro/mid/sub 三層來源域本體，並產生統計與可縮放的 circle packing 視覺化。採兩階段流程：先抽 Tenor/Vehicle/Ground 三元詞組，再獨立映射 domain。適用於使用者想從社群貼文、論壇留言、新聞或訪談逐字稿中做隱喻分析、批判論述分析、框架分析，或提到 conceptual metaphor、隱喻抽取、來源域、target domain、source domain、Tenor Vehicle Ground、CMT 時。
---

# 政治隱喻抽取

從一批政治文本中，抽出「用什麼概念在講政治」，並整理成可統計、可比較、可視覺化的三層結構。

**產出**：每則隱喻一列的 CSV（含原始例句）→ 三層來源域本體 → 頻率統計表 → 互動式視覺化。

## 對話原則

使用者多半是語言學或社會科學的研究者，不是開發者。**整個流程由你執行，不要要求使用者打開終端機、輸入指令或自己編輯設定檔。**

所有指令你自己跑，不要把指令貼給使用者叫他複製。`taxonomy.yaml`、`hierarchy_rules.yaml` 與 prompt 的修改由你代筆，動手前用自然語言說明你要加什麼、為什麼，得到同意再改。使用者給什麼格式的語料你就接什麼——Excel、Word 裡貼出來的純文字、CSV 都行，轉成 JSONL 是你的工作，不要叫他先自己整理。產生視覺化之後直接用 `open`（macOS）或 `xdg-open`（Linux）幫他打開，不要只丟一個檔案路徑。

報告結果時避免術語。「殘差桶佔 23%」要講成「有 23% 的隱喻還沒分進細類，我建議補幾條規則再跑一次」。需要使用者做判斷時，把選項和後果講清楚再問，不要預設他知道 YAML、CSV 或 venv 是什麼。

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

下面的指令用 `<skill>` 代表這個 skill 目錄的實際路徑，執行時請替換成真實路徑。它會隨安裝位置不同，常見的是 `~/.claude/skills/political-metaphor-extractor`、`~/.cursor/skills/political-metaphor-extractor`，或專案內的 `.claude/skills/political-metaphor-extractor`。需要 Python 3.9 以上；相依套件只有 PyYAML，其餘都是標準函式庫。

### 先問：結果要不要保存

這個決定會改變工作目錄放在哪裡，所以**必須在建目錄之前問**，不要跑完才問。問使用者一句：「分析結果要保存下來，還是看過就好？」

**要保存**時，在使用者指定的位置建目錄（沒指定就用目前專案根目錄），命名為 `metaphor_<識別名>`，識別名要讓人事後看得出是哪批語料，例如 `metaphor_ptt2014`、`metaphor_立院質詢`。跑完把絕對路徑告訴使用者。

**看過就好**時，建在系統暫存目錄底下：

```bash
WORK=$(mktemp -d)/metaphor_tmp && mkdir -p "$WORK" && cd "$WORK"
```

跑完把統計表直接貼在對話裡、把視覺化 HTML 開給使用者看，**確認他看過之後主動刪掉整個目錄並回報已清理**。不要默默留著——這些目錄含一個 venv，每個約數十 MB，累積幾次就很可觀，而使用者不會記得自己有這些東西。

不管哪一種都用 `metaphor_` 開頭，日後 `ls -d metaphor_*` 就能一次找出全部來清理。

**不要重複使用既有的 `metaphor_*` 目錄**，除非使用者明講要接續上次的工作。同名目錄裡的 `out/tvg.csv` 與 `out/mapped.csv` 會被無聲覆蓋，那是逐則標註的成果，重跑要重花時間與金錢，而且 `temperature` 設 0 也不保證逐字重現。相對地，`hierarchy.csv`、`stats_*.csv`、`hierarchy.html` 這些從 `mapped.csv` 幾秒就能重生的產物，覆蓋沒有關係——步驟 8 到 9 本來就要反覆重跑。

### 建立工作目錄

把設定檔複製進去，讓使用者可以自由修改而不動到 skill 本體：

```bash
cp -r <skill>/assets/* .
```

得到 `config.yaml`、`taxonomy.yaml`、`hierarchy_rules.yaml`、`prompts/`、`sample_corpus.jsonl`。

接著要準備 Python 環境。**安裝任何套件之前一定要先問過使用者，得到同意才動手**，而且要用白話問，不要丟術語。例如：

> 我需要在這個資料夾裡建一個獨立的 Python 環境，只安裝一個叫 PyYAML 的小套件，大約幾十 MB。它不會影響你電腦上其他程式，之後刪掉資料夾就清乾淨了。可以嗎？

venv 放在工作目錄內是刻意的，刪掉目錄就一併清乾淨。使用者若拒絕或說他已經有慣用環境（conda、既有 venv、系統已裝好 PyYAML），就照他的方式走，把下面指令的 `.venv/bin/python` 換成他指定的直譯器。

預設做法是建虛擬環境，**不是選配**——近年的 macOS 與 Homebrew Python 會擋下對系統環境的 `pip install`（`externally-managed-environment`），裝進 venv 一次避開這個問題：

```bash
python3 -m venv .venv
.venv/bin/pip install -q pyyaml
.venv/bin/python -c "import yaml; print('env ready')"
```

看到 `env ready` 才往下走。**後面所有指令都用 `.venv/bin/python`，不要用 `python3`**，否則會落回沒有 PyYAML 的系統環境。所有指令都假設你的工作目錄停在剛才建的 `metaphor_*` 底下，路徑都以它為基準。

極少數精簡版 Python 沒有帶 venv 模組，`python3 -m venv` 會直接失敗。這種情況要**再問一次使用者**才能改用 `pip3 install --user pyyaml`，因為它會裝進使用者的家目錄而非拋棄式的 venv；同意之後，後續指令維持 `python3`。

**每次改完這些檔案都要驗證一次**：

```bash
.venv/bin/python <skill>/scripts/validate_config.py --config config.yaml --rules hierarchy_rules.yaml
```

它檢查的是那些不會當場報錯、只會讓資料靜默流失的矛盾：prompt 的 few-shot 範例教了白名單不接受的標籤、中層規則寫在一個永遠不會出現的 macro 底下、alias 折疊到白名單外的標籤、prompt 佔位符被刪掉。有 error 就先修完再往下跑，否則你會跑完幾千則才發現一整類映射都被丟掉了。

接著把使用者的語料轉成 JSONL，一行一則，**只有 `id` 和 `text` 是必要欄位**。轉檔是你的工作：使用者可能給你 Excel、Word 貼過來的純文字、爬蟲的 CSV 或一個裝滿 txt 的資料夾，你負責讀進來、切成分析單位、補上 `id`，不要要求他先自己整理成特定格式。沒有現成 id 就照順序編（`doc001`、`doc002`……）。

```json
{"id": "doc001", "period": "2014", "text": "這群立委根本就是政黨養的走狗……"}
```

其他欄位（如上例的 `period`）可以用 `--carry-fields` 一路帶到最後，用來做分組比較。

**【核心分組原則（極重要！）】**：
- **預設一律不進行任何分組，將整份文本合併為單一組別進行統計與視覺化**。因為不同的模型（如 Claude, GPT, Gemini）在遇到沒有明確發言者或時間標籤的語料時，會胡亂猜測與拆分（如 A/B/C 三人分析或不同時間點），導致統計數據零碎、判斷錯誤、甚至麵包屑和分組 Tab 混亂。
- **除非使用者明確且主動要求做特定的分組對照**，否則不要使用 `--carry-fields` 與 `--group-field` 參數。

也接受 `.csv`（需有 `id`、`text` 欄）與 `.json`（陣列）。

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

**【Agent 模式優化指引】**：
如果當前是 **Agent 模式（尤其是暫存模式 / 看過就好模式）**，你不需要真的動用 `StrReplace` 去改寫硬碟上的 `prompts/extract_system.md` 檔案！這樣做會造成不必要的對話中斷與檔案變更。你只需要在執行標註時，**在腦中/記憶體中將當前語料的脈絡帶入推理**即可。只有在需要正式「保存」專案、或使用「腳本模式」跑全量數據時，才真正去寫入/修改該檔案。

**【防範越界修改】**：
不論在何種模式下，你**絕對不可修改全域的 Skill 本體目錄**（例如 `~/.claude/skills/...` 下的 assets 檔案）！你只能修改複製到當前工作目錄（如 `./metaphor_xxx`）底下的複製品。

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
.venv/bin/python <skill>/scripts/ingest_annotations.py --stage tvg \
    --corpus corpus.jsonl --input annotations.json \
    --output out/tvg.csv
```

*(註：只有在使用者有特定分組對照需求時，才需要在指令末端加入 `--carry-fields 欄位名`)*

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
.venv/bin/python <skill>/scripts/ingest_annotations.py --stage map \
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

中層規則（`hierarchy_rules.yaml`）代表的是研究者的學術與分析決策（人工策展層）。
**【重要對話與操作準則】：**
1. **絕對不可在未經使用者同意下，擅自動手用 `StrReplace` 修改 `hierarchy_rules.yaml`！**
2. 即使執行了 `build_hierarchy.py` 並發現殘差桶（如 `其他動物`、`其他戰爭`），你也**不可直接去修改該檔案**。
3. **語意映射與折疊（重要！）**：
   - 當發現殘差詞時，你必須發揮語言學家的專業，**先評估這些殘差詞是否能歸入「現有的中層分類」中**，避免無謂地新增一堆雜亂的新類別。
   - 例如：「國家機器」雖然不在既有規則中，但其本質是一種受政治操控的「工具」或「公器」；「防線」雖然是新詞，但本質屬於既有戰爭分類下的「防衛者」。
   - **優先將其「折疊（Fold）」進既有分類**。只有當殘差詞確實屬於一個全新且重要的概念、無法歸入現有任何中層時，才考慮建議新增中層類別。
4. **正確的做法**是：將殘差桶中未分類的隱喻詞整理成一份**清晰、親切的中文建議清單**，並主動詢問使用者：
   > 「我注意到有以下詞彙落入了『其他（殘差）』分類，為保持分類的乾淨與學術統計價值，我建議：
   > 
   > **A. 歸入/折疊至既有分類（推薦）：**
   > - 將 『國家機器』 歸入既有的中層分類 『工具』（既有分類已有 "工具", "公器" 等關鍵字）
   > - 將 『防線』 歸入既有的中層分類 『防衛者』（既有分類已有 "防衛", "守護" 等關鍵字）
   > 
   > **B. 新增全新分類（僅在現有分類皆不適合時使用）：**
   > - 針對某些全新概念，新增一個中層分類（例如：新增一個『中傷』分類放『抹黑』）
   >
   > 請問您覺得這樣調整合適嗎？還是有其他的歸類想法？」
5. 唯有在使用者明確指示「好，幫我修改」、「同意」後，你才能使用 `StrReplace` 對檔案進行對應的修改。如果不確定，請以對話協商為主，讓使用者保有完全的策展主控權。

編輯 `hierarchy_rules.yaml` 的 `mid_source`，為每個夠大的 macro domain 寫中層規則：

```yaml
mid_source:
  動物:
    狗: ["走狗", "馬狗", "狗"]
    鳥: ["青鳥", "鳥"]
```

比對方式是拿關鍵詞去 `vehicle + ground` 做子字串比對，**長詞優先**，所以 `走狗` 會正確落在「狗」而不會被更短的規則搶走。沒寫規則的 macro domain 會直接用自己當中層標籤。

```bash
.venv/bin/python <skill>/scripts/build_hierarchy.py --input out/mapped.csv \
    --rules hierarchy_rules.yaml --outdir out/
```

*(註：只有在啟用分組比較時，才需要在結尾加入 `--group-field 欄位名`)*

產生 `hierarchy.csv`、`stats_macro.csv`、`stats_mid.csv`，並印出殘差桶：

```
  clean mid (excluding '其他*' residuals): 454 (76.8%)
  residual buckets — these are your cue to add mid-level rules:
    其他動物: 8
```

殘差比例高就回頭補規則再跑一次。這一步會迭代好幾輪，很正常。

### 步驟 10：視覺化

```bash
.venv/bin/python <skill>/scripts/make_circle_packing.py --input out/hierarchy.csv \
    --output out/hierarchy.html --title "政治隱喻來源域"
```

*(註：只有在啟用分組比較時，才需要加入 `--group-field 欄位名`。在沒有指定分組時，網頁中的圓圈打包圖與麵包屑會預設以動態名稱「全部 (All)」作為最上層的根節點標題)*

產生後直接幫使用者打開，不要只回報路徑：

```bash
open out/hierarchy.html        # Linux 用 xdg-open
```

單一 HTML 檔，點圓圈往下鑽一層，點背景往上退，第三層列出原始例句。`--group-field` 會生出切換鈕做跨組比較（如不同年份）。這些操作方式要主動講給使用者聽，他不會自己猜到可以點。

離線展示時用 `--d3-src ./d3.v7.min.js` 指向本機 d3，預設走 CDN。

### 步驟 11：交付與收尾

不論使用者選哪一種保存方式，都把 `stats_macro.csv` 與 `stats_mid.csv` 的內容整理成表格直接貼在對話裡，並附上殘差比例與被拒絕的標籤數量。使用者要看的是結論，不是一句「檔案在那邊，自己去開」。

選了**保存**的，最後回報工作目錄的絕對路徑，並列出裡面哪幾個檔案是他之後會用到的（`hierarchy.csv` 給後續分析、`hierarchy.html` 給簡報、三個設定檔給論文附錄）。

選了**看過就好**的，先把 HTML 開起來給他看，等他確認看完，再刪掉整個 `metaphor_*` 暫存目錄並回報已清理。刪之前多問一句「有沒有要留下來的？」——他有可能看完才改變主意，這時把目錄搬到他指定的位置即可，不要重跑一次。

## 腳本模式

語料上千則時改用這條路。這是唯一需要 API key 的環節，而使用者不見得有，也不見得知道去哪申請——**先確認他手上有金鑰再往下談**，沒有的話說明要去模型供應商的網站申請、大致費用怎麼算，讓他決定要不要走這條路，或是改成分批用 agent 模式慢慢跑。

金鑰由你寫進工作目錄的 `.env`，不要叫使用者自己開終端機或編輯器。請他在對話裡貼給你之前，先提醒一句：貼進對話等於留在對話紀錄裡，如果他介意，可以改由他自己把金鑰填進 `.env`，你只要告訴他檔案路徑和格式就好。

```bash
echo 'GEMINI_API_KEY=使用者提供的金鑰' >> .env
```

`.env` 絕對不要提交到版控。

`config.yaml` 裡只記錄要去哪個環境變數找 key，不存金鑰本身。任何 OpenAI 相容端點都可以，改 `base_url` 與 `api_key_env` 即可。

```bash
S=<skill>/scripts

# 先 dry-run 確認讀檔與設定正確，不會送出請求
.venv/bin/python $S/extract_tvg.py --config config.yaml --input corpus.jsonl \
    --output out/tvg.csv --carry-fields period --dry-run

.venv/bin/python $S/extract_tvg.py --config config.yaml --input corpus.jsonl \
    --output out/tvg.csv --carry-fields period

.venv/bin/python $S/map_domains.py --config config.yaml \
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
.venv/bin/python <skill>/scripts/stability_check.py --config config.yaml \
    --input corpus.jsonl --sample 40 --runs 3 --outdir out/stability
```

它只告訴你「其他條件不變時輸出會晃多少」。要主張準確率，必須人工逐筆看過一定規模的樣本，且要在論文裡分別報告這兩個數字，不要混為一談。

**一定要人工抽查。** 至少隨機抽 50 筆讓使用者讀過。**把這 50 筆整理成表格貼在對話裡**，一次十幾筆分批呈現，不要叫他自己去開 CSV——他要做的是學術判斷，不是找檔案。每筆列出例句、Tenor、Vehicle、Ground 與指派的 domain，讓他能直接回「第 3 筆和第 7 筆不對」。

重點看三件事：Ground 是否真的支撐跨域映射、Tenor 是否與該則的語意焦點一致、以及有沒有把代稱當成隱喻。這三個判準要在請他審查時一併說明，不能假設他記得。

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
