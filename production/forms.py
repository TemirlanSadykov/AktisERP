from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.forms import ModelChoiceField
from django.db import transaction
import json
from .models import *


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['name']

class UserWithProfileForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    employee_id = forms.CharField(max_length=100, required=True)
    type = forms.ChoiceField(choices=UserProfile.TYPE_CHOICES, required=True)
    status = forms.BooleanField(required=False, initial=False)
    station = forms.ChoiceField(choices=UserProfile.STATION_CHOICES, required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                employee_id=self.cleaned_data['employee_id'],
                type=self.cleaned_data['type'],
                status=self.cleaned_data['status'],
                station=self.cleaned_data['station'],
            )
        return user

class UserEditForm(forms.ModelForm):
    employee_id = forms.CharField(max_length=100, required=True)
    type = forms.ChoiceField(choices=UserProfile.TYPE_CHOICES, required=True)
    status = forms.BooleanField(required=False)
    station = forms.ChoiceField(choices=UserProfile.STATION_CHOICES, required=True)
    branch = forms.ModelChoiceField(queryset=Branch.objects.all(), required=True, label='Branch')
    new_password = forms.CharField(label='New Password', widget=forms.PasswordInput, required=False, help_text="Leave blank if you do not want to change the password.")

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'employee_id', 'type', 'status', 'station', 'branch']

    def __init__(self, *args, **kwargs):
        super(UserEditForm, self).__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'userprofile'):
            self.fields['employee_id'].initial = self.instance.userprofile.employee_id
            self.fields['type'].initial = self.instance.userprofile.type
            self.fields['status'].initial = self.instance.userprofile.status
            self.fields['station'].initial = self.instance.userprofile.station
            self.fields['branch'].initial = self.instance.userprofile.branch

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Set new password if provided
        new_password = self.cleaned_data.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        if commit:
            user.save()
            user.userprofile.employee_id = self.cleaned_data['employee_id']
            user.userprofile.type = self.cleaned_data['type']
            user.userprofile.status = self.cleaned_data['status']
            user.userprofile.station = self.cleaned_data['station']
            user.userprofile.branch = self.cleaned_data['branch']
            user.userprofile.save()
        return user
    
class PassportForm(forms.ModelForm):
    class Meta:
        model = Passport
        exclude = ['size_quantities', 'rolls', 'is_completed']

class OperationAssignmentForm(forms.ModelForm):
    employee_id = forms.ModelChoiceField(queryset=UserProfile.objects.filter(type=UserProfile.EMPLOYEE), to_field_name="employee_id", empty_label="Select Employee")
    size = forms.CharField(max_length=50)
    quantity = forms.IntegerField(min_value=1)

    class Meta:
        model = Work
        fields = ['employee_id', 'quantity']

class SizeQuantityForm(forms.ModelForm):
    class Meta:
        model = SizeQuantity
        fields = ['size', 'quantity']

class DateForm(forms.Form):
    date = forms.DateField(label='Дата', widget=forms.TextInput(attrs={'type': 'date'}))

class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        label='Начало',
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=False 
    )
    end_date = forms.DateField(
        label='Окончание',
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=False
    )

class SalaryListForm(forms.Form):
    start_date = forms.DateField(
        label='Начало',
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=False 
    )
    end_date = forms.DateField(
        label='Окончание',
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=False
    )
    salary_type = forms.ChoiceField(
        label='Тип зарплаты',
        choices=(('non_fixed', 'По факту'), ('fixed', 'Оклад')),
        required=False
    )



class PassportRollForm(forms.ModelForm):
    class Meta:
        model = PassportRoll
        fields = ['roll', 'meters']
        widgets = {
            'roll': forms.Select(),
            'meters': forms.NumberInput(attrs={'type': 'number', 'step': '0.01'})
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['roll'].queryset = Roll.objects.all()

class SizeQuantityChoiceField(ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.size

class PassportSizeForm(forms.ModelForm):
    size_quantity = SizeQuantityChoiceField(queryset=None, empty_label="---------") 

    class Meta:
        model = PassportSize
        fields = ['size_quantity', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'type': 'number', 'min': '0'})
        }

    def __init__(self, *args, **kwargs):
        passport_id = kwargs.pop('passport_id', None)
        super().__init__(*args, **kwargs)
        
        if passport_id:
            passport = Passport.objects.get(pk=passport_id)
            self.fields['size_quantity'].queryset = passport.order.size_quantities.all()

class OperationForm(forms.ModelForm):
    class Meta:
        model = Operation
        fields = ['name', 'payment', 'equipment', 'node', 'preferred_completion_time', 'photo', 'employee']

class RollForm(forms.ModelForm):
    class Meta:
        model = Roll
        fields = ['name', 'color', 'fabrics', 'meters']

class AssortmentForm(forms.ModelForm):
    class Meta:
        model = Assortment
        fields = ['name']

