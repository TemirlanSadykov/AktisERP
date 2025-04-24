# production/management/commands/create_roll_batches_and_stocks.py

from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from production.models import Roll, RollBatch, Stock, StockMovement, Warehouse
from django.db import transaction

class Command(BaseCommand):
    help = "Create roll batches and stock entries from existing rolls"

    def handle(self, *args, **kwargs):
        # Try to get the first warehouse, create if none exists
        default_warehouse = Warehouse.objects.filter(is_archived=False).first()
        if not default_warehouse:
            default_warehouse = Warehouse.objects.create(name="Default", location="Auto-generated")

        count_batches = 0
        count_stocks = 0
        count_movements = 0

        with transaction.atomic():
            for roll in Roll.objects.all():
                if not all([roll.color, roll.fabric, roll.supplier, roll.width, roll.length_t]):
                    continue

                roll_batch, created = RollBatch.objects.get_or_create(
                    color=roll.color,
                    fabric=roll.fabric,
                    supplier=roll.supplier,
                    width=roll.width,
                    defaults={'company': roll.company}
                )

                if created:
                    count_batches += 1

                if roll.roll_batch != roll_batch:
                    roll.roll_batch = roll_batch
                    roll.save()

                content_type = ContentType.objects.get_for_model(RollBatch)

                stock, created_stock = Stock.objects.get_or_create(
                    content_type=content_type,
                    object_id=roll_batch.id,
                    type=Stock.ROLLS,
                    defaults={
                        'quantity': Decimal('0'),
                        'warehouse': default_warehouse,
                        'company': roll.company
                    }
                )

                stock.quantity += roll.length_t
                stock.save()

                if created_stock:
                    count_stocks += 1

                StockMovement.objects.create(
                    stock=stock,
                    movement_type='IN',
                    quantity=roll.length_t,
                    from_warehouse=None,
                    to_warehouse=default_warehouse,
                    note=f"Initial stock for roll ID {roll.id}",
                    company=roll.company
                )
                count_movements += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Batches created: {count_batches}, Stocks updated/created: {count_stocks}, Movements added: {count_movements}"
        ))
