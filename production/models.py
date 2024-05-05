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
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='user_profiles', null=True, blank=True, verbose_name='Филиал')
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    employee_id = models.CharField(max_length=100, verbose_name='ID сотрудника')
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
        (ADMIN, 'Администратор'),
        (TECHNOLOGIST, 'Технолог'),
        (EMPLOYEE, 'Сотрудник'),
        (CUTTER, 'Закройщик'),
        (QC, 'ОТК'),
        (PACKER, 'Упаковщик'),
    ]
    type = models.IntegerField(choices=TYPE_CHOICES, default=EMPLOYEE, verbose_name='Тип')
    status = models.BooleanField(default=False, verbose_name='Статус')
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
    station = models.CharField(max_length=100, choices=STATION_CHOICES, default='sewing_station', verbose_name='Станция')
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
        return f"{self.employee.username} - {event_type} at {self.timestamp}"

class Client(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    contact_info = models.TextField(verbose_name='Контактная информация')
    def __str__(self):
        return self.name

class Assortment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='assortments', null=True, blank=True, verbose_name='Филиал')
    name = models.CharField(max_length=100, verbose_name='Название')
    def __str__(self):
        return self.name

class Roll(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True, verbose_name='Филиал')
    name = models.CharField(max_length=100, verbose_name='Название')
    color = models.CharField(max_length=50, verbose_name='Цвет')
    fabrics = models.CharField(max_length=100, verbose_name='Ткани')
    meters = models.DecimalField(max_digits=10, decimal_places=2, null=True, verbose_name='Метры')
    used_meters = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True, verbose_name='Использованные метры')
    def __str__(self):
        return f"{self.name} - {self.color} - {self.fabrics} - {self.available_meters}"
    @property
    def available_meters(self):
        return self.meters - self.used_meters

class Equipment(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    def __str__(self):
        return self.name
    
class Node(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_common = models.BooleanField(default=False, verbose_name='Общий')
    SEWING = 0
    CUTTING = 1
    QC = 2
    PACKING = 3
    TYPE_CHOICES = [
        (SEWING, 'Шитье'),
        (CUTTING, 'Резка'),
        (QC, 'ОТК'),
        (PACKING, 'Упаковка'),
    ]
    type = models.IntegerField(choices=TYPE_CHOICES, default=SEWING, verbose_name='Тип')
    def __str__(self):
        return self.name
    
class Operation(models.Model):
    name = models.CharField(max_length=300, verbose_name='Название')
    payment = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Оплата')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='operations', verbose_name='Оборудование')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='operations', verbose_name='Узел')
    preferred_completion_time = models.IntegerField(verbose_name='Предпочтительное время выполнения')
    average_completion_time = models.IntegerField(null=True, verbose_name='Среднее время выполнения')
    photo = models.ImageField(upload_to='operation_photos/', null=True, blank=True, verbose_name='Фото')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='operations', null=True, blank=True, verbose_name='Сотрудник')
    def __str__(self):
        return self.name
    
class Model(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    operations = models.ManyToManyField(Operation, related_name='models', verbose_name='Операции')
    def __str__(self):
        return self.name

class SizeQuantity(models.Model):
    size = models.CharField(max_length=10, verbose_name='Размер')
    quantity = models.IntegerField(verbose_name='Количество')
    def __str__(self):
        return f"Размер: {self.size}, Количество: {self.quantity}"
    
class ClientOrder(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='client_orders', null=True, blank=True, verbose_name='Филиал')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Дата создания')
    order_number = models.CharField(max_length=100, verbose_name='Номер заказа')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='client_orders', verbose_name='Клиент')
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    TYPE_CHOICES = [
        (NEW, 'Новый'),
        (IN_PROGRESS, 'В процессе'),
        (COMPLETED, 'Завершен'),
    ]
    status = models.IntegerField(choices=TYPE_CHOICES, default=NEW, verbose_name='Статус')
    def default_term():
        return timezone.now() + datetime.timedelta(days=30)
    term = models.DateField(default=default_term, verbose_name='Срок выполнения')
    def __str__(self):
        return self.order_number

class Order(models.Model):
    client_order = models.ForeignKey(ClientOrder, on_delete=models.CASCADE, related_name='orders', verbose_name='Заказ клиента')
    name = models.CharField(max_length=100, verbose_name='Название')
    model = models.ForeignKey(Model, on_delete=models.CASCADE, related_name='orders', verbose_name='Модель')
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='orders', verbose_name='Ассортимент')
    color = models.CharField(max_length=50, null=True, verbose_name='Цвет')
    fabrics = models.CharField(max_length=100, null=True, verbose_name='Ткани')
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    TYPE_CHOICES = [
        (NEW, 'Новый'),
        (IN_PROGRESS, 'В процессе'),
        (COMPLETED, 'Завершен'),
    ]
    status = models.IntegerField(choices=TYPE_CHOICES, default=NEW, verbose_name='Статус')
    quantity = models.IntegerField(verbose_name='Количество')
    completed_quantity = models.IntegerField(default=0, verbose_name='Завершенное количество')
    payment = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Оплата')
    size_quantities = models.ManyToManyField(SizeQuantity, related_name='orders', verbose_name='Размеры и количества')
    def __str__(self):
        return f"{self.name} - {self.model}"
    def default_term():
        return timezone.now() + datetime.timedelta(days=30)
    
