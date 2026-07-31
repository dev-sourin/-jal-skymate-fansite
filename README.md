# Skymate Finder MVP

登録・ログインなしで路線、時刻表、スカイメイト運賃候補を検索する、非公式・非営利ファンサイトの動作するMVPです。

> **重要:** 同梱データはUI・検索ロジック確認用の架空サンプルです。実際の便名、時刻、運賃、空席情報として使用しないでください。本番化に際して、公開・利用可能なデータを運営者が確認して投入してください。

## 実装済み

- 出発空港・任意の到着空港・搭乗日による匿名検索
- 行き先未指定の逆引き検索
- 時間帯・予算・空席種別フィルター
- 時刻表、所要時間、運賃2商品の並列表示
- 施設使用料込みの合計目安
- 空席情報の優先順位とTTL管理
  - `EXACT_SKYMATE`
  - `GENERAL_CURRENT`
  - `GENERAL_D1`
  - `PREDICTED`
  - `UNKNOWN`
- 説明可能なルールベース利用見込み
- 全画面の非公式表示とJAL公式確認導線
- CSVからのSQLite再構築
- 時刻表・便詳細・空席詳細API
- OpenAPI（FastAPI標準）
- レスポンシブUI

## 起動方法

Python 3.11以上を推奨します。

```bash
cd skymate_fansite_mvp
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python run.py
```

ブラウザで `http://127.0.0.1:8000` を開きます。
API仕様は `http://127.0.0.1:8000/docs` です。

## Docker

```bash
docker build -t skymate-finder .
docker run --rm -p 8000:8000 -e SKYMATE_ADMIN_TOKEN=change-this skymate-finder
```

## データ更新

`data/` 配下のCSVを編集してから次を実行します。

```bash
python scripts/import_csv.py
```

動的なデモ空席日は `TODAY` / `TOMORROW` / `YESTERDAY` と、`TODAY@01:00` の形式を利用できます。本番CSVではISO 8601の実日付・日時を使用してください。

## API例

```bash
curl "http://127.0.0.1:8000/api/v1/destinations?origin=HND&date=2026-08-01&sort=price"
```

デモデータ再読込（管理用）:

```bash
curl -X POST \
  -H "X-Admin-Token: change-me-before-production" \
  http://127.0.0.1:8000/api/v1/admin/reload-demo
```

本番では必ず `SKYMATE_ADMIN_TOKEN` を環境変数で変更してください。

## 空席データの扱い

- `EXACT_SKYMATE`: 対象運賃の販売可否を直接返す、許可済みの正式ソースだけに使用します。
- `GENERAL_CURRENT`: 当日の一般席参考。スカイメイト販売可とは表示しません。
- `GENERAL_D1`: 前日の一般席参考。翌日の販売を保証しません。
- `PREDICTED`: 便数、曜日、時間帯、路線係数から算出する独自予測です。
- `UNKNOWN`: データなし、または期限切れです。

取得期限を過ぎた観測は自動的に選択対象から外れ、予測または未確認へ降格します。

## 本番化に必要な作業

- 独自に確認・作成した全路線、時刻表、運賃データの投入
- 運賃・時刻表の有効期間、改定履歴、出典管理
- 正式に利用可能な空席データソースの契約・実装
- PostgreSQL、キャッシュ、監視、バックアップへの移行
- 管理画面のOIDC/MFA認証
- アクセシビリティ、負荷、セキュリティの本番試験

公開Webページの高頻度スクレイピング、CAPTCHA回避、非公開API解析、予約操作の自動化は実装対象外です。
