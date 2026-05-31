"""
Authentication Routes Blueprint
Handles Neon Auth callbacks, email verification, session management, and tenant selection
"""
from flask import (
    Blueprint, request, redirect, url_for, jsonify,
    session, current_app, flash, render_template
)
import logging
import requests as http_requests
from app.services.auth_service import AuthService, neon_auth
from app.models.user import User
from app.extensions import db

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# LOCAL LOGIN (dev fallback — no Neon Auth required)
# =============================================================================

@auth_bp.route('/signup', methods=['POST'])
def local_signup():
    """Create a new user account for local development (no Neon Auth required)."""
    from werkzeug.security import generate_password_hash
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    confirm = data.get('confirm') or ''

    if not name or not email or not password:
        return jsonify({'error': 'Name, email and password are required'}), 400

    if confirm and password != confirm:
        return jsonify({'error': 'Passwords do not match'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    existing = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()

    if existing and existing.is_active:
        return jsonify({'error': 'An account with this email already exists'}), 400

    if existing and not existing.is_active:
        # Placeholder created by an invite — activate it instead
        existing.password_hash = generate_password_hash(password)
        existing.is_active = True
        existing.email_verified = True
        if name and not existing.username:
            existing.username = name
        db.session.commit()
        user = existing
    else:
        base_username = (name or email.split('@')[0]).replace(' ', '_').lower()
        username = base_username
        counter = 1
        while db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none():
            username = f"{base_username}{counter}"
            counter += 1
        user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            is_active=True,
            email_verified=True,
        )
        db.session.add(user)
        db.session.commit()

    auth_service = AuthService()
    session['user_id'] = user.user_id
    session['username'] = user.username
    session['logged_in'] = True
    session['auth_method'] = 'local'
    user.update_last_login()
    db.session.commit()

    redirect_url = auth_service.resolve_post_auth_redirect(user.user_id)
    return jsonify({'redirect': redirect_url})


@auth_bp.route('/login', methods=['POST'])
def local_login():
    """Traditional email/password login for local development."""
    from werkzeug.security import check_password_hash
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()

    # Invited but never activated — prompt them to set a password
    if user and not user.is_active and not user.password_hash:
        return jsonify({'error': 'Account not yet activated. Please use the invitation link or contact your administrator.'}), 401

    if not user or not user.is_active or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    auth_service = AuthService()
    session['user_id'] = user.user_id
    session['username'] = user.username
    session['logged_in'] = True
    session['auth_method'] = 'local'
    user.update_last_login()
    db.session.commit()

    redirect_url = auth_service.resolve_post_auth_redirect(user.user_id)
    return jsonify({'redirect': redirect_url})


@auth_bp.route('/activate', methods=['POST'])
def activate_account():
    """Activate an invited (placeholder) account by setting a password."""
    from werkzeug.security import generate_password_hash
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()

    if not user:
        return jsonify({'error': 'No invitation found for this email'}), 404

    if user.is_active and user.password_hash:
        return jsonify({'error': 'Account already activated. Please log in.'}), 400

    user.password_hash = generate_password_hash(password)
    user.is_active = True
    user.email_verified = True
    db.session.commit()

    auth_service = AuthService()
    session['user_id'] = user.user_id
    session['username'] = user.username
    session['logged_in'] = True
    session['auth_method'] = 'local'
    user.update_last_login()
    db.session.commit()

    redirect_url = auth_service.resolve_post_auth_redirect(user.user_id)
    return jsonify({'redirect': redirect_url})


# =============================================================================
# LOGIN PAGE
# =============================================================================

@auth_bp.route('/login')
def login():
    """Render the login/signup page"""
    if session.get('logged_in') and session.get('current_tenant_id'):
        return redirect(url_for('main.dashboard'))
    local_dev = current_app.config.get('LOCAL_DEV', False)
    return render_template('auth/login.html', local_dev=local_dev)


# =============================================================================
# NEON AUTH CALLBACK ROUTES
# =============================================================================

@auth_bp.route('/callback')
def callback():
    """
    OAuth callback handler for Neon Auth.

    Two scenarios land here:
      1. Direct landing with a Better Auth session cookie or a `?token=` query
         (browsers that allow third-party cookies for the auth domain).
      2. Better Auth's oauth-proxy redirect with `?neon_auth_session_verifier=<v>`
         (Safari / Brave / Firefox strict — cookies on the auth domain aren't
         reachable cross-site). In that case we redirect the browser to
         Better Auth's `/callback/oauth-proxy` endpoint, which decrypts the
         verifier server-side and forwards back here with the actual session
         token appended to the URL.
    """
    try:
        session_token = request.cookies.get('better-auth.session_token')
        if not session_token:
            session_token = request.args.get('token')

        if session_token:
            auth_service = AuthService()
            user = auth_service.authenticate_jwt(session_token)

            if user:
                auth_service.establish_session(user)
                redirect_url = auth_service.resolve_post_auth_redirect(user.user_id)
                return redirect(redirect_url)

        # Verifier path — exchange via Better Auth's oauth-proxy callback.
        verifier = request.args.get('neon_auth_session_verifier')
        if verifier:
            auth_url = (current_app.config.get('NEON_AUTH_URL') or '').rstrip('/')
            if auth_url:
                from urllib.parse import urlencode
                # Final return URL: same callback minus the verifier so this branch
                # doesn't loop. Better Auth will append the session token.
                final_callback = url_for('auth.callback', _external=True)
                proxy_url = (
                    f"{auth_url}/callback/oauth-proxy?"
                    + urlencode({
                        'neon_auth_session_verifier': verifier,
                        'callbackURL': final_callback,
                    })
                )
                logger.info("OAuth callback: forwarding verifier to Better Auth oauth-proxy")
                return redirect(proxy_url)

        # No server-side token available — render bridge page that fetches
        # the session from Neon Auth client-side and forwards to Flask
        logger.info("OAuth callback without server-side token, rendering bridge page")
        return render_template('auth/oauth_completing.html')

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))


