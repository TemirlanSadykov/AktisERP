from django.http import HttpResponse
from django.views import View
from reportlab.pdfgen import canvas # type: ignore
import tempfile
import os
import zipfile
from django.shortcuts import get_object_or_404
from ..models import *
from reportlab.pdfbase import pdfmetrics # type: ignore
from reportlab.pdfbase.ttfonts import TTFont # type: ignore
from urllib.parse import quote
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import qrcode # type: ignore

pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    
@method_decorator([login_required], name='dispatch')
class QRPassportSize(View):
    def get(self, request, passport_id):
        # Get the passport object
        passport = get_object_or_404(Passport, pk=passport_id)

        # Create an in-memory ZIP archive
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            # Iterate over all passport sizes for the given passport
            for passport_size in passport.passport_sizes.all():
                # Create a BytesIO buffer to hold the PDF for this passport size
                pdf_buffer = BytesIO()

                # Set custom PDF page size in points (1 inch = 72 points)
                width, height = 252, 504  # ~3.5 inches x 8.167 inches
                p = canvas.Canvas(pdf_buffer, pagesize=(width, height))
                # Convert top margin from mm to points
                top_margin = 40 * 2.83464567
                text_start_height = height - top_margin

                # Get data from passport_size
                date = passport.cut.date
                model = passport.cut.order.model.name
                color = passport_size.size_quantity.color if passport_size.size_quantity.color else "-"
                fabrics = passport_size.size_quantity.fabrics if passport_size.size_quantity.fabrics else "-"
                size_text = (f"{passport_size.size_quantity.size} - {passport_size.extra}"
                             if passport_size.extra else passport_size.size_quantity.size)
                total_quantity = passport_size.quantity

                # Generate QR code image from the SKU
                qr_data = passport_size.sku
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill='black', back_color='white')
                # Save the QR code image to a temporary file so ReportLab can load it
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                img.save(temp_file)
                temp_file.close()

                # For each unit (if quantity > 1, create multiple pages)
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

                    # If not the last page for this passport size, start a new page.
                    if piece_number < total_quantity:
                        p.showPage()

                # Clean up the temporary QR code image file
                os.remove(temp_file.name)
                p.save()

                # Prepare the PDF file to be added to the zip
                pdf_buffer.seek(0)
                pdf_filename = f"крой-{passport.cut.number}__паспорт-{passport.number}__размер-{passport_size.size_quantity.size}__qr.pdf"
                zip_file.writestr(pdf_filename, pdf_buffer.read())
                pdf_buffer.close()

        # Finalize the zip file and return it as an HTTP response
        zip_buffer.seek(0)
        filename = f"крой-{passport.cut.number}__паспорт-{passport.number}__qr.zip"
        # Encode the filename per RFC 5987 to handle non-ASCII characters
        encoded_filename = quote(filename)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        return response