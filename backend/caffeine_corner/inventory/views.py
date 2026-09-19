from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
# inventory/views.py
from django.db.models import Sum, F, Count
from django.utils import timezone
from decimal import Decimal
import datetime
import json
from online_shop.models import Order, Product, LoyaltyPoint, Notification, ActivityLog
from inventory.models import Inventory, PurchaseOrder, PurchaseOrderItem
from inventory.sales_report import ORDER_TYPES, build_sales_report, parse_report_params, sales_scope
import csv
import openpyxl
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils.html import format_html

@staff_member_required
def auto_generate_purchase_orders(request):
    if request.method != 'POST':
        return redirect('/admin/inventory/purchaseorder/')

    # Hanapin lahat ng low stock items na may supplier
    low_stock_items = Inventory.objects.filter(
        quantity_on_hand__lte=F('reorder_points'),
        quantity_on_hand__gt=0,  # hindi pa out of stock
        supplier__isnull=False,  # may supplier
    ).select_related('supplier')

    out_of_stock_items = Inventory.objects.filter(
        quantity_on_hand=0,
        supplier__isnull=False,
    ).select_related('supplier')

    all_items = list(low_stock_items) + list(out_of_stock_items)

    if not all_items:
        from django.contrib import messages
        messages.warning(request, 'No low stock items found that need reordering.')
        return redirect('/admin/inventory/purchaseorder/')

    # Group by supplier
    supplier_items = {}
    for item in all_items:
        supplier_id = item.supplier.id
        if supplier_id not in supplier_items:
            supplier_items[supplier_id] = {
                'supplier': item.supplier,
                'items':    []
            }
        supplier_items[supplier_id]['items'].append(item)

    # Generate PO per supplier
    created_pos = []
    for supplier_id, group in supplier_items.items():
        # Generate PO reference
        today     = timezone.now()
        ref_count = PurchaseOrder.objects.filter(
            ordered_at__year=today.year,
            ordered_at__month=today.month,
        ).count() + 1
        reference = f'PO-{today.strftime("%Y%m")}-{str(ref_count).zfill(4)}'

        # Avoid duplicate PO — check if may existing draft PO for same supplier today
        existing = PurchaseOrder.objects.filter(
            supplier=group['supplier'],
            status='draft',
            ordered_at__date=today.date(),
        ).first()

        if existing:
            po = existing
        else:
            po = PurchaseOrder.objects.create(
                supplier=group['supplier'],
                reference=reference,
                status='draft',
                expected_at=today.date() + timezone.timedelta(days=7),
                created_by=request.user,
                notes=f'Auto-generated on {today.strftime("%B %d, %Y")} for low stock items.',
            )

        # Add items to PO
        for item in group['items']:
            # Skip if already in this PO
            if PurchaseOrderItem.objects.filter(purchase_order=po, inventory=item).exists():
                continue

            PurchaseOrderItem.objects.create(
                purchase_order=po,
                inventory=item,
                quantity_ordered=item.reorder_quantity or (item.reorder_points * 2),
                quantity_received=0,
                unit_cost=item.cost_per_unit,
            )

        created_pos.append(po)

    from django.contrib import messages
    messages.success(
        request,
        f'Successfully generated {len(created_pos)} Purchase Order(s) for {len(all_items)} low stock item(s).'
    )
    return redirect('/admin/inventory/purchaseorder/')

