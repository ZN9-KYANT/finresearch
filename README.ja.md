# finresearch 🌙

[License: MIT](LICENSE) · Python 3.10+ · CI: `.github/workflows/ci.yml` を参照 ·
[English](README.md) | **日本語**

**AI エージェントとリサーチ自動化のための金融リサーチツール。** finresearch は無料の
オープンソース CLI です。第一に AI エージェント、cron ジョブ、スクリプトから使われる
ことを想定し、第二にターミナルの人間が使えるように設計しています。対話的な入力を一切
求めず、デフォルトでは API キー不要、JSON を stdout に、診断メッセージを stderr に
出力し、誰も見ていない無人実行でも各データ提供元に対して行儀よく振る舞います。

対象は、米国株と日本株のファンダメンタルズ、SEC EDGAR の提出書類(インサイダーの
Form 4、13F、13D/G、S-3/424B、自社株買い、8-K)、FINRA の空売り残高、SEC の未決済
(fails-to-deliver)、オプションフロー、FRED のマクロ指標、FOMC 声明と市場が織り込む
金利見通し、全市場スクリーニング、プレマーケットのギャップ銘柄です。データはすべて
公式の公開ソース(SEC EDGAR、FRED、米連邦準備制度、FINRA)か、無料のコミュニティ
エンドポイント(yfinance 経由の Yahoo Finance)から取得します。有料の API キーは不要で、
有料の AI 向け金融データ API のオープンソース代替です。

