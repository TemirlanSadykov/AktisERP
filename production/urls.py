from django.contrib.auth import views as auth_views
from django.urls import path
from .views import *

urlpatterns = [
    path('', user_redirect, name='user_redirect'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    path('admin/', admin_page, name='admin_page'),

    path('technologist/', ClientOrderListView.as_view(), name='technologist_page'),

    path('cutter/', ClientOrderListCutterView.as_view(), name='cutter_page'),

    path('qc/', ClientOrderListQcView.as_view(), name='qc_page'),

    path('packer/', ClientOrderListPackerView.as_view(), name='packer_page'),

    path('keeper/', ColorFabricListView.as_view(), name='keeper_page'),

    path('employee/', employee_page, name='employee_page'),

    # Admin management of employees
    path('admin/employees/', EmployeeListView.as_view(), name='employee_list'),
    path('admin/employees/create/', EmployeeCreateView.as_view(), name='employee_create'),
    path('admin/employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee_detail'),
    path('admin/employees/<int:pk>/edit/', employee_edit, name='employee_edit'),
    path('admin/employees/<int:pk>/delete/', EmployeeDeleteView.as_view(), name='employee_delete'),
    path('admin/employees/<int:pk>/archive/', EmployeeArchiveView.as_view(), name='employee_archive'),
    path('admin/employees/<int:pk>/unarchive/', EmployeeUnArchiveView.as_view(), name='employee_unarchive'),
    path('admin/employees/archived/', ArchivedEmployeeListView.as_view(), name='archived_employee_list'),
    path('admin/employees/upload_employees/', employee_upload, name='employee_upload'),

    path('technologist/employees/', EmployeeListTechnologistView.as_view(), name='employee_list_technologist'),
    path('technologist/employees/create/', EmployeeCreateTechnologistView.as_view(), name='employee_create_technologist'),
    path('technologist/employees/<int:pk>/', EmployeeDetailTechnologistView.as_view(), name='employee_detail_technologist'),
    path('technologist/employees/<int:pk>/edit/', employee_edit_technologist, name='employee_edit_technologist'),
    path('technologist/employees/<int:pk>/delete/', EmployeeDeleteTechnologistView.as_view(), name='employee_delete_technologist'),
    path('technologist/employees/<int:pk>/archive/', EmployeeArchiveTechnologistView.as_view(), name='employee_archive_technologist'),
    path('technologist/employees/<int:pk>/unarchive/', EmployeeUnArchiveTechnologistView.as_view(), name='employee_unarchive_technologist'),
    path('technologist/employees/archived/', ArchivedEmployeeListTechnologistView.as_view(), name='archived_employee_list_technologist'),
    path('technologist/employees/upload_employees/', employee_upload_technologist, name='employee_upload_technologist'),

    path('sub_tech/client/orders/', ClientOrderListSubView.as_view(), name='client_order_list_sub'),
    path('sub_tech/client/orders/<int:pk>/', ClientOrderDetailSubView.as_view(), name='client_order_detail_sub'),
    path('sub_tech/client/orders/order/<int:pk>/', OrderDetailSubView.as_view(), name='order_detail_sub'),
    path('sub_tech/client/orders/order/<int:cut_id>/assign_operations_by_cut/', assign_operations_by_cut_sub, name='assign_operations_by_cut_sub'),
    path('sub_tech/passports/update_work/', update_work_sub, name='update_work_sub'),
    path('sub_tech/passports/update_passport_quantity/', update_passport_quantity_sub, name='update_passport_quantity_sub'),

    path('technologist/client/orders/', ClientOrderListView.as_view(), name='client_order_list'),
    path('technologist/client/orders/create/', ClientOrderCreateView.as_view(), name='client_order_create'),
    path('technologist/client/orders/<int:pk>/', ClientOrderDetailView.as_view(), name='client_order_detail'),
    path('technologist/client/orders/<int:pk>/edit/', ClientOrderUpdateView.as_view(), name='client_order_edit'),
    path('technologist/client/orders/<int:pk>/delete/', ClientOrderDeleteView.as_view(), name='client_order_delete'),
    path('technologist/client/orders/archived/', ArchivedClientOrderListView.as_view(), name='archived_client_order_list'),
    path('technologist/client/orders/<int:pk>/archive/', ClientOrderArchiveView.as_view(), name='client_order_archive'),
    path('technologist/client/orders/<int:pk>/unarchive/', ClientOrderUnArchiveView.as_view(), name='client_order_unarchive'),
    path('technologist/client/orders/<int:pk>/complete/', client_order_complete, name='client_order_complete'),

    path('cutter/client/orders/', ClientOrderListCutterView.as_view(), name='client_order_list_cutter'),
    path('cutter/client/orders/<int:pk>/', ClientOrderDetailCutterView.as_view(), name='client_order_detail_cutter'),

    path('qc/client/orders/', ClientOrderListQcView.as_view(), name='client_order_list_qc'),
    path('qc/client/orders/<int:pk>/', ClientOrderDetailQcView.as_view(), name='client_order_detail_qc'),

    path('accountant/client/orders/', ClientOrderListAccountantView.as_view(), name='client_order_list_accountant'),
    path('accountant/client/orders/<int:pk>/', ClientOrderDetailAccountantView.as_view(), name='client_order_detail_accountant'),

    path('packer/client/orders/', ClientOrderListPackerView.as_view(), name='client_order_list_packer'),
    path('packer/client/orders/<int:pk>/', ClientOrderDetailPackerView.as_view(), name='client_order_detail_packer'),

    path('keeper/client/orders/', ClientOrderListKeeperView.as_view(), name='client_order_list_keeper'),
    path('keeper/client/orders/<int:pk>/', ClientOrderDetailKeeperView.as_view(), name='client_order_detail_keeper'),
    path('keeper/client/orders/order/<int:pk>/', OrderDetailKeeperView.as_view(), name='order_detail_keeper'),
    path('keeper/client/orders/order/ship/', shipment_complete, name='shipment_complete'),

    path('admin/calendar/', OrderCalendarView.as_view(), name='order_calendar'),
    path('admin/calendar/events/', OrderCalendarEventsView.as_view(), name='order_calendar_events'),

    path('technologist/clients/', ClientListView.as_view(), name='client_list'),
    path('technologist/clients/create/', ClientCreateView.as_view(), name='client_create'),
    path('technologist/clients/<int:pk>/', ClientDetailView.as_view(), name='client_detail'),
    path('technologist/clients/<int:pk>/edit/', ClientUpdateView.as_view(), name='client_edit'),
    path('technologist/clients/<int:pk>/delete/', ClientDeleteView.as_view(), name='client_delete'),
    path('technologist/clients/archived/', ArchivedClientListView.as_view(), name='archived_clients_list'),
    path('technologist/clients/<int:pk>/archive/', ClientArchiveView.as_view(), name='client_archive'),
    path('technologist/clients/<int:pk>/unarchive/', ClientUnArchiveView.as_view(), name='client_unarchive'),
    
    path('technologist/client/orders/order/create/<int:client_order_pk>', OrderCreateView.as_view(), name='order_create'),
    path('technologist/client/orders/order/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('technologist/client/orders/order/<int:pk>/edit/', OrderUpdateView.as_view(), name='order_edit'),
    path('technologist/client/orders/order/<int:pk>/delete/', OrderDeleteView.as_view(), name='order_delete'),
    path('technologist/passports/<int:passport_id>/assign_operations/', assign_operations, name='assign_operations'),
    path('technologist/client/orders/order/<int:cut_id>/assign_operations_by_cut/', assign_operations_by_cut, name='assign_operations_by_cut'),
    path('technologist/passports/update_work/', update_work, name='update_work'),
    path('technologist/passports/update_work_success/', update_work_success, name='update_work_success'),
    path('technologist/passports/update_passport_quantity/', update_passport_quantity, name='update_passport_quantity'),
    path('technologist/client/orders/order/<int:pk>/bom/create/', bom_create, name='bom_create'),
    path('technologist/client/orders/order/<int:pk>/bom/detail/', OrderBomView.as_view(), name='order_bom'),

    path('technologist/operations/', OperationListView.as_view(), name='operation_list'),
    path('technologist/operations/create/', OperationCreateView.as_view(), name='operation_create'),
    path('technologist/operations/<int:pk>/', OperationDetailView.as_view(), name='operation_detail'),
    path('technologist/operations/<int:pk>/edit/', OperationUpdateView.as_view(), name='operation_edit'),
    path('technologist/operations/archived/', ArchivedOperationListView.as_view(), name='archived_operation_list'),
    path('technologist/operations/<int:pk>/archive/', OperationArchiveView.as_view(), name='operation_archive'),
    path('technologist/operations/<int:pk>/unarchive/', OperationUnArchiveView.as_view(), name='operation_unarchive'),
    path('technologist/operations/<int:pk>/delete/', OperationDeleteView.as_view(), name='operation_delete'),
    path('technologist/operations/upload/', operation_upload, name='operation_upload'),
    path('technologist/operations/download/', operation_download, name='operation_download'),

    path('technologist/assortments/', AssortmentListView.as_view(), name='assortment_list'),
    path('technologist/assortments/create/', AssortmentCreateView.as_view(), name='assortment_create'),
    path('technologist/assortments/<int:pk>/', AssortmentDetailView.as_view(), name='assortment_detail'),
    path('technologist/assortments/<int:pk>/edit/', AssortmentUpdateView.as_view(), name='assortment_edit'),
    path('technologist/assortments/archived/', ArchivedAssortmentListView.as_view(), name='archived_assortment_list'),
    path('technologist/assortments/<int:pk>/archive/', AssortmentArchiveView.as_view(), name='assortment_archive'),
    path('technologist/assortments/<int:pk>/unarchive/', AssortmentUnArchiveView.as_view(), name='assortment_unarchive'), 
    path('technologist/assortments/<int:pk>/delete/', AssortmentDeleteView.as_view(), name='assortment_delete'),

    path('technologist/models/', ModelListView.as_view(), name='model_list'),
    path('technologist/models/create/', model_create, name='model_create'),
    path('technologist/models/<int:pk>/', ModelDetailView.as_view(), name='model_detail'),
    path('technologist/models/<int:pk>/edit/', model_edit, name='model_edit'),
    path('technologist/models/archived/', ArchivedModelListView.as_view(), name='archived_model_list'),
    path('technologist/models/<int:pk>/archive/', ModelArchiveView.as_view(), name='model_archive'),
    path('technologist/models/<int:pk>/unarchive/', ModelUnArchiveView.as_view(), name='model_unarchive'), 
    path('technologist/models/<int:pk>/delete/', ModelDeleteView.as_view(), name='model_delete'),

    path('technologist/nodes/', NodeListVIew.as_view(), name='node_list'),
    path('technologist/nodes/create/', NodeCreateView.as_view(), name='node_create'),
    path('technologist/nodes/<int:pk>/', NodeDetailView.as_view(), name='node_detail'),
    path('technologist/nodes/<int:pk>/edit/', NodeUpdateView.as_view(), name='node_edit'),
    path('technologist/nodes/archived/', ArchivedNodeListView.as_view(), name='archived_node_list'),
    path('technologist/nodes/<int:pk>/archive/', NodeArchiveView.as_view(), name='node_archive'),
    path('technologist/nodes<int:pk>/unarchive/', NodeUnArchiveView.as_view(), name='node_unarchive'), 
    path('technologist/nodes/<int:pk>/delete/', NodeDeleteView.as_view(), name='node_delete'),

    path('technologist/equipment/', EquipmentListView.as_view(), name='equipment_list'),
    path('technologist/equipment/create/', EquipmentCreateView.as_view(), name='equipment_create'),
    path('technologist/equipment/<int:pk>/', EquipmentDetailView.as_view(), name='equipment_detail'),
    path('technologist/equipment/<int:pk>/edit/', EquipmentUpdateView.as_view(), name='equipment_edit'),
    path('technologist/equipment/archived/', ArchivedEquipmentListView.as_view(), name='archived_equipment_list'),
    path('technologist/equipment/<int:pk>/archive/', EquipmentArchiveView.as_view(), name='equipment_archive'),
    path('technologist/equipment<int:pk>/unarchive/', EquipmentUnArchiveView.as_view(), name='equipment_unarchive'), 
    path('technologist/equipment/<int:pk>/delete/', EquipmentDeleteView.as_view(), name='equipment_delete'),

    path('employee/works/<int:id>/complete/', complete_work, name='complete_work'),

    path('cutter/client/orders/order/', OrderListCutterView.as_view(), name='order_list_cutter'),
    path('cutter/client/orders/order/<int:pk>/', OrderDetailCutterView.as_view(), name='order_detail_cutter'),
    path('cutter/client/orders/order/<int:pk>/passport/', PassportDetailView.as_view(), name='passport_detail'),
    path('qc/client/orders/order/<int:pk>/passport/', PassportDetailQcView.as_view(), name='passport_detail_qc'),
    path('packer/client/orders/order/<int:pk>/passport/', PassportDetailPackerView.as_view(), name='passport_detail_packer'),

    path('cutter/client/orders/order/<int:pk>/cut/create/', CutCreateView.as_view(), name='cut_create'),
    path('cutter/client/orders/order/<int:pk>/cut/detail/', CutDetailView.as_view(), name='cut_detail'),
    path('cutter/client/orders/order/<int:pk>/cut/edit/', CutEditView.as_view(), name='cut_edit'),
    path('cutter/cuts/delete-cut/<int:pk>/', CutDeleteView.as_view(), name='cut_delete'),

    path('cutter/client/orders/order/<int:pk>/cut/passport/create/', PassportCreateView.as_view(), name='passport_create'),
    path('cutter/cuts/delete-passport/<int:pk>/', delete_passport, name='delete_passport'),

    path('admin/client/orders/order/<int:pk>/cut/detail/', CutDetailAdminView.as_view(), name='cut_detail_admin'),
    path('technologist/client/orders/order/<int:pk>/cut/detail/', CutDetailTechnologistView.as_view(), name='cut_detail_technologist'),
    path('qc/client/orders/order/<int:pk>/cut/detail/', CutDetailQcView.as_view(), name='cut_detail_qc'),
    path('packer/client/orders/order/<int:pk>/cut/detail/', CutDetailPackerView.as_view(), name='cut_detail_packer'),

    path('qc/client/orders/order/', OrderListQcView.as_view(), name='order_list_qc'),
    path('qc/client/orders/order/<int:pk>/', OrderDetailQcView.as_view(), name='order_detail_qc'),
    path('qc/orders/api/get-piece-info/<str:barcode>/', get_piece_info, name='get_piece_info'),
    path('qc/orders/get-order-table-data/<int:order_id>/', get_order_table_data_qc, name='get_order_table_data_qc'),
    path('qc/orders/update-piece-status/<int:piece_id>/', update_piece_qc, name='update_piece_qc'),
    path('qc/scan/', scan_qc_page, name='scan_qc_page'),
    
    path('packer/client/orders/order/', OrderListPackerView.as_view(), name='order_list_packer'),
    path('packer/client/orders/order/<int:pk>/', OrderDetailPackerView.as_view(), name='order_detail_packer'),
    path('packer/orders/update-packed-by-sku/<int:sku>/', update_packed_by_sku, name='update_packed_by_sku'),
    path('packer/orders/get-order-table-data/<int:order_id>/', get_order_table_data_packer, name='get_order_table_data_packer'),
    path('packer/scan/', scan_packer_page, name='scan_packer_page'),
    
    path('keeper/color/', ColorListView.as_view(), name='color_list'),
    path('keeper/color/create/', ColorCreateView.as_view(), name='color_create'),
    path('keeper/color/<int:pk>/', ColorDetailView.as_view(), name='color_detail'),
    path('keeper/color/<int:pk>/edit/', ColorUpdateView.as_view(), name='color_edit'),
    path('keeper/color/archived/', ArchivedColorListView.as_view(), name='archived_color_list'),
    path('keeper/color/<int:pk>/archive/', ColorArchiveView.as_view(), name='color_archive'),
    path('keeper/color<int:pk>/unarchive/', ColorUnArchiveView.as_view(), name='color_unarchive'), 
    path('keeper/color/<int:pk>/delete/', ColorDeleteView.as_view(), name='color_delete'),

    path('keeper/fabrics/', FabricsListView.as_view(), name='fabrics_list'),
    path('keeper/fabrics/create/', FabricsCreateView.as_view(), name='fabrics_create'),
    path('keeper/fabrics/<int:pk>/', FabricsDetailView.as_view(), name='fabrics_detail'),
    path('keeper/fabrics/<int:pk>/edit/', FabricsUpdateView.as_view(), name='fabrics_edit'),
    path('keeper/fabrics/archived/', ArchivedFabricsListView.as_view(), name='archived_fabrics_list'),
    path('keeper/fabrics/<int:pk>/archive/', FabricsArchiveView.as_view(), name='fabrics_archive'),
    path('keeper/fabrics<int:pk>/unarchive/', FabricsUnArchiveView.as_view(), name='fabrics_unarchive'), 
    path('keeper/fabrics/<int:pk>/delete/', FabricsDeleteView.as_view(), name='fabrics_delete'),
    
    # For name changes
    path('technologist/update-assortment-name/<int:pk>/', update_assortment_name, name='update_assortment_name'),

    # For barcode creation
    path('barcode/api/qr_passport_size/<int:passport_id>/', QRPassportSize.as_view(), name='qr_passport_size'),
    #for whatsapp qr code
    path('whatsapp-qr/', WhatsAppQRCodeView.as_view(), name='whatsapp-qr'),
    path('submit-mobile/', MobileNumberSubmitView.as_view(), name='submit_mobile_number'),

    path('api/add-client/', add_client_api, name='add_client_api'),
    path('api/add-color/', add_color_api, name='add_color_api'),
    path('api/add-fabric/', add_fabric_api, name='add_fabric_api'),
    path('api/add-node/', add_node_api, name='add_node_api'),
    path('api/add-equipment/', add_equipment_api, name='add_equipment_api'),
    path('api/add-supplier/', add_supplier_api, name='add_supplier_api'),
    path('api/add-item/', add_item_api, name='add_item_api'),
    path('api/add-fabric-item/', add_fabric_item_api, name='add_fabric_item_api'),
    path('api/add-warehouse/', add_warehouse_api, name='add_warehouse_api'),
    path('api/add-assortment/', add_assortment_api, name='add_assortment_api'),

    path('api/categories/add/', add_category_api, name='add_category_api'),
    path('api/items/by_category/', items_by_category_api, name='items_by_category_api'),


    path('api/payment_details/', payment_details_view, name='payment_details'),
    path('api/client_orders/', production_details_view, name='production_details'),
    path('api/order_filter/', order_filter_view, name='order_filter'),

    path('api/employees_payment_details/<int:employee_id>/', employees_payment_details, name='employees_payment_details'),
    path('api/order_details_api/<int:order_id>/', order_details_api, name='order_details_api'),

    path('keeper/suppliers/', SupplierListView.as_view(), name='supplier_list'),
    path('keeper/suppliers/create/', SupplierCreateView.as_view(), name='supplier_create'),
    path('keeper/suppliers/<int:pk>/', SupplierDetailView.as_view(), name='supplier_detail'),
    path('keeper/suppliers/<int:pk>/edit/', SupplierUpdateView.as_view(), name='supplier_edit'),
    path('keeper/suppliers/<int:pk>/delete/', SupplierDeleteView.as_view(), name='supplier_delete'),
    path('keeper/suppliers/archived/', ArchivedSupplierListView.as_view(), name='archived_suppliers_list'),
    path('keeper/suppliers/<int:pk>/archive/', SupplierArchiveView.as_view(), name='supplier_archive'),
    path('keeper/suppliers/<int:pk>/unarchive/', SupplierUnArchiveView.as_view(), name='supplier_unarchive'),

    path('keeper/stocks/', StockListView.as_view(), name='stock_list'),
    path('keeper/stocks/materials/fabrics/', FabricsStockListView.as_view(), name='stock_list_fabrics'),
    path('keeper/stocks/materials/raw/', RawMaterialsStockListView.as_view(), name='stock_list_raw'),
    path('keeper/stocks/finished-goods/', FinishedGoodsStockListView.as_view(), name='stock_list_finished'),
    path('keeper/stocks/stock-movement', StockMovementListView.as_view(), name='stock_movement'),
    path('keeper/stocks/create/', stock_bulk_create, name='stock_create'),
    path('keeper/stocks/<int:pk>/', StockDetailView.as_view(), name='stock_detail'),
    path('keeper/stocks/<int:pk>/edit/', StockUpdateView.as_view(), name='stock_edit'),
    # path('keeper/stocks/<int:pk>/delete/', StockDeleteView.as_view(), name='stock_delete'),
    path('keeper/stocks/archived/', ArchivedStockListView.as_view(), name='archived_stocks_list'),
    path('keeper/stocks/<int:pk>/archive/', StockArchiveView.as_view(), name='stock_archive'),
    path('keeper/stocks/<int:pk>/unarchive/', StockUnArchiveView.as_view(), name='stock_unarchive'),
    path('keeper/stocks/<int:stock_id>/item/', stock_item_json, name='stock_item_json'),
    path('keeper/items/<int:pk>/update/', item_update, name='item_update'),
    path('stocks/<int:pk>/delete/', stock_delete, name='stock_delete'),

    path('keeper/receipts/', ReceiptListView.as_view(), name='receipt_list'),
    path('keeper/receipts/<int:receipt_id>/post/', post_receipt, name='post_receipt'),
    path('keeper/receipts/<int:receipt_id>/delete/', delete_receipt, name='delete_receipt'),

    path('keeper/stocks/<int:pk>/bom/detail/', BomDetailView.as_view(), name='bom_detail'),
    path('keeper/client/orders/order/<int:pk>/bom-deficit/', BomDeficitView.as_view(), name='bom_deficit'),

    path('keeper/warehouses/', WarehouseListView.as_view(), name='warehouse_list'),
    path('keeper/warehouses/create/', WarehouseCreateView.as_view(), name='warehouse_create'),
    path('keeper/warehouses/<int:pk>/', WarehouseDetailView.as_view(), name='warehouse_detail'),
    path('keeper/warehouses/<int:pk>/edit/', WarehouseUpdateView.as_view(), name='warehouse_edit'),
    path('keeper/warehouses/<int:pk>/delete/', WarehouseDeleteView.as_view(), name='warehouse_delete'),
    path('keeper/warehouses/archived/', ArchivedWarehouseListView.as_view(), name='archived_warehouses_list'),
    path('keeper/warehouses/<int:pk>/archive/', WarehouseArchiveView.as_view(), name='warehouse_archive'),
    path('keeper/warehouses/<int:pk>/unarchive/', WarehouseUnArchiveView.as_view(), name='warehouse_unarchive'),

    path('keeper/categories/', CategoryListView.as_view(), name='category_list'),
    path('keeper/categories/create/', CategoryCreateView.as_view(), name='category_create'),
    path('keeper/categories/<int:pk>/', CategoryDetailView.as_view(), name='category_detail'),
    path('keeper/categories/<int:pk>/edit/', CategoryUpdateView.as_view(), name='category_edit'),
    path('keeper/categories/<int:pk>/delete/', CategoryDeleteView.as_view(), name='category_delete'),
    path('keeper/categories/archived/', ArchivedCategoryListView.as_view(), name='archived_categories_list'),
    path('keeper/categories/<int:pk>/archive/', CategoryArchiveView.as_view(), name='category_archive'),
    path('keeper/categories/<int:pk>/unarchive/', CategoryUnArchiveView.as_view(), name='category_unarchive'),

    path('keeper/items/', ItemListView.as_view(), name='item_list'),
    path('keeper/items/create/', ItemCreateView.as_view(), name='item_create'),
    path('keeper/items/<int:pk>/', ItemDetailView.as_view(), name='item_detail'),
    path('keeper/items/<int:pk>/edit/', ItemUpdateView.as_view(), name='item_edit'),
    path('keeper/items/<int:pk>/delete/', ItemDeleteView.as_view(), name='item_delete'),
    path('keeper/items/archived/', ArchivedItemListView.as_view(), name='archived_items_list'),
    path('keeper/items/<int:pk>/archive/', ItemArchiveView.as_view(), name='item_archive'),
    path('keeper/items/<int:pk>/unarchive/', ItemUnArchiveView.as_view(), name='item_unarchive'),


    path('keeper/rolls/', RollListView.as_view(), name='roll_list'),
    path('keeper/rolls/create/', RollCreateView.as_view(), name='roll_create'),
    path('keeper/rolls/<int:pk>/', RollDetailView.as_view(), name='roll_detail'),
    path('keeper/rolls/<int:pk>/edit/', RollUpdateView.as_view(), name='roll_edit'),
    path('keeper/rolls/<int:pk>/delete/', RollDeleteView.as_view(), name='roll_delete'),
    path('keeper/rolls/combinations/', ColorFabricListView.as_view(), name='roll_combinations'),
    path('keeper/stocks/rolls/combinations/<int:rollbatch_id>/', RollsByCombinationListView.as_view(), name='roll_combination_detail'),
    path('keeper/stocks/rolls/create_bulk/', RollBulkCreateView.as_view(), name='roll_bulk_create'),

    path('keeper/stocks/orders/complete-shipment/', complete_shipment, name='complete_shipment'),

    path('ajax/get-rolls/', ajax_get_rolls, name='ajax_get_rolls'),

    path('qc/manual_check_page/', manual_check_page, name='manual_check_page'),
    path('qc/ajax/get-orders/', ajax_get_orders, name='ajax_get_orders'),
    path('qc/ajax/orders/update-checked-quantity/', update_checked_quantity, name='update_checked_quantity'),

    path('packer/manual_pack_page/', manual_pack_page, name='manual_pack_page'),
    path('packer/ajax/get-orders/', ajax_get_orders, name='ajax_get_orders'),
    path('packer/ajax/orders/update-packed-quantity/', update_packed_quantity_manually, name='update_packed_quantity_manually'),
    path('packer/ajax/orders/complete-production/', complete_production, name='complete_production'),

    path('accountant/manual_cost_page/', manual_cost_page, name='manual_cost_page'),
    path('accountant/ajax/get-model-sizes/', ajax_get_model_sizes, name='ajax_get_model_sizes'),
    path('accountant/ajax/get-size-cost-data/<int:size_id>/', ajax_get_size_cost_data, name='ajax_get_size_cost_data'),
    path('accountant/ajax/save-costs/', save_costs, name='save_costs'),

    path("set-client-scope/", set_client_scope, name="set_client_scope"),
]
