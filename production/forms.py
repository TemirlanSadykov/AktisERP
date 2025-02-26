from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.forms import ModelChoiceField
from django.db import transaction
from collections import defaultdict

import json
from .models import *
from django.db.models import F


class UserWithProfileForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    employee_id = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    type = forms.ChoiceField(choices=UserProfile.TYPE_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})


    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
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
            )
        return user

class UserEditForm(forms.ModelForm):
    employee_id = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    type = forms.ChoiceField(
        choices=UserProfile.TYPE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'margin:7px 0px 0px 10px'})
    )
    new_password = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False,
        help_text="Leave blank if you do not want to change the password."
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'employee_id', 'type', 'status']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(UserEditForm, self).__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'userprofile'):
            self.fields['employee_id'].initial = self.instance.userprofile.employee_id
            self.fields['type'].initial = self.instance.userprofile.type
            self.fields['status'].initial = self.instance.userprofile.status

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
            user.userprofile.save()
        return user
    
class CutForm(forms.ModelForm):
    size_choices = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        label="Выберите размеры"  # "Select sizes"
    )
    quantities = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Cut
        exclude = ['order', 'date', 'number', 'size_quantities', 'company']

    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if order:
            qs = order.size_quantities.all()
            unique_sizes = sorted(
                set(q.size for q in qs), 
                key=lambda s: int(s) if s.isdigit() else s
            )
            choices = [(size, size) for size in unique_sizes]
            self.fields['size_choices'].choices = choices

        # When editing an existing cut, pre-populate the fields.
        if self.instance and self.instance.pk:
            init_quantities = {}
            qs = CutSize.objects.filter(cut=self.instance)
            # Group CutSize objects by size.
            groups = defaultdict(list)
            for cs in qs:
                size_val = cs.size_quantity.size
                groups[size_val].append(cs)
            for size_val, records in groups.items():
                # Determine the unique (color, fabrics) combinations for these records.
                unique_combos = set((cs.size_quantity.color, cs.size_quantity.fabrics) for cs in records)
                # If there are duplicates from multiple color/fabric combinations,
                # assume each combination should contribute the same number.
                if unique_combos:
                    # For example, if there are 4 records for size 40 and 2 unique combos,
                    # then the intended quantity is 4 / 2 = 2.
                    count = len(records) // len(unique_combos)
                else:
                    count = len(records)
                init_quantities[size_val] = count
            self.initial['quantities'] = json.dumps(init_quantities)
            self.initial['size_choices'] = list(init_quantities.keys())

    def clean_quantities(self):
        try:
            quantities = json.loads(self.cleaned_data['quantities'])
            return {str(k): int(v) for k, v in quantities.items()}
        except (TypeError, ValueError):
            raise forms.ValidationError("Invalid quantities format.")

    def save_cut_sizes(self, cut, sizes_to_create=None):
        """
        Create CutSize records for the given cut.
        If sizes_to_create is provided, only create for those sizes.
        Otherwise, create for all selected sizes.
        """
        quantities = self.cleaned_data['quantities']
        selected_sizes = self.cleaned_data['size_choices']
        sizes = sizes_to_create if sizes_to_create is not None else selected_sizes
        for size in sizes:
            for size_quantity in cut.order.size_quantities.filter(size=size):
                count = quantities.get(size, 1)
                extras = [""] + [chr(65 + i) for i in range(count - 1)]
                for extra in extras:
                    CutSize.objects.create(
                        cut=cut,
                        size_quantity=size_quantity,
                        extra=extra
                    )

