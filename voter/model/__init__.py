import logging

logger = logging.getLogger(__name__)


def run_trainer(args):
    from voter.model.trainer import run
    run(args)
