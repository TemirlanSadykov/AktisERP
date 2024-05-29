import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    name = models.CharField(max_length=100) 
    def __str__(self):
        return self.name
    
class BranchAwareManager(models.Manager):
    def for_user(self, user):
        return self.get_queryset().filter(branch=user.profile.branch)

class UserProfile(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='user_profiles', null=True, blank=True)
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
    PACKER = 5
    TYPE_CHOICES = [
        (ADMIN, 'ADMIN'),
        (TECHNOLOGIST, 'TECHNOLOGIST'),
        (EMPLOYEE, 'EMPLOYEE'),
        (CUTTER, 'CUTTER'),
        (QC, 'QC'),
        (PACKER, 'PACKER'),
    ]
    type = models.IntegerField(choices=TYPE_CHOICES, default=EMPLOYEE)
    status = models.BooleanField(default=False)
    STATION_CHOICES = [
        ('admin_technologist', 'admin_technologist'),
        ('cutting_station', 'cutting_station'),
        ('sewing_station', 'sewing_station'),
        ('ironing_station', 'ironing_station'),
        ('quality_control', 'QC'),
        ('package', 'package'),
        ('interns', 'interns'),
        ('others', 'others'),
    ]
    station = models.CharField(max_length=100, choices=STATION_CHOICES, default='sewing_station')
    def __str__(self):
        return f"{self.employee_id} - {self.user.first_name}"
    
class EmployeeAttendance(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='employee_attendances', null=True, blank=True)
    objects = BranchAwareManager()
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_clock_in = models.BooleanField(default=False)
    def __str__(self):
        event_type = "Clock In" if self.is_clock_in else "Clock Out"
        return f"{self.employee.user} - {event_type} at {self.timestamp}"

class Client(models.Model):
    name = models.CharField(max_length=100, verbose_name='Имя')
    contact_info = models.TextField()
    def __str__(self):
        return self.name

class Roll(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True)
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=50)
    fabrics = models.CharField(max_length=100)
    meters = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    used_meters = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    def __str__(self):
        return f"{self.name} - {self.color} - {self.fabrics} - {self.available_meters}"
    @property
    def available_meters(self):
        return self.meters - self.used_meters

class Equipment(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name
    
class Node(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_common = models.BooleanField(default=False)
    SEWING = 0
    CUTTING = 1
    QC = 2
    PACKING = 3
    TYPE_CHOICES = [
        (SEWING, 'SEWING'),
        (CUTTING, 'CUTTING'),
        (QC, 'QC'),
        (PACKING, 'PACKING'),
    ]
    type = models.IntegerField(choices=TYPE_CHOICES, default=SEWING)
    def __str__(self):
        return self.name
    
class Operation(models.Model):
    name = models.CharField(max_length=300)
    number = models.CharField(max_length=100, null=True, blank=True)
    payment = models.DecimalField(max_digits=10, decimal_places=2)
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='operations')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='operations')
    preferred_completion_time = models.IntegerField()
    average_completion_time = models.IntegerField(null=True)
    photo = models.ImageField(upload_to='operation_photos/', null=True, blank=True)
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='operations', null=True, blank=True)
    def __str__(self):
        return f"{self.number} - {self.node.name} - {self.name}"
    
class Assortment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='assortments', null=True, blank=True)
    name = models.CharField(max_length=100)
    operations = models.ManyToManyField(Operation, related_name='assortments')
    def __str__(self):
        return self.name

class Model(models.Model):
    name = models.CharField(max_length=100)
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='models', null=True, blank=True)
    operations = models.ManyToManyField(Operation, through='ModelOperation', related_name='models')
    def __str__(self):
        return self.name
    
class ModelOperation(models.Model):
    model = models.ForeignKey(Model, on_delete=models.CASCADE)
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    class Meta:
        ordering = ['order']

class SizeQuantity(models.Model):
    size = models.CharField(max_length=10)
    quantity = models.IntegerField()
    def __str__(self):
        return f"size: {self.size}, quantity: {self.quantity}"
    
class ClientOrder(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='client_orders', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    order_number = models.CharField(max_length=100)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='client_orders')
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    TYPE_CHOICES = [
        (NEW, 'NEW'),
        (IN_PROGRESS, 'IN_PROGRESS'),
        (COMPLETED, 'COMPLETED'),
    ]
    status = models.IntegerField(choices=TYPE_CHOICES, default=NEW)
    def default_term():
        return timezone.now() + datetime.timedelta(days=30)
    term = models.DateField(default=default_term)
    def __str__(self):
        return self.order_number

class Order(models.Model):
    client_order = models.ForeignKey(ClientOrder, on_delete=models.CASCADE, related_name='orders')
    name = models.CharField(max_length=100)
    model = models.ForeignKey(Model, on_delete=models.CASCADE, related_name='orders')
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='orders')
    color = models.CharField(max_length=50, null=True)
    fabrics = models.CharField(max_length=100, null=True)
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    TYPE_CHOICES = [
        (NEW, 'NEW'),
        (IN_PROGRESS, 'IN_PROGRESS'),
        (COMPLETED, 'COMPLETED'),
    ]
    status = models.IntegerField(choices=TYPE_CHOICES, default=NEW)
    quantity = models.IntegerField()
    completed_quantity = models.IntegerField(default=0)
    payment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    size_quantities = models.ManyToManyField(SizeQuantity, related_name='orders')
    def __str__(self):
        return f"{self.name} - {self.model}"
    
