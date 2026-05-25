"""
Thread-local pra acessar o request.user de qualquer signal/manager
sem precisar passar `request` por toda a cadeia.

Por que NÃO um middleware simples?
- Middleware Django roda no `__call__` antes da view. Em DRF + JWT,
  `request.user` só é resolvido DENTRO da view (em `initial()` →
  `perform_authentication()`). Capturar no middleware pega AnonymousUser.
- Solução: subclassar JWTAuthentication e capturar logo após o
  super().authenticate() resolver o user. Aí thread-local fica
  populado quando os signals do post_save dispararem.

Trade-offs:
- thread-local funciona com WSGI (uma thread por request). Em ASGI/async
  precisa contextvars — não usado aqui.
- Se uma task Celery ou Django shell mutar dados, current_user fica
  None → signal grava actor=NULL = ação de sistema.
"""

from threading import local

from rest_framework_simplejwt.authentication import JWTAuthentication

_state = local()


class JWTAuthCapturesCurrentUser(JWTAuthentication):
    """JWT auth + side effect de armazenar user no thread-local."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _validated_token = result
            _state.user = user
        return result


class CurrentUserMiddleware:
    """Garante cleanup do thread-local no fim do request.

    A captura em si acontece em JWTAuthCapturesCurrentUser. Esse
    middleware existe só pra zerar o state pós-response (paranoia
    contra thread pooling reusar thread sem limpar).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            _state.user = None


def get_current_user():
    user = getattr(_state, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user
