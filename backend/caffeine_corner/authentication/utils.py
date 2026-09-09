import random
from django.core.mail import EmailMultiAlternatives
from django.conf import settings


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, code):
    subject      = 'Your Caffeine Corner Sign In Code'
    text_content = f'Your one-time code is: {code}\n\nThis code expires in 5 minutes.'

    html_content = f'''
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #FAF6F0;">
      <div style="text-align: center; margin-bottom: 24px;">
        <h1 style="color: #2C1503; font-size: 20px; letter-spacing: 2px;">CAFFEINE CORNER</h1>
      </div>
      <div style="background: white; border-radius: 16px; padding: 32px; text-align: center;">
        <p style="color: #6b7280; font-size: 14px; margin-bottom: 8px;">Your one-time sign in code is</p>
        <p style="color: #2C1503; font-size: 36px; font-weight: bold; letter-spacing: 8px; margin: 16px 0;">{code}</p>
        <p style="color: #9ca3af; font-size: 12px;">This code expires in 5 minutes.</p>
      </div>
      <p style="color: #9ca3af; font-size: 11px; text-align: center; margin-top: 24px;">
        If you did not request this code, please ignore this email.
      </p>
    </div>
    '''

    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        [email],
    )
    msg.attach_alternative(html_content, 'text/html')
    msg.send(fail_silently=False)
    
