import logging
from datetime import datetime, timedelta
from steem.post import Post
from steembase.exceptions import PostDoesNotExist, RPCErrorRecoverable, RPCError
from steevebase.io import stream_ops, save_data
import time
import pandas as pd
import numpy as np

from _thread import start_new_thread, allocate_lock

from steevebase.io import mongo_factory
from voter.config import CONFIG

mongo_address = CONFIG['DATABASE']['ADDRESS']
TIME_FORMAT = CONFIG['TIME_FORMAT']

db = mongo_factory(mongo_address)
known_bidbots_col = db.get_collection('known_bidbots')
bidbot_params_col = db.get_collection('bidbot_params')

logger = logging.getLogger(__name__)

a_lock = allocate_lock()

KNOWN_BIDBOTS = {x['_id'] for x in known_bidbots_col.find()}

WIF = CONFIG['VOTER']["WIF"]
PAST_VOTES = CONFIG['DATABASE']['PAST_VOTES_COLLECTION_NAME']

N_ACCOUNTS = 1

VOTER = 'hr1'
MAX_PERCENT = 100
N_VOTES = 10

BLOCK_INTERVAL = 3
MIN_ALLOWED_PAYOUT = 1000

AUCTION_TIME = 15

GLOBAL = {}

df_current_posts = pd.DataFrame(columns=['bid_amount_sbd', 'voting_time', 'bots'])

global_params = ['MULTIPLIER', 'STEEM_PRICE_USD', 'SBD_PRICE_USD', 'TOTAL_PAYOUTS_SUM_SBD', 'VOTING_DELAY', 'time_limits_sec', 'amount_limits', 'BASELINE_THRESHOLD']

# time_limits_sec = {
#     'buildawhale': 3 * 24 * 3600,
#     'emperorofnaps': 5 * 24 * 3600,
#     'minnowbooster': 2 * 24 * 3600,
#     'ocdb': 3 * 24 * 3600,
#     'smartsteem': 3.5 * 24 * 3600,
#     '': 5 * 24 * 3600, # default
# }

# amount_limits = {
#     'upme': [3, 100],
#     'postpromoter': [0, 49.999],
#     'minnowbooster': [0.01, 1000], # Min: 0.01, Max: 13.35, Max-Whitelist: 22.62
#     'brupvoter' : [0, 2.5],
# }


def get_id(memo):
    return memo.split('@')[-1]

def get_post(identifier, post_cache={}):
    try:
        post = Post(identifier)
        post['_id'] = identifier
        post_cache[identifier] = post
        return post
    except Exception as e:
        # logger.exception(e)
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
    if bidbot in GLOBAL['amount_limits']:
        return (amount < GLOBAL['amount_limits'][bidbot][0]) or (amount > GLOBAL['amount_limits'][bidbot][1])
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
    if bidbot not in GLOBAL['time_limits_sec']:
        bidbot = ''
    delay = (transfer['timestamp'] - post['created']).total_seconds()
    return delay > GLOBAL['time_limits_sec'][bidbot]

def voter_already_voted(post, transfer):
    votes = {x['voter'] for x in post['active_votes']}
    if VOTER in votes:
        return True

    _, count = load_data(mongo_address, PAST_VOTES, {'_id': post['identifier']})

    return count > 0

def bot_already_voted(post, transfer):
    if isinstance(transfer['to'], str):
        # if transfer['to'] is a bot name
        bots = {transfer['to']}
    elif isinstance(transfer['to'], dict):
        # if transfer['to'] is a set of bot names
        bots = transfer['to']
    else:
        raise RuntimeError('unexpected parameter: ' + str(transfer))

    voters = {x['voter'] for x in post['active_votes']}
    common_voters = voters.intersection(bots)

    return len(common_voters) > 0

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

def get_expected_payout(amount):
    value = get_value(amount)
    currency = get_currency(amount)
    return value if currency == 'SBD' else value * GLOBAL['STEEM_PRICE_USD'] / GLOBAL['SBD_PRICE_USD']

def get_proportional_vote_strength(expected_payout, total_payouts, votes_per_day):
    return votes_per_day * MAX_PERCENT * expected_payout / total_payouts

def round_percent(value):
    for i in range(N_ACCOUNTS):
        percent = round(value * 10 ** i, 2)

        if percent > 10:
            break

    return percent, i


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
    curation_not_allowed,
    max_payout_too_low,
    voter_already_voted,
    bot_already_voted,
]

def bid_invalid(bid):
    for check in CHECKS_BID:
        if check(bid):
            return True

    return False

def post_bid_invalid(post, bid):
    for check in CHECKS_POST_BID:
        # print('check:', check.__name__, check(post, bid))
        if check(post, bid):
            return True

    return False

######################################################################################################

def get_percent(expected_payout):
    percent = get_proportional_vote_strength(expected_payout, GLOBAL['TOTAL_PAYOUTS_SUM_SBD'], N_VOTES)

    percent *= GLOBAL['MULTIPLIER']

    percent, i = round_percent(percent)

    if i != 0:
        logger.info('\n\n\t!!!additional accounts not set!!!\n')

    percent = min(percent, 100)
    return percent


def _locking_upvote_cycle(bid):
    global a_lock
    with a_lock:
        _add_to_upvote_queue(bid)
        _upvote_due_posts()


