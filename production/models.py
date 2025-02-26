import datetime
import threading

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from datetime import date

# ------------------------------------------------------------------
# Company Model (Name field only for now)
# ------------------------------------------------------------------
class Company(models.Model):
    name = models.CharField(max_length=100, verbose_name="Company Name")

    def __str__(self):
        return self.name

# ------------------------------------------------------------------
# Thread-local Storage for the Current Company Context
# ------------------------------------------------------------------
_local = threading.local()

def set_current_company(company):
    """Call this (e.g., in middleware) to set the company context for the current thread."""
    _local.company = company

def get_current_company():
    return getattr(_local, 'company', None)

# ------------------------------------------------------------------
# Custom QuerySet and Manager to Auto-Filter by Company
# ------------------------------------------------------------------
class CompanyAwareQuerySet(models.QuerySet):
    def _apply_company_filter(self):
        # Prevent recursive application of the company filter.
        if getattr(self, '_company_filter_applied', False):
            return self
        current_company = get_current_company()
        if current_company is not None:
            qs = self.filter(company=current_company)
            qs._company_filter_applied = True
            return qs
        return self

    def all(self):
        return super().all()._apply_company_filter()

    def filter(self, *args, **kwargs):
        # Avoid applying the filter again if 'company' is explicitly provided.
        if 'company' in kwargs:
            return super().filter(*args, **kwargs)
        qs = super().filter(*args, **kwargs)
        return qs._apply_company_filter()


class CompanyAwareManager(models.Manager):
    def get_queryset(self):
        return CompanyAwareQuerySet(self.model, using=self._db)
    
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    modified_at = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        abstract = True

class CompanyAwareModel(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    objects = CompanyAwareManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Automatically assign the company if it's not already set.
        if not self.pk and not self.company_id:
            current_company = get_current_company()
            if current_company:
                self.company = current_company
        super().save(*args, **kwargs)

class UserProfile(CompanyAwareModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    employee_id = models.CharField(max_length=100, verbose_name='ID сотрудника')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['employee_id', 'company'], name='unique_employee_id_per_company')
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
    status = models.BooleanField(default=True, verbose_name='Статус', null=True, blank=True)
    
    
    def __str__(self):
        return f"{self.employee_id} - {self.user.first_name}"

class Client(CompanyAwareModel):
    name = models.CharField(max_length=100, verbose_name='Имя')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    
    
    
    def __str__(self):
        return self.name

class Color(CompanyAwareModel):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    
    
    def __str__(self):
        return self.name
    
class Fabrics(CompanyAwareModel):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    
    
    def __str__(self):
        return self.name

class Equipment(CompanyAwareModel):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    
    
    def __str__(self):
        return self.name
    
class Node(CompanyAwareModel):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')
    
    
    
    def __str__(self):
        return self.name
    
class Operation(CompanyAwareModel):
    name = models.CharField(max_length=300, verbose_name='Название')
    number = models.CharField(max_length=100, null=True, blank=True, verbose_name='№ПП')
    payment = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Оплата')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='operations', verbose_name='Оборудование')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='operations', verbose_name='Узел')
    preferred_completion_time = models.IntegerField(verbose_name='Предпочтительное время выполнения')
    average_completion_time = models.IntegerField(null=True, verbose_name='Среднее время выполнения')
    photo = models.ImageField(upload_to='operation_photos/', null=True, blank=True, verbose_name='Фото')
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
        return {
            field.name
            for field in self._meta.fields
            if field.name != 'company' and getattr(self, field.name) != self._original_values[field.name]
        }
    def save(self, *args, **kwargs):
        creating = self._state.adding
        node_changed = 'node' in self.changed_fields
        super().save(*args, **kwargs)
        if creating or node_changed:
            current_count = Operation.objects.filter(node=self.node).count()
            new_operation_number = current_count + 1
            self.number = f"{self.node.id}N{new_operation_number}O"
            super().save(update_fields=['number'])
    
class Assortment(CompanyAwareModel):
    name = models.CharField(max_length=100, verbose_name='Название')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    
    
    def __str__(self):
        return self.name

class Model(CompanyAwareModel):
    name = models.CharField(max_length=100, verbose_name='Название')
    assortment = models.ForeignKey(Assortment, on_delete=models.CASCADE, related_name='models', verbose_name='Ассортимент', null=True, blank=True)
    operations = models.ManyToManyField(Operation, through='ModelOperation', related_name='models', verbose_name='Операции')
    photo = models.ImageField(upload_to='model_photos/', null=True, blank=True, verbose_name='Фото')
    is_archived = models.BooleanField(default=False, verbose_name='Is Archived')

    
    
    def __str__(self):
        return self.name
    
class ModelOperation(CompanyAwareModel):
    model = models.ForeignKey(Model, on_delete=models.CASCADE)
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    

    class Meta:
        ordering = ['order']

class SizeQuantity(CompanyAwareModel):
    size = models.CharField(max_length=10, verbose_name='Размер', null=True, blank=True)
    quantity = models.IntegerField(verbose_name='Количество', null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.CASCADE, null=True, blank=True, verbose_name='Цвет')
    fabrics = models.ForeignKey(Fabrics, on_delete=models.CASCADE, null=True, blank=True, verbose_name='Ткань')

    
    
    def __str__(self):
        return f"{self.color} {self.fabrics} {self.size} ({self.quantity})"
    
class ClientOrder(CompanyAwareModel):
    order_number = models.CharField(max_length=100, verbose_name='Название')
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
    def default_launch():
        return timezone.now()
    launch = models.DateField(default=default_launch, verbose_name='Начало выполнения', blank=True, null=True)
    term = models.DateField(default=default_term, verbose_name='Срок выполнения')
    info = models.TextField(blank=True, null=True, verbose_name='Additional Information')
    
    
    def __str__(self):
        return self.order_number

class Order(CompanyAwareModel):
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
    
class Cut(CompanyAwareModel):
    number = models.IntegerField(verbose_name='Номер', editable=False)
    width = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Ширина', blank=True, null=True)
    length = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Длина', blank=True, null=True)
    consumption = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Расход', blank=True, null=True)
    date = models.DateField(auto_now_add=True, verbose_name='Дата')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='cuts', verbose_name='Заказ')
    size_quantities = models.ManyToManyField(SizeQuantity, through='CutSize', related_name='cuts', verbose_name='Размеры и количества')

    
    
    def __str__(self):
        return f"Cut {self.number} for Order {self.order}"

    def save(self, *args, **kwargs):
        if not self.pk:
            current_year = date.today().year
            latest_cut = Cut.objects.filter(date__year=current_year).order_by('-number').first()
            if latest_cut:
                self.number = latest_cut.number + 1
            else:
                self.number = 1

        super().save(*args, **kwargs)
        