@auth_bp.route('/neon-callback', methods=['POST'])
def neon_callback():
    """
    API endpoint for JavaScript client to notify backend of successful auth.
    Called after sign-in or sign-up + verification via neon-auth.js.
    Accepts token from request body (preferred) or falls back to cookie.
    """
    try:
        # Try token from request body first (works cross-origin)
        session_token = None
        body = request.get_json(silent=True) or {}

        if body.get('token'):
            session_token = body['token']

        # Fall back to cookie
        if not session_token:
            session_token = request.cookies.get('better-auth.session_token')

        if not session_token:
            return jsonify({'error': 'No session token'}), 401

        auth_service = AuthService()
        user = auth_service.authenticate_jwt(session_token)

        if not user:
            # Fallback: client may have passed user data from getSession()
            client_user = body.get('user')
            if client_user and client_user.get('id') and client_user.get('email'):
                # Clean up any dirty DB transaction from failed lookups
                try:
                    db.session.rollback()
                except Exception:
                    pass
                fallback_payload = {
                    'sub': client_user['id'],
                    'email': client_user['email'],
                    'name': client_user.get('name', ''),
                    'email_verified': client_user.get('emailVerified', False),
                }
                user = User.authenticate_with_jwt(fallback_payload)

        if user:
            auth_service.establish_session(user)
            redirect_url = auth_service.resolve_post_auth_redirect(user.user_id)

            return jsonify({
                'success': True,
                'user': user.to_dict(),
                'redirect': redirect_url,
            })

        logger.warning("neon-callback: authentication failed")
        return jsonify({'error': 'Invalid session'}), 401

    except Exception as e:
        logger.error(f"Neon callback error: {e}")
        return jsonify({'error': 'Authentication failed. Please try again.'}), 500


# =============================================================================
# EMAIL VERIFICATION
# =============================================================================

@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """Proxy email OTP verification to Neon Auth"""
    try:
        data = request.get_json()
        email = data.get('email')
        otp = data.get('otp')

        if not email or not otp:
            return jsonify({'error': 'Email and verification code are required'}), 400

        neon_auth_url = current_app.config.get('NEON_AUTH_URL', '').rstrip('/')
        if not neon_auth_url:
            return jsonify({'error': 'Auth service not configured'}), 500

        response = http_requests.post(
            f"{neon_auth_url}/email-otp/verify-email",
            json={'email': email, 'otp': otp},
            timeout=10
        )

        if response.ok:
            return jsonify({'success': True})

        error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        return jsonify({
            'error': error_data.get('message', 'Verification failed')
        }), response.status_code

    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/verify-email')
def verify_email_page():
    """Standalone email verification page for users who navigated away"""
    return render_template('auth/verify_email.html')


