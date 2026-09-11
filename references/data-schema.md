# 資料格式規格

本文件定義 pipeline 每個階段讀寫的檔案格式、欄位意義與邊界行為，所有敘述皆對應 `scripts/` 下的實作。

## 檔案流向圖

```
                       corpus.jsonl / .ndjson / .json / .csv
                       （必要欄位：id、text）
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          │ Agent 模式                                        │ 腳本模式
          v                                                   v
  annotations.json（agent 標註）                        extract_tvg.py
          │  ＋ corpus（重讀取得 carry 欄位）            config.yaml ＋ prompts/
          v                                                   │
  ingest_annotations.py --stage tvg                           │
          │                                                   │
          └───────────────────> tvg.csv <────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          v                                                   v
  mappings.json（agent 標註）                           map_domains.py
          │  ＋ tvg.csv ＋ taxonomy.yaml                 config.yaml ＋ taxonomy.yaml
          v                                                   │
  ingest_annotations.py --stage map                           │
          │                                                   │
          └──────────────────> mapped.csv <──────────────────┘
                                    │
                                    v
                          build_hierarchy.py <── hierarchy_rules.yaml
                                    │
              ┌─────────────────────┼─────────────────────┐
              v                     v                     v
        hierarchy.csv        stats_macro.csv        stats_mid.csv
              │
              ├──> make_circle_packing.py ──> hierarchy.html（單一自足檔案）
              └──> make_pairing_diagram.py ──> pairing.html（單一自足檔案）

  stability_check.py（獨立分支，僅腳本模式）
      corpus ──> sample.jsonl ──> extract_tvg.py / map_domains.py 重跑 N 次
      ──> tvg_run{N}.csv、mapped_run{N}.csv ──> doc_jaccard.csv、source_distribution.csv
```

兩種模式在 `mapped.csv` 匯流，之後的 `build_hierarchy.py` 與兩支繪圖腳本完全共用，且純本機運算。

`validate_config.py` 不在資料流上，不讀寫任何資料檔。它只檢查 `config.yaml`、`taxonomy.yaml`、`hierarchy_rules.yaml` 與 `prompts/` 四者之間的一致性，有 error 時以 exit code 1 結束，適合在跑長任務前擋一道。

## 輸入語料

`extract_tvg.read_corpus()` 依副檔名決定讀法，`ingest_annotations.py --stage tvg` 與 `stability_check.py` 都呼叫同一個函式。

| 副檔名 | 讀法 |
|---|---|
| `.jsonl`、`.ndjson` | 一行一個 JSON 物件，空行略過 |
| `.json` | 頂層為陣列時直接使用；為物件時取 `documents`，其次 `articles`，皆無則視為空清單 |
| `.csv` | 以 `csv.DictReader` 讀取，編碼 `utf-8-sig`（容許 BOM） |
| 其他 | 直接 `SystemExit`，錯誤訊息列出支援格式 |

| 欄位 | 意義 |
|---|---|
| `id` | 文件識別碼，會成為 `doc_id`。值為空或缺漏時自動補為 `doc{i+1:05d}`（如 `doc00007`），其中 `i` 是該列在**原始檔案**中的索引，因此被略過的空白列仍會佔號，編號可能不連續 |
| `text` | 文件正文。前後空白會被 `strip()`；strip 後為空字串的列**整列略過**，不進入後續任何統計的分母 |
| 其他欄位 | 預設不讀入。只有列在 `--carry-fields` 的欄位會被複製到 `carry` 字典並寫進輸出 CSV |

- `--carry-fields` 接受逗號分隔的欄位名（如 `period,board`），空白會被 trim，空項目忽略。語料中不存在該欄位時填空字串，不會報錯。
- `--limit N` 在略過空白列**之後**計數，取前 N 筆有效文件。
- `max_chars`（`config.yaml` 的 `extract.max_chars`，預設 1800）只在 `build_user_prompt()` 組 prompt 時對 `text` 做截斷，**不影響** `read_corpus` 讀進來的內容，也不套用於 agent 模式（`ingest_annotations.py` 不組 prompt）。
- `--resume` 會先讀既有輸出的 `doc_id` 集合（`existing_doc_ids`），把已出現過的文件從待處理清單移除，並以附加模式寫檔、不重寫表頭。

## tvg.csv

第一階段輸出，每列一個隱喻候選。欄位順序為 `extract_tvg.FIELDS` 加上 `--carry-fields` 指定的欄位（依指定順序附加在標準欄位之後）。

