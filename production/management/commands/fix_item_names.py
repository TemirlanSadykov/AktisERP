# production/management/commands/fix_item_names.py

from django.core.management.base import BaseCommand
from production.models import Item, Category


class Command(BaseCommand):
    help = "Set proper names and assign 'Рулон' category to all Items based on roll attributes"

    def handle(self, *args, **kwargs):
        updated = 0
        skipped = 0
        category_cache = {}

        items = Item.objects.all().select_related('color', 'fabric', 'supplier', 'company')

        for item in items:

            # Get or create "Рулон" category for this company
            company_id = item.company_id
            if company_id not in category_cache:
                category_cache[company_id], _ = Category.objects.get_or_create(
                    name="Рулон", company=item.company, defaults={"is_fabric": True}
                )
            roll_category = category_cache[company_id]

            expected_name = f"{item.color.name} {item.fabric.name} {item.width}м от {item.supplier.name}"
            item.name = expected_name
            item.category = roll_category
            item.save(update_fields=["name", "category"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Item names updated and category set: {updated}, Skipped due to missing data: {skipped}"
        ))