class CutSize(CompanyAwareModel):
    extra = models.CharField(max_length=5, blank=True, null=True, verbose_name='Дополнительно')
    cut = models.ForeignKey(Cut, on_delete=models.CASCADE, related_name='cut_sizes', verbose_name='Резка')
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='cut_sizes', verbose_name='Размер и количество')
    
    
    def __str__(self):
        return f"{self.size_quantity.size} - {self.extra}"
class Passport(CompanyAwareModel):
    cut = models.ForeignKey(Cut, on_delete=models.CASCADE, blank=True, null=True, related_name='passports', verbose_name='Крой')
    number = models.IntegerField(verbose_name='Номер', null=True, blank=True)
    size_quantities = models.ManyToManyField(SizeQuantity, through='PassportSize', related_name='passports', verbose_name='Размеры и количества')
    layers = models.DecimalField(max_digits=10, decimal_places=0, verbose_name='Слои', null=True, blank=True)
    meters = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Метры', null=True, blank=True)
    is_completed = models.BooleanField(default=False, verbose_name='Паспорт завершен')
    
    
    def __str__(self):
        return f"{self.cut.number}-{self.number}"

    @property
    def quantity(self):
        if self.layers:
            return self.layers * self.size_quantities.count()
        return 0
    
class PassportSize(CompanyAwareModel):
    passport = models.ForeignKey(Passport, on_delete=models.CASCADE, blank=True, null=True, related_name='passport_sizes', verbose_name='Паспорт')
    extra = models.CharField(max_length=5, blank=True, null=True)
    size_quantity = models.ForeignKey(SizeQuantity, on_delete=models.CASCADE, related_name='passport_sizes', verbose_name='Размер и количество')
    quantity = models.IntegerField(verbose_name='Количество')
    
    
    def __str__(self):
        return f"{self.size_quantity.size} - {self.quantity} шт"

class ProductionPiece(CompanyAwareModel):
    class StageChoices(models.TextChoices):
        NOT_CHECKED = 'NOT_CHECKED', 'Непроверено'
        CHECKED = 'CHECKED', 'Проверено'
        PACKED = 'PACKED', 'Упаковано'
        DEFECT = 'DEFECT', 'Брак'
    
    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='pieces')
    piece_number = models.IntegerField(verbose_name='Piece Number')
    stage = models.CharField(max_length=20, choices=StageChoices.choices, default=StageChoices.NOT_CHECKED, verbose_name='Stage')
    
    
    def __str__(self):
        return f"Passport ID: {self.passport_size.passport.id}, Piece: {self.piece_number}, Stage: {self.stage}"

class Work(CompanyAwareModel):
    employees = models.ManyToManyField(UserProfile, through='AssignedWork', verbose_name='Сотрудники')
    operation = models.ForeignKey(Operation, on_delete=models.CASCADE, related_name='works', verbose_name='Операция')
    passport_size = models.ForeignKey(PassportSize, on_delete=models.CASCADE, related_name='works', null=True, verbose_name='Размер и количество')
    
    
    def __str__(self):
        if self.passport_size:
            return f"{self.operation.name} - {self.passport_size.size_quantity.size}"
        else:
            return f"{self.operation.name} - Нет размера"
    
class AssignedWork(CompanyAwareModel):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='assigned_works', verbose_name='Работа')
    employee = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_tasks', verbose_name='Сотрудник')
    quantity = models.IntegerField(verbose_name='Количество')
    start_time = models.DateTimeField(null=True, blank=True, verbose_name='Время начала')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='Время окончания')
    is_success = models.BooleanField(default=False, verbose_name='Завершено успешно')
    
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.work.operation.name} - {self.work.passport_size.size_quantity.size} - {self.quantity}"