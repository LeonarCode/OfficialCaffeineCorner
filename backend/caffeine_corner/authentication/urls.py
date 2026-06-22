from django.urls import path
from .views import SendOTPView, VerifyOTPView, GoogleLoginView, FacebookLoginView, get_me, profile

urlpatterns = [
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('google/', GoogleLoginView.as_view(), name='google-login'),
    path('facebook/', FacebookLoginView.as_view(), name='facebook-login'),
    path('me/', get_me, name='get-me'),
    path('profile/', profile, name='profile'),
]