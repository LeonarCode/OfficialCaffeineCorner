from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Inventory, StockMovement
from online_shop.models import Notification


@receiver(post_save, sender=Inventory)
def check_low_stock(sender, instance, **kwargs):
    if instance.is_low_stock:
        # Avoid duplicate notifications — check if may existing unread low stock notif
        existing = Notification.objects.filter(
            type='low_stock',
            is_read=False,
            message__icontains=instance.name,
        ).exists()

        if not existing:
            Notification.objects.create(
                type='low_stock',
                title=f'Low Stock Alert — {instance.name}',
                message=(
                    f'{instance.name} ({instance.sku}) is running low. '
                    f'Current stock: {instance.quantity_on_hand} {instance.unit}. '
                    f'Reorder point: {instance.reorder_points} {instance.unit}.'
                ),
            )

@receiver(post_save, sender=StockMovement)
def check_low_stock_after_movement(sender, instance, created, **kwargs):
    if created:
        inventory = instance.inventory
        # Refresh from DB para makuha ang updated quantity
        inventory.refresh_from_db()
        if inventory.is_low_stock:
            existing = Notification.objects.filter(
                type='low_stock',
                is_read=False,
                message__icontains=inventory.name,
            ).exists()
            if not existing:
                Notification.objects.create(
                    type='low_stock',
                    title=f'Low Stock Alert — {inventory.name}',
                    message=(
                        f'{inventory.name} ({inventory.sku}) is running low after stock movement. '
                        f'Current stock: {inventory.quantity_on_hand} {inventory.unit}. '
                        f'Reorder point: {inventory.reorder_points} {inventory.unit}.'
                    ),
                )