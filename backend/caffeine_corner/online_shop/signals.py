from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Order, OrderItem, Notification
from .utils import log_activity


@receiver(post_save, sender=Order)
def create_order_notification(sender, instance, created, **kwargs):
    if created:
        if instance.order_type == 'bulk':
            Notification.objects.create(
                type='bulk_order',
                title=f'New Bulk Order #{instance.id}',
                message=f'Bulk/Catering order from {instance.email}. Event date: {instance.event_date or "Not set"}. Pax: {instance.pax or 0}.',
                order=instance,
            )
        else:
            Notification.objects.create(
                type='new_order',
                title=f'New Order #CC-{str(instance.id).zfill(5)}',
                message=f'New order from {instance.email}. Total: ₱{instance.total_price}.',
                order=instance,
            )

    # Payment paid notification
    if not created and instance.payment_status == 'paid':
        if not Notification.objects.filter(order=instance, type='payment_paid').exists():
            Notification.objects.create(
                type='payment_paid',
                title=f'Payment Received — Order #CC-{str(instance.id).zfill(5)}',
                message=f'Payment confirmed for order from {instance.email}. Total: ₱{instance.total_price}.',
                order=instance,
            )

@receiver(post_save, sender=Order)
def create_order_notification(sender, instance, created, **kwargs):
    if created:
        if instance.order_type == 'bulk':
            Notification.objects.create(
                type='bulk_order',
                title=f'New Bulk Order #{instance.id}',
                message=f'Bulk/Catering order from {instance.email}. Event date: {instance.event_date or "Not set"}. Pax: {instance.pax or 0}.',
                order=instance,
            )
        else:
            Notification.objects.create(
                type='new_order',
                title=f'New Order #CC-{str(instance.id).zfill(5)}',
                message=f'New order from {instance.email}. Total: ₱{instance.total_price}.',
                order=instance,
            )

    # Payment paid notification
    if not created and instance.payment_status == 'paid':
        if not Notification.objects.filter(order=instance, type='payment_paid').exists():
            Notification.objects.create(
                type='payment_paid',
                title=f'Payment Received — Order #CC-{str(instance.id).zfill(5)}',
                message=f'Payment confirmed for order from {instance.email}. Total: ₱{instance.total_price}.',
                order=instance,
            )


@receiver(post_save, sender=OrderItem)
def deduct_inventory_on_order(sender, instance, created, **kwargs):
    """
    Kapag nag-create ng OrderItem — automatic na bawasan ang inventory
    ng ingredients ng product.
    """
    if not created:
        return

    product = instance.product
    quantity_ordered = instance.quantity

    # Hanapin ang ingredients ng product
    ingredients = product.ingredients.select_related('inventory').all()

    if not ingredients.exists():
        return

    from inventory.models import StockMovement

    for ingredient in ingredients:
        inventory_item = ingredient.inventory
        usage_quantity = ingredient.quantity * quantity_ordered

        # I-deduct ang stock
        inventory_item.quantity_on_hand = max(
            0,
            inventory_item.quantity_on_hand - usage_quantity
        )
        inventory_item.save(update_fields=['quantity_on_hand', 'last_updated'])

        # I-record ang stock movement
        StockMovement.objects.create(
            inventory=inventory_item,
            movement_type='usage',
            quantity=usage_quantity,
            unit_cost=inventory_item.cost_per_unit,
            reference=f'Order #CC-{str(instance.order.id).zfill(5)}',
            notes=f'Auto-deducted for {product.name} x{quantity_ordered}',
        )

        # Check kung low stock na — mag-trigger ng notification
        inventory_item.refresh_from_db()
        if inventory_item.is_low_stock:
            existing = Notification.objects.filter(
                type='low_stock',
                is_read=False,
                message__icontains=inventory_item.name,
            ).exists()
            if not existing:
                Notification.objects.create(
                    type='low_stock',
                    title=f'Low Stock Alert — {inventory_item.name}',
                    message=(
                        f'{inventory_item.name} ({inventory_item.sku}) is running low '
                        f'after Order #CC-{str(instance.order.id).zfill(5)}. '
                        f'Current stock: {inventory_item.quantity_on_hand} {inventory_item.unit}. '
                        f'Reorder point: {inventory_item.reorder_points} {inventory_item.unit}.'
                    ),
                )

