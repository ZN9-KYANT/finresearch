# 変更履歴

[English](CHANGELOG.md) | **日本語**

finresearch の主な変更点を記録します。書式は
[Keep a Changelog](https://keepachangelog.com/ja/) に、バージョン番号はセマンティック
バージョニングに従います。英語版 [`CHANGELOG.md`](CHANGELOG.md) が原本で、本ファイルは
その翻訳です。

## [1.1.1] — 2026-10-02

エージェントと日本のユーザー向けのドキュメントリリース: ツール全体を解説する
Agent Skills ガイド、再構成した AGENTS.md、日本語の README と変更履歴を追加しました。
動作の変更はありません。

### 追加
- `skills/finresearch/SKILL.md`: エージェントがツール全体を習得するための Agent Skills
  ガイド。どの質問にどのコマンドを使うか、調査ワークフロー、単位とデータ上の注意点、
  出力契約をまとめています。プロジェクトスキルとして `.claude/skills/finresearch` に
  リンクされ、`scripts/install-agent-files.sh` がそのリンクを作成します。
- 日本語ドキュメント: `README.ja.md` と `CHANGELOG.ja.md`。
- `tests/test_docs.py`: すべてのコマンドがスキルと `docs/JSON.md` に記載されていること、
  日本語の変更履歴にすべてのリリースが含まれていることを検証します。

### ドキュメント
- `AGENTS.md` を再構成しました。パート A(ツールを利用するエージェント向け: 呼び出し
  契約、コマンド早見表、単位、マナー)とパート B(リポジトリを開発するエージェント向け)
  に分け、リリース手順(全バージョンで GitHub Release を作成)を追加しました。
- README と 1.0.0 の項目の数値を訂正しました: FRED エイリアスは 54 個(旧記載「56」)、
  `scan` のフィルター項目は 24 個(旧記載「約 90」)、Yahoo のリージョンは 59
  (旧記載「58」)。README の scan 項目表に `beta`、`pb`、`perf-52w` を追加しました。

## [1.1.0] — 2026-10-02

完全な機械可読出力: すべてのコマンドが JSON を出力し、共通の出力契約に従うように
なりました。AI エージェント、スクリプト、cron ジョブのための設計です。

### 追加
- `--json` 未対応だった残り 10 コマンドに対応: `sec`(主要財務データ、`--type`、
  全履歴を返す `--concept`)、`compare`、`transcript`、`fred dashboard`、`fred list`、
  `fred yield_curve`、`fomc calendar`、`fomc sentiment`、`13f who`、`13f diff`。
  これで全コマンドが `--json` を受け付けます。
- `gappers --json`(`--format json` の別名)。どのコマンドでも同じフラグが使えます。
- `scan --json` で保存済みテンプレートを一覧表示し、`scan NAME --save --json` は保存内容を
  返します。
- `docs/JSON.md`: 出力契約と、全コマンドの JSON 構造・単位のリファレンス。
- `FINRESEARCH_DEBUG=1` を設定すると、1 行のエラーではなく完全なトレースバックを表示します。

### 変更
- 全コマンド共通の出力契約: 成功時は終了コード `0`(結果が空でも有効な JSON であり、
  エラーではない)、エラー時は `1` と stderr への 1 行の `finresearch: error: …`、
  使い方の誤りは `2`(サブコマンドなしでコマンド群を実行した場合を含む。従来は `1`)。
  想定外の例外も同じ 1 行になり、認証情報はマスクされます。
- 従来 stdout に出力して終了コード 0 で終わっていたエラーが、stderr と終了コード 1 に
  なりました: 不明なティッカー(`ticker`、`sec`、`insider detail`、`news`、
  `13f holder`)、不明なスキャンテンプレートとセクター、スキャンの失敗、SEC FTD
  アーカイブへの接続不可、13F 保有明細のない提出者。
- 不明なティッカーの扱い: `ticker` は N/A だらけの表を出す代わりにエラーにします。
  `compare`/`screen` はティッカーごとの `error` 項目として報告し、`insider scan`、
  `activist`、`dilution`、`buyback`、`8k` は stderr に `[skip]` を出して読み飛ばします。
  いずれも、データを得られたティッカーが 1 つもない場合にのみ失敗します。
- `fred series --json` の観測値が数値になりました(従来は文字列)。
- `13f holder --json` に `holder` と `cik` を追加。`screen --json` の `query.filters` に
  内部フィールドが混入しなくなりました。

### 修正
- `13f holder --json` が進捗行「Fetching…」を stdout に出力して JSON の解析を壊していた
  問題。現在は stderr に出力します。
- `gappers --json` がデータソースの失敗通知を stdout に出す場合があった問題。現在は
  stderr に出力します。
- `news` が不明なティッカーを受け入れていた問題(Google Finance は不明な銘柄にも汎用の
  200 ページを返すため)と、ページ構造の変更で社名・株価の取得が壊れていた問題。
  ページタイトルで銘柄を検証し、社名はタイトルから、株価はその銘柄自身の「Current」欄
  から取得します(ETF のページでは `null`)。

### ドキュメント
- README に「エージェントと自動化のための設計」を追加: 機械向けの契約、ツール呼び出し
  と cron のレシピ、jq パイプライン、無人実行時のレート配慮。
- `.env` ファイルから読み込める設定を訂正(`FRED_API_KEY` のみ。`FINRA_API_KEY` と
  `FINRESEARCH_SEC_UA` は環境変数からのみ)。

## [1.0.0] — 2026-10-02

最初の公開リリース。無料・ポータブルで特定の証券会社に依存しない金融リサーチ CLI。
数か月にわたる日常利用で鍛えられてきました。

### 機能
- **マーケットデータ**(`ticker`、`compare`、`technicals`、`screen`): ファンダメンタルズ、
  アナリスト予想、保有者、RSI/MACD/ボリンジャーバンド/移動平均。通貨を正しく扱います:
  株価は上場通貨、財務数値は報告通貨で表示します(日本株は ¥ 表示、TSM のような
  ADR は株価が USD、財務が TWD)。
- **全市場スキャン**(`scan`): Yahoo のスクリーナーエンジンによるサーバー側での全市場
  フィルタリング。24 のフィルター項目(株価・時価総額の範囲、出来高、利益率、成長率、
  ROE、空売り比率、機関投資家・インサイダー保有比率、配当、負債、Altman Z、ベータ、
  PBR、52 週騰落率)、59 リージョン(`jp` にネイティブ対応)。名前付きスキャン
  テンプレート(`scan myscan`)を `~/.config/finresearch/scans.toml` に保存できます。
  52 週高値・安値からの距離によるポストフィルター(`--within-high/--below-high/--off-low`)。
- **SEC EDGAR 一式**(`insider`、`13f`、`13f diff`、`activist`、`dilution`、`buyback`、
  `8k`、`ftd`、`sec`): Form 4 のインサイダー取引スキャン、13F の機関投資家保有と
  四半期ごとの増減、アクティビストの 13D/G 保有、S-3/424B の希薄化イベント、XBRL
  ベースの自社株買い実績、8-K のイベント一覧、公式の未決済(Fails-to-Deliver)集計。
- **デリバティブとポジション**(`options`、`short`): オプションの異常な取引
  (出来高/建玉、プット・コール比率、IV スキュー)、FINRA の空売り残高
  (カバー日数順)。
- **マクロ**(`fred`、`fomc`): FRED ダッシュボードとイールドカーブ、FOMC 声明・議事要旨、
  タカ派/ハト派センチメントの差分、会合カレンダー、Polymarket による市場の利下げ・
  利上げ確率。
- **ニュースとプレマーケット**(`news`、`gappers`): Google Finance のヘッドライン、
  TradingView/StockAnalysis のデータによるプレマーケットのギャップ銘柄スキャナー。
- **エージェント・ファースト**(`AGENTS.md` と `scripts/install-agent-files.sh`):
  Codex/Grok/pi/Hermes がそのまま読めるプロジェクトガイド、Claude Code 向けの
  CLAUDE.md シンボリックリンク。リポジトリ外のトークン設定を使うリリース前チェック
  `scripts/privacy-sweep.sh`。
- **すぐに使える戦略**(`examples/`): 有名な公開手法をもとにした 7 つのスキャン
  テンプレート(モメンタムブレイクアウト、トレンドテンプレート、CAN SLIM の近似、
  クオリティ銘柄の押し目、当日の値上がり銘柄、出来高、日本株クオリティ)。それぞれに
  サーバー側スクリーナーでは表現できない条件を注記しています。

### 設計方針
- 無料かつ公式のデータソースのみ。任意のキー(`FRED_API_KEY`、`FINRA_API_KEY`)が
  基本機能に必須になることはありません。
- ユーザー固有の状態はすべてリポジトリ外の `~/.config/finresearch/` に置きます
  (ダウンロードした参照データと保存されたスキャン結果は `~/.cache/finresearch/`)。
- 行儀のよい設計: SEC へのリクエストはすべて 1 つのペース制御付きフェッチャーを経由し、
  FRED は表示する観測値だけを取得し、8-K の項目コードは個々の書類ではなく提出一覧
  フィードから取得します。
- オフラインで動く 117 件のテスト、ruff のポリシー、gitleaks によるシークレット検査、
  Python 3.10/3.12 での CI(プッシュ/PR ごとにテスト + ruff + gitleaks)。