# Notification "bell" — the sidebar's live unread badge (see
# static/js/notif-badge.js, polled every 20s) plus mark-as-read from either
# NotificationAdmin's changelist column or the dashboard widget
# (templates/admin/index.html), all without a page reload.
#
# HX-Request-aware rather than a plain redirect now: HTMX calls (both
# callers above) post here and swap the response straight in. A non-HTMX
# POST (e.g. JS disabled) still works and falls back to the old redirect.
@staff_member_required
@require_POST
def mark_notification_read(request, notification_id):
    from online_shop.admin import render_notif_read_cell

    notif = get_object_or_404(Notification, pk=notification_id)
    notif.is_read = True
    notif.save(update_fields=['is_read'])

    if request.headers.get('HX-Request') != 'true':
        return redirect('/admin/online_shop/notification/')

    # Keeps the dashboard's "N unread" header in sync too, if present on
    # the page that triggered this (harmless no-op otherwise — htmx just
    # won't find a matching #notif-unread-count to swap into).
    remaining = Notification.objects.filter(is_read=False).count()
    oob_count = format_html(
        '<span id="notif-unread-count" hx-swap-oob="true" '
        'class="inline-block font-semibold rounded-default text-[11px] px-2 bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400">'
        '{} unread</span>',
        remaining,
    )

    # dashboard widget: the whole row disappears (list only shows unread).
    if request.GET.get('remove'):
        return HttpResponse(oob_count)

    # changelist column: swap the link for the static "✓ Read" badge.
    return HttpResponse(render_notif_read_cell(notif) + oob_count)


@staff_member_required
def notif_unread_count(request):
    return JsonResponse({'count': Notification.objects.filter(is_read=False).count()})


# Quick Stock Adjustment widget on the Inventory changelist (see
# render_quick_adjust / InventoryAdmin.show_quick_adjust in admin.py) — logs
# a StockMovement straight from the list, no need to open the item. "+"
# posts a Purchase (stock in), "-" an Adjustment (stock out); StockMovement's
# own save() does the actual quantity_on_hand math (see that model). Returns
# the widget (reset) plus the Stock Level / Status cells out-of-band so all
# three stay in sync from one click.
@staff_member_required
@require_POST
def htmx_adjust_stock(request, inventory_id):
    from decimal import InvalidOperation
    from django.http import HttpResponseBadRequest
    from inventory.models import StockMovement
    from inventory.admin import render_quick_adjust, render_stock_bar, render_stock_status

    inventory = get_object_or_404(Inventory, pk=inventory_id)
    kind = request.GET.get('type')
    if kind not in ('purchase', 'adjustment'):
        return HttpResponseBadRequest('Invalid adjustment type')

    try:
        qty = Decimal(request.POST.get('quantity', ''))
    except InvalidOperation:
        return HttpResponseBadRequest('Invalid quantity')
    if qty <= 0:
        return HttpResponseBadRequest('Quantity must be positive')

    StockMovement.objects.create(
        inventory=inventory,
        movement_type=kind,
        quantity=qty,
        unit_cost=inventory.cost_per_unit,
        reference='Quick adjust (admin)',
        performed_by=request.user,
    )
    inventory.refresh_from_db()

    html = render_quick_adjust(inventory)
    html += format_html(
        '<span id="stock-bar-{}" hx-swap-oob="true">{}</span>',
        inventory.pk, render_stock_bar(inventory),
    )
    html += format_html(
        '<span id="stock-status-{}" hx-swap-oob="true">{}</span>',
        inventory.pk, render_stock_status(inventory),
    )
    return HttpResponse(html)


@staff_member_required
def export_orders(request):
    export_format = request.GET.get('format', 'csv')
    status_filter = request.GET.get('status', '')
    date_from     = request.GET.get('date_from', '')
    date_to       = request.GET.get('date_to', '')

    orders = Order.objects.prefetch_related('items__product').order_by('-created_at')

    if status_filter:
        orders = orders.filter(status=status_filter)
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)

    if export_format == 'excel':
        return _export_excel(orders)
    return _export_csv(orders)


def _export_csv(orders):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Order ID', 'Email', 'Order Type', 'Status',
        'Payment Method', 'Payment Status',
        'Products', 'Total Price', 'Discount',
        'Points Earned', 'Address', 'Notes',
        'Event Date', 'Pax', 'Created At'
    ])

    for order in orders:
        products = ', '.join([
            f"{item.product.name} x{item.quantity}"
            for item in order.items.all()
        ])
        writer.writerow([
            f'CC-{str(order.id).zfill(5)}',
            order.email,
            order.get_order_type_display(),
            order.get_status_display(),
            order.get_payment_method_display(),
            order.get_payment_status_display(),
            products,
            order.total_price,
            order.discount,
            order.points_earned,
            order.address,
            order.notes,
            order.event_date or '',
            order.pax or '',
            order.created_at.strftime('%Y-%m-%d %H:%M'),
        ])

    return response


