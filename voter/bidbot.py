import logging

from steem.post import Post
from steembase.exceptions import PostDoesNotExist, RPCErrorRecoverable, RPCError
from steevebase.io import stream_ops
import time
import pandas as pd
import numpy as np

from _thread import start_new_thread, allocate_lock

from steevebase.io import mongo_factory
from voter.config import CONFIG

mongo_address = CONFIG['DATABASE']['ADDRESS']
db = mongo_factory(mongo_address)
known_bidbots_col = db.get_collection('known_bidbots')

logger = logging.getLogger(__name__)

a_lock = allocate_lock()

KNOWN_BIDBOTS = {x['_id'] for x in known_bidbots_col.find()}

WIF = None

N_ACCOUNTS = 1

STEEM_PRICE_USD = .793103
SBD_PRICE_USD = .984368

VOTER = 'hr1'
MULTIPLIER = 11
MAX_PERCENT = 100
N_VOTES = 10
TOTAL_PAYOUTS_SUM = 78543.460 # SBD, as of 2018/10/16

BLOCK_INTERVAL = 3
MIN_ALLOWED_PAYOUT = 1000

AUCTION_TIME = 15
VOTING_DELAY = AUCTION_TIME * 60 - 10

df_current_posts = pd.DataFrame({
                        'post': [],
                        'pending_times': [],
                        'percent': [],
                        'voter': [],
                        'bid': [],
                        })

time_limits_sec = {
    'buildawhale': 3 * 24 * 3600,
    'emperorofnaps': 5 * 24 * 3600,
    'minnowbooster': 2 * 24 * 3600,
    'ocdb': 3 * 24 * 3600,
    'smartsteem': 3.5 * 24 * 3600,
    '': 5 * 24 * 3600, # default
}

amount_limits = {
    'upme': [3, 100],
    'postpromoter': [0, 49.999],
    'minnowbooster': [0.01, 1000], # Min: 0.01, Max: 13.35, Max-Whitelist: 22.62
    'brupvoter' : [0, 2.5],
}


def get_id(memo):
    return memo.split('@')[-1]

def get_post(identifier, post_cache={}):
    try:
        post = Post(identifier)
        post_cache[post_id] = post
        return post
    except:
        return None

def get_post_from_transfer(transfer):
    post_id = get_id(transfer['memo'])
    # if post_id in post_cache:
    #     return post_cache[post_id]

    return get_post(post_id)


def _parse_vote_time(vote_time):
    return datetime.strptime(vote_time, '%Y-%m-%dT%H:%M:%S')

def get_currency(amount):
    return amount.split(' ')[1]

def get_value(amount):
    return float(amount.split(' ')[0])

def is_bid(memo):
    if isinstance(memo, str):
        return memo.startswith('https://steemit.com')
    return False

def get_author(url):
    return url.split('/')[-2][1:]

############ CHECKS_BID ################################################

def not_a_bid(transfer):
    return not is_bid(transfer['memo'])

def bidbot_not_known(transfer):
    bidbot = transfer['to']
    return not bidbot in KNOWN_BIDBOTS

def is_out_of_bounds(transfer):
    bidbot = transfer['to']
    amount = get_value(transfer['amount'])
    if bidbot in amount_limits:
        return (amount < amount_limits[bidbot][0]) or (amount > amount_limits[bidbot][1])
    return False

def sneaky_ninja_steem(transfer):
    return transfer['to'] == 'sneaky-ninja' and get_currency(transfer['amount']) == 'STEEM'

def target_is_bidbot(transfer):
    return get_author(transfer['memo']) in KNOWN_BIDBOTS

############ CHECKS_POST_BID ###########################################

def post_doesnt_exist(post, transfer):
    return post is None

def post_too_old(post, transfer):
    bidbot = transfer['to']
    if bidbot not in time_limits_sec:
        bidbot = ''
    delay = (transfer['timestamp'] - post['created']).total_seconds()
    return delay > time_limits_sec[bidbot]

def voter_already_voted(post, transfer):
    votes = {x['voter'] for x in post['active_votes']}
    return VOTER in votes

def bot_already_voted(post, transfer):
    bidbot = transfer['to']
    votes = {x['voter'] for x in post['active_votes']}
    return bidbot in votes

def curation_not_allowed(post, transfer):
    return not post['allow_curation_rewards']

def max_payout_too_low(post, transfer):
    return post['max_accepted_payout']['amount'] < MIN_ALLOWED_PAYOUT

##########################################################################

def vote_strength_ok(percent):
    # vote strength from (0.01% and 100%>
    if percent > 0.01 and percent <= 100:
        return True
    return False


##########################################################################

CHECKS_BID = [
    not_a_bid,
    bidbot_not_known,
    target_is_bidbot,
    is_out_of_bounds,
    sneaky_ninja_steem,
]
CHECKS_POST_BID = [
    post_doesnt_exist,
    post_too_old,
    voter_already_voted,
    bot_already_voted,
    curation_not_allowed,
    max_payout_too_low
]

def bid_invalid(bid):
    for check in CHECKS_BID:
        if check(bid):
            return True

    return False

def post_bid_invalid(post, bid):
    for check in CHECKS_POST_BID:
        if check(post, bid):
            return True

    return False

