from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

class Branch(models.Model):
    name = models.CharField(max_length=100) 
    def __str__(self):
        return self.name
    
class BranchAwareManager(models.Manager):
    def for_user(self, user):
        return self.get_queryset().filter(branch=user.profile.branch)

class UserProfile(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='user_profiles', null=True, blank=True)
    objects = BranchAwareManager()
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=100)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['employee_id', 'branch'], name='unique_employee_id_per_branch')
        ]
    ADMIN = 0
    TECHNOLOGIST = 1
    EMPLOYEE = 2
    CUTTER = 3
    QC = 4
    TYPE_CHOICES = [
        (ADMIN, 'Администратор'),
        (TECHNOLOGIST, 'Технолог'),
        (EMPLOYEE, 'Сотрудник'),
        (CUTTER, 'Закройщик'),
        (QC, 'ОТК')
    ]
    type = models.IntegerField(choices=TYPE_CHOICES, default=EMPLOYEE)
    status = models.BooleanField(default=False)
    STATION_CHOICES = [
        ('admin_technologist', 'Админ/Технолог'),
        ('cutting_station', 'Закройный участок'),
        ('sewing_station', 'Швейный участок'),
        ('ironing_station', 'Утюжный участок'),
        ('quality_control', 'ОТК'),
        ('package', 'Упаковка'),
        ('interns', 'Практиканты'),
        ('others', 'Остальные'),
    ]
    station = models.CharField(max_length=100, choices=STATION_CHOICES, default='admin_technologist')
    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"
    
class EmployeeAttendance(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='employee_attendances', null=True, blank=True)
    objects = BranchAwareManager()
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_clock_in = models.BooleanField(default=False)
    def __str__(self):
        event_type = "Clock In" if self.is_clock_in else "Clock Out"
        return f"{self.employee.username} - {event_type} at {self.timestamp}"

class Client(models.Model):
    name = models.CharField(max_length=100)
    contact_info = models.TextField()
    def __str__(self):
        return self.name

class Assortment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='assortments', null=True, blank=True)
    objects = BranchAwareManager()
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class Roll(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True)
    objects = BranchAwareManager()   
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=50)
    fabrics = models.CharField(max_length=100)
    meters = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    def __str__(self):
        return f"{self.name} - {self.color} - {self.fabrics}"

class Operation(models.Model):
    name = models.CharField(max_length=100)
    payment = models.DecimalField(max_digits=10, decimal_places=2)
    equipment = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    preferred_completion_time = models.IntegerField()
    average_completion_time = models.IntegerField(null=True)
    photo = models.ImageField(upload_to='operation_photos/', null=True, blank=True)
    def __str__(self):
        return self.name
    
class Model(models.Model):
    name = models.CharField(max_length=100)
    operations = models.ManyToManyField(Operation, related_name='models')
    def __str__(self):
        return self.name
    
class SizeQuantity(models.Model):
    size = models.CharField(max_length=10)
    quantity = models.IntegerField()
    def __str__(self):
        return f"Size: {self.size}, Quantity: {self.quantity}"

class Order(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='orders', null=True, blank=True)
    objects = BranchAwareManager()
    name = models.CharField(max_length=100)
    order_number = models.CharField(max_length=100)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders')
    model = models.ForeignKey(Model, on_delete=models.CASCADE, related_name='orders')
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='orders')
    color = models.CharField(max_length=50, null=True)
    fabrics = models.CharField(max_length=100, null=True)
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    TYPE_CHOICES = [
        (NEW, 'New'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed'),
    ]
    status = models.IntegerField(choices=TYPE_CHOICES, default=NEW)
    quantity = models.IntegerField()
    completed_quantity = models.IntegerField(default=0)
    payment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def default_term():
        return timezone.now() + datetime.timedelta(days=30)
    term = models.DateField(default=default_term)
    size_quantities = models.ManyToManyField(SizeQuantity, related_name='orders')
    def __str__(self):
        return f"Order {self.order_number} for {self.client.name}"
    
class Passport(models.Model):
    date = models.DateField(auto_now_add=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='passports')
    size_quantities = models.ManyToManyField(SizeQuantity, through='PassportSize', related_name='passports')
    rolls = models.ManyToManyField(Roll, through='PassportRoll', related_name='passports')
    is_completed = models.BooleanField(default=False, verbose_name="Passport Completed")
    def __str__(self):
        return self.order.order_number
    
class PassportSize(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_sizes')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='passport_sizes')
    quantity = models.IntegerField()
    def __str__(self):
        return f"{self.size_quantity.size} - {self.quantity} pcs"

class PassportRoll(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_rolls')
    roll = models.ForeignKey(Roll, on_delete=models.CASCADE, related_name='passport_rolls')
    meters = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.meters} meters of {self.roll.name} for {self.passport.order.order_number}"
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class Work(models.Model):
    employees = models.ManyToManyField(UserProfile, through='AssignedWork')
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='works')
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='works') 
    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='works', null=True)
    def __str__(self):
        return f"{self.operation.name} - {self.passport_size.size_quantity.size}"
    
class AssignedWork(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='assigned_works')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_tasks')
    quantity = models.IntegerField()
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_success = models.BooleanField(default=False, verbose_name="Completed Successfully")
    def __str__(self):
        return f"{self.employee.employee_id} - {self.work.operation.name} - {self.quantity}"

class ReassignedWork(models.Model):
    original_assigned_work = models.ForeignKey(AssignedWork, on_delete=models.CASCADE, related_name='reassignments')
    new_employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='reassigned_works')
    reassigned_quantity = models.IntegerField()
    reason = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False, verbose_name="Completed Successfully")
    def __str__(self):
        return f"Reassigned {self.reassigned_quantity} of {self.original_assigned_work} to {self.new_employee}"