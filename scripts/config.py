import os

CONFIG = {
    'BLOCK_INTERVAL': 3, # seconds
    'BLOCK_STEP': int(3600 / 3),
    'DOWNLOADER': {
        'DELAY': int(1 * 24 * 3600 / 3)
    },
    'DATABASE': {
        'ADDRESS': os.getenv('MONGODB_ADDRESS', 'mongodb://localhost:26999'),
        # 'ADDRESS': os.getenv('MONGODB_ADDRESS', 'mongodb://107.155.87.82:26999'),
        'NAME': 'steem',
        'USER': 'admin',
        'PASSWORD': 'dmw]SR%u6Ct!',
        'SOURCE': 'admin',
        'PAST_VOTES_COLLECTION_NAME': 'past_votes',
        'BLACK_LIST_COLLECTION_NAME': 'black_list',
        },
    'TRAINING_CONFIG_FOLDER': 'training_configs/',
    'TIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'VOTER': {
        'WIF': "5Hwfg5SvG5mMdxUVRQpb6jwPzSEmiTojEYvVa5NP5TL9GU2njNx",
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

