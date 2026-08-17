from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from inertia import inertia
from inertia.http import clear_history


@inertia("Login")
def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return {}


@require_POST
def logout(request):
    auth_logout(request)
    clear_history(request)
    return redirect("home")