class Passport(models.Model):
    date = models.DateField(auto_now_add=True, verbose_name='Дата')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='passports', verbose_name='Заказ')
    size_quantities = models.ManyToManyField(SizeQuantity, through='PassportSize', related_name='passports', verbose_name='Размеры и количества')
    rolls = models.ManyToManyField(Roll, through='PassportRoll', related_name='passports', verbose_name='Рулоны')
    is_completed = models.BooleanField(default=False, verbose_name='Паспорт завершен')
    def __str__(self):
        return f"ID: {str(self.id)}"
    
class PassportSize(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Паспорт')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Размер и количество')
    quantity = models.IntegerField(verbose_name='Количество')
    CUTTING = 0
    SEWING = 1
    QC = 2
    PACKING = 3
    DONE = 4
    STAGE_CHOICES = [
        (CUTTING, 'Резка'),
        (SEWING, 'Шитье'),
        (QC, 'ОТК'),
        (PACKING, 'Упаковка'),
        (DONE, 'Готово'),
    ]
    stage = models.IntegerField(choices=STAGE_CHOICES, default=CUTTING, verbose_name='Этап')
    def __str__(self):
        return f"{self.size_quantity.size} - {self.quantity} шт"

class PassportRoll(models.Model):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_rolls', verbose_name='Паспорт')
    roll = models.ForeignKey(Roll, on_delete=models.CASCADE, related_name='passport_rolls', verbose_name='Рулон')
    meters = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Метры')
    def __str__(self):
        return f"{self.meters} метров {self.roll.name}"

class Work(models.Model):
    employees = models.ManyToManyField(UserProfile, through='AssignedWork', verbose_name='Сотрудники')
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='works', verbose_name='Операция')
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='works', verbose_name='Паспорт')
    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='works', null=True, verbose_name='Размер и количество')
    def __str__(self):
        if self.passport_size:
            return f"{self.operation.name} - {self.passport_size.size_quantity.size}"
        else:
            return f"{self.operation.name} - Нет размера"
    
class AssignedWork(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='assigned_works', verbose_name='Работа')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_tasks', verbose_name='Сотрудник')
    quantity = models.IntegerField(verbose_name='Количество')
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='Время начала')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='Время окончания')
    is_success = models.BooleanField(default=False, verbose_name='Завершено успешно')
    payment_date = models.DateField(null=True, verbose_name='Дата оплаты')
    def __str__(self):
        return f"{self.employee.employee_id} - {self.work.operation.name} - {self.quantity}"

