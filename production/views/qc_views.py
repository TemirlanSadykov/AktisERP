from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..decorators import qc_required

@login_required
@qc_required
def qc_page(request):
    return render(request, 'qc_page.html')