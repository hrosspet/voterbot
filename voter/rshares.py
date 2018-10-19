import copy
from datetime import datetime, timedelta
from steem.post import Post

AUCTION_TIME = 15
VOTING_DELAY = AUCTION_TIME * 60 - 10
MAX_PERCENT = 100
N_ACCOUNTS = 1

def approx_sqrt_v1(x):
    if x <= 1:
        return x
    # mantissa_bits, leading_1, mantissa_mask are independent of x
    msb_x = x.bit_length() - 1
    msb_z = msb_x >> 1
    msb_x_bit = 1 << msb_x
    msb_z_bit = 1 << msb_z
    mantissa_mask = msb_x_bit-1

    mantissa_x = x & mantissa_mask
    if (msb_x & 1) != 0:
        mantissa_z_hi = msb_z_bit
    else:
        mantissa_z_hi = 0
    mantissa_z_lo = mantissa_x >> (msb_x - msb_z)
    mantissa_z = (mantissa_z_hi | mantissa_z_lo) >> 1
    result = msb_z_bit | mantissa_z
    return result

weight_fct = approx_sqrt_v1

def recalculate_weights(active_votes, created, voter='hr1'):
    rshares_total = 0
    weight_total = 0
    weight_hr1 = 0

    for i, vote in enumerate(active_votes):
        w_before = weight_fct(rshares_total)

        rshares_total += vote['rshares']
        rshares_total = max(0, rshares_total)

        w = weight_fct(rshares_total) - w_before
        w = max(0, w)

        delay = (vote['time'] - created).total_seconds()
        delay_coeff = min(1, delay / (AUCTION_TIME * 60))

#         w *= delay_coeff

        # total weight calculated as without delay coefficient (just the proceeds go back to the reward pool, not curator)
        vote['weight'] = w
        weight_total += w

        # here apply the coeff to get correct weight for the curator
        w *= delay_coeff

        if vote['voter'] == voter:
            weight_hr1 = w

#     weighted_rshares = 0
    percent = 0

#     print('weight_total:', weight_total)

    if weight_total > 0:
        percent = weight_hr1 / weight_total
#         weighted_rshares = percent * rshares_total

#     return weighted_rshares, percent
    return percent, rshares_total


def remove_hr1(post):
    changed_post = post.copy()
    for i, p in enumerate(post['active_votes']):
        if p['voter'] == 'hr1':
            changed_post['active_votes'] = post['active_votes'][:i] + post['active_votes'][i+1:]
            break

    return changed_post


def inject_hr1(post, rshares_hr1, voting_time):
    hr_vote = {
        'voter': 'hr1',
        'rshares': rshares_hr1,
        'time': voting_time
    }

    injected = False
    for i, vote in enumerate(post['active_votes']):
        if vote['time'] > voting_time:
            post['active_votes'] = post['active_votes'][:i] + \
                                    [hr_vote] + \
                                    post['active_votes'][i+1:]
            injected = True
            break

    if not post['active_votes']:
        post['active_votes'] = [hr_vote]
    elif not injected:
        post['active_votes'] += [hr_vote]

def amount_to_rshares(amount, steem_price_usd, sbd_price_usd, rshares_to_sbd):
    amount, currency = parse_amount(amount)
    if currency == 'STEEM':
        amount = amount * steem_price_usd / sbd_price_usd

    return int(amount / rshares_to_sbd)

def sbd_to_rshares(sbd, global_params):
    return sbd / global_params['RSHARES_TO_SBD']

def inject_hr1_bidbot(post, rshares_hr1, rshares_bidbot, voting_time):
    hr_vote = {
        'voter': 'hr1',
        'rshares': rshares_hr1,
        'time': voting_time
    }

    bidbot_vote = {
        'voter': '_bidbot_',
        'rshares': rshares_bidbot,
        'time': voting_time + timedelta(seconds=120)
    }

    injected_votes = [hr_vote, bidbot_vote]

    injected = False
    for i, vote in enumerate(post['active_votes']):
        if vote['time'] > voting_time:
            post['active_votes'] = post['active_votes'][:i] + injected_votes
            injected = True
            break

    if not post['active_votes']:
        post['active_votes'] = injected_votes
    elif not injected:
        post['active_votes'] += injected_votes

def parse_voting(active_votes):
    for vote in active_votes:
        vote['rshares'] = int(vote['rshares'])
        if isinstance(vote['time'], str):
            vote['time'] = datetime.strptime(vote['time'], '%Y-%m-%dT%H:%M:%S')

    return active_votes


def get_post_curator_payout(post):
    payout = 0
    if post['curator_payout_value']['amount'] > 0:
        # reward already paid out
        pending = False
        payout = post['curator_payout_value']['amount']
    else:
        # pending payout
        pending = True
        payout = post['pending_payout_value']['amount'] * 0.25 # curators get 25% from the post reward

    return payout, pending