| 欄位 | 意義 |
|---|---|
| `record_id` | 候選唯一識別碼，格式 `{doc_id}::m{k}`。`k` 從 1 起算，且是該文件 `metaphors` 陣列的位置序號；被過濾掉的項目仍佔號，故同一文件的 `k` 可能不連續 |
| `doc_id` | 來源文件的 `id` |
| `tenor` | 本體，被談論的政治對象 |
| `tenor_pos` | 本體的詞性標記 |
| `vehicle` | 喻體，用來談論本體的具象詞語 |
| `vehicle_pos` | 喻體的詞性標記 |
| `semantic_focus` | 該則文本的語意焦點 |
| `ground` | 共同特徵，支撐跨域映射的理據 |
| `literal_anchor` | 字面線索詞，輔助動作型喻體的還原 |
| `rationale` | 模型／標註者對該映射的簡短說明 |
| `evidence` | 原始例句，來自標註 JSON 的 `evidence_text` 欄位（**欄名不同，請注意**） |
| `confidence` | 標註信心值 |
| `model` | 產生該列的模型名稱。腳本模式取 `config.llm.model`；agent 模式取 `--model`，預設 `agent` |

寫入規則（`rows_from_results`）：

- 只有 `vehicle` 與 `tenor` **兩者皆非空**的項目才會寫出，其餘靜默丟棄。
- carry 欄位以 `row.update()` 附加，若 carry 欄位名與標準欄名相同會覆蓋標準值，命名時請避開上表。

## mapped.csv

第二階段輸出。欄位為輸入 CSV 的**全部欄位**（含 carry 欄位），再附加 `map_domains.ADDED_FIELDS` 中尚未出現的欄位。

| 欄位 | 意義 |
|---|---|
| `target_domain` | 目標域，通過 taxonomy 白名單後的標籤；無適用標籤時為空字串 |
| `source_domain` | 來源域，通過白名單且不在 `invalid_source_terms` 中；否則為空字串 |
| `mapping_valid` | `"1"` 或 `"0"`。**只有 `target_domain` 與 `source_domain` 皆為非空字串時才是 `"1"`**，任一為空即為 `"0"` |

標籤淨化流程（`map_domains.normalise`，`ingest_annotations.py` 匯入同一函式，兩模式行為一致）：

1. `strip()` 去頭尾空白。
2. `strip("。.,，")` 去掉**頭尾**的句號、點號與中英文逗號，再 `strip()` 一次。所以 `動物。` 會被還原成 `動物` 後才比對白名單。
3. 若此時為空字串，直接回傳空字串。
4. 查 alias 表（`target_domain_aliases` / `source_domain_aliases`）折疊同義詞與英文標籤；查無則保留原值。**alias 比對發生在去標點之後**，故 alias 的 key 不需寫標點變體。
5. 若對應的 allowed 清單非空且折疊後的標籤不在清單中，**清成空字串**，不會保留原標籤、也不會另設 `OTHER` 之類的桶。allowed 清單為空時視同不啟用過濾。
6. `source_domain` 另外檢查 `invalid_source_terms`，命中者清空（第二道網；此類詞通常本來就不在 allowed 清單裡）。

其他行為差異：

- `map_domains.py --drop-invalid` 會直接不寫出 `mapping_valid != "1"` 的列；`ingest_annotations.py --stage map` **沒有這個旗標**，一律全部寫出，由下游 `build_hierarchy.py` 過濾。
- `ingest_annotations.py --stage map` 會額外統計「原始標籤非空但被清空」的情形，以 `target=xxx ×N` 形式列印，供你決定要修標註還是擴充 taxonomy。
- 兩者都會對「JSON 中有但 CSV 裡不存在的 `record_id`」印出 warning 並忽略；`tvg.csv` 有而 JSON 缺漏的列則以空映射處理，`mapping_valid` 為 `"0"`。

## hierarchy.csv

`build_hierarchy.py` 輸出。欄位為 `mapped.csv` 全部欄位再附加 `build_hierarchy.ADDED_FIELDS`。

