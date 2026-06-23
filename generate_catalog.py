import sqlite3
import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from PIL import Image as PILImage
import time

def create_catalog_pdf():
    """Создаёт красивый PDF-каталог"""
    
    # Проверяем, есть ли товары
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, category, name, description, price, photo_path FROM products")
    products = cur.fetchall()
    conn.close()
    
    if not products:
        print("❌ Нет товаров в базе!")
        return None
    
    # Создаём PDF
    timestamp = int(time.time())
    pdf_path = f"catalog_{timestamp}.pdf"
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    # Создаём стили
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a237e'),
        alignment=1,  # Center
        spaceAfter=30
    )
    
    category_style = ParagraphStyle(
        'CategoryStyle',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor('#0d47a1'),
        spaceBefore=20,
        spaceAfter=10
    )
    
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.HexColor('#212121'),
        spaceAfter=5
    )
    
    desc_style = ParagraphStyle(
        'DescStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#424242'),
        spaceAfter=5
    )
    
    price_style = ParagraphStyle(
        'PriceStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#e53935'),
        fontName='Helvetica-Bold',
        spaceAfter=20
    )
    
    # Собираем элементы PDF
    elements = []
    
    # Заголовок
    elements.append(Paragraph("🇨🇳 ИМПОРТНЫЙ АГРЕГАТОР", title_style))
    elements.append(Paragraph("Китайские двери, покрытия и мебель", styles['Normal']))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Актуальные цены и наличие уточняйте у менеджера", styles['Italic']))
    elements.append(Spacer(1, 30))
    
    current_category = None
    
    for prod_id, category, name, desc, price, photo_path in products:
        # Добавляем заголовок категории
        if category != current_category:
            current_category = category
            elements.append(Paragraph(f"📂 {category}", category_style))
            elements.append(Spacer(1, 10))
        
        # Добавляем фото
        if photo_path and os.path.exists(photo_path):
            try:
                # Изменяем размер фото
                img = PILImage.open(photo_path)
                img_width, img_height = img.size
                
                target_width = 400
                ratio = target_width / img_width
                target_height = img_height * ratio
                
                temp_img_path = f"temp_{prod_id}_{timestamp}.jpg"
                img = img.resize((int(target_width), int(target_height)), PILImage.Resampling.LANCZOS)
                img.save(temp_img_path, 'JPEG', quality=85)
                
                elements.append(Image(temp_img_path, width=4*inch, height=(target_height/target_width)*4*inch))
                
                # Удаляем временный файл
                os.remove(temp_img_path)
                
            except Exception as e:
                print(f"⚠️ Ошибка фото для {name}: {e}")
                elements.append(Paragraph("🖼 [Фото отсутствует]", styles['Normal']))
        
        # Информация о товаре
        elements.append(Paragraph(f"<b>{name}</b>", name_style))
        elements.append(Paragraph(desc, desc_style))
        elements.append(Paragraph(f"💰 {price}", price_style))
        elements.append(Paragraph(f"Артикул: #{prod_id}", styles['Normal']))
        elements.append(Spacer(1, 10))
        elements.append(PageBreak())
    
    # Строим PDF
    doc.build(elements)
    
    print(f"✅ PDF создан: {pdf_path}")
    return pdf_path

if __name__ == "__main__":
    create_catalog_pdf()
