# Personal Media Sync

これは個人のメディアファイルを各種クラウドストレージ（Google 写真、Quark クラウド、115 クラウドなど）に自動的にスケジュールでバックアップするための個人的なユーティリティスクリプト集です。

## 機能

- スケジュールによる自動メディア同期
- 各種クラウドストレージサービスとの連携
- GitHub Actions を用いた定期的なバックアップワークフロー

## 設定 (GitHub Secrets)

GitHub リポジトリの **Settings -> Secrets and variables -> Actions** にて、以下の環境変数を設定してください：

| 変数名 | 必須 | 説明 |
| :--- | :--- | :--- |
| `TWITTER_USERS_ARCHIVE` | ✅ | アーカイブ対象のリスト（カンマ区切り） |
| `TWITTER_COOKIES` | ❌ | データ取得用の認証 Cookie（JSON形式） |
| `COOKIES_115` | ⚠️ | 115 クラウドドライブへのバックアップ用 Cookie |
| `COOKIES_QUARK` | ⚠️ | Quark クラウドへのバックアップ用 Cookie |
| `GOOGLE_PHOTOS_TOKEN` | ⚠️ | Google 写真バックアップ用の API トークン |

## Google 写真 API トークンの取得方法

1. [Google Cloud Console](https://console.cloud.google.com/) で **Photos Library API** を有効にします。
2. 「デスクトップアプリ」用の OAuth クライアント ID を作成し、`credentials.json` をダウンロードして `tools/` ディレクトリに配置します。
3. ローカルで以下のスクリプトを実行し、ブラウザで認証を完了させます：
   ```bash
   python tools/get_google_photos_token.py
   ```
4. コンソールに出力された Base64 文字列をコピーし、GitHub Secret の `GOOGLE_PHOTOS_TOKEN` に保存します。

## 免責事項

このプロジェクトは個人的なデータバックアップの目的でのみ作成されました。外部への公開サービスとしては意図されていません。
