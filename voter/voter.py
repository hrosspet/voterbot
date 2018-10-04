import logging
import time
from datetime import datetime, timedelta
import pandas as pd

from _thread import start_new_thread, allocate_lock

from steembase.exceptions import PostDoesNotExist, RPCErrorRecoverable, RPCError

from steevebase.io import save_data, load_data, stream_ops, get_steem_info
from steevebase.downloader import process_post, convert_to_post

from voter.wrangler import clean_post
from voter.checks import Checks
from voter.config import CONFIG

logger = logging.getLogger(__name__)

DB_NAME = CONFIG['DATABASE']['NAME']
PAST_VOTES = CONFIG['DATABASE']['PAST_VOTES_COLLECTION_NAME']
# RAW_POSTS_COLLECTION_NAME = CONFIG['DATABASE']['RAW_POSTS_COLLECTION_NAME']
TIME_FORMAT = CONFIG['TIME_FORMAT']

VOTERBOT = CONFIG['VOTER']

STRENGTH = VOTERBOT['STRENGTH']
WIF = VOTERBOT["WIF"]
VOTING_DELAY = VOTERBOT['VOTING_DELAY']

# Constants
VOTER = 'hr1'
BLOCK_INTERVAL = CONFIG['BLOCK_INTERVAL'] # seconds


class Voter:
    def __init__(self, args):
        assert args.db_address.startswith("mongodb://")

        self.checks = Checks(args.db_address, args.load_model_name, args.model_config_name)

        self.posts = set()
        self.df_current_posts = pd.DataFrame({'post': [],
                                              'pending_times': []})
        self.df_past_votes = pd.DataFrame({'vote_time': pd.Series(dtype='datetime64[ns]'),
                                          '_id': []})

        self.db_address = args.db_address
        time_now = datetime.utcnow()
        minusdelta24 = time_now - timedelta(hours=24)

        query = {"vote_time": {"$gt": minusdelta24}}
        old_voted_posts_iter, _ = load_data(self.db_address, PAST_VOTES, query)
        for post in old_voted_posts_iter:
            self.df_past_votes = self.df_past_votes.append(
                {'vote_time': int(post["vote_time"].timestamp()), '_id': post['_id']}, ignore_index=True)

        logger.info("Past votes loaded: %d", len(self.df_past_votes))

        self.steem_address = args.steem_address
        self.wif = WIF

        start_block_number = get_steem_info(self.steem_address)['head_block_number'] - int(VOTING_DELAY / BLOCK_INTERVAL)
        self.stream = stream_ops('comment', steem_address=self.steem_address, wif=self.wif, start_block_number=start_block_number)

        self.a_lock = allocate_lock()

    def refresh_and_clean_post(self, post):
        post = convert_to_post(post)

        if post:
            post = process_post(post) # from downloader
            post = clean_post(post) # from wrangler

        return post


    def _add_to_upvote_queue(self, post):
        pending_time = post['created'] + timedelta(seconds=VOTING_DELAY)
        delay = (pending_time - datetime.utcnow()).total_seconds()

        # logger.info('Adding to upvote queue with delay: %d', delay)
        self.df_current_posts = self.df_current_posts.append(
            {'pending_times': pending_time,
             'post': post},
            ignore_index=True)


    def _pop_old_votes(self):
        if not self.df_past_votes.empty:
            minusdelta24 = int(datetime.utcnow().timestamp()) - 24*3600
            self.df_past_votes = self.df_past_votes.query('vote_time > {}'.format(minusdelta24))
            self.checks.update_past_votes(len(self.df_past_votes))

    def _upvote_due_posts(self):
        clean_current_posts = []
        for i, one_post_info in self.df_current_posts.iterrows():
            current_time = datetime.utcnow()
            if one_post_info['pending_times'] <= current_time:
                post = one_post_info['post']
                post = self.refresh_and_clean_post(post)

                clean_current_posts.append(i)

                if self.checks.check_conditions(post, Checks.checklist_voter):
                    logger.info("$%.2f : " % float(post["pending_payout_value"]) + "busy.org" + post['url'])

                    created = datetime.strptime(str(post['created']), TIME_FORMAT)
                    age = (datetime.utcnow() - created).total_seconds()

                    logger.info("%s: Upvoting(%d/24hrs) with %s votes after %d: busy.org%s" % (
                        current_time, len(self.df_past_votes) + 1, post["net_votes"], age,
                        post['url']))

                    retry_upvote = True
                    while retry_upvote:
                        try:
                            post.upvote(STRENGTH, VOTER)
                            # time.sleep(BLOCK_INTERVAL)
                            retry_upvote = False
                        except RPCError as e:
                            # logger.exception(e)

                            for i, x in enumerate(e.args):
                                print(i, ':', x)

                            if 'Assert Exception:abs_rshares > STEEM_VOTE_DUST_THRESHOLD' in e.args[0]:
                                break
                            else:
                                time.sleep(BLOCK_INTERVAL)

                        except Exception as e:
                            logger.exception("Error when voting.")
                            break

                    if retry_upvote:
                        # if upvote cycle not finished with an upvote (in which case retry_upvote == True), skip saving this vote
                        continue

                    self.df_past_votes = self.df_past_votes.append({'_id': post['_id'],
                                                                    'vote_time': int(current_time.timestamp())},
                                                                    ignore_index=True)
                    self.checks.update_past_votes(len(self.df_past_votes))

                    save_post = {
                                '_id': post['_id'],
                                'vote_time': current_time,
                                'net_votes': post['net_votes'],
                                'pending_payout_value': post['pending_payout_value'],
                                'probability': float(self.checks.probability)
                                }

                    save_data(self.db_address, PAST_VOTES, save_post)


        self.df_current_posts = self.df_current_posts.drop(clean_current_posts)

    def _locking_upvote_cycle(self, post):
        with self.a_lock:
            if self.checks.check_conditions(post, Checks.checklist_all):
                self._add_to_upvote_queue(post)
            self._pop_old_votes()
            self._upvote_due_posts()

    def execute(self):
        logger.info("Listening to Steem.")
        post = True
        while post:
            try:
                post = next(self.stream)
            except (TypeError, AttributeError) as e:
                logger.exception(e)
                time.sleep(BLOCK_INTERVAL)
                continue
            except (StopIteration, KeyError, RPCErrorRecoverable, RPCError) as e:
                logger.exception(e)
                time.sleep(BLOCK_INTERVAL)
                self.stream = stream_ops('comment', steem_address=self.steem_address, wif=self.wif)
                continue

            # save_data(self.db_address, RAW_POSTS_COLLECTION_NAME, post) # necessary for checking spam

            post = clean_post(post) # from wrangler
            start_new_thread(self._locking_upvote_cycle, (post,))

def run(args):
    voter = Voter(args)
    logger.info('Voting with: %s', VOTER)
    voter.execute()
