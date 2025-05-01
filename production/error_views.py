from django.shortcuts import render

def error_403(request, exception):
   context = {}
   return render(request,'errors/403.html', context)

def error_404(request, exception):
   context = {}
   return render(request,'errors/404.html', context)

def error_500(request):
   context = {}
   return render(request,'errors/500.html', context)