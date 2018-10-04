import logging

logger = logging.getLogger(__name__)

def run_bidbot(args):
    from voter.bidbot import run
    run(args)


def run_voter(args):
    from voter.voter import run
    run(args)


def run_wrangler(args):
    from voter.wrangler import run
    run(args)