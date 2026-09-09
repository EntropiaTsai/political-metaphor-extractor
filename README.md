# political-metaphor-extractor

Political Metaphor Extractor（以下簡稱 **PME**）是一個 Cursor Agent Skill，用來從政治文本語料中抽取概念性隱喻，建立三層來源域本體，並產生統計與互動式視覺化。

## 安裝

最省事的方式是讓 agent 幫你裝。打開 Cursor，在對話裡貼上這一句：

> 我想要使用這個 skill https://github.com/EntropiaTsai/political-metaphor-extractor

agent 會把它 clone 到你的個人 skills 目錄、確認環境可用，之後在所有專案都能觸發。

想自己下指令也可以：

```bash
git clone https://github.com/EntropiaTsai/political-metaphor-extractor.git \
  ~/.cursor/skills/political-metaphor-extractor
```

只想在單一專案使用、或想跟著該專案的 git 分享給協作者，就改 clone 到 `<你的專案>/.cursor/skills/political-metaphor-extractor`。不用 git 的話，把整個資料夾下載後複製到上述任一位置也一樣。

Cursor 會自動載入，不需要額外設定。

## 開始用

裝好之後，直接在對話裡描述你要做的事就會觸發，例如：

> 這是我蒐集的 PTT 貼文 posts.jsonl，幫我抓政治隱喻，做出三層來源域統計和視覺化

agent 會依照 `SKILL.md` 帶你走完抽取、建本體、統計到視覺化。你不需要自己讀 `SKILL.md`，那份是寫給 agent 看的。

**預設不需要任何 API key。** 由 agent 直接讀 prompt 進行標註，適合數十到約兩百則的語料。語料達上千則時可改用腳本模式批次呼叫 LLM API，此時需要你自己的金鑰，寫在自己的 `.env` 裡（本 skill 不含也不會索取任何金鑰）。

這套流程是針對**政治文本**設計的，prompt 與 taxonomy 都內建了政治語境的假設。用在其他領域需要大幅改寫，細節見 `SKILL.md` 的「適用範圍」。

## 環境需求

- Python 3.9 以上
- PyYAML（`pip3 install pyyaml`）

其餘全部使用標準函式庫。視覺化預設從 CDN 載入 d3，若要離線使用，下載 d3 後以 `--d3-src` 指向本機檔案。

想自己確認環境沒問題，開一個工作目錄跑一致性檢查（不要開在 skill 資料夾裡，產生的檔案會混進 repo）：

```bash
SKILL=~/.cursor/skills/political-metaphor-extractor
mkdir -p ~/Desktop/metaphor && cd ~/Desktop/metaphor
cp -r $SKILL/assets/* .
python3 $SKILL/scripts/validate_config.py --config config.yaml --rules hierarchy_rules.yaml
```

看到 `config is consistent` 就代表環境沒問題。`assets/sample_corpus.jsonl` 是六則示範語料，可以拿來走一遍完整流程。

## 內容

```
SKILL.md                 工作流程主文件（agent 讀這份）
assets/                  設定範本，複製到你的工作目錄後修改
  config.yaml            模型與批次設定
  taxonomy.yaml          domain 標籤空間
  hierarchy_rules.yaml   中層規則
  prompts/               兩階段的 system 與 user prompt
scripts/                 pipeline 腳本
references/              prompt 設計、taxonomy 設計、人工後審、資料格式
```

換一批語料時要改 `prompts/extract_system.md` 的語料脈絡區塊、`taxonomy.yaml` 的標籤清單、`hierarchy_rules.yaml` 的中層規則，改完跑 `validate_config.py` 檢查一致性。這些 agent 都會幫你處理，細節見 `SKILL.md`。

## 授權與引用

如果這套流程對你的研究有幫助，請在方法章節說明使用了 LLM 輔助的兩階段隱喻抽取流程，並附上你實際使用的 `config.yaml`、`taxonomy.yaml` 與 `hierarchy_rules.yaml` 作為附錄——這三個檔案是重現實驗的最小充分條件。
