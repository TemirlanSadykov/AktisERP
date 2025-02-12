from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
from faker import Faker
import random
from ...models import (Branch, UserProfile, EmployeeAttendance, Client, Roll,
                             Equipment, Node, Operation, Assortment, Model, ModelOperation,
                             ClientOrder, Order)

class Command(BaseCommand):
    help = "Populate the database with specific dummy data for selected models"

    def handle(self, *args, **options):
        faker = Faker('ru_RU')

        # Create a single Branch
        main_branch = Branch.objects.create(name=faker.company())

        # Create Equipment
        equipments = [Equipment.objects.create(name=faker.unique.word()) for _ in range(20)]

        # Create Nodes
        nodes = [Node.objects.create(name=faker.unique.word(), number=str(faker.random_int(min=1000, max=9999)), type=random.choice([0, 1, 2, 3])) for _ in range(10)]

        # Create Users and UserProfiles
        user_profiles = []
        for _ in range(50):
            user = User.objects.create_user(username=faker.unique.user_name(), email=faker.email(), password='password')
            profile = UserProfile.objects.create(
                user=user,
                branch=main_branch,
                employee_id=faker.unique.random_int(min=1000, max=9999),
                type=random.choice([1, 2, 3, 4, 5]),  # Avoid creating admin types if not needed
                station=random.choice([choice[0] for choice in UserProfile.STATION_CHOICES]),
                status=faker.boolean())
            user_profiles.append(profile)

        # Create Employee Attendance records
        for profile in user_profiles:
            EmployeeAttendance.objects.create(
                branch=main_branch,
                employee=profile,
                timestamp=faker.date_time_this_year(before_now=True, after_now=False, tzinfo=timezone.get_current_timezone()),
                is_clock_in=faker.boolean())

        # Create Clients
        clients = [Client.objects.create(name=faker.name()) for _ in range(5)]

        # Create Rolls
        rolls = [Roll.objects.create(
            branch=main_branch,
            name=faker.word(),
            color=faker.color_name(),
            fabrics=faker.word(),
            meters=faker.random_number(digits=3),
            used_meters=faker.random_number(digits=2)) for _ in range(10)]

        # Create Operations
        operations = []
        for node in nodes:
            for _ in range(10):  # Each node gets 10 operations
                operation = Operation.objects.create(
                    name=faker.sentence(),
                    number=str(faker.unique.random_int(min=1000, max=9999)),
                    payment=faker.random_number(digits=5),
                    equipment=random.choice(equipments),
                    node=node,
                    preferred_completion_time=faker.random_int(min=1, max=10),
                operations.append(operation)

        # Create Assortments and Models
        assortments = [Assortment.objects.create(branch=main_branch, name=faker.word()) for _ in range(10)]
        for assortment in assortments:
            for _ in range(2):  # 2 models per assortment
                model = Model.objects.create(name=faker.word(), assortment=assortment)
                for operation in random.sample(operations, k=random.randint(1, 5)):  # 1-5 operations per model
                    ModelOperation.objects.create(model=model, operation=operation, order=random.randint(1, 100))

        # Create Client Orders and Orders
        for client in clients:
            client_order = ClientOrder.objects.create(
                branch=main_branch,
                created_at=timezone.now(),  # Ensure timezone-aware datetime
                order_number=faker.unique.random_int(min=1000, max=9999),
                client=client,
                status=random.choice([0, 1, 2]),
                term=timezone.now() + datetime.timedelta(days=30))  # Ensure term is set properly

            for _ in range(2):  # 2 orders per client order
                model_choice = random.choice(Model.objects.filter(assortment__isnull=False))
                order = Order.objects.create(
                    client_order=client_order,
                    model=model_choice,
                    assortment=model_choice.assortment,
                    color=faker.color_name(),
                    fabrics=faker.word(),
                    quantity=faker.random_int(min=1, max=100),
                    status=random.choice([0, 1, 2]))

        self.stdout.write(self.style.SUCCESS('Successfully populated the database with specific dummy data for selected models.'))