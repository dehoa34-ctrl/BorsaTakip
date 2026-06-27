# BorsaTakip AI - Gelişmiş Hisse & Kripto Analiz

Bu proje, Python (FastAPI) ve modern Web teknolojileri kullanılarak geliştirilmiş, hisse senedi ve kripto paralar için teknik analiz yaparak **AL/SAT/TUT** sinyalleri üreten dinamik bir takip platformudur.

## 🚀 Özellikler
- **Gerçek Zamanlı Veri**: `yfinance` üzerinden tüm dünya borsaları ve kripto paralar için anlık veri takibi.
- **Teknik Analiz (AI)**: RSI (Göreceli Güç Endeksi) ve Hareketli Ortalamalar (SMA 20/50) kullanılarak otomatik sinyal üretimi.
- **Profesyonel Grafikler**: TradingView tarafından geliştirilen `Lightweight Charts` ile profesyonel OHLC grafikleri.
- **Modern Arayüz**: Glassmorphism (cam tasarımı) ve karanlık mod ile şık bir kullanıcı deneyimi.
- **Otomatik Değil**: Sinyaller sadece bilgilendirme amaçlıdır, otomatik işlem yapmaz.

## 🛠️ Kurulum ve Çalıştırma
1. **Bağımlılıkları Yükleyin**:
   ```bash
   pip install fastapi uvicorn yfinance pandas requests
   ```
2. **Uygulamayı Başlatın**:
   ```bash
   python main.py
   ```
3. **Erişim**:
   Web tarayıcınızdan `http://localhost:8000` adresine gidin.

## 🔍 Kullanım İpuçları
- **Hisse Aramak İçin**: Sembolün sonuna borsa kodunu ekleyin (Örn: `THYAO.IS` - Borsa İstanbul, `AAPL` - Nasdaq).
- **Kripto Aramak İçin**: `BTC-USD`, `ETH-TRY` gibi formatları kullanın.
- **Sinyaller**: 
  - **GÜÇLÜ AL**: RSI < 30 (Aşırı satım).
  - **GÜÇLÜ SAT**: RSI > 70 (Aşırı alım).
  - **AL**: Fiyat SMA50 üzerine çıktığında.
  - **SAT**: Fiyat SMA50 altına indiğinde.

*UYARI: Bu uygulama bir yatırım danışmanlığı aracı değildir. Verilen sinyaller matematiksel indikator sonuçlarıdır.*
