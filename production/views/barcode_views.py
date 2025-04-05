from django.http import HttpResponse
from django.views import View
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import barcode
from barcode.writer import ImageWriter
import tempfile
import os
from django.shortcuts import get_object_or_404
from ..models import *
from barcode import Code128
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import qrcode

pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    
@method_decorator([login_required], name='dispatch')
class BarcodePassportSizePerPiece(View):
    def get(self, request, passport_size_id):
        passport_size = get_object_or_404(PassportSize, pk=passport_size_id)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="passport_{passport_size.passport.id}-'
            f'size_{passport_size.id}_qrcode.pdf"'
        )

        # Custom page size in points (1 inch = 72 points)
        width, height = 252, 504  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))
        top_margin = 40 * 2.83464567  # Convert mm to points (1 mm = 2.83464567 points)
        text_start_height = height - top_margin

        # Get common data from passport_size
        date = passport_size.passport.cut.date
        model = passport_size.passport.cut.order.model.name
        color = passport_size.size_quantity.color if passport_size.size_quantity.color else "-"
        passport = passport_size.passport
        fabrics = passport_size.size_quantity.fabrics if passport_size.size_quantity.fabrics else "-"
        size_text = (f"{passport_size.size_quantity.size} - {passport_size.extra}"
                     if passport_size.extra else passport_size.size_quantity.size)
        total_quantity = passport_size.quantity

        # Generate QR code using the SKU of the PassportSize
        qr_data = passport_size.sku  # Use SKU as the QR code data
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        # Save the QR code image to a temporary file (only once)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img.save(temp_file)
        temp_file.close()

        # Loop over the PassportSize quantity to create one page per unit.
        for piece_number in range(1, total_quantity + 1):
            p.setFont("DejaVuSans", 14)
            p.drawString(10, text_start_height, f"Дата: {date}")
            p.drawString(10, text_start_height - 25, f"Крой-Паспорт: {passport}")
            p.drawString(10, text_start_height - 50, f"Модель: {model}")
            p.drawString(10, text_start_height - 75, f"Цвет: {color}")
            p.drawString(10, text_start_height - 100, f"Ткань: {fabrics}")
            p.drawString(10, text_start_height - 125, f"Размер: {size_text}")
            p.drawString(10, text_start_height - 150, f"Единица: {piece_number}/{total_quantity}")

            qr_code_y_position = text_start_height - 375
            qr_code_size = 220
            p.drawImage(
                temp_file.name,
                (width - qr_code_size) / 2,
                qr_code_y_position,
                width=qr_code_size,
                height=qr_code_size,
                mask='auto'
            )
            p.setFont("DejaVuSans", 12)
            p.drawString(10, qr_code_y_position - 10, f"QR Data: {qr_data}")

            # If not the last page, start a new page.
            if piece_number < total_quantity:
                p.showPage()

        # Clean up the temporary file after processing all pages.
        os.remove(temp_file.name)
        p.save()
        return response