import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eform.settings')
django.setup()

from django.contrib.auth.models import User

def update_emails():
    emails = {
        'user': 'voquy1354@gmail.com',
        'checker': '22010307@st.phenikaa-uni.edu.vn',
        'manager': 'chiquy313@gmail.com'
    }
    
    for username, email in emails.items():
        try:
            u = User.objects.get(username=username)
            u.email = email
            u.save()
            print(f"Updated {username} with email {email}")
        except User.DoesNotExist:
            print(f"User {username} does not exist.")

if __name__ == '__main__':
    update_emails()