class Passport(models.Model):
    date = models.DateField(auto_now_add=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='passports')
    size_quantities = models.ManyToManyField(SizeQuantity, through='PassportSize', related_name='passports')
    rolls = models.ManyToManyField(Roll, through='PassportRoll', related_name='passports')
    is_completed = models.BooleanField(default=False)
    def __str__(self):
        return f"ID: {str(self.id)}"
    
class PassportSize(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_sizes')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='passport_sizes')
    quantity = models.IntegerField()
    CUTTING = 0
    SEWING = 1
    QC = 2
    PACKING = 3
    DONE = 4
    STAGE_CHOICES = [
        (CUTTING, 'CUTTING'),
        (SEWING, 'SEWING'),
        (QC, 'QC'),
        (PACKING, 'PACKING'),
        (DONE, 'DONE'),
    ]
    stage = models.IntegerField(choices=STAGE_CHOICES, default=CUTTING)
    def __str__(self):
        return f"{self.size_quantity.size} - {self.quantity} шт"

class PassportRoll(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_rolls')
    roll = models.ForeignKey(Roll, on_delete=models.CASCADE, related_name='passport_rolls')
    meters = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.meters} meters {self.roll.name}"

class Work(models.Model):
    employees = models.ManyToManyField(UserProfile, through='AssignedWork')
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='works')
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='works')
    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='works', null=True)
    def __str__(self):
        if self.passport_size:
            return f"{self.operation.name} - {self.passport_size.size_quantity.size}"
        else:
            return f"{self.operation.name} - Нет размера"
    
class AssignedWork(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='assigned_works')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_tasks')
    quantity = models.IntegerField()
    start_time = models.DateTimeField(null=True, blank=True )
    end_time = models.DateTimeField(null=True, blank=True)
    is_success = models.BooleanField(default=False)
    payment_date = models.DateField(null=True)
    def __str__(self):
        return f"{self.employee.employee_id} - {self.work.operation.name} - {self.work.passport_size.size_quantity.size} - {self.quantity}"

class ReassignedWork(models.Model):
    original_assigned_work = models.ForeignKey(AssignedWork, on_delete=models.CASCADE, related_name='reassignments')
    new_employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='reassigned_works')
    reassigned_quantity = models.IntegerField()
    reason = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
    payment_date = models.DateField(null=True)
    def __str__(self):
        return f"Переназначено {self.reassigned_quantity} от {self.original_assigned_work} к {self.new_employee}"
    
class Error(models.Model):
    class ErrorType(models.TextChoices):
        DEFECT = 'DEFECT', 'DEFECT'
        DISCREPANCY = 'DISCREPANCY', 'DISCREPANCY'
    
    class DefectType(models.TextChoices):
        STITCHING = 'STITCHING', 'STITCHING'
        CUTTING = 'CUTTING', 'CUTTING'
        FABRIC = 'FABRIC', 'FABRIC'
        ASSEMBLY = 'ASSEMBLY', 'ASSEMBLY'
        OTHER = 'OTHER', 'OTHER'

    class Status(models.TextChoices):
        REPORTED = 'REPORTED', 'REPORTED'
        UNRESOLVABLE = 'UNRESOLVABLE', 'UNRESOLVABLE'
        RESOLVED = 'RESOLVED', 'RESOLVED'
    
    error_type = models.CharField(max_length=20, choices=ErrorType.choices)
    defect_type = models.CharField(max_length=20, choices=DefectType.choices, null=True, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    responsible_employees = models.ManyToManyField(UserProfile, through='ErrorResponsibility')
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='errors')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='errors')
    quantity = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED)
    reported_date = models.DateTimeField(default=timezone.now)
    resolved_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.error_type == self.ErrorType.DEFECT:
            return f"Дефект: {self.defect_type} - Степень: {self.severity}"
        else:
            discrepancy_type = "Надостаток" if self.quantity < 0 else "Избыток"
            return f"Несоответствие: {discrepancy_type} на {abs(self.quantity)}"

class ErrorResponsibility(models.Model):
    error = models.ForeignKey(Error, on_delete=models.CASCADE, related_name='error_responsibilities')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='error_responsibilities')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Процент ответственности, приписываемый этому сотруднику.")

    def __str__(self):
        return f"{self.employee.user.username} - {self.percentage}%"

class FixedSalary(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='fixed_salaries', null=True, blank=True)
    position = models.CharField(max_length=100)
    employees = models.ManyToManyField(UserProfile, related_name='fixed_salaries')
    salary = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.position} - {self.salary}"

class SalaryPayment(models.Model):
    fixed_salary = models.ForeignKey(FixedSalary, on_delete=models.CASCADE, related_name='salary_payments')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='salary_payments')
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.employee.user.username} - {self.payment_date} - {self.amount}"