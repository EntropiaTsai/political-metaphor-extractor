# political-metaphor-extractor

Political Metaphor Extractor（以下簡稱 **PME**）是一個 Agent Skill，用來從政治文本語料中抽取概念性隱喻，建立三層來源域本體，並產生統計與互動式視覺化。

背後的分析方法論來自於開發者本人的相關研究：https://entropiatsai.github.io/sicol/index.html#/1

## 實際運行展示

以下為實際執行此 Skill 的完整對話與產出流程（包含隱喻標註、指派來源域、撰寫中層規則、產生互動式圓圈打包圖）：

[![PME 實際運行示範影片](https://img.youtube.com/vi/FYQF73CzfMI/0.jpg)](https://youtu.be/FYQF73CzfMI)

*(註：您可以點擊上方預覽圖或點擊 [YouTube 示範影片連結](https://youtu.be/FYQF73CzfMI) 直接線上觀看)*

**設計給研究者，不是給工程師。** 全程用對話操作：你把語料交給 AI 助理、用中文說你想做什麼，剩下的它會處理。你不需要寫程式、不需要輸入指令，也不需要看懂任何設定檔。

它遵循 [Agent Skills 開放標準](https://agentskills.io)，不綁定特定模型或工具，Claude Code、Cursor、Codex 等會讀 `SKILL.md` 的 AI 助理都能用。

## 安裝

在你的 AI 助理對話框裡貼上這一句就好：

> 我想要使用這個 skill https://github.com/EntropiaTsai/political-metaphor-extractor

它會先問你要裝成整台電腦都能用、還是只在目前這個專案裡用，然後自己下載安裝並告訴你放在哪裡。裝一次就好，之後每次開新對話都叫得動。

自己一個人做研究就選整台電腦都能用；如果你在一個要跟別人共用的專案資料夾裡工作，選只在這個專案，它會跟著專案一起分享給協作者。

<details>
<summary>給正在讀這段的 agent：安裝指示（使用者可略過）</summary>

把整個 repo clone 下來，資料夾名稱保持 `political-metaphor-extractor`，放進下表對應的位置，裝完用白話告訴使用者放在哪裡、之後怎麼觸發。

**動手前要問使用者兩件事。**

第一，裝的範圍。用白話問：「要裝成整台電腦都能用，還是只在這個專案裡用？」整台電腦能用（個人層級）適合自己一個人做研究，之後開任何專案都叫得動；只在這個專案用（專案層級）則會跟著這個資料夾的 git 一起分享給協作者，也方便為這批語料單獨調整分類架構。研究者多半要的是前者，但**不要替他決定**，尤其他正在一個共用的研究專案裡工作時。

第二，你跑在哪個工具裡。**要判斷的是執行環境，不是你的模型**——在 Cursor 裡執行的 Claude 模型屬於 Cursor，該裝 `~/.cursor/skills/`。判斷不出來就一起問使用者，這比猜錯好；若當下無法詢問，才退而用 `~/.claude/skills/`，Claude Code 與 Cursor 都會載入它。

| 工具 | 整台電腦（個人層級） | 只在這個專案 |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Cursor | `~/.cursor/skills/` | `.cursor/skills/` |
| 其他相容工具 | `~/.agents/skills/` | `.agents/skills/` |

`~/.agents/skills/` 是跨工具的通用慣例，Cursor 會讀，但 Claude Code 目前只讀 `.claude` 系列。**同一台機器只裝一份**——裝在多個位置之後改動不會互相同步，很難追是哪一份在生效。安裝前先看看其他位置是不是已經有同名資料夾，有的話更新既有那份，不要再開一份。

安裝指令，路徑換成上面問出來的位置：

```bash
git clone https://github.com/EntropiaTsai/political-metaphor-extractor.git \
  ~/.claude/skills/political-metaphor-extractor
```

裝在專案層級時提醒使用者：這個資料夾會被 git 追蹤，commit 之後協作者 clone 下來就能直接用。

Claude Code 的注意事項：如果 `~/.claude/skills/` 是這次才第一次建立，要提醒使用者重啟 Claude Code 才會開始監看它。

</details>

## 開始用

裝好之後，直接用中文描述你要做的事，例如：

> 這是我蒐集的 PTT 貼文，幫我抓政治隱喻，做出三層來源域統計和視覺化

語料給什麼格式都可以——Excel、CSV、純文字、一整個資料夾的檔案都行，助理會自己整理。它會在開始前問你兩件事：分析結果要不要保存下來、能不能在你電腦上建一個小的執行環境。不保存的話，它會把統計和視覺化直接呈現給你看，結束後主動清乾淨，不會在硬碟上留下你記不得的資料夾。

跑完你會拿到三層來源域的頻率統計，以及兩份互動式圖表：

- **圓圈打包圖**回答「政治被比喻成什麼」。可以點擊縮放，點進最內層能看到每個隱喻的原始例句。
- **配對圖**回答「誰被比喻成什麼」。左邊是被談論的對象、右邊是來源域，點任一邊就會拉出它配到的所有東西。這張圖常常會露出圓圈圖看不到的分工——例如同一批資料裡，支持者被講成猴子和鳥，政治人物卻是被講成狗。

**預設不需要任何 API key、不需要付費。** 助理會直接讀 prompt 逐則標註，適合數十到約兩百則的語料。語料達上千則時可改用批次呼叫 LLM API 的模式，那才需要你自己的金鑰（本 skill 不含也不會索取任何金鑰）。

這套流程是針對**政治文本**設計的，prompt 與分類架構都內建了政治語境的假設。用在其他領域需要大幅改寫，細節見 `SKILL.md` 的「適用範圍」。

## 電腦需求

需要 Python 3.9 以上。macOS 與多數 Linux 內建就有，不用另外裝；Windows 若沒有，助理會告訴你怎麼處理。除此之外只需要一個叫 PyYAML 的小套件，助理會徵得你同意後裝在獨立環境裡，不會動到你電腦上其他設定。

視覺化圖表預設從網路載入繪圖函式庫，所以開圖時要能連網。需要離線展示（例如研討會現場網路不穩）就先跟助理說，它會改成把函式庫一起打包進去。

<details>
<summary>給熟悉終端機的人：自行驗證安裝</summary>

```bash
SKILL=~/.claude/skills/political-metaphor-extractor   # 換成你實際安裝的位置
mkdir -p ~/Desktop/metaphor_check && cd ~/Desktop/metaphor_check
cp -r $SKILL/assets/* .

python3 -m venv .venv
.venv/bin/pip install -q pyyaml
.venv/bin/python $SKILL/scripts/validate_config.py --config config.yaml --rules hierarchy_rules.yaml
```

看到 `config is consistent` 就代表環境沒問題，確認完可以直接 `rm -rf ~/Desktop/metaphor_check`。`assets/sample_corpus.jsonl` 是六則示範語料，可以拿來走一遍完整流程。

</details>

## 內容

```
SKILL.md                 工作流程主文件（agent 讀這份）
assets/                  設定範本，複製到工作目錄後修改
  config.yaml            模型與批次設定
  taxonomy.yaml          domain 標籤空間
  hierarchy_rules.yaml   中層規則
  prompts/               兩階段的 system 與 user prompt
scripts/                 pipeline 腳本
references/              prompt 設計、taxonomy 設計、人工後審、資料格式
```

換一批語料時，`prompts/extract_system.md` 的語料脈絡區塊、`taxonomy.yaml` 的標籤清單、`hierarchy_rules.yaml` 的中層規則都要跟著調整。這些助理會提議並代你修改，改完自動驗證一致性，你只需要判斷它的提議合不合理。

## 授權與引用

如果這套流程對你的研究有幫助，請在方法章節說明使用了 LLM 輔助的兩階段隱喻抽取流程，並附上你實際使用的 `config.yaml`、`taxonomy.yaml` 與 `hierarchy_rules.yaml` 作為附錄——這三個檔案是重現實驗的最小充分條件。