# =============================================================================
# FORGOT PASSWORD PROXY
# =============================================================================

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Proxy forgot-password requests to Neon Auth to avoid cross-origin issues"""
    try:
        data = request.get_json(silent=True) or {}
        email = data.get('email')

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        neon_auth_url = current_app.config.get('NEON_AUTH_URL', '').rstrip('/')
        if not neon_auth_url:
            return jsonify({'error': 'Auth service not configured'}), 500

        response = http_requests.post(
            f"{neon_auth_url}/forget-password/email",
            json={'email': email},
            timeout=10
        )

        if response.ok:
            return jsonify({'success': True})

        error_data = {}
        if response.headers.get('content-type', '').startswith('application/json'):
            error_data = response.json()
        return jsonify({
            'error': error_data.get('message', 'Could not send reset email')
        }), response.status_code

    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# SESSION & API ROUTES
# =============================================================================

@auth_bp.route('/session')
def get_session():
    """Get current session info for the frontend"""
    if session.get('logged_in'):
        return jsonify({
            'authenticated': True,
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('current_role'),
            'tenant_id': session.get('current_tenant_id'),
            'auth_method': session.get('auth_method', 'neon_auth')
        })

    return jsonify({'authenticated': False})


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """API endpoint for logout"""
    try:
        # Clear Flask session
        session.clear()

        response_data = {
            'success': True,
            'message': 'Logged out successfully'
        }

        # Include Neon Auth sign-out URL for client-side cleanup
        neon_auth_url = current_app.config.get('NEON_AUTH_URL', '')
        if neon_auth_url:
            response_data['neon_signout_url'] = f"{neon_auth_url.rstrip('/')}/sign-out"

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify a Neon Auth JWT token"""
    try:
        data = request.get_json()
        token = data.get('token')

        if not token:
            return jsonify({'valid': False, 'error': 'No token provided'}), 400

        payload = neon_auth.verify_token(token)

        if payload:
            return jsonify({
                'valid': True,
                'payload': {
                    'sub': payload.get('sub'),
                    'email': payload.get('email'),
                    'name': payload.get('name')
                }
            })

        return jsonify({'valid': False, 'error': 'Invalid token'}), 401

    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return jsonify({'valid': False, 'error': str(e)}), 500


@auth_bp.route('/link-account', methods=['POST'])
def link_account():
    """Link a Neon Auth account to an existing local user account"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.get_json()
        neon_auth_user_id = data.get('neon_auth_user_id')

        if not neon_auth_user_id:
            return jsonify({'error': 'No Neon Auth user ID provided'}), 400

        user_id = session.get('user_id')
        user = User.find_by_id(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        existing = User.find_by_neon_auth_id(neon_auth_user_id)
        if existing and existing.user_id != user.user_id:
            return jsonify({'error': 'This account is already linked to another user'}), 400

        user.neon_auth_user_id = neon_auth_user_id
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Account linked successfully'
        })

    except Exception as e:
        logger.error(f"Account linking error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/status')
def auth_status():
    """Check auth provider configuration status"""
    return jsonify({
        'neon_auth_configured': bool(current_app.config.get('NEON_AUTH_URL'))
    })


# =============================================================================
# NO ORGANIZATION PAGE
# =============================================================================

@auth_bp.route('/no-organization')
def no_organization():
    """Page shown when authenticated user has no tenant memberships"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

    # Check for pending invitations before showing "no org" page
    from app.services.tenant_service import TenantService
    tenant_service = TenantService()
    user_id = session.get('user_id')
    pending = tenant_service.get_pending_invitations(user_id)
    if pending:
        return redirect(url_for('auth.invitations'))

    return render_template('auth/no_organization.html')


@auth_bp.route('/invitations')
def invitations():
    """Show pending invitations for the current user"""
    if not session.get('logged_in'):
        flash('Please log in first', 'warning')
        return redirect(url_for('auth.login'))

    from app.services.tenant_service import TenantService
    tenant_service = TenantService()
    user_id = session.get('user_id')

    pending = tenant_service.get_pending_invitations(user_id)
    active_tenants = tenant_service.get_user_tenants(user_id)

    return render_template(
        'auth/invitations.html',
        invitations=pending,
        has_active_tenants=len(active_tenants) > 0,
    )


