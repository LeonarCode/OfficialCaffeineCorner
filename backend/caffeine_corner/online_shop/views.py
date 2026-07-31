from decimal import Decimal

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from .models import Category, Product, Order, OrderItem, CartItem, LoyaltyPoint, Rating, TownZone
from .serializer import (
    CategorySerializer, ProductSerializer, RatingSerializer,
    OrderSerializer, CreateOrderSerializer,
    CartItemSerializer, LoyaltyPointSerializer, TownZoneSerializer
)
import os
import hmac
import json
import base64
import hashlib
import requests
from django.contrib.admin.views.decorators import staff_member_required

import qrcode, io, base64

@staff_member_required
def print_order_receipt(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'items__variant'),
        id=order_id
    )
    return render(request, 'admin/order_receipt.html', {'order': order})

@staff_member_required
def table_qr_page(request):
    
    tables = []
    for i in range(1, 6):
        url = f'http://localhost:5173/menu?table={i}'
        qr  = qrcode.QRCode(version=1, box_size=8, border=3)
        qr.add_data(url)
        qr.make(fit=True)
        img    = qr.make_image(fill_color='#2C1503', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_b64 = base64.b64encode(buffer.getvalue()).decode()
        tables.append({
            'number': i,
            'url':    url,
            'qr_b64': img_b64,
        })
    return render(request, 'admin/table_qr_page.html', {'tables': tables})

# ← HUWAG TANGGALIN — para sa download
@staff_member_required
def generate_table_qr(request, table_number):
    url = f'http://localhost:5173/menu?table={table_number}'
    qr  = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img    = qr.make_image(fill_color='#2C1503', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="table_{table_number}_qr.png"'
    return response


# ← BAGONG VIEW — para sa page display
@staff_member_required
def table_qr_page(request):
    tables = []
    for i in range(1, 6):
        url    = f'http://localhost:5173/menu?table={i}'
        qr     = qrcode.QRCode(version=1, box_size=8, border=3)
        qr.add_data(url)
        qr.make(fit=True)
        img    = qr.make_image(fill_color='#2C1503', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        tables.append({
            'number': i,
            'url':    url,
            'qr_b64': base64.b64encode(buffer.getvalue()).decode()
        })
    return render(request, 'admin/table_qr_page.html', {'tables': tables})


def _get_paymongo_headers():
    secret_key = os.getenv("PAYMONGO_SKEY")
    encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def _create_paymongo_payment(source_id, amount, order):
    try:
        requests.post(
            "https://api.paymongo.com/v1/payments",
            headers=_get_paymongo_headers(),
            json={
                "data": {
                    "attributes": {
                        "amount": amount,
                        "currency": "PHP",
                        "source": {"id": source_id, "type": "source"},
                        "description": f"Caffeine Corner Order #{order.id}",
                    }
                }
            },
        )
    except Exception as e:
        print(f"PayMongo payment creation failed: {e}")


# ─── Create GCash Source ──────────────────────────────────────────────────────

class CreatePayMongoSourceView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        amount_cents = request.data.get('amount')
        order_id     = request.data.get('order_id')
        success_url  = request.data.get('success_url', 'http://localhost:5173/order-success')
        failed_url   = request.data.get('failed_url', 'http://localhost:5173/checkout')

        if not amount_cents or not order_id:
            return Response({'error': 'amount and order_id are required.'}, status=400)

        res = requests.post(
            "https://api.paymongo.com/v1/sources",
            headers=_get_paymongo_headers(),
            json={
                "data": {
                    "attributes": {
                        "amount":   amount_cents,
                        "currency": "PHP",
                        "type":     "gcash",
                        "redirect": {
                            "success": success_url,
                            "failed":  failed_url,
                        }
                    }
                }
            }
        )

        data = res.json()

        if res.status_code != 200:
            return Response({'error': data}, status=res.status_code)

        source_id    = data['data']['id']
        checkout_url = data['data']['attributes']['redirect']['checkout_url']

        # Save paymongo_id sa order
        Order.objects.filter(id=order_id).update(paymongo_id=source_id)

        return Response({
            'source_id':    source_id,
            'checkout_url': checkout_url,
        }, status=200)
    

# ─── Webhook ──────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def paymongo_webhook(request):
    webhook_secret = os.getenv("PAYMONGO_WEBHOOK_SECRET", "")
    sig_header     = request.headers.get("Paymongo-Signature", "")

    sig_parts = {}
    for part in sig_header.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            sig_parts[k.strip()] = v.strip()

    timestamp = sig_parts.get("t", "")
    test_sig  = sig_parts.get("te", "")
    live_sig  = sig_parts.get("li", "")

    raw_body = request.body.decode("utf-8")
    message  = f"{timestamp}.{raw_body}"
    expected = hmac.new(
        webhook_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected not in (test_sig, live_sig):
        return Response({'error': 'Invalid signature'}, status=400)

    payload    = json.loads(raw_body)
    event_type = payload.get("data", {}).get("attributes", {}).get("type", "")

    if event_type == "source.chargeable":
        source_data = payload["data"]["attributes"]["data"]
        source_id   = source_data["id"]
        amount      = source_data["attributes"]["amount"]

        order = Order.objects.filter(paymongo_id=source_id).first()
        if not order:
            return Response({'error': 'Order not found'}, status=404)

        _create_paymongo_payment(source_id, amount, order)

    elif event_type == "payment.paid":
        payment_data = payload["data"]["attributes"]["data"]
        source_id    = payment_data["attributes"].get("source", {}).get("id", "")

        order = Order.objects.filter(paymongo_id=source_id).first()
        if order:
            order.payment_status = "paid"
            order.status         = "confirmed"
            order.save()

            if order.user:
                CartItem.objects.filter(user=order.user).delete()

                # ← gamitin ang existing LoyaltyPoint.earn() method
                loyalty, _ = LoyaltyPoint.objects.get_or_create(user=order.user)
                loyalty.earn(order.total_price)

    return Response({'status': 'ok'}, status=200)

def dine_in_landing(request, table_number):
    """Landing page kapag na-scan ang QR code ng table."""
    valid_tables = ['1', '2', '3', '4', '5']
    if str(table_number) not in valid_tables:
        return render(request, 'dine_in_invalid.html', status=404)
    return render(request, 'dine_in_landing.html', {
        'table_number': table_number,
        'redirect_url': f'http://localhost:5173/menu?table={table_number}'
    })

# ─── Categories ───────────────────────────────────────────
class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True)


# ─── Products ─────────────────────────────────────────────
class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        qs = Product.objects.filter(is_available=True).select_related('category').prefetch_related('variants', 'ratings')
        category = self.request.query_params.get('category')
        featured = self.request.query_params.get('featured')
        search = self.request.query_params.get('search')
        if category:
            qs = qs.filter(category__name__iexact=category)
        if featured:
            qs = qs.filter(is_featured=True)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_available=True)



# ─── Ratings ──────────────────────────────────────────────
class RatingListCreateView(generics.ListCreateAPIView):
    serializer_class = RatingSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Rating.objects.filter(
            product_id=self.kwargs['product_id']
        ).select_related('user').order_by('-created_at')

    def perform_create(self, serializer):
        product = get_object_or_404(Product, pk=self.kwargs['product_id'])
        # Check if already rated
        if Rating.objects.filter(user=self.request.user, product=product).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError('You have already rated this product.')
        serializer.save(user=self.request.user, product=product)


# ─── Cart ─────────────────────────────────────────────────
class CartListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartItemSerializer

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('product', 'variant')


class CartAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get('product')
        variant_id = request.data.get('variant')
        quantity = int(request.data.get('quantity', 1))

        product = get_object_or_404(Product, pk=product_id)
        variant = get_object_or_404(Product, pk=variant_id) if variant_id else None

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            variant=variant,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return Response(CartItemSerializer(cart_item).data, status=status.HTTP_200_OK)


class CartUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartItemSerializer

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user)


class CartDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user)


