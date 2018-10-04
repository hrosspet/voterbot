import logging
import math
import re
import numpy as np
from datetime import datetime, timedelta
from copy import copy

from steevebase.io import load_data, save_data, create_interval_query
from voter.checks import Checks
from voter.config import CONFIG

logger = logging.getLogger(__name__)

BLOCK_STEP = CONFIG['BLOCK_STEP']
TIME_FORMAT = CONFIG['TIME_FORMAT']

# RAW_POSTS_COLLECTION_NAME = CONFIG['DATABASE']['RAW_POSTS_COLLECTION_NAME']
# CLEAN_POSTS_COLLECTION_NAME = CONFIG['DATABASE']['CLEAN_POSTS_COLLECTION_NAME']

sub_dict = [{'!\[.*?\]\(.*?\.(jpg|JPG|png|PNG|gif|GIF)\)': '<pic>'},
            {"<img src[ ]*=.*?>": "<pic>"},
            {"http.*?\.(jpg|JPG|png|PNG|gif|GIF)": "<pic>"},
            {"Body:.*?\.(jpg|JPG|png|PNG|gif|GIF)": "Body:<pic>"},
            {"<pic>' alt=(.*?)\.(jpg|JPG|png|PNG|gif|GIF).*?>": "<pic>"},
            {"<pic>' border.*? alt=(.*?)\.(jpg|JPG|png|PNG|gif|GIF).*?>": "<pic>"},
            {"<pic>' title.*? alt=(.*?)\.(jpg|JPG|png|PNG|gif|GIF).*?>": "<pic>"},
            {"<pic>[^ ]*?\.(jpg|JPG|png|PNG|gif|GIF)": "<pic>"},
            {"<pic> '[^ ]*?\.(jpg|JPG|png|PNG|gif|GIF)'": "<pic>"},
            {"\[(.*?)\]\(.*?\)": "<link=\\1>"},
            {"<a href[ ]*=.*?>(.*?)</a>": "<link=\\1>"}]


def _remove_mess(line):
    # normal mess
    line = line.replace("\n", "+").replace("\r", "").replace("\"", "'")

    # skip non-ascii characters
    line = line.encode('utf-8', 'ignore').decode('ascii', 'ignore')

    # imgs, links
    for d in sub_dict:
        for k in d:
            line = re.sub(k, d[k], line)

    return line


def clean_post(post):
    cleaned_post = copy(post)

    for val in ('body', 'title'):
        cleaned_post[val] = _remove_mess(post[val])

    if 'created' in post and isinstance(post['created'], str):
        cleaned_post['created'] = datetime.strptime(post['created'], '%Y-%m-%dT%H:%M:%S')

    if 'timestamp' in post:
        cleaned_post['created'] = cleaned_post.pop('timestamp')

    return cleaned_post


def post_log_reputation(votes):
    return sum([np.log(max(int(vote['reputation']), 1)) * int(vote['weight']) / 10000 for vote in votes])


def extract_features(post):
    assert post['total_pending_payout_value']['asset'] == 'STEEM'
    assert post['total_pending_payout_value']['amount'] == 0.

    copy_intact = ['_id', 'title', 'body', 'net_votes', 'url', 'active_votes', 'created']

    extracted_post = post.copy()

    for k,v in post.items():
        if k not in copy_intact:
            # throw away keys we don't need
            extracted_post.pop(k)

    if 'total_payout' in post:
        extracted_post['total_payout'] = post['total_payout'] # backward compatibility
    else:
        total_payout_value = float(post['total_payout_value']['amount'])
        pending_payout_value = float(post['pending_payout_value']['amount'])
        extracted_post['total_payout'] = total_payout_value + pending_payout_value

    extracted_post['total_weighted_log_rep'] = post_log_reputation(post['active_votes'])

    return extracted_post


def wrangler_iterator(input_name, blacklist_db_address, block_step=BLOCK_STEP, query=None):
    posts_count = 0
    filtered_count = 0

    checks = Checks(db_address=blacklist_db_address)

    raw_posts_iter, raw_posts_count = load_data(input_name, col_name=RAW_POSTS_COLLECTION_NAME, query=query)

    num_batches = math.ceil(raw_posts_count / block_step)

    for batch in range(num_batches):
        step = min(block_step, raw_posts_count - block_step * batch)

        # download & clean
        posts = [clean_post(next(raw_posts_iter)) for i in range(step)]
        posts_count += len(posts)

        # filter
        filtered_posts = [post for post in posts if checks.check_conditions(post, Checks.checklist_all)]
        filtered_count += len(filtered_posts)

        # transform
        transformed_posts = [extract_features(post) for post in filtered_posts]

        logger.info("Number of posts processed: %d / %d", posts_count, raw_posts_count)
        yield transformed_posts

    logger.info("Total clean posts: %d / %d", filtered_count, raw_posts_count)


def run(args):
    logger.debug("Fetching raw data from database collection: %s.", RAW_POSTS_COLLECTION_NAME)
    logger.debug("Saving processed data to database collection: %s.", CLEAN_POSTS_COLLECTION_NAME)

    blacklist_db_address = args.blacklist

    if blacklist_db_address is None:
        blacklist_db_address = args.input
        assert blacklist_db_address.startswith("mongodb://"), 'Missing address of blacklist db'

    start_time = None
    end_time = None

    if args.start_time:
        start_time = datetime.strptime(args.start_time, TIME_FORMAT)

    if args.end_time:
        end_time = datetime.strptime(args.end_time, TIME_FORMAT)

    if args.days:
        start_time = datetime.utcnow() - timedelta(days=args.days)
        end_time = None

    # keyword: eg. 'created' or 'last_payout'
    query = create_interval_query(args.keyword, start_time, end_time)
    logger.info("Using following interval query: %s" % query)

    for posts in wrangler_iterator(args.input, blacklist_db_address, block_step=BLOCK_STEP, query=query):
        save_data(args.output, CLEAN_POSTS_COLLECTION_NAME, posts)

    logger.info("Cleanup and feature extraction finished")
