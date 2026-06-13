# 🎛️ Athena — セルフホスト型マルチエージェント・フレームワーク

![Version](https://img.shields.io/badge/version-0.11.40-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)

**言語：** [Français](README.md) · [English](README.en.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Deutsch](README.de.md) · [中文](README.zh.md) · 日本語（このファイル）

軽量サーバーや控えめな GPU でも動作するよう設計された「低リソース」で高度にモジュール化された AI オーケストレーター。**Web UI**、**CLI**、**Telegram**、**ローカル音声**でアクセスできます。

📖 **[完全なユーザーガイドを読む](docs/USER_GUIDE.md)** — Athena のインストール・設定・利用を順を追って学べます。

## ✨ 主な機能

### 🔐 プロ仕様マルチテナント & コラボレーション
* **セキュリティ & SSO**：企業向けの OIDC / OAuth2 認証。管理者が管理する招待制登録。
* **保存時暗号化**：データベース（SQLite）に保存される会話と実行トレースは Fernet（AES-128-CBC + HMAC-SHA256）で保存時暗号化。鍵はあなたの管理下（`.env` または外部シークレットマネージャー）。
* **コスト管理（クォータ）**：ユーザーごとの 1 日あたりトークンクォータで API 支出を自動制限。
* **高度なセキュリティ**：Web 閲覧向けの SSRF（DNS リバインディング）対策を内蔵し、ログ内の秘密情報を自動マスキング。
* **完全な分離**：各ユーザーが独自のメモリ（RAG、Core Memory）、カレンダー、リスト、API 予算を持ちます。
* **セルフサービス LLM**：各ユーザーが自分の API キーでグローバルモデルを上書き可能（OpenAI、Anthropic、Gemini、Groq など）。
* **共有プロジェクト**：きめ細かなロール（閲覧者 / 編集者）と衝突防止ファイルロックを備えた共同ワークスペース。

### 🧠 オーケストレーション & LLM エンジン
* **マルチモデル**：OpenAI、Anthropic、Gemini、Ollama、Groq、Mistral、Qwen、互換のローカル API。
* **Swarm（群れ）**：専門エージェント間の自動ルーティング（ハンドオフ）、並行実行、エージェント間ディベート。
* **固定パイプライン（任意）**：エージェントが逸脱せず順番に処理する厳格な組み立てラインを強制可能。
* **モジュラー構成**：機能別ルーターに分割された FastAPI バックエンドと、堅牢でスレッドセーフな **SQLite** データベース。
* **タスク分離**：実行ごとに分離された状態（ContextVars）。並列リクエストは互いに干渉しません。

### 🌐 高度な Web UI
* **バーチャルオフィス（3D アイソメトリック）**：群れの可視化、アクティブなエージェントのハイライト、委任アニメーション。
* **コックピット & テレメトリ**：消費（トークン、ユーザーごとのコスト）、実行、エラーをリアルタイム追跡。
* **可観測性**：完全な履歴と、ツール呼び出しとシステムを監査するためのリアルタイムログパネル。
* **内蔵ミニ IDE**：**編集可能**なファイルエクスプローラー — 複数タブ編集（CodeMirror）、ハイライト、自動補完、Ctrl+S 保存（閲覧者は読み取り専用）、サイズ変更可能なパネル、エージェントが開いているファイルを変更した際の**ライブリロード**。
* **統合ツール**：カレンダー、リスト、ターミナル、生成メディアのギャラリー。
* **ノーコード設定**：分かりやすい UI で挙動（ルーティン、メモリ、ロール）を完全管理。

### 🧰 ツールと拡張性（Skills）
* **MCP サーバー（Model Context Protocol）**：コーディング不要で外部サーバーを接続。Home Assistant MCP コネクタは安全性のためローカルに同梱。
* **Computer Use（RPA 2.0）**：LLM 向けに最適化された対話型ヘッドレスブラウザを操作。
* **Git & コードナビゲーション**：リポジトリ（ログ、ブランチ、編集）を理解し、Docker サンドボックスで bash/python を実行。
* **その場での Skill 作成**：AI が*自分のツールをコーディング*して恒久的に保存し、能力を拡張できます！
* **SSH 管理**：SSH コマンドでリモートサーバーを管理。
* **クリエイティブ & Web**：高度な Web 検索、画像/動画生成（Fal、Replicate）、スクレイピング。
* **メディア & 会議**：音声ファイルや会議全体の要約・文字起こし。

### 🎨 AthenaDesign Studio
* **AI デザインスタジオ**：作りたいものを記述すると、Athena が **HTML/CSS/JS** インターフェース、**React/JSX** コンポーネント、**Mermaid** 図を生成して**ライブプレビュー**し、隔離された **Docker サンドボックス**で **Python**（PowerPoint プレゼン、Matplotlib/Plotly グラフ）を実行します。
* **デザインシステム**：ブランド（色・タイポグラフィ）を適用 — 手入力、CSS から抽出、または**サイトの URL からインポート**。
* **インポート & ビジョン**：参照として画像/ドキュメント（PDF）を添付したり Web ページを取り込み。ビジョンの自動ルーティング（マルチモーダルモデルがあれば使用、なければ適切にフォールバック）。
* **反復**：プレビューへの注釈、**WYSIWYG スライダー**（色/角丸/フォント）、バージョン、失敗スクリプトの**自動修正**、**PDF/PPTX/HTML** へのエクスポート、**リンク共有**（読み取り専用・サンドボックス化）。
* **統合プロジェクト**：1 つの Athena プロジェクトが**コード**と**デザイン**の両方を保持。

### 🔌 プラグイン & 自動修正
* **プラグインタブ**：MCP サーバーや skills に加えてファーストクラスの拡張を有効化。
* **Claude Code プラグイン**：重いコーディングを **Claude Code** エージェント（CLI）に委任。アクティブなプロジェクトに限定し、有効化するとコーダーに自動付与。
* **自動修正（自己修復）**：デザイン（Python）も**コーダー**（Code-Test-Fix：`pytest`/`npm test`）も、上限付きループでエラーを自動的に修正します。

### 🏠 ホームオートメーション & 自動化
* **ネイティブなホームオートメーション（Home Assistant）**：状態の読み取りとアクション実行（照明、シャッター、センサー）を即座に。
* **空間認識**：あなたがどの部屋にいるかを把握し、物理環境へのアクションを向けます。
* **能動的ルーティン & ワークフロー**：ユーザーごとに分離された CRON スケジュール、Webhook トリガー、深い **n8n** 連携。
* **カレンダー & リスト**：Google Calendar、iCal、CalDAV と双方向同期。Todo と買い物リストを管理。
* **能動的通知**：Athena から Telegram、Discord、Slack、メール、Webhook へ自律的にアラート。

### 💾 メモリ & 学習
* **RAG ベクトルデータベース**：ChromaDB による文書の自動セマンティックインデックス。
* **ナレッジグラフ & Core Memory**：恒久的な事実の保管と、関係のグラフモデリング。
* **自己改善**：複雑なタスク後に経験フィードバックを永続化し、今後の挙動を洗練。
* **バックアップ & 復元**：状態（会話、RAG、ルーティン、設定）の完全バックアップ/復元。

### 🎙️ 音声アシスタント（STT/TTS）
* **100% ローカルで滑らか**：**Kokoro TTS**（ローカル Docker API）による高速な音声合成と、最適化された **Whisper STT** による文字起こし。
* **ウェイクワード検出**：openWakeWord、「バージイン」（AI の発話を割り込み）対応。
* **ESP32-S3 サテライト**：ESPHome 音声サテライトをフレームワークへ直接接続（S2S）、Home Assistant を経由せず。

## 🚀 クイックインストール（1 行）

> [!NOTE]
> *このリポジトリが非公開の場合、これらのコマンドを動かすにはアクセス権（トークンまたは SSH キー）が必要です。手動でクローンすることもできます。*

**Linux / macOS**：このコマンドをターミナルに貼り付けてください：
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**：PowerShell で次を実行：
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Docker Compose 版**：`docker compose up -d --build`

**起動**：`athena start` または `python3 server.py`。アクセス先 👉 **http://localhost:8000/**。

### ⚙️ マルチワーカー展開（スケーリング）
共有される可変状態（アカウントとクォータ、認証セッション、ルーティン、招待、共有プロジェクト、ユーザーごとの設定）は WAL モードの共通 SQLite DB（`athena_state.sqlite3`）にアトミック更新で保存され、**複数ワーカー間で一貫**します：
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **マルチワーカーでの RAG。** 単一プロセスではベクトルストアは組み込み（ローカル ChromaDB）。マルチワーカーでは **`CHROMA_SERVER_HOST`**（+ `CHROMA_SERVER_PORT`）を設定すると、全ワーカーが同じ ChromaDB サーバーに接続します（同時書き込み安全）。同梱の `docker-compose.yml` には `chroma` サービスが含まれています。他の状態はネイティブにマルチワーカー安全です。

### 🔒 本番環境のセキュリティ
- **TLS 必須**：Athena を HTTPS リバースプロキシ（Caddy、Nginx、Traefik）の背後に配置。HTTPS を検出（`X-Forwarded-Proto: https`）すると **HSTS** を自動送出。
- **暗号鍵を `.env` の外へ**：ディスク/バックアップ盗難に備え、`DB_ENCRYPTION_KEY` は環境変数 / シークレットマネージャー経由で注入。
- **セキュリティヘッダー**（CSP、X-Frame-Options、nosniff、Referrer/Permissions-Policy）は既定で有効 — 無効化は `SECURITY_HEADERS=false`、カスタマイズは `CONTENT_SECURITY_POLICY`。
- **ガードレール**：総当たり対策スロットル（`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`）、レート制限（`RATE_LIMIT_PER_MIN`、既定 300/IP/分）、パスワードポリシー（`MIN_PASSWORD_LENGTH`、既定 8）、**監査ログ**（`GET /api/audit`、管理者）、「user」アカウントが作成した自動化の**管理者承認**。
- **ツール単位の RBAC**：`ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` でコード/コマンド実行を管理者に限定。
- **コンテナ**：イメージは **非 root** ユーザーで `HEALTHCHECK` 付きで動作。インストール監査：`bash scripts/security_scan.sh`。

### 📡 LLM 可観測性（任意 — OpenInference / Phoenix）
内蔵コックピットに加え、Athena は**標準化された LLM トレース**（OpenInference / OpenTelemetry）を **Phoenix**（Arize）へエクスポートできます。有効化：
```bash
pip install -r requirements-observability.txt
docker compose --profile observability up -d         # Phoenix (UI: http://localhost:6006)
```
その後 `.env` に：`OPENINFERENCE_ENABLED=true` と `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`。既定では無効。

---

## 🛡️ 比較：Athena vs 市場

> [!NOTE]
> **方法論。** 比較可能なものを比較します：**Athena**、**Hermes**、**OpenClaw** は*ホスト型アプリ/アシスタント*。**CrewAI** と **AutoGen** は自分のコードに組み込む*オーケストレーション・ライブラリ*（ゆえに「N/A」）。Athena の差別化は「UI があること」ではなく、**マルチテナント + エンタープライズ級セキュリティ + エージェント的コーディング + 可観測性**を 1 つのセルフホスト製品に統合した点です。

| カテゴリ | 基準 | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **UI & UX** | **GUI** | **完全な Web ダッシュボード（3D アイソメトリック、ノードグラフ、統合ターミナル）** | なし | コンパニオンアプリ + Live Canvas | なし（別の CrewAI Studio） | 基本（AutoGen Studio） |
| | **対話チャネル** | Web、ターミナル UI、Telegram、Discord、Slack、音声 | CLI、Telegram、Slack、Discord | **15 以上のチャネル** | Python コード | CLI / コード |
| | **IDE / ローカル開発統合** | Web コードコンソール + サンドボックス | なし | あり（ローカルアシスタント） | 自分のコードに統合 | 自分のコードに統合 |
| **オーケストレーション** | **マルチエージェントモデル** | **自動セマンティックルーティングの Swarm** | 並列の分離サブエージェント | マルチエージェントルーティング | 順次 / 階層 | ディベート / グループチャット |
| | **グループトポロジー** | 有機的なディベートとハンドオフ | 分離ハンドオフ | チャネル/エージェント別ルーティング | 順次/階層プロセス | **高度なグループチャット** |
| | **固定パイプライン** | あり（任意の組み立てライン） | 有機的 | — | **ネイティブ** | 線形または有機的 |
| | **永続化（メモリ）** | **ベクトル DB + セッション横断の暗号化履歴** | あり（SQLite + FTS5） | あり（永続セッション） | あり（短期/長期） | 限定的 |
| | **クローズドループ学習** | **自動生成 skills + 経験 RAG** | あり | 拡張可能ツール | なし | なし |
| | **ツール & MCP** | **ネイティブ + MCP + Home Assistant** | あり（MCP） | あり（ブラウザ、canvas、cron、MCP） | あり（crewai-tools + MCP） | あり（function calling） |
| **全体的セキュリティ** | **認証** | **パスワード、トークン、SSO (OIDC)** | なし（ローカル） | 基本（ローカル） | N/A | N/A |
| | **アクセス制御 (RBAC)** | **あり（閲覧者/編集者ロール）** | なし | なし | N/A | N/A |
| | **ユーザー別クォータ/コスト** | **あり（日次トークンクォータ + 予算アラート）** | なし | なし | N/A | N/A |
| **実行 & ネットワーク** | **実行サンドボックス** | **使い捨て Docker コンテナ（リソース制限）** | 場合による | ホスト | コードインタープリタ経由 | **あり（Docker）** |
| | **SSRF 対策シールド** | **あり（DNS リバインディング、内部ネット/メタデータ遮断）** | なし | なし | N/A | N/A |
| **データ保護** | **秘密情報マスキング（ログ）** | **あり** | なし | 部分的 | N/A | N/A |
| | **保存時暗号化** | **あり（Fernet/AES-128）** | なし | ストレージ依存 | N/A | N/A |
| | **マルチテナント分離** | **あり（ユーザー別にメモリ/予定/予算を分離）** | なし | ワークスペース単位 | N/A | N/A |
| | **人手承認 (HITL)** | **あり（UI で機微な操作を捕捉）** | あり（チャット経由） | 基本 | 自前で実装 | 自前で実装 |

## 📄 ライセンス

**Apache 2.0** ライセンスで配布 — [LICENSE](LICENSE) を参照。自由に利用・改変・再配布できます。
