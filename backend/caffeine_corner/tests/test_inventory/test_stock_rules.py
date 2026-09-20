"""The rules for how stock moves — direction of each movement type, when stock is applied, and what staff may enter."""
from decimal import Decimal

from django.test import TestCase

from inventory.models import StockMovement
from inventory.stock import MAX_STOCK, check_movement, show
from tests.support.factories import make_item

ALL_TYPES = {value for value, _label in StockMovement.MOVEMENT_TYPES}


class MovementDirectionTests(TestCase):
    def setUp(self):
        self.item = make_item(on_hand='100')

    def move(self, kind, quantity='1'):
        return StockMovement.objects.create(inventory=self.item, movement_type=kind, quantity=Decimal(quantity))

    def stock(self):
        self.item.refresh_from_db()
        return self.item.quantity_on_hand

    def test_every_type_is_stock_in_or_stock_out_never_both(self):
        self.assertEqual(StockMovement.STOCK_IN | StockMovement.STOCK_OUT, ALL_TYPES)
        self.assertFalse(StockMovement.STOCK_IN & StockMovement.STOCK_OUT)

    def test_each_type_moves_stock_the_way_its_label_says(self):
        for kind in sorted(ALL_TYPES):
            with self.subTest(kind=kind):
                before = self.stock()
                movement = self.move(kind, '2')
                label = movement.get_movement_type_display()
                if kind in StockMovement.STOCK_IN:
                    self.assertEqual(self.stock(), before + 2)
                    self.assertTrue(label.startswith('Stock In'), label)
                else:
                    self.assertEqual(self.stock(), before - 2)
                    self.assertTrue(label.startswith('Stock Out'), label)

    def test_return_to_supplier_takes_stock_out(self):
        # it used to add stock: goods handed back to a supplier were counted as arriving
        self.move('return', '5')
        self.assertEqual(self.stock(), Decimal('95.00'))

    def test_what_staff_can_enter_by_hand_leaves_out_the_automatic_and_ambiguous_types(self):
        self.assertEqual(set(StockMovement.MANUAL_TYPES), {'purchase', 'adjustment', 'spoilage', 'return'})
        self.assertLessEqual(set(StockMovement.MANUAL_TYPES), ALL_TYPES)


class WhenStockIsApplied(TestCase):
    def setUp(self):
        self.item = make_item(on_hand='10')

    def stock(self):
        self.item.refresh_from_db()
        return self.item.quantity_on_hand

    def test_stock_changes_when_the_movement_is_created_and_not_when_it_is_saved_again(self):
        movement = StockMovement.objects.create(inventory=self.item, movement_type='purchase', quantity=Decimal('5'))
        self.assertEqual(self.stock(), Decimal('15.00'))
        movement.notes = 'edited later'
        movement.save()                                   # used to push stock by +5 again
        movement.save()
        self.assertEqual(self.stock(), Decimal('15.00'))
        self.assertEqual(StockMovement.objects.get().notes, 'edited later')

    def test_usage_from_an_order_floors_stock_at_zero_rather_than_failing(self):
        # orders can't be refused because the shelf count is off; the history still shows what was used
        movement = StockMovement.objects.create(inventory=self.item, movement_type='usage', quantity=Decimal('50'))
        self.assertEqual(self.stock(), Decimal('0.00'))
        self.assertEqual(movement.quantity_change, Decimal('-50.00'))

    def test_a_record_can_be_kept_without_moving_stock_again(self):
        # what "Opening stock" uses: the item already holds the quantity, the movement just documents it
        movement = StockMovement(inventory=self.item, movement_type='purchase', quantity=Decimal('10'), reference='Opening stock')
        movement.save(apply_to_stock=False)
        self.assertEqual(self.stock(), Decimal('10.00'))
        self.assertEqual(movement.quantity_change, Decimal('10.00'))


class CheckMovementTests(TestCase):
    """The shared rule behind the item page, the Stock Movements form and Quick Adjust."""

    def setUp(self):
        self.item = make_item(on_hand='10', unit='kg')

    def check(self, kind, quantity):
        return check_movement(self.item, kind, Decimal(quantity))

    def test_good_movements_pass(self):
        self.assertIsNone(self.check('purchase', '5'))
        self.assertIsNone(self.check('adjustment', '10'))          # taking out exactly what's there is fine
        self.assertIsNone(self.check('spoilage', '0.01'))

    def test_quantity_must_be_positive(self):
        self.assertEqual(self.check('purchase', '0'), 'Quantity must be greater than 0.')
        self.assertEqual(self.check('adjustment', '-1'), 'Quantity must be greater than 0.')

    def test_cannot_take_out_more_than_is_on_hand(self):
        for kind in ('adjustment', 'spoilage', 'return'):
            with self.subTest(kind=kind):
                self.assertEqual(self.check(kind, '10.01'), 'Only 10.00 kg on hand — you can’t take out 10.01.')

    def test_cannot_overflow_the_stock_field(self):
        self.assertEqual(self.check('purchase', str(MAX_STOCK)), 'That quantity is too large.')          # 10 on hand + this
        self.assertEqual(self.check('purchase', str(MAX_STOCK + 1)), 'That quantity is too large.')

    def test_quantities_read_with_two_decimals_and_thousands_separators(self):
        self.assertEqual(show(Decimal('12.5')), '12.50')
        self.assertEqual(show(1000), '1,000.00')
