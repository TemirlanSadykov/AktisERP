import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    name = models.CharField(max_length=100) 
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return self.name
    
class BranchAwareManager(models.Manager):
    def for_user(self, user):
        return self.get_queryset().filter(branch=user.profile.branch)

class UserProfile(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='user_profiles', null=True, blank=True, verbose_name='Филиал')
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    employee_id = models.CharField(max_length=100, verbose_name='ID сотрудника')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    fingerprint = models.CharField(max_length=255, null=True, blank=True, verbose_name='Browser Fingerprint')  # New field for fingerprint
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
    KEEPER = 6
    TYPE_CHOICES = [
        (ADMIN, 'Администратор'),
        (TECHNOLOGIST, 'Технолог'),
        (EMPLOYEE, 'Сотрудник'),
        (CUTTER, 'Закройщик'),
        (QC, 'ОТК'),
        (PACKER, 'Упаковщик'),
        (KEEPER, 'Кладовщик'),
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
        ('warehouse', 'Склад'),
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
    distance = models.FloatField(null=True, blank=True, verbose_name='Distance from Workplace (meters)')
    fingerprint = models.CharField(max_length=255, null=True, blank=True, verbose_name='Browser Fingerprint')
    def __str__(self):
        event_type = "Clock In" if self.is_clock_in else "Clock Out"
        return f"{self.employee} - {event_type} at {self.timestamp} (Distance: {self.distance}m)"

class Client(models.Model):
    name = models.CharField(max_length=100, verbose_name='Имя')
    contact_info = models.TextField(verbose_name='Контактная информация')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    def __str__(self):
        return self.name

class Color(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return self.name
    
class Fabrics(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return self.name

class Roll(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True, verbose_name='Филиал')
    name = models.CharField(max_length=100, verbose_name='Название')
    color = models.ForeignKey(Color, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True, verbose_name='Цвет')
    fabrics = models.ForeignKey(Fabrics, on_delete=models.CASCADE, related_name='rolls', null=True, blank=True, verbose_name='Ткань')
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, verbose_name='Ширина')
    meters = models.DecimalField(max_digits=10, decimal_places=2, null=True, verbose_name='Метры')
    used_meters = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True, verbose_name='Использованные метры')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    def __str__(self):
        return f"{self.name} - {self.color} - {self.fabrics} - {self.available_meters}"
    @property
    def available_meters(self):
        return self.meters - self.used_meters
class Equipment(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return self.name
    
class Node(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    number = models.CharField(max_length=100, null=True, blank=True, verbose_name='№ узла')
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
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    def __str__(self):
        return self.name
    
class Operation(models.Model):
    name = models.CharField(max_length=300, verbose_name='Название')
    number = models.CharField(max_length=100, null=True, blank=True, verbose_name='№ПП')
    payment = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Оплата')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='operations', verbose_name='Оборудование')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='operations', verbose_name='Узел')
    preferred_completion_time = models.IntegerField(verbose_name='Предпочтительное время выполнения')
    average_completion_time = models.IntegerField(null=True, verbose_name='Среднее время выполнения')
    photo = models.ImageField(upload_to='operation_photos/', null=True, blank=True, verbose_name='Фото')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='operations', null=True, blank=True, verbose_name='Сотрудник')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = {}
        for field in self._meta.fields:
            try:
                value = getattr(self, field.name)
            except AttributeError:
                value = None
            self._original_values[field.name] = value
    def __str__(self):
        return f"{self.number} - {self.node.name} - {self.equipment.name} - {self.name}"
    @property
    def changed_fields(self):
        return {field.name for field in self._meta.fields if getattr(self, field.name) != self._original_values[field.name]}
    def save(self, *args, **kwargs):
        creating = self._state.adding
        node_changed = 'node' in self.changed_fields
        super().save(*args, **kwargs)
        if creating or node_changed:
            current_count = Operation.objects.filter(node=self.node).count()
            new_operation_number = current_count + 1
            self.number = f"{self.node.number}N{new_operation_number}O"
            super().save(update_fields=['number'])
    
class Assortment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='assortments', null=True, blank=True, verbose_name='Филиал')
    name = models.CharField(max_length=100, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return self.name

class Model(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='models', verbose_name='Ассортимент', null=True, blank=True)
    operations = models.ManyToManyField(Operation, through='ModelOperation', related_name='models', verbose_name='Операции')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    def __str__(self):
        return self.name
    
class ModelOperation(models.Model):
    model = models.ForeignKey(Model, on_delete=models.CASCADE)
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    class Meta:
        ordering = ['order']

class SizeQuantity(models.Model):
    size = models.CharField(max_length=10, verbose_name='Размер')
    quantity = models.IntegerField(verbose_name='Количество')
    color = models.CharField(verbose_name='Цвет', null=True, blank=True)
    def __str__(self):
        return f"Размер: {self.size}, Количество: {self.quantity}"
    
class ClientOrder(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='client_orders', null=True, blank=True, verbose_name='Филиал')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Дата создания')
    order_number = models.CharField(max_length=100, verbose_name='Номер заказа')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='client_orders', verbose_name='Клиент')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
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
    model = models.ForeignKey(Model, on_delete=models.CASCADE, related_name='orders', verbose_name='Модель')
    colors = models.ManyToManyField(Color, related_name='orders', blank=True, verbose_name='Цвета')
    fabrics = models.ManyToManyField(Fabrics, related_name='orders', blank=True, verbose_name='Ткани')
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
        return f"{self.model}"
    
class Passport(models.Model):
    date = models.DateField(auto_now_add=True, verbose_name='Дата')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='passports', verbose_name='Заказ')
    size_quantities = models.ManyToManyField(SizeQuantity, through='PassportSize', related_name='passports', verbose_name='Размеры и количества')
    rolls = models.ManyToManyField(Roll, through='PassportRoll', related_name='passports', verbose_name='Рулоны')
    is_completed = models.BooleanField(default=False, verbose_name='Паспорт завершен')
    def __str__(self):
        return f"ID {str(self.id)}"
    
