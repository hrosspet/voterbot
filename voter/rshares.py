import copy

AUCTION_TIME = 15
VOTING_DELAY = AUCTION_TIME * 60 - 10

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


def parse_voting(active_votes):
    for vote in active_votes:
        vote['rshares'] = int(vote['rshares'])
        if isinstance(vote['time'], str):
            vote['time'] = datetime.strptime(vote['time'], '%Y-%m-%dT%H:%M:%S')

    return active_votes



def get_share(post, voter='hr1', rshares_hr1=0, voting_time=None):

    rshares_hr1 = int(rshares_hr1)

    changed_post = copy.deepcopy(post.export())
#     changed_post = post.export()

    created = changed_post['created']
    # parse times
    changed_post['active_votes'] = parse_voting(changed_post['active_votes'])
    # sort wrt times
    changed_post['active_votes'] = sorted(changed_post['active_votes'], key=lambda x: x['time'])

    if voting_time is None:
        voting_time = created + timedelta(seconds=VOTING_DELAY)

    inject_hr1(changed_post, rshares_hr1, voting_time)

    percent, new_rshares = recalculate_weights(changed_post['active_votes'], created, voter=voter)

    if post.curator_payout_value > 0:
        # reward already paid out
        pending = False
        payout = post.curator_payout_value
    else:
        # pending payout
        pending = True
        payout = post.pending_payout_value * 0.25 # curators get 25% from the post reward

    if new_rshares == rshares_hr1:
        payout = new_rshares * RSHARES_TO_SBD
    else:
        payout_increase = new_rshares / (new_rshares - rshares_hr1)
        payout *= payout_increase

    return payout * percent, percent