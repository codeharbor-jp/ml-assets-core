## ml-assets-core Analytics Dashboard

Next.js を用いた KPI ダッシュボードのサンプルです。`/api/v1/metrics/*` エンドポイントを 10〜60 秒間隔でポーリングし、Sharpe / MaxDD / Data Quality 等の指標を表示します。

### 開発手順

```bash
cd dashboards/analytics
npm install
npm run dev
```

環境変数:

- `NEXT_PUBLIC_CORE_API_URL` : ml-assets-core API を指すベース URL（例: `http://localhost:8000/api/v1`）

### ページ構成

- `app/page.tsx` : KPI カードとチャート（ダミーデータ）を描画
- `lib/api.ts` : Analytics API からデータを取得し TTL キャッシュする fetch ラッパ
- `components/KpiCard.tsx` : メトリクス数値表示用のプレーンなカード

実際の本番では Chakra UI / Tremor 等の UI ライブラリを適用し、Auth0 / Cognito 等で認証を追加してください。