| 欄位 | 意義 |
|---|---|
| `macro_target` | 目標域頂層標籤，直接取自 `hierarchy_rules.yaml` 的 `macro_target`（常數，全表相同；未設定時為空字串） |
| `mid_target` | 目標域中層標籤。以 `target_domain` 查 `target_merge` 折疊近義類別，查無則沿用 `target_domain` 原值 |
| `macro_source` | 來源域頂層標籤，等同 `source_domain`，未做任何轉換 |
| `mid_source` | 來源域中層標籤，由 `assign_mid()` 依關鍵詞規則產生 |
| `sub_source` | 來源域底層標籤，等同 `vehicle` 原字串，刻意保留表層形式以便稽核 |
| `is_residual_mid` | `"1"` 表示該列落入殘差桶（有規則但無一命中），`"0"` 表示由規則命中或該 macro 尚無規則 |

`mapping_valid` 篩選：**預設只保留 `mapping_valid == "1"` 的列**，其餘在讀入迴圈即 `continue` 掉。加上 `--keep-invalid` 才會全部保留；此時 `source_domain` 為空的列其 `macro_source` 亦為空，`compile_mid_rules` 查不到規則而使 `mid_source` 同樣為空、`is_residual_mid` 為 `"0"`，會在後續統計中形成一個空標籤群組。

`assign_mid()` 的三種結果：

| 情境 | `mid_source` | `is_residual_mid` |
|---|---|---|
| 該 macro 在 `mid_source` 下沒有規則區塊（或區塊為空） | 等於 `macro_source` 本身，三層退化成兩層 | `"0"` |
| 有規則且某關鍵詞命中 | 該關鍵詞所屬的 mid 標籤 | `"0"` |
| 有規則但全部落空 | `{residual_prefix}{macro}`，預設即 `其他動物` 這類字串 | `"1"` |

比對細節：`compile_mid_rules` 把每個 macro 底下所有 `(關鍵詞, mid 標籤)` 攤平成一個清單，並**依關鍵詞字串長度由長到短排序**，`assign_mid` 依序取第一個命中者。這是刻意設計：`走狗` 排在 `狗` 前面，因此不會被較短的規則搶走。比對對象是 `f"{vehicle} {ground}"` 這個以單一空格串接的字串，純子字串比對，不做斷詞、不分大小寫處理。

## stats_macro.csv 與 stats_mid.csv

兩張頻率表由同一個 `frequency_rows()` 產生，差別只在 key 欄位。

| 檔案 | 欄位順序 |
|---|---|
| `stats_macro.csv` | `group`、`macro_source`、`count`、`ratio` |
| `stats_mid.csv` | `group`、`macro_source`、`mid_source`、`count`、`ratio` |

| 欄位 | 意義 |
|---|---|
| `group` | 分組值。未指定 `--group-field` 時**全部為字串 `all`**；指定時取該列該欄的值，該列缺此欄則為空字串 |
| `macro_source` | 來源域頂層標籤 |
| `mid_source` | 來源域中層標籤（僅 `stats_mid.csv`） |
| `count` | 該組合的列數 |
| `ratio` | **組內佔比** = `count ÷ 該 group 的總列數`，四捨五入到小數第 6 位。分母是同一 `group` 的所有列，不是全表，因此跨組比較請用此欄而非 `count` |

兩張表都只統計 `is_residual_mid == "0"` 的列，**殘差桶完全不計入**，連帶也不計入 `ratio` 的分母。因此 `stats_macro.csv` 的 `count` 總和會小於 `hierarchy.csv` 的列數。排序為：先依 `group` 字典序，再依 `count` 遞減，最後依 key 欄位值字典序。

`make_circle_packing.py` 讀 `hierarchy.csv`，同樣預設濾掉 `is_residual_mid == "1"`（`--include-residual` 可保留），用到的欄位為 `macro_source`、`mid_source`、`sub_source`、`evidence`、`tenor` 與 `--group-field` 指定的欄位。`--labels` 接受一個 JSON 物件檔，把原始標籤字串映射到顯示名稱，特殊 key `__root__` 是根節點標籤（可由 `--root-label` 設定）。

`make_pairing_diagram.py` 讀同一份 `hierarchy.csv`、同樣的殘差過濾規則，但額外需要 **`mid_target`** 與 `vehicle`；缺 `mid_target` 會直接中止並提示先跑 `build_hierarchy.py`。它把資料沿目標軸切開：左欄是 `mid_target`、右欄是 `macro_source`（可就地展開成 `mid_source`），連線的權重是該組合的列數。`--labels` 吃的是**同一個 JSON 檔**，目標側與來源側的名稱共用一份對照表。兩支腳本的 macro 配色由 `sorted(set(macro_source))` 的順序決定且共用同一組色票，所以同一個來源域在兩張圖上顏色一致。

