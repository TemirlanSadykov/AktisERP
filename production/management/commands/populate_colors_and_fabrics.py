from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Color, Fabrics  # Replace `your_app` with your actual app name

class Command(BaseCommand):
    help = "Populate the Color and Fabrics models with default data"

    def handle(self, *args, **kwargs):
        colors_data = [
            "Красный", "Синий", "Зелёный", "Жёлтый", "Чёрный", 
            "Белый", "Оранжевый", "Фиолетовый", "Розовый", "Коричневый"
        ]

        fabrics_data = [
            "Хлопок", "Шерсть", "Шёлк", "Лён", "Джинс", 
            "Полиэстер", "Кашемир", "Вискоза", "Акрил", "Микрофибра"
        ]

        with transaction.atomic():
            for color in colors_data:
                Color.objects.get_or_create(name=color)

            for fabric in fabrics_data:
                Fabrics.objects.get_or_create(name=fabric)

        self.stdout.write(self.style.SUCCESS("Data population completed successfully."))