def get_share(post, voter='hr1', rshares_hr1=0, voting_time=None, global_params=None, simulation=False, bid_amount_sbd=None):

    rshares_hr1 = int(rshares_hr1)

    if isinstance(post, Post):
        post = post.export()

    changed_post = copy.deepcopy(post)
#     changed_post = post.export()

    created = changed_post['created']
    # parse times
    changed_post['active_votes'] = parse_voting(changed_post['active_votes'])
    # sort wrt times
    changed_post['active_votes'] = sorted(changed_post['active_votes'], key=lambda x: x['time'])

    if voting_time is None:
        voting_time = created + timedelta(seconds=VOTING_DELAY)
    else:
        voting_time = max(created + timedelta(seconds=VOTING_DELAY), voting_time)

    if simulation:
        bid_rshares = sbd_to_rshares(bid_amount_sbd, global_params)
        inject_hr1_bidbot(changed_post, rshares_hr1, bid_rshares, voting_time)
        injected_rshares = rshares_hr1 + bid_rshares
    else:
        inject_hr1(changed_post, rshares_hr1, voting_time)
        injected_rshares = rshares_hr1

    percent, new_rshares = recalculate_weights(changed_post['active_votes'], created, voter=voter)

    # payout, pending = get_post_curator_payout(post)

    # if new_rshares == injected_rshares:
    payout = new_rshares * global_params['RSHARES_TO_SBD']
    # else:
    #     payout_increase = new_rshares / (new_rshares - injected_rshares)
    #     payout *= payout_increase

    return payout * percent, percent


def get_proportional_vote_strength(expected_payout, total_payouts, votes_per_day):
    return votes_per_day * MAX_PERCENT * expected_payout / total_payouts

def round_percent(value):
    for i in range(N_ACCOUNTS):
        percent = round(value * 10 ** i, 2)

        if percent > 10:
            break

    return percent, i

def get_proportional_rshares(post_payout, total_payouts, votes_per_day, rshares, multiplier):
    percent = get_proportional_vote_strength(post_payout, total_payouts, votes_per_day)

    percent *= multiplier

    percent, i = round_percent(percent)
    return rshares / (10 ** i) * percent / MAX_PERCENT

def vote_strength_ok(rshares, rshares_hr1):
    # vote strength from (0.01% and 100%>
    if rshares > 0.0001 * rshares_hr1 and rshares <= rshares_hr1:
        return True
    return False

###################################################################################################################

def is_bid(memo):
    if isinstance(memo, str):
#         return memo.startswith('https://steemit.com')
        return memo.startswith('https://')
    return False

def get_currency(amount):
    return amount.split(' ')[1]

def get_value(amount):
    return float(amount.split(' ')[0])

def parse_amount(amount):
    amount = amount.split(' ')
    return float(amount[0]), amount[1]

def get_permlink(url):
    return url.split('/')[-1]

def get_author(url):
    return url.split('/')[-2][1:]

def get_ap(url):
    url = url.split('/')
    return url[-2][1:], url[-1]

def parse_timestamp(timestamp):
    return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')

###################################################################################################################

def simulate_vote(bid_amount_sbd, total_payouts_sum, post, bid, global_params, simulation_df):
    expected_reward = 0
    hrshares = 0

    if bid_amount_sbd > 0:
        # how strong should the vote be?
        is_on_time = bid['timestamp'] < post['created'] + timedelta(seconds=VOTING_DELAY)
        # post not upvoted or is in the queue, but still not upvoted
        if not simulation_df.loc[post['identifier'], 'updated'] or is_on_time:
            if simulation_df.loc[post['identifier'], 'updated'] and is_on_time:
                # add previous bid amount to expected payout
                bid_amount_sbd += simulation_df.loc[post['identifier'], 'bid_amount']

            rshares_hr1 = global_params['rshares_hr1']

            hrshares_tentative = get_proportional_rshares(bid_amount_sbd, total_payouts_sum, global_params['N_VOTES'], rshares_hr1, global_params['MULTIPLIER'])
    #         hrshares_tentative = rshares_above_baseline[i]

            hrshares_tentative = min(hrshares_tentative, rshares_hr1)

            if vote_strength_ok(hrshares_tentative, rshares_hr1):
                # first simulate only with information available at the time of the bid
                simulated_reward, _ = get_share(post, 'hr1', hrshares_tentative, bid['timestamp'], global_params, simulation=True, bid_amount_sbd=bid_amount_sbd)

                if simulated_reward / hrshares_tentative >= global_params['BASELINE_THRESHOLD'] * global_params['RSHARES_TO_SBD'] * 0.25:
                    # how much will we get from the vote?
                    expected_reward, _ = get_share(post, 'hr1', hrshares_tentative, voting_time=bid['timestamp'], global_params=global_params)
                    hrshares = hrshares_tentative

                    return expected_reward, hrshares, bid_amount_sbd, True

    return simulation_df.loc[post['identifier']]