def _add_to_upvote_queue(bid):
    global df_current_posts

    bid_amount_sbd = get_expected_payout(bid['amount'])
    if bid_amount_sbd > 0:
        post = get_post_from_transfer(bid)

        if not post_bid_invalid(post, bid):
            post_id = post['identifier']
            bots = {bid['to']}
            voting_time = post['created'] + timedelta(seconds=GLOBAL['VOTING_DELAY'])
            delay = (pending_time - datetime.utcnow()).total_seconds()

            if post_id in df_current_posts.index:
                previous_bid_amount_sbd = df_current_posts.loc[post_id, 'bid_amount_sbd']
                previous_bots = df_current_posts.loc[post_id, 'bots']

                bots.update(previous_bots)
                bid_amount_sbd += previous_bid_amount_sbd

                logger.info(' increasing bid ($%.2f -> $%.2f): busy.org%s', previous_bid_amount_sbd, bid_amount_sbd, post['url'])
                # increase also delay? - such that more bids can come..

            df_current_posts.loc[post_id] = [bid_amount_sbd, voting_time, bots]
            logger.info(' adding to upvote queue (%ds, $%.2f): busy.org%s', delay, bid_amount_sbd, post['url'])

            df_current_posts = df_current_posts.sort_values(by='voting_time')


def upvote_post(post, voter, percent):
    created = datetime.strptime(str(post['created']), TIME_FORMAT)
    age = datetime.utcnow() - created

    logger.info("  Upvoting (%s / %.2f%%): %s votes after [%s]: busy.org%s",
        voter, percent, post["net_votes"], age, post['url'])

    retry_upvote = True
    while retry_upvote:
        try:
            if not DRY_RUN:
                post.upvote(percent, voter)
                # time.sleep(BLOCK_INTERVAL)
            retry_upvote = False
        except RPCError as e:
            # logger.exception(e)
            # for i, x in enumerate(e.args):
            #     print(i, ':', x)

            if 'Assert Exception:abs_rshares > STEEM_VOTE_DUST_THRESHOLD' in e.args[0] or \
            'Assert Exception:itr->vote_percent != o.weight: Your current vote on this comment is identical to this vote.' in e.args[0]:
                break
            else:
                time.sleep(BLOCK_INTERVAL)

        except Exception as e:
            logger.exception("Error when voting.")
            break

    # if upvote cycle not finished with an upvote (in which case retry_upvote == True), skip saving this vote
    success = not retry_upvote
    return success


def log_vote(post_id, voting_time, percent, voter, bid):
    if not DRY_RUN:
        save_post = {
                    '_id': post['_id'],
                    'vote_time': current_time,
                    'percent': percent,
                    'voter': voter,
                    'bid': bid,
                    }
        save_data(mongo_address, PAST_VOTES, save_post)


def vote_profitable(post, voter, percent, current_time, bid_amount_sbd):
    hrshares_tentative = global_params['rshares_hr1'] * percent / MAX_PERCENT
    simulated_reward, _ = get_share(post, voter, hrshares_tentative, current_time, GLOBAL, simulation=True, bid_amount_sbd=bid_amount_sbd)

    if simulated_reward / hrshares_tentative >= GLOBAL['BASELINE_THRESHOLD'] * GLOBAL['RSHARES_TO_SBD'] * 0.25:
        return True

    return False

def _upvote_due_posts():
    global df_current_posts
    clean_current_posts = []

    for identifier, pending_upvote in df_current_posts.iterrows():
        current_time = datetime.utcnow()

        if pending_upvote['voting_time'] <= current_time:
            post = get_post(identifier)
            clean_current_posts.append(identifier)

            bid_amount_sbd = pending_upvote['bid_amount_sbd']
            percent = get_percent(bid_amount_sbd)

            # fake bid to look like a bid, but contain the set of all bots which should be upvoting the post
            bid = {'to': pending_upvote['bots']}
            if vote_strength_ok(percent) and not post_bid_invalid(post, bid) and vote_profitable(post, VOTER, percent, current_time, bid_amount_sbd):
                # additional checks here
                success = upvote_post(post, VOTER, percent)
                if success:
                    log_vote(post_id, current_time, percent, VOTER, bid)


    df_current_posts = df_current_posts.drop(clean_current_posts)

######################################################################################################

def transfer_to_str(transfer):
    return transfer['from'] + ' -> ' + transfer['to'] + \
            ' (' + str(transfer['amount']) + ') ' + transfer['memo']

def insert_param_db(name, value):
    bidbot_params_col.insert_one({'_id': name, 'value': value})

def download_param_db(name):
    return bidbot_params_col.find_one({'_id': name})['value']

def update_global_params_db():
    global GLOBAL

    for param in global_params:
        temp = download_param_db(param)
        if param not in GLOBAL or GLOBAL[param] != temp:
            if param not in GLOBAL:
                logger.info('%s initialized -> %s', param, str(temp))
            else:
                logger.info('%s changed %s -> %s', param, str(GLOBAL[param]), str(temp))

            GLOBAL[param] = temp

######################################################################################################

def run(args):
    global DRY_RUN
    DRY_RUN = args.dry_run

    logger.info('\n\n\tDRY_RUN: %s\n', DRY_RUN)
    logger.info('KNOWN_BIDBOTS: %d', len(KNOWN_BIDBOTS))
    logger.info('AUCTION_TIME: %d', AUCTION_TIME)
    logger.info('N_ACCOUNTS: %d', N_ACCOUNTS)
    logger.info('WIF is None: %d', WIF is None)

    update_global_params_db()

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
            # logger.exception(e)
            time.sleep(BLOCK_INTERVAL)
            logger.info('refreshing stream')
            stream = stream_ops('transfer', wif=WIF)
            continue

        update_global_params_db()

        if bid_invalid(transfer):
            continue

        logger.info(transfer_to_str(transfer))

        start_new_thread(_locking_upvote_cycle, (transfer,))