class ReassignedWork(models.Model):
    original_assigned_work = models.ForeignKey(AssignedWork, on_delete=models.CASCADE, related_name='reassignments', verbose_name='Исходное назначенное задание')
    new_employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='reassigned_works', verbose_name='Новый сотрудник')
    reassigned_quantity = models.IntegerField(verbose_name='Переназначенное количество')
    reason = models.TextField(blank=True, null=True, verbose_name='Причина')
    is_completed = models.BooleanField(default=False, verbose_name='Завершено')
    is_success = models.BooleanField(default=False, verbose_name='Завершено успешно')
    payment_date = models.DateField(null=True, verbose_name='Дата оплаты')
    def __str__(self):
        return f"Переназначено {self.reassigned_quantity} от {self.original_assigned_work} к {self.new_employee}"
    
class Error(models.Model):
    class ErrorType(models.TextChoices):
        DEFECT = 'DEFECT', 'Дефект'
        DISCREPANCY = 'DISCREPANCY', 'Расхождение'
    
    class DefectType(models.TextChoices):
        STITCHING = 'STITCHING', 'Ошибка шитья'
        CUTTING = 'CUTTING', 'Ошибка резки'
        FABRIC = 'FABRIC', 'Дефект ткани'
        ASSEMBLY = 'ASSEMBLY', 'Ошибка сборки'
        OTHER = 'OTHER', 'Прочие ошибки'

    class Status(models.TextChoices):
        REPORTED = 'REPORTED', 'Сообщено'
        UNRESOLVABLE = 'UNRESOLVABLE', 'Неразрешимо'
        RESOLVED = 'RESOLVED', 'Разрешено'
    
    error_type = models.CharField(max_length=20, choices=ErrorType.choices, verbose_name='Тип ошибки')
    defect_type = models.CharField(max_length=20, choices=DefectType.choices, null=True, blank=True, verbose_name='Тип дефекта')
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Стоимость')
    responsible_employees = models.ManyToManyField(UserProfile, through='ErrorResponsibility', verbose_name='Ответственные сотрудники')
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='errors', verbose_name='Паспорт')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='errors', verbose_name='Размер и количество')
    quantity = models.IntegerField(verbose_name='Количество')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED, verbose_name='Статус')
    reported_date = models.DateTimeField(default=timezone.now, verbose_name='Дата сообщения')
    resolved_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата решения')

    def __str__(self):
        if self.error_type == self.ErrorType.DEFECT:
            return f"Дефект: {self.defect_type} - Степень: {self.severity}"
        else:
            discrepancy_type = "Надостаток" if self.quantity < 0 else "Избыток"
            return f"Несоответствие: {discrepancy_type} на {abs(self.quantity)}"

class ErrorResponsibility(models.Model):
    error = models.ForeignKey(Error, on_delete=models.CASCADE, related_name='error_responsibilities', verbose_name='Ошибка')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='error_responsibilities', verbose_name='Сотрудник')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Процент ответственности', help_text="Процент ответственности, приписываемый этому сотруднику.")

    def __str__(self):
        return f"{self.employee.user.username} - {self.percentage}%"

class FixedSalary(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='fixed_salaries', null=True, blank=True, verbose_name='Филиал')
    position = models.CharField(max_length=100, verbose_name='Должность')
    employees = models.ManyToManyField(UserProfile, related_name='fixed_salaries', verbose_name='Сотрудники')
    salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Зарплата')

    def __str__(self):
        return f"{self.position} - {self.salary}"

class SalaryPayment(models.Model):
    fixed_salary = models.ForeignKey(FixedSalary, on_delete=models.CASCADE, related_name='salary_payments', verbose_name='Фиксированная зарплата')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='salary_payments', verbose_name='Сотрудник')
    payment_date = models.DateField(verbose_name='Дата платежа')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')

    def __str__(self):
        return f"{self.employee.user.username} - {self.payment_date} - {self.amount}"