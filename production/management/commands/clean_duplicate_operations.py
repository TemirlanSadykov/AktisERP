from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Operation, ModelOperation  # Adjust to your actual app name

class Command(BaseCommand):
    help = 'Cleans duplicate operations based on name, node, and equipment, keeping the one with the lower operation number.'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Get all operations ordered by name, node, equipment, and number
            operations = Operation.objects.all().order_by('name', 'node', 'equipment', 'number')
            last_seen = {}

            # Pre-fetch IDs of operations used in any Model
            used_operation_ids = set(ModelOperation.objects.values_list('operation_id', flat=True))

            for operation in operations:
                # Check if the operation is used in any models
                if operation.id in used_operation_ids:
                    continue  # Skip this operation if it's being used

                key = (operation.name, operation.node_id, operation.equipment_id)
                if key in last_seen:
                    existing_op = last_seen[key]
                    # Compare the numbers after "N" and before "O"
                    existing_number = int(existing_op.number.split('N')[1].split('O')[0])
                    current_number = int(operation.number.split('N')[1].split('O')[0])

                    if existing_number < current_number:
                        # If existing operation number is lower, delete the current one
                        self.stdout.write(f"Deleting: {operation.number} - {operation.name}")
                        operation.delete()
                    else:
                        # Otherwise, delete the existing operation and update the last_seen
                        self.stdout.write(f"Deleting: {existing_op.number} - {existing_op.name}")
                        existing_op.delete()
                        last_seen[key] = operation
                else:
                    # First operation with this name-node-equipment combination
                    last_seen[key] = operation

            self.stdout.write(self.style.SUCCESS("Duplicate operations cleaned."))