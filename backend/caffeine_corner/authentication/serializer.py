from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password

class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

class SocialAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    provider = serializers.ChoiceField(choices=['google', 'facebook'])


class RiderRegisterSerializer(serializers.Serializer):
    email            = serializers.EmailField()
    username         = serializers.CharField(max_length=150)
    phone            = serializers.CharField(max_length=15)
    password         = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        from .models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return data


class RiderLoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        from .models import User
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or password.')

        if not check_password(data['password'], user.password):
            raise serializers.ValidationError('Invalid email or password.')

        if not user.is_rider:
            raise serializers.ValidationError('This account is not registered as a rider.')

        data['user'] = user
        return data