def get_expected_payout(amount):
    value = get_value(amount)
    currency = get_currency(amount)
    return value if currency == 'SBD' else value * STEEM_PRICE_USD / SBD_PRICE_USD

def get_proportional_vote_strength(expected_payout, total_payouts, votes_per_day):
    proportion = votes_per_day * MAX_PERCENT * expected_payout / total_payouts

    for i in range(N_ACCOUNTS):
        percent = round(proportion * 10 ** i, 2)

        if percent > 10:
            break

    return percent, i

def upvote_bid(post, bid, expected_payout):
    percent = get_proportional_vote_strength(expected_payout, TOTAL_PAYOUTS_SUM, N_VOTES)

    percent = MULTIPLIER * percent
    percent = min(percent, 100)

    if vote_strength_ok(percent):
        # schedule for upvote
        print('adding to upvote queue (%.2f%%, $%.2f): busy.org%s', (percent, expected_payout, post['url']))
        with a_lock:
            _add_to_upvote_queue(post, percent, VOTER, bid)

        # how much will we get from the vote?
#         expected_reward = get_share(post, 'hr1', hrshares)[0]
#     else:
#         expected_reward = 0
#         hrshares = 0

######################################################################################################

def _locking_upvote_cycle():
        with a_lock:
            _upvote_due_posts()


def _add_to_upvote_queue(post, percent, voter, bid):
    pending_time = post['created'] + timedelta(seconds=VOTING_DELAY)
    delay = (pending_time - datetime.utcnow()).total_seconds()

    # logger.info('Adding to upvote queue with delay: %d', delay)
    global df_current_posts
    df_current_posts = df_current_posts.append(
        {'pending_times': pending_time,
         'post': post['identifier'],
         'percent': percent,
         'voter': voter,
         'bid': bid
         },
        ignore_index=True)


def _upvote_due_posts(self):
    clean_current_posts = []
    for i, one_post_info in df_current_posts.iterrows():
        current_time = datetime.utcnow()
        if one_post_info['pending_times'] <= current_time:
            identifier = one_post_info['post']
            post = get_post(identifier)
            bid = one_post_info['bid']
            percent = one_post_info['percent']
            voter = one_post_info['voter']

            clean_current_posts.append(i)

            if not post_bid_invalid(post, bid):
                logger.info("$%.2f : " % float(post["pending_payout_value"]) + "busy.org" + post['url'])

                created = datetime.strptime(str(post['created']), TIME_FORMAT)
                age = (datetime.utcnow() - created).total_seconds()

                logger.info("%s: Upvoting (%s/%.2f%%): %s votes after %d: busy.org%s" % (
                    current_time, voter, percent, post["net_votes"], age, post['url']))

                retry_upvote = True
                while retry_upvote:
                    try:
                        if not DRY_RUN:
                            post.upvote(percent, voter)
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

                if not DRY_RUN:
                    save_post = {
                                '_id': post['_id'],
                                'vote_time': current_time,
                                'percent': percent,
                                'voter': voter,
                                'bid': bid,
                                }

                    save_data(self.db_address, PAST_VOTES, save_post)


    df_current_posts = df_current_posts.drop(clean_current_posts)

######################################################################################################


def run(args):

    global DRY_RUN
    DRY_RUN = args.dry_run
    logger.info('\n\n\tDRY_RUN: %s\n', DRY_RUN)
    logger.info('KNOWN_BIDBOTS: %d', len(KNOWN_BIDBOTS))
    logger.info('STEEM_PRICE_USD: %.2f', STEEM_PRICE_USD)
    logger.info('SBD_PRICE_USD: %.2f', SBD_PRICE_USD)
    logger.info('TOTAL_PAYOUTS_SUM: %.3f', TOTAL_PAYOUTS_SUM)
    logger.info('MULTIPLIER: %d', MULTIPLIER)
    logger.info('AUCTION_TIME: %d', AUCTION_TIME)
    logger.info('VOTING_DELAY: %d', VOTING_DELAY)
    logger.info('N_ACCOUNTS: %d', N_ACCOUNTS)
    logger.info('WIF is None: %d', WIF is None)

    stream = stream_ops('transfer', wif=WIF)

    logger.info("Listening to Steem.")
    transfer = True
    while transfer:
        try:
            transfer = next(stream)
        except (TypeError, AttributeError) as e:
            logger.exception(e)
            time.sleep(BLOCK_INTERVAL)
            continue
        except (StopIteration, KeyError, RPCErrorRecoverable, RPCError) as e:
            logger.exception(e)
            time.sleep(BLOCK_INTERVAL)
            stream = stream_ops('transfer', wif=None)
            continue

        # save_data(self.db_address, RAW_POSTS_COLLECTION_NAME, post) # necessary for checking spam

        if bid_invalid(transfer):
            continue

        post = get_post_from_transfer(transfer)

        if post_bid_invalid(post, transfer):
            continue

        print('\nbid:', transfer)

        expected_payout = get_expected_payout(transfer['amount'])

        if expected_payout > 0:
            upvote_bid(post, expected_payout)

        start_new_thread(_locking_upvote_cycle)
