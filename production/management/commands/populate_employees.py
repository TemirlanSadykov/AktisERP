from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from ...models import UserProfile, Branch

class Command(BaseCommand):
    help = "Populate the UserProfile table with default data"

    def handle(self, *args, **kwargs):
        try:
            branch = Branch.objects.get(id=1)
        except Branch.DoesNotExist:
            self.stdout.write(self.style.ERROR("Branch with id 1 does not exist. Please create it first."))
            return

        user_types = [
            UserProfile.ADMIN,
            UserProfile.TECHNOLOGIST,
            UserProfile.CUTTER,
            UserProfile.QC,
            UserProfile.PACKER,
            UserProfile.KEEPER,
            UserProfile.MANAGER,
        ]

        total_users = len(user_types) + 10  # One user per type + 10 employees
        password = "su1209gi"

        with transaction.atomic():
            user_counter = 1

            # Create one record for each user type
            for user_type in user_types:
                user, _ = User.objects.get_or_create(username=str(user_counter))
                user.set_password(password)
                user.save()
                UserProfile.objects.get_or_create(
                    user=user,
                    branch=branch,
                    defaults={
                        "employee_id": str(user_counter),
                        "type": user_type,
                        "status": False,
                        "station": 'others',
                    }
                )
                user_counter += 1

            # Create 10 employees
            for _ in range(10):
                user, _ = User.objects.get_or_create(username=str(user_counter))
                user.set_password(password)
                user.save()
                UserProfile.objects.get_or_create(
                    user=user,
                    branch=branch,
                    defaults={
                        "employee_id": str(user_counter),
                        "type": UserProfile.EMPLOYEE,
                        "status": False,
                        "station": 'others',
                    }
                )
                user_counter += 1

        self.stdout.write(self.style.SUCCESS(f"UserProfile data population for {total_users} users completed successfully."))
