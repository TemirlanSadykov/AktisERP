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
from barcode.writer import ImageWriter
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO

class BarcodePassport(View):
    def get(self, request, passport_id):
        passport = get_object_or_404(Passport, pk=passport_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport.id}_barcode.pdf"'

        # Set up PDF
        p = canvas.Canvas(response, pagesize=letter)
        width, height = letter

        # Generate and save barcode image
        barcode_data = f"{passport.id}"
        barcode_class = barcode.get_barcode_class('code128')
        barcode_obj = barcode_class(barcode_data, writer=ImageWriter())
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        barcode_obj.write(temp_file)
        temp_file.close()

        # Calculate center alignment
        x_center = (width - 400) / 2
        y_center = (height - 200) / 2

        # Draw the barcode image centered on the PDF
        p.drawImage(temp_file.name, x_center, y_center, width=400, height=200, mask='auto')

        p.showPage()
        p.save()

        # Clean up temporary file
        os.remove(temp_file.name)

        return response
    
class BarcodePassportSize(View):
    def get(self, request, passport_size_id):
        passport_size = get_object_or_404(PassportSize, pk=passport_size_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_barcode.pdf"'

        # Set up PDF
        p = canvas.Canvas(response, pagesize=letter)
        width, height = letter

        # Generate and save barcode image
        barcode_data = f"{passport_size.passport.id}-{passport_size.id}"
        barcode_class = barcode.get_barcode_class('code128')
        barcode_obj = barcode_class(barcode_data, writer=ImageWriter())
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        barcode_obj.write(temp_file)
        temp_file.close()

        # Calculate center alignment
        x_center = (width - 400) / 2
        y_center = (height - 200) / 2

        # Draw the barcode image centered on the PDF
        p.drawImage(temp_file.name, x_center, y_center, width=400, height=200, mask='auto')

        p.showPage()
        p.save()

        # Clean up temporary file
        os.remove(temp_file.name)

        return response
    
class BarcodePassportSizePerPiece(View):
    def get(self, request, passport_size_id):
        passport_size = get_object_or_404(PassportSize, pk=passport_size_id)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="passport_{passport_size.passport.id}-size_{passport_size.id}_barcodes.pdf"'

        # Set up PDF
        p = canvas.Canvas(response, pagesize=letter)
        width, height = letter

        # Retrieve all related ProductionPiece instances
        pieces = ProductionPiece.objects.filter(passport_size=passport_size)

        # Loop through each ProductionPiece to generate barcodes
        for piece in pieces:
            barcode_data = f"{passport_size.passport.id}-{passport_size.id}-{piece.id}"
            barcode_class = barcode.get_barcode_class('code128')
            barcode_obj = barcode_class(barcode_data, writer=ImageWriter())

            # Save the barcode image to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            barcode_obj.write(temp_file)
            temp_file.close()

            # Draw the barcode image on the PDF
            barcode_height = 200
            barcode_width = 400
            p.drawImage(temp_file.name, (width - barcode_width) / 2, (height - barcode_height) / 2, width=barcode_width, height=barcode_height, mask='auto')
            
            # Clean up the temporary file
            os.remove(temp_file.name)

            # Create a new page for the next barcode
            p.showPage()

        p.save()
        return response

def generate_barcode(request, product_id):
    barcode = Code128(str(product_id), writer=ImageWriter())
    buffer = BytesIO()
    barcode.write(buffer)
    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Content-Disposition'] = 'inline; filename="barcode_{}.png"'.format(product_id)
    return response

def barcode_scan_page(request, product_id):
    barcode_url = '/production/barcode/{}/'.format(product_id)
    return render(request, 'barcode_scan.html', {'barcode_url': barcode_url, 'product_id': product_id})