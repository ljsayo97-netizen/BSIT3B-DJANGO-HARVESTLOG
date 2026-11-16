from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods, require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse


def _is_superuser(user):
    return user.is_superuser


def _is_regular_user(user):
    """Check if user is a regular farmer (not staff/superuser)."""
    return not user.is_staff and not user.is_superuser


# PAGE
@login_required(login_url='login')
def user_list_page(request):
    query = request.GET.get('q', '').strip()

    users_list = User.objects.all().order_by('-date_joined')

    if query:
        users_list = users_list.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)

    return render(request, 'users/list.html', {
        'users': users,
        'query': query,
    })


# LIST USERS (AJAX)
@login_required(login_url='login')
def user_list_ajax(request):
    users_list = User.objects.all().order_by('-date_joined')
    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)
    data = list(users.object_list.values(
        'id',
        'username',
        'first_name',
        'last_name',
        'email',
        'is_staff',
        'is_active',
        'date_joined',
    ))
    return JsonResponse({
        "data":     data,
        "has_next": users.has_next(),
        "has_prev": users.has_previous(),
        "page":     users.number,
        "pages":    users.paginator.num_pages,
        "total":    users.paginator.count,
    })


# GET SINGLE USER (AJAX)
@login_required(login_url='login')
def user_get_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    return JsonResponse({
        "id":         user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "is_staff":   user.is_staff,
        "is_active":  user.is_active,
    })


# CREATE / UPDATE USER (AJAX)
@login_required(login_url='login')
@require_POST
def user_save_ajax(request):
    """Validate and create or update a user, returning its data as JSON."""
    user_id = request.POST.get("id")

    if user_id:
        user = get_object_or_404(User, pk=user_id)
        is_update = True
    else:
        user = User()
        is_update = False

    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()

    if not username:
        return JsonResponse({"error": "Username is required."}, status=400)

    dup_qs = User.objects.filter(Q(username=username) | (Q(email=email) & ~Q(email="")))
    if user_id:
        dup_qs = dup_qs.exclude(pk=user_id)
    if dup_qs.filter(username=username).exists():
        return JsonResponse({"error": "That username is already taken."}, status=400)
    if email and dup_qs.filter(email=email).exists():
        return JsonResponse({"error": "That email is already in use."}, status=400)

    user.username   = username
    user.first_name = request.POST.get("first_name", "")
    user.last_name  = request.POST.get("last_name", "")
    user.email      = email
    user.is_staff   = request.POST.get("is_staff") == "true"
    user.is_active  = request.POST.get("is_active") == "true"

    password = request.POST.get("password")
    if password:
        user.set_password(password)
    elif not user_id:
        return JsonResponse({"error": "Password is required for new users."}, status=400)

    try:
        user.save()
    except IntegrityError:
        return JsonResponse({"error": "Could not save user due to a conflict (duplicate username/email)."}, status=400)

    messages.success(
        request,
        f'User "{user.username}" has been {"updated" if is_update else "saved"} successfully.'
    )

    return JsonResponse({
        "status": "success",
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
    })


# DELETE USER (AJAX)
@login_required(login_url='login')
@require_POST
def user_delete_ajax(request, pk):
    """Delete the specified user and confirm as JSON."""
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({"error": "You cannot delete yourself"}, status=400)
    username = user.username
    user.delete()
    return JsonResponse({
        "status": "deleted",
        "message": f'User "{username}" has been deleted successfully.',
    })


# TOGGLE USER ACTIVE STATUS (AJAX)
@login_required(login_url='login')
@require_POST
def user_toggle_active_ajax(request, pk):
    """Activate or deactivate the specified user and confirm as JSON."""
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(
        request,
        f'User "{user.username}" has been '
        f'{"reactivated" if user.is_active else "deactivated"} successfully.',
    )
    return JsonResponse({
        "status": "success",
        "is_active": user.is_active,
        "message": f'User "{user.username}" has been '
                   f'{"reactivated" if user.is_active else "deactivated"} successfully.',
    })


