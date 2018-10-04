# coding=utf-8
from datetime import datetime, timedelta
import numpy as np
import logging
import pandas as pd

from steembase.exceptions import PostDoesNotExist
from steem.post import Post

from voter.config import CONFIG
from steevebase.model.utils import get_char_ind_dicts
from steevebase.io import load_training_config, load_data, insert_item_db

logger = logging.getLogger(__name__)

VOTERBOT = CONFIG['VOTERBOT']

MODEL_PROB_THRESH = VOTERBOT['MODEL']['PROBABILITY_THRESHOLD']

TARGET_DAILY_VOTES = VOTERBOT['TARGET_DAILY_VOTES']
DAILY_GOOD_POSTS = VOTERBOT['DAILY_GOOD_POSTS']
BLACK_LIST_TAGS = VOTERBOT['BLACKLIST_TAGS']
PLAGIARISM_DETECTORS = VOTERBOT['PLAGIARISM_DETECTORS']

LIMITS = VOTERBOT['LIMITS']

BLACK_LIST_COL = CONFIG['DATABASE']['BLACK_LIST_COLLECTION_NAME']
RAW_POSTS_COL = CONFIG['DATABASE']['RAW_POSTS_COLLECTION_NAME']

LEN_LIMIT = LIMITS['LEN_LIMIT']
VOTES_LIMIT = LIMITS['VOTES_LIMIT']
PAYOUT_LIMIT = LIMITS['PAYOUT_LIMIT']
AGE_LIMIT = LIMITS['AGE_LIMIT']
SPAM_LIMIT = LIMITS['SPAM_LIMIT']

DELAY = CONFIG['DOWNLOADER']['DELAY']

class Checks():

    def __init__(self, db_address, load_model_name=None, model_config_name=None):
        self.posts = set()
        self.past_votes_len = 0

        self.db_address = db_address

        db_blacklist, _ = load_data(self.db_address, BLACK_LIST_COL)
        self.blacklist = set(x['_id'] for x in db_blacklist)
        logger.info("Blacklist loaded: %d", len(self.blacklist))

        if load_model_name:
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
            output = self.probability > predictions[0][0] and self.probability > MODEL_PROB_THRESH
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
            is_unseen = post['_id'] not in self.posts
            self.posts.add(post['_id'])
            return is_unseen
        except PostDoesNotExist:
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
            created = post['created']
        except PostDoesNotExist:
            return False

        # Check whether called in Voter or in Wrangler - not nice :(
        if datetime.utcnow() - created >= timedelta(hours=DELAY / (3600 / 3)): # DELAY in number of blocks
            return True

        # find out how many posts were created by the author in the last 24 hours
        start_time = datetime.utcnow() - timedelta(hours=24)
        last_24_hrs = {'$gte': start_time}
        query = {'author': author, 'created': last_24_hrs}
        _, count = load_data(self.db_address, RAW_POSTS_COL, query)

        if count > 2 * SPAM_LIMIT:
            self.add_to_blacklist(author, count)

        return count < SPAM_LIMIT

    def check_tag_not_blacklisted(self, post):
        try:
            if 'tags' in post:
                return not any([f in BLACK_LIST_TAGS for f in post['tags']])
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
        # threshold = TARGET_DAILY_VOTES / DAILY_GOOD_POSTS * TARGET_DAILY_VOTES / self.past_votes_len \
        #     if self.past_votes_len != 0 else 1
        threshold = 0.3
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

    def check_conditions(self, post, check_list):
        for check in check_list:
            # print('%s(post) = %d' % (check, check(self, post)))
            if not check(self, post):
                return False
        return True

    checklist_all = [check_post_exists,
                     check_unseen,
                     check_len, # most posts filtered out here
                     check_post_not_plagiarism, # because of wrangler
                     check_author_not_blacklisted,
                     check_tag_not_blacklisted]
    checklist_voter = [check_post_exists,    # can be deleted
                       check_len, # because of edits
                       check_post_age,
                       check_payout_not_declined,
                       check_post_not_plagiarism,
                       check_tag_not_blacklisted, # need to re-check, tags can be edited
                       check_votes,
                       check_payout,
                       #check_target_daily_votes,
                       check_classification,
                       check_author_not_spamming]
