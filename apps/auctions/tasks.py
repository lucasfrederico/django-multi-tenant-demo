"""
Tasks Celery do app auctions.

Por enquanto só uma task de "notificação" — não manda email de verdade,
só loga. Em produção, isso plugaria num SES / SendGrid / etc.

O ponto da task é demonstrar:
- desacoplamento de side-effects do request (response volta sem esperar
  envio do email)
- retry behavior automático do Celery
- idempotência (task carrega bid_id, não o objeto serializado)
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def notify_outbid(bid_id: int):
    """
    Notifica o usuário cujo bid acabou de ser superado.

    No mundo real: lookup do bid anterior, lookup dos contatos do user,
    chamada pro provider de email. Aqui só loga.
    """
    from apps.auctions.models import Bid

    bid = Bid.objects.select_related("auction", "bidder").get(pk=bid_id)
    auction = bid.auction
    previous_top = (
        Bid.objects
        .filter(auction=auction)
        .exclude(pk=bid.pk)
        .order_by("-amount")
        .select_related("bidder")
        .first()
    )
    if previous_top is None:
        logger.info("notify_outbid: bid#%s é o primeiro do leilão", bid_id)
        return

    logger.info(
        "notify_outbid: user %s foi superado em %s (novo bid %s > anterior %s)",
        previous_top.bidder_id,
        auction_id_safe := auction.pk,
        bid.amount,
        previous_top.amount,
    )
    # TODO: chamar provider de email aqui. Por enquanto só log.
    return {"notified_user": previous_top.bidder_id, "auction": auction_id_safe}
