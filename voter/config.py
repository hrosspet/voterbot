import os

CONFIG = {
    'BLOCK_INTERVAL': 3, # seconds
    'BLOCK_STEP': int(3600 / 3),
    'DOWNLOADER': {
        'DELAY': int(1 * 24 * 3600 / 3)
    },
    'DATABASE': {
        'ADDRESS': os.getenv('MONGODB_ADDRESS', 'mongodb://localhost:26999'),
        'NAME': 'steem',
        'USER': 'admin',
        'PASSWORD': os.getenv('MONGODB_PASSWORD'),
        'SOURCE': 'admin',
        'PAST_VOTES_COLLECTION_NAME': 'past_votes',
        'BLACK_LIST_COLLECTION_NAME': 'black_list',
        'PAST_COMMENTS_COLLECTION_NAME': 'past_comments',
        'VOTES_COLLECTION_NAME': 'raw_votes',

        # 'FEED_RECO_COLLECTION_NAME': 'recommendations',
        'FEED_RECO_COLLECTION_NAME': 'new_reco_collection',
        'RECOS_ID_COL_NAME': 'user_reco_ids',
        'POST_RECO_COLLECTION_NAME': 'post_recommendations',

        'USER_FOL_COLLECTION_NAME': 'user_following', # 500
        # 'USER_FOL_COLLECTION_NAME': 'user_following_750',
        # 'USER_MUTE_COLLECTION_NAME': 'user_mutes',

        'LOGGING_COL_NAME': 'logging',
        'CONFIGS_COL_NAME': 'configs',
        },
    'TRAINING_CONFIG_FOLDER': 'training_configs/',
    'TIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'VOTER': {
        'WIF': os.getenv('VOTER_WIF'),
        'STRENGTH': .02,
        'BLACKLIST_TAGS': {'pizzagate', 'chemtrails', 'conspiracy', 'statistics', 'utopian-io', \
                        'photography', 'christian-trail', 'christiantrail', 'gospel', 'religion'},
        'PLAGIARISM_DETECTORS': {'cheetah', 'steemcleaners', 'mack-bot'},
        'TARGET_DAILY_VOTES': 1000,
        'DAILY_GOOD_POSTS': 1000.,
        'VOTING_DELAY': 30*60 - 10,
        'LIMITS': {
            'LEN_LIMIT': 350,
            'AGE_LIMIT': 30*60 + 120,
            'PAYOUT_LIMIT': 1,
            'VOTES_LIMIT': 50,
            'SPAM_LIMIT': 4,
            'REPUTATION': 0
        },
        'MODEL': {
            'PROBABILITY_THRESHOLD': 0.4,
        }
    },
}

