import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eform.settings')
django.setup()

from django.contrib.auth.models import Group, User

def setup_rbac():
    print("--- Starting RBAC Configuration ---")
    
    # 1. Create Groups if they don't exist
    checker_group, created1 = Group.objects.get_or_create(name='Checker')
    if created1:
        print("Created Group: Checker")
    else:
        print("Group Checker already exists")

    manager_group, created2 = Group.objects.get_or_create(name='Manager')
    if created2:
        print("Created Group: Manager")
    else:
        print("Group Manager already exists")

    # 2. Create test accounts
    # Checker Account
    checker_user, created_c = User.objects.get_or_create(username='checker')
    if created_c:
        checker_user.set_password('123456aA@')
        checker_user.save()
        print("Created test Checker account: checker / 123456aA@")
    checker_group.user_set.add(checker_user)

    # Manager Account
    manager_user, created_m = User.objects.get_or_create(username='manager')
    if created_m:
        manager_user.set_password('123456aA@')
        manager_user.save()
        print("Created test Manager account: manager / 123456aA@")
    manager_group.user_set.add(manager_user)

    # Submitter Account (Regular User)
    user, created_u = User.objects.get_or_create(username='user')
    if created_u:
        user.set_password('123456aA@')
        user.save()
        print("Created test Submitter account: user / 123456aA@")

    # Add superusers to groups
    admins = User.objects.filter(is_superuser=True)
    for admin in admins:
        checker_group.user_set.add(admin)
        manager_group.user_set.add(admin)
        print(f"Added admin '{admin.username}' to both Checker & Manager groups for easy testing.")

    print("--- RBAC Configuration Completed ---")

if __name__ == '__main__':
    setup_rbac()