def _export_excel(orders):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Orders'

    header_fill = PatternFill(start_color='3D1F00', end_color='3D1F00', fill_type='solid')
    header_font = Font(color='C4A882', bold=True, size=11)
    border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB'),
    )

    headers = [
        'Order ID', 'Email', 'Order Type', 'Status',
        'Payment Method', 'Payment Status',
        'Products', 'Total Price', 'Discount',
        'Points Earned', 'Address', 'Notes',
        'Event Date', 'Pax', 'Created At'
    ]

    for col, header in enumerate(headers, 1):
        cell           = ws.cell(row=1, column=col, value=header)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border    = border

    col_widths = [12, 30, 15, 12, 18, 16, 40, 14, 12, 14, 35, 25, 12, 8, 18]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    ws.row_dimensions[1].height = 25

    for row_idx, order in enumerate(orders, 2):
        products = ', '.join([
            f"{item.product.name} x{item.quantity}"
            for item in order.items.all()
        ])
        row_data = [
            f'CC-{str(order.id).zfill(5)}',
            order.email,
            order.get_order_type_display(),
            order.get_status_display(),
            order.get_payment_method_display(),
            order.get_payment_status_display(),
            products,
            float(order.total_price),
            float(order.discount),
            order.points_earned,
            order.address,
            order.notes,
            str(order.event_date) if order.event_date else '',
            order.pax or '',
            order.created_at.strftime('%Y-%m-%d %H:%M'),
        ]

        fill_color = 'FFFFFF' if row_idx % 2 == 0 else 'FAF6F0'
        row_fill   = PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid')

        for col_idx, value in enumerate(row_data, 1):
            cell           = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill      = row_fill
            cell.border    = border
            cell.alignment = Alignment(vertical='center', wrap_text=True)
            ws.row_dimensions[row_idx].height = 20

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="orders_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    wb.save(response)
    return response

# The PDF's item-by-item transaction log is one row per line item sold — a
# month is already ~20 pages. Past this many lines it's left out (with a note)
# rather than building a document too big to render or print.
MAX_LOG_ITEMS = 4000


@staff_member_required
def sales_report_view(request):
    context = {
        **admin.site.each_context(request),
        'title': 'Sales Report',
        'params': parse_report_params(request.GET),
        'order_types': ORDER_TYPES,
    }
    return render(request, 'admin/sales_report.html', context)


@staff_member_required
def sales_report_data(request):
    """JSON feed behind the interactive Sales Report page. Staff only: this
    is every sale the shop has made."""
    p = parse_report_params(request.GET)
    return JsonResponse(build_sales_report(p.date_from, p.date_to, p.granularity, p.order_type))


