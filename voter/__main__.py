from datetime import datetime
from subprocess import check_output
import argparse
import logging
import sys
import os
from time import gmtime

from voter.config import CONFIG

DELAY = CONFIG['DOWNLOADER']['DELAY']

RUN_ID = datetime.strftime(datetime.utcnow(), '%Y%m%d%H%M%S')


def parse_arguments():
    from steevebase import run_downloader
    from voter.model import run_trainer
    from voter import run_bidbot, run_voter, run_wrangler

    parser = argparse.ArgumentParser(
        prog='voterbot',
        description="Launcher and runner for steembot voter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        type=str,
        choices=('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'),
        default='INFO',
        help="Level of standard output logging.")

    parser.add_argument('--loglevel',
                        default=None,
                        choices=('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'),
                        help='Level of file [logs/<run_id>.log] output logging')

    parser.add_argument('--gitdir',
                        default='.git',
                        help='Path to the voterbot github repo to get a commit hash for run_id')

    subparsers = parser.add_subparsers(title='subcommand',
                                       help='use subcommand --help to get help')

    download_parser = subparsers.add_parser(
        name='downloader', help='Downloads data',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    download_type = download_parser.add_mutually_exclusive_group()
    download_type.add_argument("--stream",
                               help="Use the streaming mode",
                               action="store_true")
    download_type.add_argument("--post-count",
                               help="Download given number of posts",
                               type=int)
    download_type.add_argument("--block-count",
                               help="Download given number of blocks",
                               type=int)
    download_type.add_argument("-d",
                               "--days",
                               help="Download posts from last D (float) days (minus delay in blocks)",
                               type=float)

    download_parser.add_argument("--delay",
                                 type=int,
                                 help="Number of blocks the download is shifted into the past",
                                 default=DELAY)
    download_parser.add_argument("-s",
                                 "--steem-address",
                                 help="Steem address in a format host:port")
    download_parser.add_argument("-o",
                                 "--output",
                                 help="Mongo address or path to the file",
                                 default=os.getenv('MONGODB_ADDRESS', 'mongodb://localhost:26999'))
    download_parser.add_argument("--votes",
                               help="Download votes instead of posts",
                               action="store_true")
    download_parser.set_defaults(func=run_downloader)

    wrangling_parser = subparsers.add_parser(
        name='wrangler', help='Cleans data and extracts features from data',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    wrangling_parser.add_argument("-i",
                                  "--input",
                                  required=True,
                                  help="Mongo address or path to the input file")
    wrangling_parser.add_argument("-bl",
                                  "--blacklist",
                                  help="Mongo address of the blacklist db. Must be set when different from --input.")
    wrangling_parser.add_argument("-s",
                                  "--start-time",
                                  help="Start of time interval to wrangle")
    wrangling_parser.add_argument("-e",
                                  "--end-time",
                                  help="End of time interval to wrangle")
    wrangling_parser.add_argument("-d",
                                  "--days",
                                  type=float,
                                  help="Wrangle posts from last N days")
    wrangling_parser.add_argument("-k",
                                  "--keyword",
                                  help="What keyword should the interval query use: {created, last_payout, ...}",
                                  default='created')
    wrangling_parser.add_argument("-o",
                                  "--output",
                                  required=True,
                                  help="Mongo output address or path to the output file")
    wrangling_parser.set_defaults(func=run_wrangler)

    training_parser = subparsers.add_parser(
        name='trainer', help='Trains model on the labeled data',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    training_parser.add_argument("-l",
                                 "--load-model-name",
                                 help="Name of the model to load and continue training on")
    training_parser.add_argument("-s",
                                 "--save-model-name",
                                 default='model_weights',
                                 help="Name used for saving the trained model (without extension)")
    training_parser.add_argument("-c",
                                 "--training-config-name",
                                 help="JSON file containing parameters for training",
                                 default="training_configs/default_training_setup.json")
    training_parser.set_defaults(func=run_trainer)

    voter_parser = subparsers.add_parser(
        name='voter', help='Votes for posts on the blockchain',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    voter_parser.add_argument("-l",
                              "--load-model-name",
                              required=True,
                              help="Name of the model to load and use for voting")
    voter_parser.add_argument("-c",
                              "--model-config-name",
                              help="JSON file containing parameters for training",
                              default="training_configs/default_training_setup.json")
    voter_parser.add_argument("-s",
                              "--steem-address",
                              type=str,
                              help="Steem address",
                              default="")
    voter_parser.add_argument("-db",
                              "--db-address",
                              help="Mongo address to the db with past vote times and blacklist",
                              default="mongodb://107.155.87.82:26999")
    voter_parser.set_defaults(func=run_voter)

    bidbot_parser = subparsers.add_parser(
        name='bidbot', help='Votes for posts on the blockchain',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    bidbot_parser.add_argument("-d",
                               "--dry-run",
                               help="Use bidbot for testing - no upvotes & no store to db",
                               action="store_true")
    bidbot_parser.add_argument("-s",
                              "--steem-address",
                              type=str,
                              help="Steem address",
                              default="")
    bidbot_parser.add_argument("-db",
                              "--db-address",
                              help="Mongo address to the db with past vote times and blacklist",
                              default="mongodb://107.155.87.82:26999")
    bidbot_parser.set_defaults(func=run_bidbot)


    # if no arguments are passed, print help and exit
    import sys
    if len(sys.argv) < 0:
        parser.print_help()
        sys.exit(1)
    else:
        return parser.parse_args()


def get_git_dir_hash(gitdir):
    return check_output(['git',
                         '--git-dir={}'.format(gitdir),
                         'rev-parse',
                         '--short',
                         'HEAD']).decode().strip()


def generate_run_id(gitdir, run_func):
    commit_hash = get_git_dir_hash(gitdir)
    return '{}-{}-{}'.format(RUN_ID, commit_hash, run_func)


class InjectRunID(logging.Filter):
    def __init__(self, run_id):
        self.run_id = run_id
        super().__init__()

    def filter(self, record):
        record.run_id = self.run_id
        return True


def prepare_logging(level, run_id, loglevel):
    logger = logging.getLogger()
    logging.Formatter.converter = gmtime
    formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s - %(message)s",
                                  CONFIG['TIME_FORMAT'])
    injecter = InjectRunID(run_id)

    logger.setLevel('DEBUG')

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    ch.addFilter(injecter)
    ch.setLevel(level)
    logger.addHandler(ch)

    if loglevel:
        os.makedirs('logs/', exist_ok=True)
        lh = logging.FileHandler('logs/{}.log'.format(run_id))
        lh.setFormatter(formatter)
        lh.addFilter(injecter)
        lh.setLevel(loglevel)
        logger.addHandler(lh)
        logger.info('Logging %s into file %s', loglevel, run_id)

    return logger


def main():
    args = parse_arguments()

    global RUN_ID
    RUN_ID = generate_run_id(args.gitdir, args.func.__name__)
    logger = prepare_logging(args.verbosity, RUN_ID, args.loglevel)

    logger.info(vars(args))
    logger.info("######### STARTING #########")
    logger.info('run_id: %s', RUN_ID)
    logger.debug('Received command line arguments: \n{}'.format(args))

    try:
        args.func(args)
    except KeyboardInterrupt:
        logger.warning("Terminated by user.")
    except SystemExit:
        logger.info("Finished.")
    logger.info("######### FINISHED #########")


if __name__ == "__main__":
    main()
