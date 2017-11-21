from hashlib import sha256

from django.shortcuts import redirect
from django.core.urlresolvers import resolve
try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    MiddlewareMixin = object

from allauth.account.adapter import get_adapter


class AllauthTwoFactorMiddleware(MiddlewareMixin):
    """
    Reset the login flow if another page is loaded halfway through the login.
    (I.e. if the user has logged in with a username/password, but not yet
    entered their two-factor credentials.) This makes sure a user does not stay
    half logged in by mistake.

    """

    def process_request(self, request):
        match = resolve(request.path)
        if not match.url_name or not match.url_name.startswith(
                'two-factor-authenticate'):
            try:
                del request.session['allauth_2fa_user_id']
            except KeyError:
                pass


class BaseRequire2FAMiddleware(MiddlewareMixin):
    """
    Ensure that particular users have two-factor authentication enabled before
    they have access to the rest of the app.

    If they don't have 2FA enabled, they will be redirected to the 2FA
    enrollment page and not be allowed to access other pages.
    """

    # List of URL names that the user should still be allowed to access.
    allowed_pages = [
        # They should still be able to log out or change password.
        'account_change_password',
        'account_logout',
        'account_reset_password',

        # URLs required to set up two-factor
        'two-factor-setup',
        'two-factor-qr-code',
    ]
    # The message to the user if they don't have 2FA enabled and must enable it.
    require_2fa_message = "You must enable two-factor authentication before doing anything else."

    def require_2fa(self, request):
        """
        Check if this request is required to have 2FA before accessing the app.

        This should return True if this request requires 2FA. (Note that the user was already)

        You can access anything on the request, but generally request.user will
        be most interesting here.
        """
        raise NotImplemented('You must implement test_request.')

    def process_view(self, request, view_func, view_args, view_kwargs):
        # The user is not logged in, do nothing.
        if request.user.is_anonymous:
            return

        # If this doesn't require 2FA, then stop processing.
        if not self.require_2fa(request):
            return

        # If the user is on one of the allowed pages, do nothing.
        if request.path in map(reverse, self.allowed_pages):
            return

        # User already has two-factor configured, do nothing.
        if get_adapter(request).has_2fa_enabled(request.user):
            return

        # If there is already a pending message related to two-factor (likely
        # created by a redirect view), simply update the message text. Make sure
        # to mark the storage as not processed.
        storage = messages.get_messages(request)
        # Base this on the class name so this can be subclassed multiple times,
        # don't just use the class name though since this ends up in the HTML.
        tag = sha256('{}.{}'.format(self.__module__, self.__name__)).hexdigest()
        for m in storage:
            if m.extra_tags == tag:
                m.message = self.require_2fa_message
                storage.used = False
                break
        # Otherwise, create a new message.
        else:
            storage.used = False
            messages.error(request, self.require_2fa_message, extra_tags=tag)

        # Redirect user to two-factor setup page.
        return redirect('two-factor-setup')