class PassportSize(models.Model):
    extra = models.CharField(max_length=5, blank=True, null=True)
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Паспорт')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Размер и количество')
    roll = models.ForeignKey(Roll, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Рулон', blank=True, null=True)
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

class ProductionPiece(models.Model):
    class StageChoices(models.TextChoices):
        NOT_CHECKED = 'NOT_CHECKED', 'Непроверено'
        CHECKED = 'CHECKED', 'Проверено'
        PACKED = 'PACKED', 'Упаковано'
        DEFECT = 'DEFECT', 'Брак'

    class DefectType(models.TextChoices):
        STITCHING = 'STITCHING', 'Ошибка шитья'
        CUTTING = 'CUTTING', 'Ошибка резки'
        FABRIC = 'FABRIC', 'Дефект ткани'
        ASSEMBLY = 'ASSEMBLY', 'Ошибка сборки'
        OTHER = 'OTHER', 'Прочие ошибки'

    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='pieces')
    piece_number = models.IntegerField(verbose_name='Piece Number')
    stage = models.CharField(max_length=20, choices=StageChoices.choices, default=StageChoices.NOT_CHECKED, verbose_name='Stage')
    defect_type = models.CharField(max_length=20, choices=DefectType.choices, null=True, blank=True, verbose_name='Defect Type')
    def __str__(self):
        return f"Passport ID: {self.passport_size.passport.id}, Piece: {self.piece_number}, Stage: {self.stage}"

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
        return f"{self.employee.employee_id} - {self.work.operation.name} - {self.work.passport_size.size_quantity.size} - {self.quantity}"

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

    class Status(models.TextChoices):
        REPORTED = 'REPORTED', 'Сообщено'
        UNRESOLVABLE = 'UNRESOLVABLE', 'Неразрешимо'
        RESOLVED = 'RESOLVED', 'Разрешено'
    
    error_type = models.CharField(max_length=20, choices=ErrorType.choices, verbose_name='Тип ошибки')
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Стоимость')
    responsible_employees = models.ManyToManyField(UserProfile, through='ErrorResponsibility', verbose_name='Ответственные сотрудники')
    piece = models.ForeignKey(ProductionPiece, on_delete=models.CASCADE, related_name='errors', null=True, blank=True, verbose_name='Единица')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED, verbose_name='Статус')
    reported_date = models.DateTimeField(default=timezone.now, verbose_name='Дата сообщения')
    resolved_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата решения')

    def __str__(self):
        return f"{self.error_type}: {self.piece.passport_size.passport.order} - {self.piece.passport_size.passport.id} - {self.piece.passport_size.size_quantity.size} - {self.piece.id}"
    
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
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    def __str__(self):
        return f"{self.position} - {self.salary}"

class SalaryPayment(models.Model):
    fixed_salary = models.ForeignKey(FixedSalary, on_delete=models.CASCADE, related_name='salary_payments', verbose_name='Оклад')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='salary_payments', verbose_name='Сотрудник')
    payment_date = models.DateField(verbose_name='Дата платежа')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')

    def __str__(self):
        return f"{self.employee.user.username} - {self.payment_date} - {self.amount}"
    
    
class PhoneNumberScaner(models.Model):
    mobile_number = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)