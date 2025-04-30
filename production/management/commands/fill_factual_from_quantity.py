from django.core.management.base import BaseCommand
from production.models import SizeQuantity

class Command(BaseCommand):
    help = "Fill `factual` with the same value as `quantity` for all SizeQuantity entries where `factual` is None."

    def handle(self, *args, **kwargs):
        updated = 0
        for sq in SizeQuantity.objects.filter(factual__isnull=True):
            if sq.quantity is not None:
                sq.factual = sq.quantity
                sq.save(update_fields=['factual'])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} SizeQuantity records."))
