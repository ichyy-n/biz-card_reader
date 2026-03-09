# biz-card_reader

## 概要

LINEで名刺画像を送信すると、OpenAI API（GPT Vision）でOCR解析し、Google Drive / Google Sheetsに自動保存する名刺管理システム。マルチユーザー対応（承認制）で、ユーザーごとにGoogle Driveフォルダ・スプレッドシートを自動作成し、データを分離管理する。

## 機能

- LINE Bot経由で名刺画像を受信・解析
- OpenAI API（Vision）で名刺情報を構造化抽出（会社名・部署名・氏名・住所・電話番号・メールアドレス）
- Google Driveに画像保存・Google Sheetsに名刺データを自動登録（ユーザーごとにリソース分離）
- マルチユーザー対応（ユーザー承認制 + Google OAuth per-user認証）
- 管理者API（ユーザー承認・取消・一覧）
- 画像サイズ制限（5MB）
- トークンの暗号化保存（Fernet）
- OAuthステートのHMAC署名 + nonce検証によるCSRF対策

## アーキテクチャ

```
LINE App
  │
  │ 名刺画像送信
  ▼
LINE Messaging API
  │
  │ Webhook (POST /callback)
  ▼
FastAPI (Render)
  ├── 署名検証 (X-Line-Signature)
  ├── ユーザー認可チェック (PostgreSQL)
  │     ├── 未登録 → 仮レコード作成 + 管理者通知
  │     ├── 未承認 → 無応答
  │     ├── 未認証 → OAuth URL送信
  │     └── 認証済み → イベント処理
  │
  ├── OpenAI API (GPT Vision)
  │     └── 名刺画像 → JSON構造化データ
  │
  ├── Google Drive API
  │     └── 名刺画像アップロード (per-userフォルダ)
  │
  └── Google Sheets API (gspread)
        └── 名刺データ + Driveリンクを追記 (per-userスプレッドシート)
```

## 技術スタック

- **言語**: Python
- **Webフレームワーク**: FastAPI + Uvicorn
- **ORM**: SQLAlchemy
- **データベース**: PostgreSQL（psycopg2）
- **LINE連携**: LINE Messaging API（line-bot-sdk v3）
- **AI/OCR**: OpenAI API（GPT Vision）
- **Google連携**: Google Drive API, Google Sheets API (gspread), Google Auth OAuthLib
- **暗号化**: cryptography（Fernet）
- **ホスティング**: Render

## セットアップ

### 前提条件

- Python 3.x
- LINE Developersアカウント（Messaging APIチャネル）
- Google Cloud Projectおよびサービスアカウント（OAuth 2.0クライアント）
- OpenAI APIキー
- PostgreSQL データベース

### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `LINE_CHANNEL_SECRET` | LINE Messaging APIのチャネルシークレット | `abc123...` |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging APIのチャネルアクセストークン | `Bearer xxx...` |
| `OPENAI_API_KEY` | OpenAI APIキー | `sk-...` |
| `SQL_URL` | PostgreSQLの接続URL | `postgresql://user:pass@host:5432/dbname` |
| `CLIENT_SECRET_PATH` | Google OAuth クライアントシークレットJSONファイルのパス | `json_files/client_secret.json` |
| `CRYPT_KEY` | Fernet暗号化キー（トークン暗号化用） | `create_cryptkey.py`で生成 |
| `SESSION_SECRET_KEY` | セッションミドルウェアのシークレットキー | 任意のランダム文字列 |
| `ADMIN_API_KEY` | 管理者APIの認証キー | 任意のランダム文字列 |
| `ADMIN_LINE_USER_ID` | 管理者のLINE User ID（新規ユーザー通知先） | `Uxxxxxxxxx...` |
| `RENDER_EXTERNAL_URL` | デプロイ先の外部URL | `https://your-app.onrender.com` |
| `FOLDER_ID` | （移行用・非推奨）既存Google DriveフォルダID | `1abc...` |
| `SHEET_ID` | （移行用・非推奨）既存Google SpreadsheetID | `1xyz...` |
| `ALLOWED_LINE_USERS` | （移行用・非推奨）許可済みLINEユーザーIDのカンマ区切り | `Uaaa,Ubbb` |

### Google Cloud Console 設定

1. Google Cloud Consoleでプロジェクトを作成
2. Google Drive API と Google Sheets API を有効化
3. OAuth 2.0クライアントIDを作成（Webアプリケーション）
4. スコープ: `drive.file`, `spreadsheets`
5. 承認済みリダイレクトURI: `https://{RENDER_EXTERNAL_URL}/oauth2callback`
6. クライアントシークレットJSONをダウンロードし、`CLIENT_SECRET_PATH`で指定したパスに配置

### LINE Developers 設定

1. LINE DevelopersコンソールでMessaging APIチャネルを作成
2. Webhook URL: `https://{RENDER_EXTERNAL_URL}/callback`
3. Webhookの利用をオンに設定
4. チャネルシークレット・チャネルアクセストークンを取得

### ローカル起動

```bash
git clone https://github.com/ichyy-n/biz-card_reader
cd biz-card_reader
pip install -r requirements.txt
# 環境変数を設定（.envファイルを作成）
uvicorn main:app --reload
```

## Renderへのデプロイ

1. GitHubリポジトリをRenderに接続
2. Web Serviceとしてデプロイ（Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`）
3. Environment Variablesに全環境変数を設定
4. PostgreSQL DB URLを `SQL_URL` に設定

## 利用方法

### ユーザー（LINE）

1. LINE BotをフォローしてLINEメッセージを送信
2. 管理者が承認するまで待機（管理者にLINE通知が届く）
3. 承認後、次にメッセージを送るとOAuth認証URLが届く → Google認証を完了
4. 名刺画像を送信 → Google Drive / Google Sheetsに自動保存される

### 管理者（ユーザー承認）

```bash
# ユーザー一覧確認
curl -H "X-Admin-API-Key: {ADMIN_API_KEY}" \
  https://{RENDER_EXTERNAL_URL}/admin/users

# ユーザー承認
curl -X POST -H "X-Admin-API-Key: {ADMIN_API_KEY}" \
  https://{RENDER_EXTERNAL_URL}/admin/users/{line_user_id}/approve

# ユーザー取消
curl -X POST -H "X-Admin-API-Key: {ADMIN_API_KEY}" \
  https://{RENDER_EXTERNAL_URL}/admin/users/{line_user_id}/revoke
```

## ライセンス

MIT
