from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import OTPCode
from .serializer import SendOTPSerializer, VerifyOTPSerializer
from .utils import generate_otp, send_otp_email
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

User = get_user_model()

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_me(request):
    return Response({
        'email': request.user.email,
        'id': request.user.id,
    })

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def profile(request):
    user = request.user

    if request.method == 'GET':
        return Response({
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'date_joined': user.date_joined,
        })

    if request.method == 'PUT':
        username = request.data.get('username', user.username)
        user.username = username
        user.save()
        return Response({
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'date_joined': user.date_joined,
        })

class SendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = generate_otp()
            OTPCode.objects.create(email=email, code=code)
            send_otp_email(email, code)
            return Response({'message': 'OTP sent successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']

            otp = OTPCode.objects.filter(
                email=email,
                code=code,
                is_used=False
            ).last()

            if not otp:
                return Response({'error': 'Invalid code.'}, status=status.HTTP_400_BAD_REQUEST)

            if otp.is_expired():
                return Response({'error': 'Code has expired.'}, status=status.HTTP_400_BAD_REQUEST)

            otp.is_used = True
            otp.save()

            user, _ = User.objects.get_or_create(email=email)
            tokens = get_tokens_for_user(user)
            return Response(tokens, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = 'http://localhost:5173'
    client_class = OAuth2Client


class FacebookLoginView(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    callback_url = 'http://localhost:5173'
    client_class = OAuth2Client