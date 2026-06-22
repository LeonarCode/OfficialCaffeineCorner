import random
from django.core.mail import send_mail
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(email, code):
    send_mail(
        subject='Your Caffeine Corner Sign In Code',
        message=f'Your one-time code is: {code}\n\nThis code expires in 5 minutes.',
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[email],
        fail_silently=False,
    )
    