@staff_member_required
def sales_report_document_view(request):
    """Printable, document-style sales report — 'Export as PDF' just prints
    this page (browser Save-as-PDF), so everything needed has to be baked
    into the HTML server-side rather than fetched client-side.

    Numbers come from the same build_sales_report() as the interactive page,
    so the two can't drift apart; only the row-level detail (transaction log,
    delivery list) is assembled here."""
    p = parse_report_params(request.GET)
    report = build_sales_report(p.date_from, p.date_to, p.granularity, p.order_type)
    orders, items = sales_scope(p.date_from, p.date_to, p.order_type)

    # Detailed transaction log — one group per order type, each with its own
    # subtotal. On by default for a month or less (as it always was); longer
    # ranges leave it out unless asked for, and it's never built past
    # MAX_LOG_ITEMS lines.
    log_requested = request.GET.get('log', '1' if report['meta']['days'] <= 31 else '0') == '1'
    log_lines     = items.count() if log_requested else 0
    show_log      = log_requested and log_lines <= MAX_LOG_ITEMS
    log_note      = ''
    if log_requested and not show_log:
        log_note = (f'The item-level transaction log has {log_lines:,} lines — too many for a single '
                    f'document, so it is left out. Narrow the date range to include it.')

    groups = {
        t['key']: {'key': t['key'], 'label': t['label'], 'rows': [], 'qty': 0, 'subtotal': Decimal('0')}
        for t in report['by_type']
    }
    if show_log:
        for item in items.select_related('order', 'product', 'variant').order_by('order__created_at', 'order_id', 'id'):
            group = groups[item.order.order_type]
            subtotal = item.price * item.quantity
            group['rows'].append({
                'date':     item.order.created_at,
                'order_id': item.order_id,
                'name':     item.product.name,
                'size':     item.variant.get_size_display() if item.variant else '—',
                'qty':      item.quantity,
                'price':    item.price,
                'subtotal': subtotal,
            })
            group['qty'] += item.quantity
            group['subtotal'] += subtotal

    # Delivery fee summary — orders that actually had a delivery zone/fee. The
    # per-zone totals are always shown; the order-by-order listing is part of
    # the detail (same switch as the item log) so a long range can't bloat it.
    zone_orders         = orders.filter(zone__isnull=False, delivery_fee__gt=0)
    delivery_by_zone    = list(
        zone_orders.order_by().values('zone__name')
        .annotate(n=Count('id'), fees=Sum('delivery_fee'))
        .order_by('-fees', 'zone__name')
    )
    total_delivery_fees = sum((z['fees'] for z in delivery_by_zone), Decimal('0'))
    delivery_orders     = list(zone_orders.select_related('zone').order_by('created_at')) if show_log else []

    # Downpayment collection summary
    down        = orders.filter(downpayment_amount__gt=0).aggregate(n=Count('id'), paid=Sum('downpayment_amount'), left=Sum('remaining_balance'))
    full        = orders.filter(downpayment_amount=0)
    full_total  = (
        (items.filter(order__downpayment_amount=0).aggregate(s=Sum(F('price') * F('quantity')))['s'] or Decimal('0'))
        + (full.aggregate(f=Sum('delivery_fee'))['f'] or Decimal('0'))
    )

    context = {
        **admin.site.each_context(request),
        'title':        'Sales Report',
        'params':       p,
        'order_types':  ORDER_TYPES,
        'report':       report,
        'groups':       list(groups.values()),
        'show_log':     show_log,
        'log_requested': log_requested,
        'log_note':     log_note,
        'generated_at': timezone.now(),
        'prepared_by':  request.user.get_full_name() or request.user.email,
        'reference_no': f'RPT-{timezone.now().strftime("%Y%m%d-%H%M%S")}',
        'show_delivery_section':   p.order_type in ('', 'regular'),
        'delivery_orders':         delivery_orders,
        'delivery_by_zone':        delivery_by_zone,
        'total_delivery_fees':     total_delivery_fees,
        'orders_with_downpayment': down['n'] or 0,
        'downpayment_total':       down['paid'] or Decimal('0'),
        'remaining_total':         down['left'] or Decimal('0'),
        'full_payment_count':      full.count(),
        'full_payment_total':      full_total,
    }
    return render(request, 'admin/sales_report_document.html', context)

