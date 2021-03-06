"""
This module uses oauth to allow applications and users access.
Supports 2-legged oauth for application requests, and for trusted
applications accessing user-restricted methods.  Supports 3-legged
oauth for non-trusted applications that want to access user methods.

To use this module, add this to your settings.py:

SPOTSEEKER_AUTH_MODULE = spotseeker_server.auth.oauth

"""
from django.http import HttpResponse

from oauth_provider.utils import get_oauth_request, verify_oauth_request
from oauth_provider.store import store, InvalidConsumerError, InvalidTokenError
from spotseeker_server.models import TrustedOAuthClient


def authenticate_application(*args, **kwargs):
    request = args[1]
    try:
        oauth_request = get_oauth_request(request)
        consumer = store.get_consumer(request, oauth_request,
                                      oauth_request['oauth_consumer_key'])
        verify_oauth_request(request, oauth_request, consumer)

        request.META['SS_OAUTH_CONSUMER_NAME'] = consumer.name
        request.META['SS_OAUTH_CONSUMER_PK'] = consumer.pk

        return
    except Exception as e:
        response = HttpResponse("Error authorizing application")
        response.status_code = 401
        return response


def authenticate_user(*args, **kwargs):
    request = args[1]
    try:
        oauth_request = get_oauth_request(request)
        consumer = store.get_consumer(request, oauth_request,
                                      oauth_request['oauth_consumer_key'])
        verify_oauth_request(request, oauth_request, consumer)

        # Allow a trusted client to either give us a user via header, or do the
        # 3-legged oauth
        try:
            trusted_client = TrustedOAuthClient.objects.get(consumer=consumer)
        except Exception as e:
            pass

        if trusted_client and trusted_client.is_trusted:
            user = request.META["HTTP_XOAUTH_USER"]

        if not user:
            access_token = store.get_access_token(request, oauth_request, consumer, oauth_request[u'oauth_token'])
            user = store.get_user_for_access_token(request, oauth_request, access_token)

        request.META['SS_OAUTH_CONSUMER_NAME'] = consumer.name
        request.META['SS_OAUTH_CONSUMER_PK'] = consumer.pk
        request.META['SS_OAUTH_USER'] = user

        return
    except Exception as e:
        response = HttpResponse("Error authorizing application")
        response.status_code = 401
        return response
