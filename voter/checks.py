# coding=utf-8
from datetime import datetime, timedelta
import logging
import numpy as np

from steembase.exceptions import PostDoesNotExist
from steem.post import Post

from steevebase.io import load_training_config, load_data, insert_item_db, is_main_post

from voter.model.utils import get_char_ind_dicts
from voter.spam_check import SpamCheck
from voter.config import CONFIG

logger = logging.getLogger(__name__)

CONFIG_BOT = CONFIG['VOTER']

MODEL_PROB_THRESH = CONFIG_BOT['MODEL']['PROBABILITY_THRESHOLD']

TARGET_DAILY_VOTES = CONFIG_BOT['TARGET_DAILY_VOTES']
DAILY_GOOD_POSTS = CONFIG_BOT['DAILY_GOOD_POSTS']
BLACK_LIST_TAGS = CONFIG_BOT['BLACKLIST_TAGS']
PLAGIARISM_DETECTORS = CONFIG_BOT['PLAGIARISM_DETECTORS']

LIMITS = CONFIG_BOT['LIMITS']

BLACK_LIST_COL = CONFIG['DATABASE']['BLACK_LIST_COLLECTION_NAME']

LEN_LIMIT = LIMITS['LEN_LIMIT']
VOTES_LIMIT = LIMITS['VOTES_LIMIT']
PAYOUT_LIMIT = LIMITS['PAYOUT_LIMIT']
AGE_LIMIT = LIMITS['AGE_LIMIT']
SPAM_LIMIT = LIMITS['SPAM_LIMIT']
REPUTATION_LIMIT = LIMITS['REPUTATION']

DELAY = CONFIG['DOWNLOADER']['DELAY']

def init_commenter():
    global PAYOUT_LIMIT, AGE_LIMIT, LEN_LIMIT
    CONFIG_BOT = CONFIG['COMMENTER']
    PAYOUT_LIMIT = CONFIG_BOT['LIMITS']['PAYOUT_LIMIT']
    AGE_LIMIT = CONFIG_BOT['LIMITS']['AGE_LIMIT']
    LEN_LIMIT = CONFIG_BOT['LIMITS']['LEN_LIMIT']

