from django.core.management.base import BaseCommand
from production.models import SizeQuantity, Order

class Command(BaseCommand):
    help = "Populate SizeQuantity.model from associated Order if not already set"

    def handle(self, *args, **kwargs):
        updated = 0
        already_set = 0
        skipped = 0

        for sq in SizeQuantity.objects.all():
            if sq.model_id:
                already_set += 1
                continue

            orders = Order.objects.filter(size_quantities=sq)
            if orders.exists():
                order = orders.first()
                sq.model_id = order.model_id
                sq.save(update_fields=['model'])
                updated += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Updated: {updated}, Already set: {already_set}, Skipped (no order): {skipped}"
        ))