def dashboard_callback(request, context):

    # Stats
    total_orders = Order.objects.count()
    revenue = Order.objects.filter(
        payment_status='paid'
    ).aggregate(total=Sum('items__price'))['total'] or 0
    active_products = Product.objects.filter(is_available=True).count()
    low_stock = Inventory.objects.filter(
        quantity_on_hand__lte=F('reorder_points')
    ).count()

    # Orders last 30 days
    today = timezone.now().date()
    days = [(today - datetime.timedelta(days=i)) for i in range(29, -1, -1)]
    order_counts = [
        Order.objects.filter(created_at__date=day).count()
        for day in days
    ]

    # Recent orders
    recent_orders_data = []
    for order in Order.objects.select_related('user').prefetch_related(
        'items__product'
    ).order_by('-created_at')[:5]:
        first_item = order.items.first()
        recent_orders_data.append({
            'id': order.id,
            'customer': order.email,
            'product': first_item.product.name if first_item else '—',
            'row': order.address[:20] if order.address else '—',
            'qty': order.item_count,
            'sum': f'₱{order.total_price}',
            'date': order.created_at.strftime('%b %d, %Y'),
        })

    # Low stock items
    low_stock_items = list(
        Inventory.objects.filter(
            quantity_on_hand__lte=F('reorder_points')
        ).values('name', 'quantity_on_hand', 'unit', 'reorder_points')[:5]
    )
    # Out of stock items
    out_of_stock = Inventory.objects.filter(quantity_on_hand=0).count()

    # Top customers
    top_customers_data = [
        {'email': lp.user.email, 'points': lp.points}
        for lp in LoyaltyPoint.objects.select_related('user').order_by('-points')[:5]
    ]
    unread_notifications = Notification.objects.filter(is_read=False).order_by('-created_at')[:5]

    recent_logs = ActivityLog.objects.select_related('user').order_by('-created_at')[:8]

    # Icon + badge-variant per notification type, resolved server-side so the
    # template stays presentation-only (no type-string branching there).
    NOTIF_STYLES = {
        'new_order':    ('shopping_cart', 'primary'),
        'bulk_order':   ('restaurant',    'warning'),
        'low_stock':    ('warning',       'danger'),
        'payment_paid': ('check_circle',  'success'),
    }

    # Same idea for the activity feed dot color.
    LOG_VARIANTS = {
        'order_created':   'success',
        'order_updated':   'info',
        'order_cancelled': 'danger',
        'payment_paid':    'success',
        'product_created': 'primary',
        'product_updated': 'info',
        'user_login':      'warning',
        'stock_movement':  'base',
    }

    # Chart.js dataset — colors reference Unfold's CSS variables so the chart
    # automatically matches the active primary color and light/dark theme.
    chart_data = {
        "labels": [d.strftime('%b %d') for d in days],
        "datasets": [{
            "label": "Orders",
            "data": order_counts,
            "backgroundColor": "var(--color-primary-600)",
            "borderColor": "var(--color-primary-600)",
            "borderWidth": 0,
            "borderRadius": 4,
            "maxBarThickness": 18,
        }],
    }
    chart_options = {
        "plugins": {"legend": {"display": False}},
        "scales": {
            "y": {"beginAtZero": True, "ticks": {"precision": 0}},
            "x": {"ticks": {"maxTicksLimit": 10}},
        },
    }

    context.update({
        'unread_count': Notification.objects.filter(is_read=False).count(),
        'unread_notifications': [
            {
                'id':         n.id,
                'title':      n.title,
                'message':    n.message,
                'type':       n.type,
                'icon':       NOTIF_STYLES.get(n.type, ('campaign', 'base'))[0],
                'variant':    NOTIF_STYLES.get(n.type, ('campaign', 'base'))[1],
                'created_at': n.created_at.strftime('%b %d, %Y %H:%M'),
                'order_id':   n.order.id if n.order else None,
            }
            for n in unread_notifications
        ],
        "kpi": [
            {"title": "Total Orders", "metric": str(total_orders), "icon": "shopping_cart", "variant": "primary"},
            {"title": "Revenue", "metric": f"₱{revenue:,.2f}", "icon": "payments", "variant": "success"},
            {"title": "Active Products", "metric": str(active_products), "icon": "coffee", "variant": "info"},
            {"title": "Low Stock", "metric": str(low_stock) if low_stock else "—", "icon": "warning", "variant": "danger" if low_stock else "base"},
        ],
        "chart_json": json.dumps(chart_data),
        "chart_options_json": json.dumps(chart_options),
        'recent_logs': [
            {
                'action':     log.get_action_display(),
                'action_key': log.action,
                'variant':    LOG_VARIANTS.get(log.action, 'base'),
                'user':       log.user.email if log.user else 'System',
                'details':    log.details,
                'created_at': log.created_at.strftime('%b %d, %H:%M'),
            }
            for log in recent_logs
        ],
        "recent_orders": recent_orders_data,
        'low_stock_items': low_stock_items,
        'out_of_stock':    out_of_stock,
        "top_customers": top_customers_data,
    })

    return context