→ 機械向けの契約、ツール呼び出しと cron のレシピは
[エージェントと自動化のための設計](#エージェントと自動化のための設計) へ。エージェントには
[finresearch スキル](skills/finresearch/SKILL.md)(英語)を導入すれば、1 つのファイルで
ツール全体を習得できます。日本株での使い方は [日本株での使い方](#日本株での使い方) を
参照してください。

> このドキュメントは英語版 [README.md](README.md) の翻訳です。内容に差異がある場合は
> 英語版が優先されます。

## 主な機能

- **`insider`** — SEC EDGAR に直接アクセスする Form 4 スクリーナー。インサイダーの
  市場での買い・売りを、役職、株数、価格、金額とともにウォッチリスト全体で一覧化します。
  再配信業者ではなく、提出書類そのものを解析します。
- **`13f`** — Form 13F-HR による機関投資家の保有状況。任意の提出者の保有銘柄
  (`13f holder BRK-B`)、ある銘柄を保有する機関(`13f who NVIDIA CORP`)、四半期ごとの
  保有者の変化(`13f diff NOKIA CORP` — 提出者ごとの新規・全売却・買い増し・売り)。
  提出書類ごとに金額の単位を判定します(実際のデータ品質の落とし穴: 単位は 2023 年に
  千ドルから 1 ドル単位に変わりましたが、今も誤って提出する機関があります)。
- **`activist`** — 銘柄に対する SC 13D/G の大量保有。5% 以上の保有者を、アクティビスト
  的な意図の記述があるものと受動的な 13G 保有者に分けて表示します。
- **`dilution`** — S-3 シェルフ登録と 424B の発行条件確定、株数・規模のヒント、ATM
  (at-the-market)プログラムの検出。インサイダー買いの弱気側の鏡像です。
- **`buyback`** — 自社株買いプログラム: XBRL による実際の買付額の推移
  (`PaymentsForRepurchaseOfCommonStock`)、承認額・残額、8-K/添付資料での発表。
- **`8k`** — 項目コード別のイベント一覧(2.02 決算、4.01 監査人の変更、4.02 過去の
  財務諸表への依拠不可、1.01 重要な契約、5.02 役員の異動など)。`--has` で絞り込めます。
- **`ftd`** — SEC の未決済(Fails-to-Deliver)データ。月 2 回公表される公式データで、
  スクイーズ分析の基礎になります。未決済金額で集計し、銘柄ごとの履歴も表示します。
- **`short`** — FINRA の空売り残高をカバー日数順に表示(キー不要の過去データ。任意の
  無料 API キーで最新の半月ごとのデータ)。
- **`options`** — ライブのオプションチェーンから異常な取引を検出: 出来高と建玉の比較、
  プット・コール比率、IV スキュー(yfinance、無料)。
- **`fomc`** — FRB 声明のタカ派/ハト派スコアと会合間のスタンス変化、議事要旨、会合
  カレンダー。さらに `fomc odds` で Polymarket の FOMC 市場から金利決定の確率を取得します。
- **`fred`** — 80 万以上の FRED 系列に対する 54 個の厳選エイリアス、マクロ
  ダッシュボード、逆イールドのスプレッド付きイールドカーブ。
- **`gappers`** — カタリストとなるヘッドライン付きのプレマーケット・ギャップ銘柄
  スキャナー。
- **`scan`** — Yahoo のサーバー側エンジンによる全市場スクリーニング: 株価・バリュ
  エーション・利益率・成長性・空売り・保有構成にわたる 24 のフィルター項目、59 の
  リージョン(米国、日本など)。銘柄リストは不要で、市場全体から候補を見つけます。
- **`ticker` / `sec` / `compare` / `screen`** — ファンダメンタルズ、XBRL の財務項目
  (`--concept revenue`)、銘柄比較、PEG を考慮したスクリーナー。日本株(`7203.T`、
  `6758.T` など)も ¥ 表示で端から端まで動作します。

## インストール

```bash
git clone https://github.com/ZN9-KYANT/finresearch.git
cd finresearch
pip install -e .

# 任意: gappers のカタリストに JS で描画される TradingView ニュースを使う場合
pip install -e ".[crawl4ai]"
```

任意の設定(`screen` と `insider scan` が共通で使用):

```bash
mkdir -p ~/.config/finresearch
# 1 行に 1 ティッカー、# 以降はコメント
cat > ~/.config/finresearch/watchlist.txt <<'EOF'
NVDA
ASML
VST
EOF
# 任意: FRED API キー(無料、https://fred.stlouisfed.org/docs/api/api_key.html)
echo "FRED_API_KEY=yourkey" > ~/.config/finresearch/.env && chmod 600 ~/.config/finresearch/.env
```

ウォッチリストのファイルがない場合、リスト系のコマンドは小さな中立的デモ銘柄群で
動作します。`FRED_API_KEY` は環境変数、`~/.config/finresearch/.env`、またはカレント
ディレクトリの `.env` から読み込みます。`FINRA_API_KEY`(無料、
https://finra.org/finra-data。最新の空売り残高が取得可能になります)と
`FINRESEARCH_SEC_UA` は環境変数からのみ読み込みます。`FINRESEARCH_CONFIG_DIR` で設定
ディレクトリ全体の場所を変更できます。

## エージェントと自動化のための設計

finresearch は、エージェントが呼び出すツール、あるいはスケジューラが無人で実行する
ツールとして作られています。呼び出し側に対して、次のことを保証します。

| 契約 | エージェント・スクリプト・cron ジョブにとっての意味 |
|---|---|
| **非対話** | プロンプト、ページャー、TTY を前提としません。cron、CI、systemd/launchd タイマー、ツール呼び出し環境で安全に使えます。 |
| **すべてのコマンドで stdout に JSON** | 全コマンドが `--json` に対応。stdout はちょうど 1 つの JSON ドキュメントになり、進捗・警告・`[skip]` 通知は stderr に出ます。全コマンドの構造と単位: [`docs/JSON.md`](docs/JSON.md)(英語)。 |
| **予測可能な終了コード** | `0` 成功、`1` エラー(stderr に `finresearch: error: …` の 1 行、stdout は空)、`2` 使い方の誤り。不明なティッカー、到達できないデータソース、誤ったテンプレートはエラーです。トレースバックが必要なら `FINRESEARCH_DEBUG=1` を設定します。 |
| **空はエラーではない** | 「該当なし」は有効な JSON(`[]`、`{"results": []}`)と終了コード 0 で返るため、`jq -e 'length > 0'` がそのままアラート条件になります。 |
| **生の値と明示的な単位** | JSON には整形前の数値が入ります。`ticker --json` は `currency`(上場通貨)と `financial_currency`(報告通貨)を明示します。単位の約束(パーセントか分数か、13F の金額単位)は [`AGENTS.md`](AGENTS.md) に記載しています。 |
| **デフォルトでキー不要** | `fred` 以外のすべてのコマンドは設定なしで動作します。任意のキーは環境変数から読むため、シークレットマネージャーや crontab の環境変数行にそのまま使えます。 |
| **ジョブごとの分離** | `FINRESEARCH_CONFIG_DIR=/path/to/job` で、エージェントやジョブごとに独自のウォッチリスト、スキャンテンプレート、`.env` を持てます。 |
| **保存済みクエリ** | エージェントが一度スクリーニング条件を設計すれば(`scan NAME --save`)、cron ジョブが名前で何度でも再実行できます(`scan NAME --json`)。 |
| **自己記述的** | すべての階層で `finresearch --help` と `<command> --help` が使えるため、エージェントがツールの機能を把握できます。`--version` でパイプラインの動作を固定できます。 |
| **無人でも行儀よく** | SEC へのリクエストは 1 つのペース制御付きフェッチャーで毎秒 10 件未満に抑え、User-Agent を明示します。FRED は表示する観測値だけを取得し、8-K の項目コードは書類ごとのダウンロードではなく 1 回のフィード取得で得ます。 |

`--json` を付けない場合、すべてのコマンドは同じ終了コードのまま、人間向けの
Markdown を出力します。

### エージェントからの呼び出し

シェルコマンドやサブプロセスを実行できるエージェントフレームワークなら、どれでも
ツールとして使えます。最小限の Python ラッパー:

```python
import json, subprocess

def finresearch(*args):
    """finresearch のコマンドを実行し、解析済みの JSON を返す(stderr = 診断情報)。"""
    proc = subprocess.run(["finresearch", *args, "--json"],
                          capture_output=True, text=True, check=True, timeout=300)
    return json.loads(proc.stdout)

trades = finresearch("insider", "scan", "--tickers", "NVDA,AMD,MU", "--days", "7")
movers = finresearch("scan", "--day-chg-min", "5", "--volume-min", "5000000")
```

エージェントにはツールの説明として `finresearch --help`(またはこの README)を、返って
くるデータのスキーマとして [`docs/JSON.md`](docs/JSON.md) を渡してください。各サブ
コマンドの `--help` にフラグと単位が載っています。`check=True` の場合、エラーは
`CalledProcessError` として送出され、その `stderr` に 1 行の理由が入っています。

### 定期実行(cron)

ただのコマンドなので、cron、systemd タイマー、launchd、GitHub Actions のスケジュール、
エージェント自身のスケジューラのどれでも動きます。cron は最小限の環境で実行されるため、
絶対パスを使い、キーは crontab の変数として設定し、`%` は `\%` とエスケープしてください。

```cron
# 時刻はこのマシンのローカル時刻です(以下の例は米国東部時間の市場時間を想定)。
FR=/home/you/finresearch/.venv/bin/finresearch
OUT=/home/you/research
FINRESEARCH_SEC_UA=my-research-bot/1.0 you@example.com

# 月〜金 08:45: プレマーケットのギャップ銘柄(各実行は ~/.cache/finresearch/gappers/ にも保存)
45 8 * * 1-5  $FR gappers --json > $OUT/gappers-$(date +\%F).json 2>> $OUT/cron.log

# 月〜金 18:30: ウォッチリスト全体のインサイダーの市場での売買
30 18 * * 1-5 $FR insider scan --days 1 --json > $OUT/insiders-$(date +\%F).json 2>> $OUT/cron.log

# 毎日 07:00: 監査人の変更(4.01)または財務諸表への依拠不可(4.02)の 8-K が出たときだけ通知
0 7 * * *     $FR 8k NVDA,AMD,MU --days 1 --has 4.01,4.02 --json | jq -e 'length > 0' >/dev/null && echo "restatement-risk 8-K filed" | mail -s finresearch you@example.com

# 毎日 07:15: FOMC の市場予想確率のスナップショット
15 7 * * *    $FR fomc odds --json > $OUT/fomc-odds-$(date +\%F).json 2>> $OUT/cron.log

# 日曜 10:00: 保存済みの全市場スクリーニングを再実行(quality-dip は examples/scans.toml に同梱)
0 10 * * 0    $FR scan quality-dip --json > $OUT/quality-dip-$(date +\%F).json 2>> $OUT/cron.log
```

日本のマシンで米国市場の時間に合わせる場合: 米国東部時間は夏時間(EDT)で日本時間の
13 時間遅れ、冬時間(EST)で 14 時間遅れです。たとえば米国プレマーケットの 08:45 ET は、
夏は 21:45 JST、冬は 22:45 JST です。

### パイプライン(jq)

```bash
finresearch scan quality-dip --json | jq -r '.results[].symbol'          # 次の処理に渡すティッカー
finresearch insider scan --days 14 --json \
  | jq -r '.[] | select(.transactions | length > 0) | "\(.ticker): \(.transactions | length) trades"'
finresearch gappers --json --no-catalyst | jq -r '.gappers[] | "\(.symbol) \(.premarket_gap_pct)%"'
finresearch fomc odds --limit 1 --json \
  | jq -r '.[0] | "\(.meeting): " + ([.buckets | to_entries[] | "\(.key) \(.value*100|round)%"] | join(", "))'
```

### 無人実行時のレート配慮

- **SEC EDGAR** は内部でペース制御しています(毎秒 10 件以下)。定期実行や大量の利用では、
  SEC がブロックではなく連絡を取れるよう、`FINRESEARCH_SEC_UA` に実在の連絡先を設定して
  ください。`insider`/`13f` の過去検索は `--days` を控えめにしてください。
- **FRED** は 1 分あたり 120 リクエストまでです。`fred dashboard` の全表示は約 40 件を
  使うため、1 分に 1 回程度までにしてください。
- **Yahoo 系のコマンド**(`ticker`、`compare`、`screen`、`scan`、`options`)は非公式の
  エンドポイントを使い、レートに敏感です。ループで回さずスケジュールで実行し、ジョブの
  間隔を数分空けてください。

### finresearch スキル(エージェントにツール全体を教える)

[`skills/finresearch/SKILL.md`](skills/finresearch/SKILL.md)(英語)は、エージェント向けに
書いた完全な利用ガイドです。どの質問にどのコマンドを使うか、調査ワークフロー、単位と
データ上の注意点、JSON の契約をまとめています。Agent Skills 形式(YAML フロントマター +
Markdown)に従っているため、スキル対応のエージェントは必要なときに読み込みます。それ
以外のエージェントには、このファイルを示すだけで十分です。

```bash
# Claude Code(全プロジェクト共通)。スキルはシンボリックリンク経由で docs/JSON.md を
# 参照するため、コピーではなくディレクトリごとリンクしてください
mkdir -p ~/.claude/skills && ln -s "$PWD/skills/finresearch" ~/.claude/skills/finresearch
```

このリポジトリ内では、Claude Code は `.claude/skills/finresearch` ですでにこのスキルを
認識しています。

### このリポジトリで作業するコーディングエージェント

ルートの `AGENTS.md` に、すべてのコーディングエージェントが従うべきガイドがあります:
ツールの使い方、セットアップ、検証ゲート、アーキテクチャ、単位の約束、リリース手順。
Codex、Grok、pi、Hermes はこのファイルをそのまま読み、Claude Code はそのシンボリック
リンクである `CLAUDE.md` を読みます。クローン直後は 1 コマンドでリンク類をまとめて
作成できます:

```bash
./scripts/install-agent-files.sh   # CLAUDE.md とプロジェクトスキルをリンクし、.cursor ルールを書き出す
```

## 日本株での使い方

finresearch は日本の上場銘柄にも対応しています。Yahoo Finance の表記どおり、証券
コードに `.T` を付けて指定します(トヨタ自動車 = `7203.T`、ソニーグループ = `6758.T`、
ソフトバンクグループ = `9984.T`)。

```bash
finresearch ticker 7203.T                                  # 概要(株価・時価総額は円)
finresearch ticker 7203.T --section financials             # 財務諸表(円)
finresearch ticker 6758.T --section technicals             # テクニカル指標(¥ 表示)
finresearch compare 7203.T 6758.T 9984.T                   # 銘柄比較
finresearch screen --tickers 7203.T,6758.T,8306.T --max-pe 30
finresearch scan --region jp --mktcap 5e12 1e14 --sort mktcap   # 時価総額 5 兆円以上
finresearch scan --region jp --mktcap 1e12 1e14 --pe-max 15     # 時価総額 1 兆円以上・PER 15 倍以下
```

- **通貨**: 日本株は株価・財務数値ともに円です。`--json` の `currency` と
  `financial_currency` は `JPY` になります。
- **`scan --region jp` の金額は円**: `--mktcap 5e12 1e14` は 5 兆円〜100 兆円です。
  `screen` の `--min-mktcap`/`--max-mktcap` も上場通貨(円)で比較します。
- **日本株クオリティのテンプレート**: `examples/scans.toml` の `jp-quality` を
  `~/.config/finresearch/scans.toml` に追加すると、`finresearch scan jp-quality` で
  実行できます。
- **米国専用の機能**: SEC EDGAR(`sec`、`insider`、`13f`、`activist`、`dilution`、
  `buyback`、`8k`、`ftd`)、FINRA(`short`)、`options` は米国市場のデータです。日本の
  開示(EDINET、TDnet)には対応していません。
- **データの遅延**: Yahoo Finance のデータは非公式で、遅延することがあります。

## 所有・資金フロー系コマンド(SEC EDGAR)

```bash
finresearch insider scan --tickers NVDA,AMD,MU --days 7 --min-value 100000
finresearch insider detail META --days 30         # 1 社の Form 4 取引すべて
finresearch 13f holder BRK-B --top 15             # 1 提出者の最新の保有銘柄(四半期末時点)
finresearch 13f who NVIDIA CORP                   # ある銘柄を保有する提出者
finresearch 13f diff NOKIA CORP --limit 15        # 提出者ごとの四半期比の新規/全売却/買い増し/売り
finresearch activist NOK,SPCX --days 400          # SC 13D/G の保有(アクティビストか受動的か)
finresearch dilution VST,NVDA --days 365          # S-3 シェルフ + 424B の発行条件確定
finresearch buyback NVDA,VST --days 400           # 自社株買いの実績(XBRL)+ 発表
finresearch 8k NVDA --days 60 --has 2.02,4.02     # 項目コード別の 8-K イベント一覧
```

## コマンドリファレンス

### 銘柄データ(yfinance)

```bash
finresearch ticker VST                          # 概要
finresearch ticker VST --section financials     # 損益計算書、貸借対照表、キャッシュフロー
finresearch ticker VST --section kpis           # EPS・売上高予想、利益率、PEG
finresearch ticker VST --section earnings       # 決算履歴、サプライズ、次回予定日
finresearch ticker VST --section insiders       # インサイダー取引(yfinance の表示)
finresearch ticker VST --section holdings       # 機関投資家の保有(yfinance の表示)
finresearch ticker VST --section technicals     # RSI、MACD、ボリンジャー、移動平均、シグナル
finresearch ticker VST --json
```

### SEC EDGAR(構造化 XBRL と提出書類)

```bash
finresearch sec VST                        # 主要な財務データ
finresearch sec VST --type 10-K            # 種類別の提出書類
finresearch sec VST --concept revenue      # わかりやすいエイリアス -> XBRL タグの時系列
finresearch sec VST --concept NetIncomeLoss
```

### インサイダー取引(SEC EDGAR Form 4 — 直接取得)

```bash
finresearch insider scan --tickers NVDA,AMD,MU --days 7 --min-value 100000
finresearch insider scan                          # ~/.config/finresearch/watchlist.txt を使用
finresearch insider detail META --days 30         # 1 社の Form 4 取引すべて
finresearch insider detail META --json
```

市場での取引(コード P/S)に絞り込みます。付与、行使、源泉徴収は `detail` でコード
付きの参考情報として表示します。データは `data.sec.gov` の提出一覧と、提出書類自身の
XML から取得します。

### 機関投資家の保有(SEC Form 13F-HR — 直接取得)

```bash
finresearch 13f holder BRK-B --top 15       # 1 提出者の最新の保有銘柄(四半期末時点)
finresearch 13f holder 0001067983 --json    # CIK で指定
finresearch 13f who NVIDIA CORP             # ある銘柄を保有する提出者(13F-HR の全文検索)
```

`13f` の金額は四半期末時点の評価額です。`<value>` の単位は 2023-01-03 以降の提出では
1 ドル単位、それ以前は千ドル単位ですが、規則どおりに提出しない機関もあります。
finresearch は提出書類ごとに 1 株あたりの推定価格を実際の株価と比べ(できない場合は
提出日で判断し)、その結論をヘッダーに表示します。`13f who` は EDGAR の全文検索を
使います(検索インデックスの上限は 1 万件。ページ送りによる取得は今後の予定です)。

### FOMC(米連邦準備制度)

```bash
finresearch fomc calendar              # 会合カレンダー、次回会合までの日数
finresearch fomc statement             # 最新の声明(全文 + センチメントスコア)
finresearch fomc statement 2026-06-16  # 特定の会合
finresearch fomc minutes --full        # 議事要旨(会合の約 3 週間後に公表)
finresearch fomc sentiment             # 直近 2 回の声明のタカ派/ハト派の変化
finresearch fomc odds                  # 市場が織り込む金利決定の確率(Polymarket)
finresearch fomc statement --json
```

`fomc odds` は予測市場のライブ価格を読み取ります(金利変更幅ごとの価格を確率分布に
正規化)。CME FedWatch 自体はボット対策でブロックされ、利用規約でも制限されているため、
Polymarket の公開 Gamma API を無料の代替として使っています。

### 機関投資家のフロー: 未決済、空売り残高、オプション

```bash
finresearch ftd top                            # 最新の SEC ファイルで未決済の大きい銘柄
finresearch ftd top --by quantity --min-quantity 10000
finresearch ftd sym GME --files 3              # 1 銘柄の未決済の履歴
finresearch short --top 15                     # FINRA の空売り残高(カバー日数順)
finresearch short --by si --min-si 1000000
finresearch options NVDA                       # 異常な取引 + プット・コール比率 + IV スキュー
finresearch options NVDA --vol-oi 2.0 --json
```

`ftd` は SEC が月 2 回公表する公式データです(キー不要)。`short` はキーなしでは無料の
過去データで動作し、`FINRA_API_KEY`(無料)を設定すると最新の半月ごとのデータを取得
します。`options` は yfinance のチェーンを使います(遅延あり)。

### FRED マクロデータ

```bash
finresearch fred dashboard                       # 金利、インフレ、雇用、GDP など
finresearch fred dashboard --group inflation
finresearch fred series fed_funds --years 2
finresearch fred yield_curve                     # イールドカーブ全体 + 2年-10年/3か月-10年スプレッド
finresearch fred search "housing" --limit 10
finresearch fred list                            # 54 個のエイリアスすべて
```

### スクリーニングと比較

```bash
finresearch compare VST WMB GEV CEG TLN
finresearch screen --tickers NVDA,AMD,MU --max-peg 2 --sort growth
finresearch screen                                    # 設定ファイルのウォッチリストを使用
```

### 全市場スキャン(サーバー側)

`scan` は Yahoo のサーバー側スクリーナーエンジンで市場全体を対象に実行します。銘柄
リストは不要です(指定した銘柄を絞り込む `screen` とは異なります)。クエリはサーバー側で
数千の銘柄に対して実行され、該当銘柄が総件数とともに 1 回の呼び出しで返ります。

```bash
finresearch scan [範囲フィールド] [min/max フィールド] [--sector X] [--industry X]
                 [--region us] [--sort FIELD] [--ascending] [--limit N] [--json]
```

#### 範囲フィールド(下限 LO と上限 HI の 2 つの値。生の数値)

```bash
--price 5 100        # 日中の株価帯
--mktcap 2e9 2e10    # 時価総額帯(20 億〜200 億)。米国以外は上場通貨(region jp なら円)
```

#### しきい値フィールド(--名前-min / --名前-max)

比率のフィルターは**パーセントの数値**で指定します。`--netmargin-min 20` は 20% の
意味です(Yahoo の比率項目はパーセントで表現されています。実際に確認した結果:
利益率 > 20 では約 1 万銘柄中 約 2,277 銘柄が残り、> 0.2 ではほぼすべてが残ります)。

| フラグ | 対象 | 単位 |
|---|---|---|
| `--avgvol-min/max` | 3 か月平均の 1 日出来高 | 株 |
| `--volume-min/max` | 当日の出来高 | 株 |
| `--day-chg-min/max` | 当日の値動き | パーセント |
| `--pe-min/max` | 実績 PER | そのまま |
| `--peg-min/max` | PEG(5 年) | そのまま |
| `--netmargin-min/max` | 純利益率 | パーセント |
| `--grossmargin-min/max` | 粗利益率 | パーセント |
| `--ebitda-margin-min/max` | EBITDA マージン | パーセント |
| `--revgrowth-min/max` | 1 年の売上成長率 | パーセント |
| `--epsgrowth-min/max` | EPS 成長率 | パーセント |
| `--roe-min/max` | 自己資本利益率(ROE) | パーセント |
| `--shortfloat-min/max` | 浮動株に対する空売り比率 | パーセント |
| `--dtc-min/max` | 空売りのカバー日数 | 日 |
| `--inst-held-min/max` | 機関投資家の保有比率 | パーセント |
| `--insider-held-min/max` | インサイダーの保有比率 | パーセント |
| `--divyield-min/max` | 予想配当利回り | パーセント |
| `--debteq-min/max` | 負債資本倍率 | そのまま |
| `--quickratio-min/max` | 当座比率 | そのまま |
| `--altmanz-min/max` | Altman Z スコア | そのまま |
| `--beta-min/max` | ベータ | そのまま |
| `--pb-min/max` | PBR | そのまま |
| `--perf-52w-min/max` | 52 週の値動き | パーセント |

#### その他のオプション

```bash
--region us          # us, jp, gb, de, fr, hk, kr, tw, in, ca, au ...(Yahoo の 59 リージョン)
--sector financial   # Yahoo のセクター語彙に対するあいまい一致
--industry banks     # あいまい一致。不明な値なら候補を表示
--sort FIELD         # mktcap(既定)、price、day-chg、volume、pe、peg、netmargin、
                     # revgrowth、shortfloat、perf-52w
--ascending          # 昇順(既定は降順)
--limit 20           # 取得件数。Yahoo のページ上限は 250
--within-high 0.25   # 52 週高値から 25% 以内(分数。クライアント側で処理)
--below-high 0.2     # 52 週高値から 20% 以上下(押し目帯の上限)
--off-low 0.3        # 52 週安値から 30% 以上上(Minervini 流)
--json               # 機械向け出力: {"total", "dropped_by_post_filter", "results"}
```

52 週高値・安値からの距離による 3 つのフィルター(`--within-high/--below-high/
--off-low`)は、取得したページに対してクライアント側で実行します。Yahoo のスクリー
ナーでは高値・安値からの距離をサーバー側で指定できないためです。絞り込み前に十分な
候補が含まれるよう `--limit 250` と組み合わせてください(除外された件数が表示され、
`total` には絞り込み前の該当件数が残ります)。

#### レシピ

```bash
# 流動性のある割安株: 5〜100 ドル、十分な出来高、低 PER、ある程度の空売り
finresearch scan --price 5 100 --avgvol-min 500000 --pe-min 8 --shortfloat-min 5

# ショートスクイーズ候補: 高い空売り比率、カバー日数の増加、超小型株を除く
finresearch scan --shortfloat-min 15 --dtc-min 4 --price 2 50 --sort shortfloat

# 優良な複利成長株: 黒字、成長、低レバレッジ
finresearch scan --netmargin-min 15 --revgrowth-min 10 --debteq-max 1 --pe-min 0

# 安値圏の高配当株
finresearch scan --divyield-min 4 --price 5 200 --avgvol-min 2000000

# 日本の超大型株(時価総額は円で指定。5 兆円 = 5e12)
finresearch scan --region jp --mktcap 5e12 1e14 --sort mktcap

# モメンタム: 出来高を伴う当日の大幅高
finresearch scan --day-chg-min 5 --volume-min 5000000 --sort day-chg
```

注意: 1 回の呼び出しで返るのは最大 250 件(Yahoo のページ上限)で、実際の総該当件数は
常に表示されます。データは Yahoo のもの(非公式、遅延あり)です。内部では yfinance の
スクリーナーエンジンを使うため API キーは不要ですが、Yahoo のレート制限の影響を受けます。
定期実行は問題ありませんが、短い間隔のループは避けてください
([無人実行時のレート配慮](#無人実行時のレート配慮) を参照)。

#### 名前付きスキャンテンプレート(スキャン条件の保存)

独自のスキャン条件は `~/.config/finresearch/scans.toml` に TOML テンプレートとして保存し、
名前で実行します。キーは CLI のフラグ名(`--` を除く)とまったく同じです。

```bash
# 条件を指定して実行し、--save NAME2 --desc を付けて保存
finresearch scan --price 5 100 --avgvol-min 500000 --shortfloat-min 5 --save value2 --desc "cheap, liquid, shorted"
finresearch scan value2                     # 実行
finresearch scan                            # 保存済みテンプレートの一覧
finresearch scan value2 --limit 40          # CLI のフラグがテンプレートの値より優先
finresearch scan value2 --netmargin-min 10 --save value3   # 派生させて別名で保存
```

`scans.toml` の形式(手で編集することもできます):

```toml
[value2]
description = "cheap, liquid, shorted"
price = [5.0, 100.0]        # 範囲フィールド: [下限, 上限] の組
avgvol-min = 500000
shortfloat-min = 5.0
sort = "shortfloat"

[jp-mega]
description = "Japan large caps, cheap"
region = "jp"
mktcap = [5e12, 1e14]
pe-max = 12
```

優先順位: コマンドラインで指定しなかったフィルターをテンプレートが補うため、一時的な
上書き(`--limit` や、より厳しいしきい値)を自然に組み合わせられます。存在しない
テンプレート名を指定すると保存済みの一覧を示してエラーになり、不明な TOML キーは
クエリの実行前に有効なキーの一覧とともに拒否されます。

**すぐに使える例:** [`examples/scans.toml`](examples/scans.toml) には、有名な公開手法を
もとにした 7 つのテンプレートが同梱されています: モメンタムブレイクアウト
(Qullamaggie 流)、Minervini のトレンドテンプレート、CAN SLIM の近似、クオリティ銘柄の
押し目、当日の値上がり銘柄、出来高上位、日本株のクオリティスクリーン。それぞれに、
スクリーナーエンジンでは表現できない条件(RS パーセンタイル、移動平均の並び、予想の
修正)と、手作業で確認すべき点を注記しています。[examples/README.md](examples/README.md)
(英語)を参照してください。

導入方法:

```bash
cat examples/scans.toml >> ~/.config/finresearch/scans.toml
finresearch scan                      # 7 つがテンプレート一覧に表示される
finresearch scan quality-dip          # 1 つを実行。フラグでの上書きも可能
```

リリース履歴は [`CHANGELOG.ja.md`](CHANGELOG.ja.md)([English](CHANGELOG.md))を参照して
ください。

### プレマーケットのギャップ銘柄

```bash
finresearch gappers                                  # カタリストのヘッドライン付き上位 10 銘柄
finresearch gappers --min-gap 5 --min-price 3 --min-volume 50000
finresearch gappers --no-catalyst                    # 高速
finresearch gappers --catalyst crawl4ai              # TradingView ニュース(crawl4ai が必要)
finresearch gappers --json --no-catalyst             # パイプ・エージェント向け(= --format json)
```

各実行の JSON は `~/.cache/finresearch/gappers/` にも保存されます(`--output-dir` で変更可)。

## データソースと利用規約

| ソース | 使用するコマンド | アクセス方式 |
|---|---|---|
| SEC EDGAR(`data.sec.gov`、`www.sec.gov`、`efts.sec.gov`) | `sec`、`insider`、`13f`、`activist`、`dilution`、`buyback`、`8k`、`ftd` | 公式の公開 API。User-Agent を明示し、毎秒 10 件以下を遵守 |
| SEC FTD ファイル(`www.sec.gov/files/data/fails-deliver-data`) | `ftd` | 公式の公開データセット。月 2 回の zip |
| FINRA API(`api.finra.org`) | `short` | キー不要の過去データ。最新データは無料の API キー |
| 米連邦準備制度(`federalreserve.gov`) | `fomc` | 公開ページ。声明・議事要旨ごとに 1 リクエスト |
| FRED(`fred.stlouisfed.org`) | `fred` | 公式 API。無料キー。毎分 120 リクエストを遵守 |
| Yahoo Finance(**yfinance** 経由) | `ticker`、`compare`、`screen`、`options`、日本株 | 非公式のコミュニティエンドポイント。データは遅延あり |
| Polymarket(Gamma API) | `fomc odds` | 公開の予測市場 API。認証不要 |
| TradingView / StockAnalysis / Google Finance | `gappers`、カタリスト | 公開 Web ページ(SSR)。非公式 |

**正確性と利用規約に関する注意。** yfinance による Yahoo Finance へのアクセスは非公式で
あり、Yahoo の利用規約の対象です。TradingView/StockAnalysis/Google Finance のデータは
公開ページから取得した非公式なものです。金融データは遅延(株価は最大 15 分程度)、速報値、
あるいは提供元での誤りを含む場合があります。判断に使う情報は、引用元の一次情報で確認して
ください。本ツールは調査・学習用であり、投資助言ではなく、市場データの再配信サービスでも
ありません。取得したデータは自身の分析の範囲で使い、提供元のデータを再公開・再販売しない
でください。すべてのソースには、公開されている正規の方法で、規約に沿ったレートで
アクセスしています。

`SEC EDGAR` のフェアアクセス規定では連絡先の明示が必要です。既定の User-Agent は
`finresearch/<version> contact@example.com` です。定期実行や大量の利用では
`FINRESEARCH_SEC_UA="your-tool/1.0 you@yourdomain.com"` を設定してください。

## テストと CI

```bash
pip install -e ".[dev]"
pytest tests/          # スコアラー、パーサー、単位判定、フォーマッター、テクニカル、出力契約
ruff check src/ tests/
```

CI はプッシュ/PR ごとにテスト + ruff + gitleaks によるシークレット検査を実行します
(Python 3.10 と 3.12)。コーディングエージェントで開発に参加する場合は
[このリポジトリで作業するコーディングエージェント](#このリポジトリで作業するコーディングエージェント)
を参照してください。

## ライセンス

[MIT](LICENSE)
