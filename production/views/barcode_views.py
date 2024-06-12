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

pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))

@method_decorator([login_required], name='dispatch')
class BarcodePassport(View):
    def get(self, request, passport_id):
        passport = get_object_or_404(Passport, pk=passport_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport.id}_barcode.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points
        width, height = 252, 588  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))
        p.setFont("DejaVuSans", 10)

        # Top margin and initial text position
        top_margin = 15 * 2.83464567
        text_start_height = height - top_margin

        # Additional Passport data
        model_name = passport.order.model.name  # Assuming model relation exists
        color = passport.order.color
        assortment = passport.order.assortment
        passport_number = passport.id

        p.drawString(10, text_start_height, f"Модель: {model_name}")
        p.drawString(10, text_start_height - 20, f"Цвет: {color}")
        p.drawString(10, text_start_height - 40, f"Ассортимент: {assortment}")
        p.drawString(10, text_start_height - 60, f"Паспорт: №{passport_number}")

        # Generate and position barcode
        barcode_data = f"{passport.id}"
        barcode_class = barcode.get_barcode_class('code128')
        barcode_obj = barcode_class(barcode_data, writer=ImageWriter())
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        barcode_obj.write(temp_file)
        temp_file.close()

        barcode_y_position = text_start_height - 250

        # Draw the barcode image on the PDF
        barcode_height = 140
        barcode_width = 280
        p.drawImage(temp_file.name, (width - barcode_width) / 2, barcode_y_position, width=barcode_width, height=barcode_height, mask='auto')

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
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_barcode.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points
        width, height = 252, 588  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))
        p.setFont("DejaVuSans", 10)

        # Top margin and initial text position
        top_margin = 15 * 2.83464567
        text_start_height = height - top_margin

        # Additional Passport Size data
        model_name = passport_size.passport.order.model.name
        color = passport_size.passport.order.color
        assortment = passport_size.passport.order.assortment
        passport_number = passport_size.passport.id
        size = passport_size.size_quantity.size

        p.drawString(10, text_start_height, f"Модель: {model_name}")
        p.drawString(10, text_start_height - 20, f"Цвет: {color}")
        p.drawString(10, text_start_height - 40, f"Ассортимент: {assortment}")
        p.drawString(10, text_start_height - 60, f"Паспорт: №{passport_number}")
        p.drawString(10, text_start_height - 80, f"Размер: {size}")

        # Generate and position barcode
        barcode_data = f"{passport_size.passport.id}-{passport_size.id}"
        barcode_class = barcode.get_barcode_class('code128')
        barcode_obj = barcode_class(barcode_data, writer=ImageWriter())
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        barcode_obj.write(temp_file)
        temp_file.close()

        barcode_y_position = text_start_height - 250

        # Draw the barcode image on the PDF
        barcode_height = 140
        barcode_width = 280
        p.drawImage(temp_file.name, (width - barcode_width) / 2, barcode_y_position, width=barcode_width, height=barcode_height, mask='auto')

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
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_barcodes.pdf"'

        # Custom page size with a 30:70 ratio, dimensions in points (1 inch = 72 points)
        width, height = 252, 588  # Approximately 3.5 inches by 8.167 inches

        # Set up PDF with custom size
        p = canvas.Canvas(response, pagesize=(width, height))

        # Retrieve all related ProductionPiece instances
        pieces = ProductionPiece.objects.filter(passport_size=passport_size)

        # Loop through each ProductionPiece to generate barcodes and add additional information
        top_margin = 15 * 2.83464567  # Convert mm to points (1 mm = 2.83464567 points)
        text_start_height = height - top_margin

        for piece in pieces:
            # Draw additional data about the piece
            model_name = passport_size.passport.order.model.name
            color = passport_size.passport.order.color
            assortment = passport_size.passport.order.assortment
            passport_number = passport_size.passport.id
            size = passport_size.size_quantity.size

            p.setFont("DejaVuSans", 10)
            p.drawString(10, text_start_height, f"Модель: {model_name}")
            p.drawString(10, text_start_height - 20, f"Цвет: {color}")
            p.drawString(10, text_start_height - 40, f"Ассортимент: {assortment}")
            p.drawString(10, text_start_height - 60, f"Паспорт: №{passport_number}")
            p.drawString(10, text_start_height - 80, f"Размер: {size}")
            p.drawString(10, text_start_height - 100, f"ID Единицы: {piece.id}")

            # Generate barcode
            barcode_data = f"{passport_number}-{passport_size.id}-{piece.id}"
            barcode_class = barcode.get_barcode_class('code128')
            barcode_obj = barcode_class(barcode_data, writer=ImageWriter())

            # Save the barcode image to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            barcode_obj.write(temp_file)
            temp_file.close()

            barcode_y_position = text_start_height - 250

            # Draw the barcode image on the PDF
            barcode_height = 140
            barcode_width = 280
            p.drawImage(temp_file.name, (width - barcode_width) / 2, barcode_y_position, width=barcode_width, height=barcode_height, mask='auto')
            
            # Clean up the temporary file
            os.remove(temp_file.name)

            # Create a new page for the next barcode and data set
            p.showPage()

        p.save()
        return response