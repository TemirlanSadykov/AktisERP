from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    path('', user_redirect, name='user_redirect'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('employee/clock-in-out/', clock_in_out, name='clock_in_out'),
    
    path('employee/', employee_page, name='employee_page'),
    path('technologist/', technologist_page, name='technologist_page'),
    path('admin/', admin_page, name='admin_page'),
    path('cutter/', cutter_page, name='cutter_page'),
    path('qc/', qc_page, name='qc_page'),

    path('admin/branches/', BranchListView.as_view(), name='branch_list'),
    path('admin/branches/create/', BranchCreateView.as_view(), name='branch_create'),
    path('admin/branches/<int:pk>/', BranchDetailView.as_view(), name='branch_detail'),
    path('admin/branches/<int:pk>/edit/', BranchUpdateView.as_view(), name='branch_edit'),
    path('admin/branches/<int:pk>/delete/', BranchDeleteView.as_view(), name='branch_delete'),
    path('admin/branches/switch/', branch_switch, name='branch_switch'),

    # Admin management of employees
    path('admin/employees/', EmployeeListView.as_view(), name='employee_list'),
    path('admin/employees/create/', EmployeeCreateView.as_view(), name='employee_create'),
    path('admin/employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee_detail'),
    path('admin/employees/<int:pk>/edit/', employee_edit, name='employee_edit'),
    path('admin/employees/<int:pk>/delete/', EmployeeDeleteView.as_view(), name='employee_delete'),

    path('admin/passports/<int:pk>/', passport_detail_admin, name='passport_detail_admin'),

    path('admin/salaries/', salary_list, name='salary_list'),
    path('admin/salaries/<int:pk>/', salary_detail, name='salary_detail'),
    path('admin/salaries/export-salaries/', export_salaries_to_excel, name='export_salaries'),

    path('admin/attendances/', attendance_list, name='attendance_list'),

    path('admin/orders/', OrderListView.as_view(), name='order_list'),
    path('admin/orders/create/', OrderCreateView.as_view(), name='order_create'),
    path('admin/orders/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('admin/orders/<int:pk>/edit/', OrderUpdateView.as_view(), name='order_edit'),
    path('admin/orders/<int:pk>/delete/', OrderDeleteView.as_view(), name='order_delete'),
    path('admin/orders/<int:order_id>/create_size_quantity/', SizeQuantityCreateView.as_view(), name='create_size_quantity'),
    path('admin/orders/edit-size-quantity/<int:sq_id>/', edit_size_quantity, name='edit_size_quantity'),
    path('admin/orders/delete-size-quantity/<int:sq_id>/', delete_size_quantity, name='delete_size_quantity'),

    path('admin/clients/', ClientListView.as_view(), name='client_list'),
    path('admin/clients/create/', ClientCreateView.as_view(), name='client_create'),
    path('admin/clients/<int:pk>/', ClientDetailView.as_view(), name='client_detail'),
    path('admin/clients/<int:pk>/edit/', ClientUpdateView.as_view(), name='client_edit'),
    path('admin/clients/<int:pk>/delete/', ClientDeleteView.as_view(), name='client_delete'),

    path('technologist/orders/', OrderListTechnologistView.as_view(), name='order_list_technologist'),
    path('technologist/orders/<int:pk>/', OrderDetailTechnologistView.as_view(), name='order_detail_technologist'),
    path('technologist/passports/<int:passport_id>/assign_operations/', assign_operations, name='assign_operations'),
    path('technologist/passports/update_work/', update_work, name='update_work'),
    path('technologist/passports/update_work_success/', update_work_success, name='update_work_success'),
    path('technologist/passports/<int:passport_id>/complete/', complete_passport, name='complete_passport'),
    path('technologist/passports/reassign-work/', reassign_work, name='reassign_work'),
    path('technologist/passports/api/reassigned_works/<int:assigned_work_id>/', get_reassigned_works, name='get_reassigned_works'),
    path('technologist/passports/reassign-work/complete/', complete_reassigned_work, name='complete_reassigned_work'),

    path('technologist/operations/', OperationListView.as_view(), name='operation_list'),
    path('technologist/operations/create/', OperationCreateView.as_view(), name='operation_create'),
    path('technologist/operations/<int:pk>/', OperationDetailView.as_view(), name='operation_detail'),
    path('technologist/operations/<int:pk>/edit/', OperationUpdateView.as_view(), name='operation_edit'),
    path('technologist/operations/<int:pk>/delete/', OperationDeleteView.as_view(), name='operation_delete'),
    path('technologist/operations/<int:operation_id>/calculate_average/', calculate_average_completion_time, name='calculate_average'),

    path('technologist/rolls/', RollListView.as_view(), name='roll_list'),
    path('technologist/rolls/create/', RollCreateView.as_view(), name='roll_create'),
    path('technologist/rolls/<int:pk>/', RollDetailView.as_view(), name='roll_detail'),
    path('technologist/rolls/<int:pk>/edit/', RollUpdateView.as_view(), name='roll_edit'),
    path('technologist/rolls/<int:pk>/delete/', RollDeleteView.as_view(), name='roll_delete'),

    path('technologist/assortments/', AssortmentListView.as_view(), name='assortment_list'),
    path('technologist/assortments/create/', AssortmentCreateView.as_view(), name='assortment_create'),
    path('technologist/assortments/<int:pk>/', AssortmentDetailView.as_view(), name='assortment_detail'),
    path('technologist/assortments/<int:pk>/edit/', AssortmentUpdateView.as_view(), name='assortment_edit'),
    path('technologist/assortments/<int:pk>/delete/', AssortmentDeleteView.as_view(), name='assortment_delete'),

    path('technologist/models/', ModelListView.as_view(), name='model_list'),
    path('technologist/models/create/', ModelCreateView.as_view(), name='model_create'),
    path('technologist/models/<int:pk>/', ModelDetailView.as_view(), name='model_detail'),
    path('technologist/models/<int:pk>/edit/', ModelUpdateView.as_view(), name='model_edit'),
    path('technologist/models/<int:pk>/delete/', ModelDeleteView.as_view(), name='model_delete'),

    path('employee/works/done/', done_works_list, name='done_works_list'),
    path('employee/works/pending/', pending_works_list, name='pending_works_list'),
    path('employee/works/reassigned/', reassigned_works_list, name='reassigned_works_list'),
    path('employee/works/<int:assigned_work_id>/start/', start_work, name='start_work'),
    path('employee/works/<int:assigned_work_id>/finish/', finish_work, name='finish_work'),

    path('cutter/orders/', OrderListCutterView.as_view(), name='order_list_cutter'),
    path('cutter/orders/<int:pk>/', OrderDetailCutterView.as_view(), name='order_detail_cutter'),
    path('cutter/orders/<int:pk>/passport', PassportDetailView.as_view(), name='passport_detail'),
    path('cutter/orders/<int:pk>/passport/create', PassportCreateView.as_view(), name='passport_create'),
    path('cutter/orders/passport/<int:pk>/delete/', PassportDeleteView.as_view(), name='passport_delete'),
    path('cutter/orders/passport/<int:passport_id>/create_passport_roll/', PassportRollCreateView.as_view(), name='create_passport_roll'),
    path('cutter/orders/passport/<int:passport_id>/create_passport_size/', PassportSizeCreateView.as_view(), name='create_passport_size'),
    # path('cutter/orders/passport/edit-size-quantity/<int:sq_id>/', edit_size_quantity_passport, name='edit_size_quantity_passport'),
    # path('cutter/orders/passport/delete-size-quantity/<int:sq_id>/', delete_size_quantity_passport, name='delete_size_quantity_passport'),
]
