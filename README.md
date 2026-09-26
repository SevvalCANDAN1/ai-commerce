# AI-Commerce

Akıllı e-ticaret API’si. Müşteri tarafında cümleyle semantik ürün arama, satıcı tarafında geçmiş satıştan talep tahmini.

**Bitirme sunumu:** [https://youtu.be/8fKWc7tU6m4](https://youtu.be/8fKWc7tU6m4)

Güncel kod dalı: `cursor/module-2-smart-search`

## Ne çalışıyor

- Üyelik, sepet, checkout, mock ödeme, sipariş
- Semantik arama: Azure OpenAI `text-embedding-3-small` (768 boyut) + MongoDB vektör arama (Atlas `$vectorSearch`; lokal Docker’da cosine)
- Arama niyeti: Gemini
- Talep tahmini: Olist verisinden önceden eğitilmiş model (`ml/models/demand_forecast.json`)
- Geç teslim riski: satın alma anı heuristic (eğitimli sklearn modeli API’de yok)

## Çalıştırma

`.env.example` dosyasını `.env` olarak kopyala; Mongo, JWT, Azure OpenAI ve Gemini değerlerini doldur. `.env` commit etme.

```powershell
docker compose up -d --build
