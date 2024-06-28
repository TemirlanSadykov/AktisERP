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
class BarcodePassport(View):
    def get(self, request, passport_id):
        passport = get_object_or_404(Passport, pk=passport_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport.id}_qrcode.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points
        width, height = 252, 504  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))
        p.setFont("DejaVuSans", 14)

        # Top margin and initial text position
        top_margin = 40 * 2.83464567
        text_start_height = height - top_margin

        # Additional Passport data
        model_name = passport.order.model.name  # Assuming model relation exists
        color = passport.order.color
        fabrcis = passport.order.fabrics
        passport_number = passport.id

        p.drawString(10, text_start_height, f"Модель: {model_name}")
        p.drawString(10, text_start_height - 25, f"Цвет: {color}")
        p.drawString(10, text_start_height - 50, f"Ткань: {fabrcis}")
        p.drawString(10, text_start_height - 75, f"Паспорт: №{passport_number}")

        # Generate and position QR code
        qr_data = f"{passport.id}"
        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        # Save the QR code image to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img.save(temp_file)
        temp_file.close()

        qr_code_y_position = text_start_height - 350

        # Draw the QR code image on the PDF
        qr_code_size = 220
        p.drawImage(temp_file.name, (width - qr_code_size) / 2, qr_code_y_position, width=qr_code_size, height=qr_code_size, mask='auto')

        # Draw the QR data text under the QR code
        p.setFont("DejaVuSans", 12)
        p.drawString(10, qr_code_y_position - 20, f"QR Data: {qr_data}")

        p.showPage()
        p.save()

        # Clean up temporary file
        os.remove(temp_file.name)

        return response
    
@method_decorator([login_required], name='dispatch')
class BarcodePassportSize(View):
    def get(self, request, passport_size_id):
        passport_size = get_object_or_404(PassportSize, pk=passport_size_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_qrcode.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points
        width, height = 252, 504  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))
        p.setFont("DejaVuSans", 14)

        # Top margin and initial text position
        top_margin = 40 * 2.83464567
        text_start_height = height - top_margin

        # Additional Passport Size data
        model_name = passport_size.passport.order.model.name
        color = passport_size.passport.order.color
        fabrics = passport_size.passport.order.fabrics
        passport_number = passport_size.passport.id
        size = passport_size.size_quantity.size

        p.drawString(10, text_start_height, f"Модель: {model_name}")
        p.drawString(10, text_start_height - 25, f"Цвет: {color}")
        p.drawString(10, text_start_height - 50, f"Ткань: {fabrics}")
        p.drawString(10, text_start_height - 75, f"Паспорт: №{passport_number}")
        p.drawString(10, text_start_height - 100, f"Размер: {size}")

        # Generate and position QR code
        qr_data = f"{passport_size.passport.id}-{passport_size.id}"
        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        # Save the QR code image to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img.save(temp_file)
        temp_file.close()

        qr_code_y_position = text_start_height - 350

        # Draw the QR code image on the PDF
        qr_code_size = 220
        p.drawImage(temp_file.name, (width - qr_code_size) / 2, qr_code_y_position, width=qr_code_size, height=qr_code_size, mask='auto')

        # Draw the QR data text under the QR code
        p.setFont("DejaVuSans", 12)
        p.drawString(10, qr_code_y_position - 20, f"QR Data: {qr_data}")

        p.showPage()
        p.save()

        # Clean up temporary file
        os.remove(temp_file.name)

        return response
    
@method_decorator([login_required], name='dispatch')
class BarcodePassportSizePerPiece(View):
    def get(self, request, passport_size_id):
        passport_size = get_object_or_404(PassportSize, pk=passport_size_id)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_qrcodes.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points (1 inch = 72 points)
        width, height = 252, 504  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))

        # Retrieve all related ProductionPiece instances
        pieces = ProductionPiece.objects.filter(passport_size=passport_size)

        # Loop through each ProductionPiece to generate QR codes and add additional information
        top_margin = 40 * 2.83464567  # Convert mm to points (1 mm = 2.83464567 points)
        text_start_height = height - top_margin

        piece_number = 1

        for piece in pieces:
            # Draw additional data about the piece
            model_name = passport_size.passport.order.model.name
            color = passport_size.passport.order.color
            fabrics = passport_size.passport.order.fabrics
            passport_number = passport_size.passport.id
            size = passport_size.size_quantity.size

            p.setFont("DejaVuSans", 14)
            p.drawString(10, text_start_height, f"Модель: {model_name}")
            p.drawString(10, text_start_height - 25, f"Цвет: {color}")
            p.drawString(10, text_start_height - 50, f"Ткань: {fabrics}")
            p.drawString(10, text_start_height - 75, f"Паспорт: №{passport_number}")
            p.drawString(10, text_start_height - 100, f"Размер: {size}")
            p.drawString(10, text_start_height - 125, f"Единица: {piece_number}")

            # Generate QR code
            qr_data = f"{passport_number}-{passport_size.id}-{piece.id}"
            qr = qrcode.QRCode(
                version=1,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')

            # Save the QR code image to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            img.save(temp_file)
            temp_file.close()

            qr_code_y_position = text_start_height - 350

            # Draw the QR code image on the PDF
            qr_code_size = 220
            p.drawImage(temp_file.name, (width - qr_code_size) / 2, qr_code_y_position, width=qr_code_size, height=qr_code_size, mask='auto')

            # Draw the QR data text under the QR code
            p.setFont("DejaVuSans", 12)
            p.drawString(10, qr_code_y_position - 20, f"QR Data: {qr_data}")

            # Clean up the temporary file
            os.remove(temp_file.name)

            # Create a new page for the next QR code and data set
            p.showPage()

            piece_number += 1

        p.save()
        return response