class ModelCustomForm(forms.ModelForm):
    operations_data = forms.CharField(widget=forms.HiddenInput(), required=False)  # Stores JSON order data

    class Meta:
        model = Model
        fields = ['name', 'operations']  # Ensure 'operations' is handled by the form

    def __init__(self, *args, **kwargs):
        self.assortment_id = kwargs.pop('a_id', None)
        copy_id = kwargs.pop('copy_id', None)
        super(ModelCustomForm, self).__init__(*args, **kwargs)
        queryset = Operation.objects.all().select_related('node').order_by('number')
        self.fields['operations'] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=forms.CheckboxSelectMultiple,
            required=False
        )
        # Set initial operations based on instance or copy_id
        if copy_id:
            original_model = Model.objects.get(pk=copy_id)
            self.fields['operations'].initial = [op.pk for op in original_model.operations.all()]
        elif self.instance.pk:
            self.fields['operations'].initial = [op.pk for op in self.instance.operations.all()]

    def save(self, commit=True):
        model_instance = super().save(commit=False)
        if self.assortment_id:
            model_instance.assortment = Assortment.objects.get(pk=self.assortment_id)
        
        if commit:
            model_instance.save()
            self.save_m2m()
            if 'operations_data' in self.cleaned_data and self.cleaned_data['operations_data']:
                operations_data = json.loads(self.cleaned_data['operations_data'])
                self.update_operations_order(model_instance, operations_data)
        return model_instance

    def update_operations_order(self, model_instance, operations_data):
        with transaction.atomic():
            # Clear existing operations to reset them with new order
            ModelOperation.objects.filter(model=model_instance).delete()

            # Re-add operations with the correct order
            for operation_info in operations_data:
                operation_id = operation_info['operation_id']
                order = operation_info['order']
                operation = Operation.objects.get(pk=operation_id)
                ModelOperation.objects.create(
                    model=model_instance,
                    operation=operation,
                    order=order
                )

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'contact_info']

class ClientOrderForm(forms.ModelForm):
    class Meta:
        model = ClientOrder
        fields = ['order_number', 'client', 'term', 'status']
        widgets = {
            'term': forms.DateInput(format=('%Y-%m-%d'), attrs={'type': 'date'}),
        }

    def clean_term(self):
        term = self.cleaned_data.get('term')
        today = timezone.localdate()
        if term < today:
            raise ValidationError("The term date cannot be earlier than today.")
        return term

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['name', 'model', 'assortment', 'color', 'fabrics', 'status', 'quantity', 'completed_quantity', 'payment']
        widgets = {
            'status': forms.Select(choices=Order.TYPE_CHOICES), 
        }

    def __init__(self, *args, **kwargs):
        super(OrderForm, self).__init__(*args, **kwargs)
        self.fields['model'].queryset = Model.objects.all()
        self.fields['assortment'].queryset = Assortment.objects.all()

        # Make certain fields optional in the form
        self.fields['model'].required = False
        self.fields['assortment'].required = False

class OrderFormTechnologist(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['model', 'assortment']

    def __init__(self, *args, **kwargs):
        super(OrderFormTechnologist, self).__init__(*args, **kwargs)
        self.fields['model'].queryset = Model.objects.all()
        self.fields['assortment'].queryset = Assortment.objects.all()

class NodeForm(forms.ModelForm):
    class Meta:
        model = Node
        fields = ['name', 'number', 'is_common', 'type']

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name']

class SizeQuantityChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.size

class ErrorForm(forms.ModelForm):
    size_quantity = SizeQuantityChoiceField(queryset=SizeQuantity.objects.none())

    class Meta:
        model = Error
        fields = ['passport', 'size_quantity', 'quantity', 'defect_type']  
    
    def __init__(self, *args, **kwargs):
        order_pk = kwargs.pop('order_pk', None)
        self.error_type = kwargs.pop('error_type', None)
        super().__init__(*args, **kwargs)

        if order_pk:
            order = Order.objects.get(pk=order_pk)
            self.fields['passport'].queryset = Passport.objects.filter(order=order)
            self.fields['size_quantity'].queryset = order.size_quantities.all()

        if self.error_type != 'DEFECT':
            if 'defect_type' in self.fields:
                del self.fields['defect_type']
        else:
            self.fields['defect_type'].required = True

    def save(self, commit=True):
        self.instance.error_type = self.error_type
        return super().save(commit=commit)

class FixedSalaryForm(forms.ModelForm):
    employees = forms.ModelMultipleChoiceField(
        queryset=UserProfile.objects.all().order_by('employee_id'),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = FixedSalary
        fields = ['position', 'salary', 'employees']
        
class UploadFileForm(forms.Form):
    excel_file = forms.FileField(
        label='Select an Excel file',
        help_text='Maximum size allowed is 10MB',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx'])]
    )

class ErrorResponsibilityForm(forms.ModelForm):
    class Meta:
        model = ErrorResponsibility
        fields = ['employee', 'percentage']
        widgets = {
            'employee': forms.Select(),
            'percentage': forms.NumberInput(attrs={'type': 'number', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = UserProfile.objects.all().order_by('employee_id')