# ─── Orders ───────────────────────────────────────────────
class OrderListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items__product', 'items__variant')

class TownZoneListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TownZoneSerializer
    queryset = TownZone.objects.filter(is_active=True)

class OrderCreateView(APIView):
    permission_classes = [AllowAny]

    GLOBAL_MIN_ORDER = 1000  # ← constant sa taas ng class

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        user       = request.user if request.user.is_authenticated else None
        order_type = data.get('order_type', 'regular')

        if user and not data.get('items'):
            cart_items = CartItem.objects.filter(user=user).select_related('product', 'variant')
            if not cart_items.exists():
                return Response({'error': 'Cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)
            data['items'] = [
                {'product': item.product.id, 'variant': item.variant.id if item.variant else None, 'quantity': item.quantity}
                for item in cart_items
            ]

        # ─── Zone Validation (regular + bulk — may delivery) ─────
        zone         = None
        delivery_fee = 0
        if order_type in ['regular', 'bulk']:
            zone_id = data.get('zone_id')
            if not zone_id:
                return Response({'error': 'Please select a delivery zone.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                zone = TownZone.objects.get(id=zone_id, is_active=True)
            except TownZone.DoesNotExist:
                return Response({'error': 'Selected zone is not available for delivery.'}, status=status.HTTP_400_BAD_REQUEST)
            delivery_fee = zone.delivery_fee

        discount    = 0
        points_used = 0
        if user and data.get('points_to_use', 0) > 0:
            try:
                loyalty     = LoyaltyPoint.objects.get(user=user)
                discount    = loyalty.redeem(data['points_to_use'])
                points_used = data['points_to_use']
            except (LoyaltyPoint.DoesNotExist, ValueError) as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.create(
            user=user,
            email=data['email'],
            address=data.get('address', ''),
            notes=data.get('notes', ''),
            payment_method=data['payment_method'],
            discount=discount,
            points_used=points_used,
            order_type=order_type,
            event_date=data.get('event_date'),
            pax=data.get('pax', 0),
            table_number=data.get('table_number', ''),
            zone=zone,
            delivery_fee=delivery_fee,
        )

        subtotal = 0
        for item_data in data['items']:
            product = get_object_or_404(Product, pk=item_data['product'])
            variant = None
            price   = product.price
            if item_data.get('variant'):
                from .models import Variant
                variant = get_object_or_404(Variant, pk=item_data['variant'])
                price  += variant.additional_price
            quantity = item_data.get('quantity', 1)
            OrderItem.objects.create(order=order, product=product, variant=variant, quantity=quantity, price=price)
            subtotal += price * quantity

        # ─── Global Minimum Order (regular + bulk lang) ─────────────
        if order_type in ['regular', 'bulk'] and subtotal < self.GLOBAL_MIN_ORDER:
            order.delete()
            return Response({
                'error': f'Minimum order amount is ₱{self.GLOBAL_MIN_ORDER:.2f}. Your order subtotal is ₱{subtotal:.2f}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ─── Minimum order check para sa zone ─────────────────────
        if zone and zone.min_order_amount > 0 and subtotal < zone.min_order_amount:
            order.delete()
            return Response({
                'error': f'Minimum order for {zone.name} is ₱{zone.min_order_amount}. Your order subtotal is ₱{subtotal}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if order_type == 'bulk':
            from decimal import Decimal
            grand_total              = subtotal + delivery_fee
            downpayment              = round(grand_total * Decimal('0.50'), 2)
            order.downpayment_amount = downpayment
            order.remaining_balance  = grand_total - downpayment
            order.payment_status     = 'unpaid'

        if user:
            loyalty, _          = LoyaltyPoint.objects.get_or_create(user=user)
            earned               = loyalty.earn(subtotal - discount)
            order.points_earned  = earned

        order.save()

        if user and order_type == 'regular':
            CartItem.objects.filter(user=user).delete()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.prefetch_related('items__product', 'items__variant')


# ─── Loyalty Points ───────────────────────────────────────
class LoyaltyPointView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LoyaltyPointSerializer

    def get_object(self):
        loyalty, _ = LoyaltyPoint.objects.get_or_create(user=self.request.user)
        return loyalty