class Checks():

    def __init__(self, db_address=None, load_model_name=None, model_config_name=None):
        if db_address:
            self.posts = set()
            self.past_votes_len = 0

            self.db_address = db_address

            db_blacklist, _ = load_data(self.db_address, BLACK_LIST_COL)
            # self.blacklist = set(x['_id'] for x in db_blacklist if 'reason' not in x or x['reason'] != 'unsubscribe')
            self.blacklist = set(x['_id'] for x in db_blacklist)
            logger.info("Blacklist loaded: %d", len(self.blacklist))

            self.spam_check = None

        if load_model_name:
            # init spam check
            init_time_interval_hrs = 24

            self.spam_check = SpamCheck(db_address=db_address, init_time_interval_hrs=init_time_interval_hrs)
            logger.info('SpamCheck init on last %d hours', init_time_interval_hrs)

            from steevebase.model import models

            model_config = load_training_config(model_config_name)

            self.output_size = model_config['MODEL']['OUTPUT_SIZE']

            DATA_CONFIG = model_config['DATA']
            self.max_seq_len = DATA_CONFIG['MAX_SEQ_LEN']
            self.embedding_size = len(DATA_CONFIG['ALPHABET']) + 1  # 1 symbol reserved for unknown chars


            self.model_class = models.create_cnn_class(model_config)
            self.model_class.load_weights(load_model_name)
            logger.info("Model %s loaded..." % load_model_name)

            self.char2ind, _ = get_char_ind_dicts(model_config['DATA']['ALPHABET'])
            self.probability = 0.

    def update_past_votes(self, past_votes_len):
        self.past_votes_len = past_votes_len

    def _decide(self, predictions, output_size):
        if output_size == 1:
            self.probability = predictions[0][-1]
            output = self.probability > MODEL_PROB_THRESH
        elif output_size == 2:
            self.probability = predictions[0][1]
            output = self.probability > MODEL_PROB_THRESH
        else:
            raise ValueError("Undefined format of predictions..can't decide.", predictions)
        return output

    def check_post_age(self, post):
        try:
            time_since_created = (datetime.utcnow() - post['created']).total_seconds()
            return time_since_created < AGE_LIMIT
        except PostDoesNotExist:
            return False

    def check_unseen(self, post):
        try:
            if post['_id'] not in self.posts:
                self.posts.add(post['_id'])
                if self.spam_check:
                    self.spam_check.update_author(post['author']) # we need to track each post in the spam check
                return True
        except PostDoesNotExist:
            return False

        return False

    def check_author_not_blacklisted(self, post):
        try:
            author = post['author']
        except PostDoesNotExist:
            return False

        return author not in self.blacklist

    def add_to_blacklist(self, author, count):
        item = {'_id': author, 'created': datetime.utcnow(), 'reason': 'auto', 'count': count}
        self.blacklist.add(author)
        insert_item_db(self.db_address, BLACK_LIST_COL, item)
        logger.info("%s added to blacklist with %d posts in the last 24hrs", author, count)

    def check_author_not_spamming(self, post):
        try:
            author = post['author']
        except PostDoesNotExist:
            return False

        if self.spam_check is None:
            # skip when no spam_check
            return True

        count = self.spam_check.get_count_24hrs(author)

        if count > 2 * SPAM_LIMIT:
            self.add_to_blacklist(author, count)

        return count < SPAM_LIMIT

    def check_tag_not_blacklisted(self, post):
        try:
            if 'tags' in post:
                return not any([f in BLACK_LIST_TAGS for f in post['tags'] if isinstance(f, str)])
            else:
                return True
        except PostDoesNotExist:
            return False

    def check_post_not_plagiarism(self, post):
        if 'active_votes' in post:
            voters = set([vote['voter'] for vote in post['active_votes']])
            intersection = PLAGIARISM_DETECTORS.intersection(voters)
            return len(intersection) == 0
        else:
            return True

    def check_payout_not_declined(self, post):
        try:
            if post['max_accepted_payout']['amount'] >= 100: # payout cap at least 100 SBD
                return True
            return False
        except PostDoesNotExist:
            return False

    def check_post_exists(self, post):
        if post is not None:
            return True
        else:
            return False

    def check_votes(self, post):
        return post["net_votes"] < VOTES_LIMIT

    def check_payout(self, post):
        return float(post["pending_payout_value"]) < PAYOUT_LIMIT

    def check_target_daily_votes(self, post):
        threshold = TARGET_DAILY_VOTES / self.past_votes_len \
            if self.past_votes_len != 0 else 1

        return np.random.rand() < threshold

    def check_len(self, clean_post):
        return len(clean_post['title']) + len('+') + len(clean_post['body']) >= LEN_LIMIT

    def check_classification(self, post):
        from steevebase.model.generator import unwrap_single_post, one_hot_encode_post

        # transform post into the format expected by the model
        title, body, _, _ = unwrap_single_post(post)
        input_data = one_hot_encode_post(title, body, self.char2ind, self.max_seq_len, self.embedding_size) # includes random sampling!
        input_data = {"main_input": np.array([input_data])}

        # classify post
        predictions = self.model_class.predict(input_data, batch_size=1)

        logger.info("[%.2f] : busy.org%s", predictions[0,1], post['url'])

        return self._decide(predictions, self.output_size)

    def check_main_post(self, post):
        return is_main_post(post)

    def check_conditions(self, post, check_list):
        for check in check_list:
            # print('%s(post) = %d' % (check, check(self, post)))
            if not check(self, post):
                return False
        return True

    def check_reputation(self, post):
        if int(post['author_reputation']) < REPUTATION_LIMIT:
            return False
        return True

    checklist_all = [check_post_exists,
                     check_unseen,
                     check_len, # most posts filtered out here
                     check_post_not_plagiarism, # because of wrangler
                     check_author_not_blacklisted,
                     check_tag_not_blacklisted,
                     check_author_not_spamming]
    checklist_voter = [check_post_exists,    # can be deleted
                       check_len, # because of edits
                       check_author_not_blacklisted,
                       check_author_not_spamming,
                       check_reputation,
                       check_post_age,
                       check_payout_not_declined,
                       check_post_not_plagiarism,
                       check_tag_not_blacklisted, # need to re-check, tags can be edited
                       check_votes,
                       check_payout,
                       # check_target_daily_votes,
                       check_classification]
    checklist_commenter = [
        check_main_post,
        check_post_age,
        check_payout,
        check_reputation,
        check_tag_not_blacklisted,
        check_post_not_plagiarism
    ]
    checklist_recommendation = [
        check_main_post,
        check_len,
        check_reputation,
        check_tag_not_blacklisted,
        check_post_not_plagiarism
    ]
