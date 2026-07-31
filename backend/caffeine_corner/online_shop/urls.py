from django.urls import path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    RatingListCreateView, CartListView, CartAddView,
    CartUpdateView, CartDeleteView,
    OrderListView, OrderCreateView, OrderDetailView,
    LoyaltyPointView, RatingListCreateView, paymongo_webhook, CreatePayMongoSourceView, TownZoneListView
)

urlpatterns = [
    # Categories
    path('categories/', CategoryListView.as_view(), name='categories'),

    # Products
    path('products/', ProductListView.as_view(), name='products'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:product_id>/reviews/', RatingListCreateView.as_view(), name='product-reviews'),

    # Cart
    path('cart/', CartListView.as_view(), name='cart'),
    path('cart/add/', CartAddView.as_view(), name='cart-add'),
    path('cart/<int:pk>/update/', CartUpdateView.as_view(), name='cart-update'),
    path('cart/<int:pk>/delete/', CartDeleteView.as_view(), name='cart-delete'),

    # Orders
    path('orders/', OrderListView.as_view(), name='orders'),
    path('orders/create/', OrderCreateView.as_view(), name='order-create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),

    # Loyalty
    path('loyalty/', LoyaltyPointView.as_view(), name='loyalty'),

    # paymoney integration would go here
    path('paymongo/webhook/', paymongo_webhook, name='paymongo-webhook'),
    path('paymongo/create-source/', CreatePayMongoSourceView.as_view(), name='create-paymongo-source'),
    # Town Zones
    path('zones/', TownZoneListView.as_view(), name='zones'),
]