兩支腳本產生的 HTML 都把分組順序寫在 `DATA.order`，而不是在瀏覽器端讀 `Object.keys(DATA.groups)`——JS 會把 `"2014"` 這種整數形式的 key 排到最前面，導致「全部 (All)」被擠到最後、開啟時停在錯誤的組別。

## Agent 模式的 JSON 格式

`load_records()` 接受三種外層形狀，兩個 stage 共用：

1. 物件且含清單的 `results`、`records` 或 `items`（依此順序取第一個命中的 key）；若都不是清單，則把整個物件視為單筆記錄包成一個清單。
2. 頂層即為陣列。
3. 整份不是合法 JSON 時，退回逐行 JSONL 解析（空行略過）；任一行不合法即中止並指出行號。空檔案直接中止。

`--stage tvg` 的每筆記錄：

```json
{"text_id": "doc001", "metaphors": [
  {"vehicle": "走狗", "vehicle_pos": "名詞", "semantic_focus": "政治人物的行為",
   "tenor": "立委", "tenor_pos": "名詞", "ground": "盲從聽命的追隨者",
   "rationale": "以受豢養的犬類映射對政黨的絕對服從。",
   "literal_anchor": "養、咬",
   "evidence_text": "這群立委根本就是政黨養的走狗。", "confidence": 0.95}
]}
```

- `text_id` 必須與語料的 `id` 完全相同（以字串比對）；對不上會列 warning 並忽略整筆。
- 每則語料都要有一筆記錄，沒有隱喻時 `metaphors` 給空陣列，否則腳本會回報缺漏，且比例統計的分母會錯。
- `evidence_text` 寫進 CSV 時欄名變為 `evidence`；其餘鍵名與 CSV 欄名一致。缺漏的鍵一律填空字串。

`--stage map` 的每筆記錄：

```json
{"record_id": "doc001::m1", "target_domain": "政治人物", "source_domain": "動物"}
```

- 缺 `record_id` 或其值為 falsy 的記錄會被丟棄；重複的 `record_id` 由後出現者覆蓋。
- 只能使用 `taxonomy.yaml` 中的標籤，無適用時給空字串，不要自創標籤、不要輸出 `OTHER`。

## 設定檔

### config.yaml

檔內的 prompt 與 taxonomy 相對路徑，一律以 **`config.yaml` 自身所在目錄**為基準解析（`Path(args.config).resolve().parent`），與你的當前工作目錄無關。絕對路徑則原樣使用。注意 `ingest_annotations.py --stage map` 不讀 config，其 `--taxonomy` 路徑是相對於當前工作目錄。

| 鍵 | 意義 | 程式內預設 |
|---|---|---|
| `llm.base_url` | OpenAI 相容端點，尾端斜線會被去掉，實際請求 `{base_url}/chat/completions` | 必填 |
| `llm.model` | 模型名稱，同時寫入 `model` 欄 | 必填 |
| `llm.api_key_env` | 存放金鑰的環境變數名稱（config 只記變數名，不存金鑰） | `LLM_API_KEY` |
| `llm.temperature` | 取樣溫度，標註任務請保持 0 | `0.0` |
| `llm.max_tokens` | 單次回應上限；觸頂時拋 `LLMError` 並提示調高或降 batch | `4000` |
| `llm.timeout_seconds` | 單次請求逾時秒數 | `180` |
| `llm.retries` | 重試總次數 | `3` |
| `llm.retry_backoff_seconds` | 退避基數，第 n 次等待 `n × 基數` 秒 | `3.0` |
| `llm.extra_body` | 直接併入請求 payload 的供應商專屬參數 | `{}` |
| `extract.prompts.system` | 第一階段 system prompt 路徑 | 必填 |
| `extract.prompts.user` | 第一階段 user prompt 樣板路徑，內含 `{{context_json}}` | 必填 |
| `extract.batch_size` | 每次請求的文件數 | `6` |
| `extract.max_chars` | 每篇文件送進 prompt 的字元上限 | `1800` |
| `extract.fallback_chunk_size` | 批次解析失敗時的重切大小，遞迴深度上限 3 | `2` |
| `extract.sleep_seconds` | 批次之間的間隔秒數 | `0.1` |
| `map.prompts.system` | 第二階段 system prompt 路徑，含三個 taxonomy 佔位符 | 必填 |
| `map.prompts.user` | 第二階段 user prompt 樣板路徑 | 必填 |
| `map.taxonomy` | taxonomy 檔路徑（相對於 config 目錄） | 必填 |
| `map.batch_size` | 每次請求的三元詞組數 | `20` |
| `map.max_tokens` | 設定後覆寫該階段的 `llm.max_tokens` | 不覆寫 |
| `map.sleep_seconds` | 批次之間的間隔秒數 | `0.05` |