class PassportForm(forms.ModelForm):
    # New field for selecting the unique combination.
    combination = forms.ChoiceField(
        label="Color & Fabric", 
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Passport
        # Include combination in the fields so it renders.
        fields = ['combination', 'layers']
        widgets = {
            'layers': forms.NumberInput(attrs={'type': 'number', 'step': '1', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        cut = kwargs.pop('cut', None)
        super().__init__(*args, **kwargs)
        if cut:
            unique_combinations = set()
            # Loop over all cut_sizes to get unique (color, fabric) combinations.
            for cut_size in cut.cut_sizes.all():
                color = cut_size.size_quantity.color      # Model instance.
                fabric = cut_size.size_quantity.fabrics    # Model instance.
                # Store a tuple: (color_id, fabric_id, color_name, fabric_name)
                unique_combinations.add((color.id, fabric.id, str(color), str(fabric)))
            # Build choices: value "12|5", label "Blue Cotton"
            choices = [
                (f"{color_id}|{fabric_id}", f"{color_name} {fabric_name}")
                for (color_id, fabric_id, color_name, fabric_name) in unique_combinations
            ]
            # Sort choices alphabetically by label.
            choices = sorted(choices, key=lambda x: x[1])
            # Insert a placeholder choice at the beginning.
            choices.insert(0, ("", "------"))
            self.fields['combination'].choices = choices
            # Optionally, you can set the initial value to the placeholder (which will force validation if not changed)
            self.initial['combination'] = ""
        else:
            self.fields['combination'].choices = [("", "------")]

class OperationAssignmentForm(forms.ModelForm):
    employee_id = forms.ModelChoiceField(queryset=UserProfile.objects.filter(type=UserProfile.EMPLOYEE), to_field_name="employee_id", empty_label="Select Employee")
    size = forms.CharField(max_length=50)
    quantity = forms.IntegerField(min_value=1)

    class Meta:
        model = Work
        fields = ['employee_id', 'quantity']

class SizeQuantityForm(forms.ModelForm):
    color = forms.ModelChoiceField(queryset=Color.objects.none(), empty_label="Select Color", widget=forms.Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = SizeQuantity
        fields = ['size', 'quantity', 'color']
        widgets = {
            'size': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Size'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter Quantity'}),
        }

    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if order:
            self.fields['color'].queryset = order.colors.all()

class DateForm(forms.Form):
    date = forms.DateField(label='Дата', widget=forms.TextInput(attrs={'type': 'date','class': 'form-control'}))

class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        label='Начало',
        widget=forms.TextInput(attrs={'type': 'date','class': 'form-control'}),
        required=False 
    )
    end_date = forms.DateField(
        label='Окончание',
        widget=forms.TextInput(attrs={'type': 'date','class': 'form-control'}),
        required=False
    )

class OperationForm(forms.ModelForm):
    class Meta:
        model = Operation
        fields = ['name', 'payment', 'equipment', 'node', 'preferred_completion_time', 'photo']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'payment': forms.NumberInput(attrs={'class': 'form-control'}),
            'equipment': forms.Select(attrs={'class': 'form-control'}),
            'node': forms.Select(attrs={'class': 'form-control'}),
            'preferred_completion_time': forms.DateTimeInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['equipment'].queryset = Equipment.objects.filter(is_archived=False).order_by('name')
        self.fields['node'].queryset = Node.objects.filter(is_archived=False).order_by('name')
        # Prepend an "Add New Equipment" option.
        equipment_choices = list(self.fields['equipment'].choices)
        self.fields['equipment'].choices = [("add_new", "Add New Equipment")] + equipment_choices

        # Prepend an "Add New Node" option.
        node_choices = list(self.fields['node'].choices)
        self.fields['node'].choices = [("add_new", "Add New Node")] + node_choices
    
class AssortmentForm(forms.ModelForm):
    class Meta:
        model = Assortment
        fields = ['name']
        widgets = {
                'name': forms.TextInput(attrs={'class': 'form-control'})
            }

class ModelCustomForm(forms.ModelForm):
    operations_data = forms.CharField(widget=forms.HiddenInput(), required=False)  # Stores JSON order data

    class Meta:
        model = Model
        fields = ['name', 'operations', 'photo']  # Ensure 'operations' is handled by the form
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'operations': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        }
        
    def __init__(self, *args, **kwargs):
        self.assortment_id = kwargs.pop('a_id', None)
        copy_id = kwargs.pop('copy_id', None)
        super(ModelCustomForm, self).__init__(*args, **kwargs)
        queryset = Operation.objects.filter(is_archived=False).select_related('node').order_by('number')
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
        if 'photo' not in self.changed_data:
            model_instance.photo = self.instance.photo

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
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name'}),
        }

class ClientOrderForm(forms.ModelForm):
    class Meta:
        model = ClientOrder
        fields = ['order_number', 'client', 'launch', 'term', 'info']
        widgets = {
            'order_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name'}),
            'client': forms.Select(attrs={'class': 'form-control'}),
            'launch': forms.DateInput(format=('%Y-%m-%d'),
                                      attrs={'type': 'date', 'class': 'form-control'}),
            'term': forms.DateInput(format=('%Y-%m-%d'),
                                    attrs={'type': 'date', 'class': 'form-control'}),
            'info': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Additional Info'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = Client.objects.filter(is_archived=False).order_by('name')
        # Prepend an "Add New Client" option.
        # Note: ModelChoiceField choices is a list of (value, label) tuples.
        orig_choices = list(self.fields['client'].choices)
        self.fields['client'].choices = [("add_new", "Add New Client")] + orig_choices

    def clean_term(self):
        term = self.cleaned_data.get('term')
        launch = self.cleaned_data.get('launch')
        today = timezone.localdate()
        if term < launch:
            raise ValidationError("The term date cannot be earlier than today or the launch date.")
        return term

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['model', 'colors', 'fabrics', 'quantity']
        widgets = {
            'model': forms.Select(attrs={'class': 'form-control'}),
            'colors': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'fabrics': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(OrderForm, self).__init__(*args, **kwargs)
        self.fields['model'].queryset = Model.objects.filter(is_archived=False).order_by('name')
        self.fields['colors'].queryset = Color.objects.filter(is_archived=False).order_by('name')
        self.fields['fabrics'].queryset = Fabrics.objects.filter(is_archived=False).order_by('name')

        # Make certain fields optional in the form
        self.fields['model'].required = False
        self.fields['colors'].required = False
        self.fields['fabrics'].required = False

class NodeForm(forms.ModelForm):
    class Meta:
        model = Node
        fields = ['name']
        widgets = {
                'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter name'}),
            }
    

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter equipment name'}),
        }

class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter color name'}),
        }

class FabricsForm(forms.ModelForm):
    class Meta:
        model = Fabrics
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter fabrics name'}),
        }

class SizeQuantityChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.size
        
class UploadFileForm(forms.Form):
    excel_file = forms.FileField(
        label='Select an Excel file',
        help_text='Maximum size allowed is 10MB',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx'])]
    )