# AUTHENTICATION PAGES
@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        # Role-based redirection
        if _is_regular_user(request.user):
            return redirect('farmer_dashboard')
        return redirect('dashboard')

    failed_attempts, remaining = _get_lock_state(request)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is not None:
        _reset_lock_state(request)
        login(request, user)
        # Role-based redirection after login
        if _is_regular_user(user):
            return redirect('farmer_dashboard')
        return redirect('dashboard')

    failed_attempts += 1
    request.session['failed_attempts'] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        remaining = _set_lock_state(request)
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(request, 'auth/login.html')


def _reset_lock_state(request):
    request.session['failed_attempts'] = 0
    request.session['lock_time'] = None


def _get_lock_state(request):
    failed_attempts = request.session.get('failed_attempts', 0)
    lock_time = request.session.get('lock_time')

    if not lock_time:
        return failed_attempts, None

    try:
        unlock_time = timezone.datetime.fromisoformat(lock_time)
    except (TypeError, ValueError):
        _reset_lock_state(request)
        return 0, None

    if timezone.now() < unlock_time:
        remaining = int((unlock_time - timezone.now()).total_seconds())
        return failed_attempts, remaining

    _reset_lock_state(request)
    return 0, None


def _set_lock_state(request):
    lock_until = timezone.now() + LOCK_DURATION
    request.session['failed_attempts'] = MAX_FAILED_ATTEMPTS
    request.session['lock_time'] = lock_until.isoformat()
    return int(LOCK_DURATION.total_seconds())


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        # Role-based redirection
        if _is_regular_user(request.user):
            return redirect('farmer_dashboard')
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )
    login(request, user)
    # Role-based redirection after register
    if _is_regular_user(user):
        return redirect('farmer_dashboard')
    return redirect('dashboard')


@login_required(login_url='login')
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def home(request):
    """Render the farm operations dashboard for the signed-in user."""
    return render(
        request,
        'home.html',
        build_dashboard_context(request.user, year=request.GET.get('year')),
    )


@login_required(login_url='login')
def farmer_dashboard(request):
    """Render the farmer dashboard for regular users."""
    from .dashboard import build_farmer_dashboard_context
    
    context = build_farmer_dashboard_context(request.user)
    return render(request, 'users/farmer_dashboard.html', context)


@login_required(login_url='login')
def connected_users(request):
    """Render the connected users dashboard for admins."""
    from datetime import timedelta
    from django.utils import timezone
    
    # Get users who have logged in within the last 24 hours
    recent_cutoff = timezone.now() - timedelta(hours=24)
    recent_users = User.objects.filter(last_login__gte=recent_cutoff).order_by('-last_login')
    
    # Get all users for comparison
    all_users = User.objects.all().order_by('-date_joined')
    
    # Calculate activity status for each user
    now = timezone.now()
    user_activity = []
    for u in all_users:
        if not u.last_login:
            status = 'Never logged in'
            last_seen = 'N/A'
        else:
            diff = now - u.last_login
            total_seconds = int(diff.total_seconds())
            if total_seconds < 3600:
                last_seen = 'Just now'
                status = 'Online'
            elif total_seconds < 86400:
                hours = total_seconds // 3600
                last_seen = '%d hours ago' % hours
                status = 'Recently active'
            elif total_seconds < 604800:
                days = total_seconds // 86400
                last_seen = '%d days ago' % days
                status = 'Active this week'
            else:
                weeks = total_seconds // 604800
                last_seen = '%d weeks ago' % weeks
                status = 'Inactive'
        
        user_activity.append({
            'user': u,
            'status': status,
            'last_seen': last_seen,
        })
    
    # Sort: online first, then by last login time
    user_activity.sort(key=lambda x: (0 if x['status'] == 'Online' else 1, x['user'].last_login or timezone.datetime.min), reverse=False)
    
    return render(
        request,
        'users/connected_users.html',
        {
            'recent_users': recent_users,
            'user_activity': user_activity,
            'now': now,
        }
    )