`.env` 由 `load_env_file()` 以 `KEY=VALUE` 逐行解析，忽略空行與 `#` 開頭；使用 `os.environ.setdefault`，因此**已存在的環境變數優先於 `.env`**。值兩端的引號會被去掉。

### taxonomy.yaml

所有鍵皆可省略，省略時視為空集合。

| 鍵 | 意義 | 程式內預設 |
|---|---|---|
| `allowed_target_domains` | 目標域白名單，渲染進 `{{allowed_target_domains}}`（每行一個 `- ` 條列），並在寫檔前強制過濾 | `[]`（空清單＝不過濾） |
| `allowed_source_domains` | 來源域白名單，渲染進 `{{allowed_source_domains}}`，用法同上 | `[]`（空清單＝不過濾） |
| `invalid_source_terms` | 明令禁用的來源域（純價值判斷詞），以頓號串接後渲染進 `{{invalid_source_terms}}`，並在事後清空命中者 | `[]` |
| `target_domain_aliases` | 目標域同義詞／英文標籤 → 正式標籤的對照表 | `{}` |
| `source_domain_aliases` | 來源域同義詞／英文標籤 → 正式標籤的對照表 | `{}` |

### hierarchy_rules.yaml

| 鍵 | 意義 | 程式內預設 |
|---|---|---|
| `macro_target` | 寫入每列 `macro_target` 欄的常數字串 | `""` |
| `target_merge` | `target_domain` → `mid_target` 的折疊表，未列出者沿用原值 | `{}` |
| `residual_prefix` | 殘差桶標籤前綴，實際標籤為 `{prefix}{macro}` | `其他` |
| `mid_source` | 兩層巢狀：`macro 標籤 → mid 標籤 → 關鍵詞清單`。同一 macro 下所有關鍵詞會被攤平並依長度由長到短排序後比對 | `{}` |

## stability_check.py 的產出

全部寫在 `--outdir` 之下。此腳本以 `subprocess` 呼叫另兩支腳本，工作目錄固定為 **skill 根目錄**（`scripts/` 的上一層），故 `--config` 若給相對路徑是相對於該處解析。

| 檔案 | 內容 |
|---|---|
| `sample.jsonl` | 以 `--seed`（預設 4242）洗牌後取前 `--sample`（預設 40）篇的抽樣語料。**每行只有 `id` 與 `text` 兩個鍵**，carry 欄位不會保留 |
| `tvg_run{N}.csv` | 第 N 次（N 從 1 到 `--runs`，預設 3）`extract_tvg.py` 的輸出，欄位同 `tvg.csv`，但因未傳 `--carry-fields` 而只有標準欄位 |
| `mapped_run{N}.csv` | 第 N 次 `map_domains.py` 的輸出，欄位同 `mapped.csv` |
| `doc_jaccard.csv` | 逐文件的跨次一致性 |
| `source_distribution.csv` | 各次的來源域分布 |

`doc_jaccard.csv` 欄位：

| 欄位 | 意義 |
|---|---|
| `doc_id` | 文件識別碼，取所有次數出現過的 `doc_id` 聯集後排序 |
| `mean_jaccard` | 該文件在所有「兩兩配對」上的 Jaccard 平均值，四捨五入到小數第 4 位。比較單位是該文件所有 `mapping_valid == "1"` 列的 `(target_domain, source_domain)` **集合**（去重，不計次數）。兩集合皆空時定義為 1.0；`--runs 1` 時沒有配對，一律 1.0 |
| `pairs_run1` | 第 1 次執行中該文件的相異 domain pair 數量，用來判斷高一致性是否只是因為抽不到東西 |

`source_distribution.csv` 欄位：

| 欄位 | 意義 |
|---|---|
| `run` | 第幾次執行，從 1 起算 |
| `source_domain` | 來源域標籤，只計 `mapping_valid == "1"` 的列 |
| `count` | 該次該標籤的列數，依次數由多到少排列 |

此數值是**可重現性**指標，不是準確率。終端另會列印整體平均 Jaccard，以及 `mean_jaccard < 0.5` 的文件數量作為人工複核的優先清單。
