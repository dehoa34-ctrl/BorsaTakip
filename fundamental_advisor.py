"""
fundamental_advisor.py — Temel Analiz için Yapay Zeka Değerlendirme ve Öneri Modülü.
Hisselerin finansal rasyolarını süzerek Türkçe analiz raporları, skorlar ve kararlar üretir.
"""

import logging

logger = logging.getLogger(__name__)

def generate_fundamental_report(symbol: str, metrics: dict) -> dict:
    """
    Şirketin rasyolarına göre 100 üzerinden temel kalite skoru, 
    nihai yatırım kararı ve Türkçe YZ analiz raporu üretir.
    """
    roic = metrics.get("roic") or 0.0
    roe = metrics.get("roe") or 0.0
    pe = metrics.get("pe")
    pb = metrics.get("pb") or 1.0
    net_debt_ebitda = metrics.get("net_debt_ebitda") or 0.0
    current_ratio = metrics.get("current_ratio") or 1.2
    rev_growth = metrics.get("rev_growth") or 0.0
    earn_growth = metrics.get("earn_growth") or 0.0
    
    # 1. Temel Kalite Skoru Hesaplama (0 - 100)
    score = 50 # Nötr başlangıç skoru
    
    # Kârlılık (ROIC & ROE etkisi)
    if roic > 20: score += 15
    elif roic > 10: score += 8
    elif roic < 5: score -= 10
    
    if roe > 25: score += 15
    elif roe > 15: score += 8
    elif roe < 8: score -= 10
    
    # Borçluluk (Net Borç / FAVÖK & Cari Oran)
    if net_debt_ebitda < 1.5: score += 10
    elif net_debt_ebitda > 3.5: score -= 15
    
    if current_ratio > 1.5: score += 5
    elif current_ratio < 0.9: score -= 8
    
    # Büyüme
    if rev_growth > 40: score += 10
    if earn_growth > 50: score += 10
    elif earn_growth < 0: score -= 8
    
    # Değerleme (F/K ve PD/DD ucuzluğu)
    if pe is not None:
        if pe < 8: score += 10
        elif pe > 25: score -= 12
    else:
        # F/K olmaması büyüme hisselerinde normaldir ama skor nötr kalır
        pass
        
    if pb < 1.5: score += 8
    elif pb > 6.0: score -= 10
    
    # Skoru 15 ile 95 arasında sınırla (Uç değerler gerçekçi dursun)
    score = max(15, min(95, score))
    
    # 2. Nihai Karar ve Renk Belirleme
    if score >= 75:
        recommendation = "Güçlü Al"
        color = "#16a34a" # Koyu Yeşil
    elif score >= 58:
        recommendation = "Al"
        color = "#22c55e" # Yeşil
    elif score >= 40:
        recommendation = "Nötr"
        color = "#94a3b8" # Gri/Mavi
    else:
        recommendation = "Sat"
        color = "#ef4444" # Kırmızı
        
    # 3. Dinamik Türkçe Analiz Raporu Oluşturma
    report_sentences = []
    
    # Giriş ve Karlılık Yorumu
    if roic > 18 or roe > 22:
        report_sentences.append(
            f"{symbol} hissesinin kârlılık rasyoları oldukça güçlüdür. ROIC oranı %{roic:.2f} ve Özsermaye Kârlılığı (ROE) %{roe:.2f} ile şirketin yatırılan sermayeyi son derece yüksek verimlilikle kâra dönüştürdüğünü kanıtlamaktadır."
        )
    elif roic > 8 or roe > 12:
        report_sentences.append(
            f"{symbol} istikrarlı ve dengeli bir kârlılık yapısına sahiptir. ROIC %{roic:.2f} ve ROE %{roe:.2f} ile sektör ortalamasına yakın bir verimlilik sergilemektedir."
        )
    else:
        report_sentences.append(
            f"{symbol} hissesinin kârlılık göstergeleri zayıf seyretmektedir. ROIC oranı %{roic:.2f} ve ROE %{roe:.2f} değerleri, yatırılan sermayenin yeterince etkin kullanılamadığını işaret etmektedir."
        )
        
    # Borçluluk ve Finansal Sağlık Yorumu
    if net_debt_ebitda <= 1.5:
        report_sentences.append(
            f"Net Borç / FAVÖK oranı {net_debt_ebitda:.2f} seviyesinde olup, şirketin borç yükünü taşımakta hiçbir zorluk çekmediğini ve finansal riskinin oldukça düşük olduğunu göstermektedir."
        )
    elif net_debt_ebitda > 3.0:
        report_sentences.append(
            f"Net Borç / FAVÖK oranının {net_debt_ebitda:.2f} ile kritik eşik olan 3,0'ün üzerinde olması, şirketin faiz ve borç maliyetleri karşısında hassasiyet taşıdığını ve finansal borç yükünün yüksek olduğunu göstermektedir."
        )
    else:
        report_sentences.append(
            f"Net Borç / FAVÖK oranı {net_debt_ebitda:.2f} ile makul ve yönetilebilir seviyededir. Likidite dengesi stabil olup kısa vadeli borç ödeme kapasitesi yeterlidir."
        )
        
    # Büyüme ve Değerleme Yorumu
    pe_str = f"{pe:.2f}" if pe is not None else "N/A"
    if pe is not None and pe < 10:
        report_sentences.append(
            f"F/K oranının {pe_str} ve PD/DD oranının {pb:.2f} olması, hissenin mevcut kârı ve defter değerine kıyasla oldukça **ucuz ve iskontolu** fiyatlandığını teyit etmektedir."
        )
    elif pe is not None and pe > 25:
        report_sentences.append(
            f"F/K oranının {pe_str} ve PD/DD oranının {pb:.2f} olması, piyasanın şirketten çok yüksek büyüme beklediğini veya hisse fiyatının kısa vadeli kârlılığa göre bir miktar **pahalı** kaldığını göstermektedir."
        )
    else:
        report_sentences.append(
            f"F/K oranı {pe_str} ve PD/DD oranı {pb:.2f} ile tarihsel BIST ortalamalarına paralel, dengeli bir değerleme düzeyindedir."
        )
        
    # Gelecek Görünüm / Büyüme Cümlesi
    if rev_growth > 30:
        report_sentences.append(
            f"Şirketin çeyreklik gelirlerinde %{rev_growth:.2f} düzeyinde gerçekleşen büyüme ivmesi, pazar payını artırma ve ciro genişletme yönünde güçlü bir potansiyel barındırmaktadır."
        )
    elif rev_growth < 5:
        report_sentences.append(
            f"Yıllık büyüme hızının %{rev_growth:.2f} gibi sınırlı kalması, ciroda durağanlık olduğunu ve şirketin büyüme katalizörlerine ihtiyaç duyduğunu göstermektedir."
        )
        
    # Sonuç / Öneri Özeti
    if score >= 70:
        report_sentences.append(
            f"Temel analiz kriterlerine ve rasyo sentezine göre {symbol}, uzun vadeli portföyler için **{recommendation.upper()}** statüsünde güçlü bir değer yatırımı alternatifi sunmaktadır."
        )
    elif score >= 50:
        report_sentences.append(
            f"Şirketin finansal yapısı sağlam temellere oturmakla birlikte, hissede yeni bir pozisyon açmak için teknik analiz onayının beklenmesi veya seçici olunması önerilir."
        )
    else:
        report_sentences.append(
            f"Yüksek borçluluk ve zayıf kârlılık rasyoları nedeniyle {symbol} şu an için **yüksek risk** barındırmaktadır ve temkinli yaklaşılması tavsiye edilir."
        )
        
    ai_report = " ".join(report_sentences)
    
    return {
        "roic": roic,
        "pe": pe,
        "pb": pb,
        "net_debt_ebitda": net_debt_ebitda,
        "score": score,
        "recommendation": recommendation,
        "color": color,
        "report": ai_report
    }