@receiver(post_save, sender=Order)
def restore_inventory_on_cancel(sender, instance, created, **kwargs):
    """
    Kapag na-cancel ang order — i-restore ang inventory.
    """
    if created:
        return

    # Check kung bag-o lang na-cancel
    try:
        old = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    # Dapat gumawa ng pre_save signal para ma-track ang old status
    # Gamitin natin ang instance._state
    if instance.status != 'cancelled':
        return

    # Check kung may existing restoration na
    from inventory.models import StockMovement
    already_restored = StockMovement.objects.filter(
        reference=f'CANCEL-Order #CC-{str(instance.id).zfill(5)}'
    ).exists()

    if already_restored:
        return

    for order_item in instance.items.prefetch_related('product__ingredients__inventory').all():
        product    = order_item.product
        quantity   = order_item.quantity
        ingredients = product.ingredients.select_related('inventory').all()

        for ingredient in ingredients:
            inventory_item = ingredient.inventory
            restore_qty    = ingredient.quantity * quantity

            inventory_item.quantity_on_hand += restore_qty
            inventory_item.save(update_fields=['quantity_on_hand', 'last_updated'])

            StockMovement.objects.create(
                inventory=inventory_item,
                movement_type='adjustment',
                quantity=restore_qty,
                unit_cost=inventory_item.cost_per_unit,
                reference=f'CANCEL-Order #CC-{str(instance.id).zfill(5)}',
                notes=f'Restored — Order #{instance.id} cancelled.',
            )

# I-store ang old status bago mag-save
@receiver(pre_save, sender=Order)
def store_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = Order.objects.get(pk=instance.pk).status
        except Order.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Order)
def restore_inventory_on_cancel(sender, instance, created, **kwargs):
    if created:
        return

    # Only trigger kapag nagbago sa cancelled
    old_status = getattr(instance, '_old_status', None)
    if old_status == 'cancelled' or instance.status != 'cancelled':
        return

    from inventory.models import StockMovement
    already_restored = StockMovement.objects.filter(
        reference=f'CANCEL-Order #CC-{str(instance.id).zfill(5)}'
    ).exists()

    if already_restored:
        return

    for order_item in instance.items.prefetch_related('product__ingredients__inventory').all():
        product     = order_item.product
        quantity    = order_item.quantity
        ingredients = product.ingredients.select_related('inventory').all()

        for ingredient in ingredients:
            inventory_item = ingredient.inventory
            restore_qty    = ingredient.quantity * quantity

            inventory_item.quantity_on_hand += restore_qty
            inventory_item.save(update_fields=['quantity_on_hand', 'last_updated'])

            StockMovement.objects.create(
                inventory=inventory_item,
                movement_type='adjustment',
                quantity=restore_qty,
                unit_cost=inventory_item.cost_per_unit,
                reference=f'CANCEL-Order #CC-{str(instance.id).zfill(5)}',
                notes=f'Restored — Order #{instance.id} cancelled.',
            )

@receiver(post_save, sender=Order)
def create_order_notification(sender, instance, created, **kwargs):
    if created:
        # Log activity
        log_activity(
            action='order_created',
            model_name='Order',
            object_id=instance.id,
            details=f'New {"bulk" if instance.order_type == "bulk" else "regular"} order from {instance.email}. Total: ₱{instance.total_price}.',
        )

        if instance.order_type == 'bulk':
            Notification.objects.create(
                type='bulk_order',
                title=f'New Bulk Order #{instance.id}',
                message=f'Bulk/Catering order from {instance.email}. Event date: {instance.event_date or "Not set"}. Pax: {instance.pax or 0}.',
                order=instance,
            )
        else:
            Notification.objects.create(
                type='new_order',
                title=f'New Order #CC-{str(instance.id).zfill(5)}',
                message=f'New order from {instance.email}. Total: ₱{instance.total_price}.',
                order=instance,
            )

    if not created:
        old_status = getattr(instance, '_old_status', None)

        # Payment paid log
        if instance.payment_status == 'paid' and old_status != 'paid':
            log_activity(
                action='payment_paid',
                model_name='Order',
                object_id=instance.id,
                details=f'Payment confirmed for Order #CC-{str(instance.id).zfill(5)}. Amount: ₱{instance.total_price}.',
            )
            if not Notification.objects.filter(order=instance, type='payment_paid').exists():
                Notification.objects.create(
                    type='payment_paid',
                    title=f'Payment Received — Order #CC-{str(instance.id).zfill(5)}',
                    message=f'Payment confirmed for order from {instance.email}. Total: ₱{instance.total_price}.',
                    order=instance,
                )

        # Order cancelled log
        if instance.status == 'cancelled' and old_status != 'cancelled':
            log_activity(
                action='order_cancelled',
                model_name='Order',
                object_id=instance.id,
                details=f'Order #CC-{str(instance.id).zfill(5)} cancelled. Was: {old_status}.',
            )

        # Order updated log
        if old_status and old_status != instance.status and instance.status != 'cancelled':
            log_activity(
                action='order_updated',
                model_name='Order',
                object_id=instance.id,
                details=f'Order #CC-{str(instance.id).zfill(5)} status changed from {old_status} to {instance.status}.',
            )