@auth_bp.route('/invitations/<int:membership_id>/accept', methods=['POST'])
def accept_invitation(membership_id):
    """Accept a pending invitation"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

    from app.services.tenant_service import TenantService
    from app.services.auth_service import AuthService

    tenant_service = TenantService()
    auth_service = AuthService()
    user_id = session.get('user_id')

    success, errors = tenant_service.accept_invitation(membership_id, user_id)

    if success:
        # Get the membership to establish tenant session
        from app.models.tenant_membership import TenantMembership
        membership = TenantMembership.find_by_id(membership_id)
        if membership:
            auth_service.establish_tenant_session(user_id, membership.tenant_id)
        flash('Invitation accepted! Welcome to the team.', 'success')
        return redirect(url_for('main.dashboard'))
    else:
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('auth.invitations'))


@auth_bp.route('/invitations/<int:membership_id>/decline', methods=['POST'])
def decline_invitation(membership_id):
    """Decline a pending invitation"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

    from app.services.tenant_service import TenantService

    tenant_service = TenantService()
    user_id = session.get('user_id')

    success, errors = tenant_service.decline_invitation(membership_id, user_id)

    if success:
        flash('Invitation declined.', 'info')
    else:
        for error in errors:
            flash(error, 'error')

    return redirect(url_for('auth.invitations'))


# =============================================================================
# MULTI-TENANT ROUTES
# =============================================================================

@auth_bp.route('/select-tenant')
def select_tenant():
    """Tenant selection page - shown when user has multiple organizations"""
    if not session.get('logged_in'):
        flash('Please log in first', 'warning')
        return redirect(url_for('auth.login'))

    from app.services.tenant_service import TenantService
    tenant_service = TenantService()
    user_id = session.get('user_id')
    tenants = tenant_service.get_user_tenants(user_id)

    if not tenants:
        return redirect(url_for('auth.no_organization'))

    if len(tenants) == 1:
        tenant = tenants[0]
        session['current_tenant_id'] = tenant['tenant_id']
        session['current_tenant_slug'] = tenant['slug']
        session['current_tenant_name'] = tenant['name']
        session['current_role'] = tenant['role']
        return redirect(url_for('main.dashboard'))

    return render_template('auth/select_tenant.html', tenants=tenants)


@auth_bp.route('/switch-tenant', methods=['POST'])
def switch_tenant():
    """Switch active tenant context"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401

    tenant_slug = request.form.get('tenant_slug') or (request.get_json(silent=True) or {}).get('tenant_slug')
    if not tenant_slug:
        flash('No organization specified', 'error')
        return redirect(url_for('auth.select_tenant'))

    from app.services.tenant_service import TenantService
    from app.models.tenant import Tenant

    tenant = Tenant.find_by_slug(tenant_slug)
    if not tenant:
        flash('Organization not found', 'error')
        return redirect(url_for('auth.select_tenant'))

    tenant_service = TenantService()
    user_tenants = tenant_service.get_user_tenants(session.get('user_id'))
    tenant_data = next((t for t in user_tenants if t['slug'] == tenant_slug), None)

    if not tenant_data:
        flash('You are not a member of this organization', 'error')
        return redirect(url_for('auth.select_tenant'))

    session['current_tenant_id'] = tenant_data['tenant_id']
    session['current_tenant_slug'] = tenant_data['slug']
    session['current_tenant_name'] = tenant_data['name']
    session['current_role'] = tenant_data['role']

    flash(f'Switched to {tenant_data["name"]}', 'success')
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/register-organization', methods=['GET', 'POST'])
def register_organization():
    """Register a new organization (tenant)"""
    if not session.get('logged_in'):
        flash('Please log in first', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return render_template('auth/register_organization.html')

    from app.services.tenant_service import TenantService
    from app.utils.validators import sanitize_input

    name = sanitize_input(request.form.get('name', ''))
    business_type = sanitize_input(request.form.get('business_type', 'auto_repair'))
    email = sanitize_input(request.form.get('email', ''))
    phone = sanitize_input(request.form.get('phone', ''))
    address = sanitize_input(request.form.get('address', ''))

    if not name or len(name) < 2:
        flash('Organization name must be at least 2 characters', 'error')
        return render_template('auth/register_organization.html')

    tenant_service = TenantService()
    user_id = session.get('user_id')

    success, errors, tenant = tenant_service.create_tenant(
        name=name,
        owner_user_id=user_id,
        business_type=business_type,
        email=email or None,
        phone=phone or None,
        address=address or None,
    )

    if success:
        session['current_tenant_id'] = tenant.tenant_id
        session['current_tenant_slug'] = tenant.slug
        session['current_tenant_name'] = tenant.name
        session['current_role'] = 'owner'

        flash(f'Organization "{tenant.name}" created successfully!', 'success')
        return redirect(url_for('onboarding.step', step_number=1))
    else:
        for error in errors:
            flash(error, 'error')
        return render_template('auth/register_organization.html')
