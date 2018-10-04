import numpy as np
np.random.seed(1337)  # for reproducibility, needs to be before importing keras

from steevebase.model.utils import get_char_ind_dicts


def sample_body(body, target_len):
    slack = len(body) - target_len
    if slack > 0:
        rand_offset = np.random.randint(slack)
    else:
        rand_offset = 0

    return body[rand_offset:rand_offset + target_len]


def sample_post(title_sample, body, max_len):
    # always include title
    title_sample = title_sample[:max_len - 1]  # take max maxlen-1 chars from the title
    title_sample += "+"  # add "+" to separate title from body

    # count how many chars we can take from the body
    target_body_len = max_len - len(title_sample)

    # take that number of chars from random starting point in the body
    body_sample = sample_body(body, target_body_len)

    sample = title_sample + body_sample

    return sample


def post_to_num_pad(sample, char2ind, max_len):
    res = np.zeros(max_len, dtype='float32')

    # padding with 0 from the right if post shorter than max_len
    for i, c in enumerate(sample):
        res[i] = char2ind[c]

    return res.astype(int)


def one_hot_encode(x, n_classes):
    return np.eye(n_classes, dtype='float32')[x]


def one_hot_encode_post(title, body, char2ind, max_seq_len, embedding_size):
    # sample post
    sample = sample_post(title, body, max_seq_len)

    # convert to indices in the alphabet, if too short, pad
    encoded_post = post_to_num_pad(sample, char2ind, max_seq_len)

    # one-hot encoding    
    one_hot_post = one_hot_encode(encoded_post, embedding_size)

    return one_hot_post


def unwrap_single_post(post_dict):
    title = post_dict['title']
    body = post_dict['body']
    net_votes = post_dict['net_votes']
    y = None
    if 'target' in post_dict:
        y = post_dict['target']

    return title, body, net_votes, y


def get_batch(data, ind, training_config, batch_size):
    DATA_CONFIG = training_config['DATA']
    EMBEDDING_SIZE = len(DATA_CONFIG['ALPHABET']) + 1  # 1 symbol reserved for unknown chars
    MAX_SEQ_LEN = DATA_CONFIG['MAX_SEQ_LEN']
    char2ind, _ = get_char_ind_dicts(DATA_CONFIG['ALPHABET'])

    OUTPUT_SIZE = training_config['MODEL']['OUTPUT_SIZE']


    batch_x = np.zeros((batch_size, MAX_SEQ_LEN, EMBEDDING_SIZE))
    batch_y = np.zeros((batch_size, OUTPUT_SIZE))
    batch_net_votes = np.zeros((batch_size, 1))

    for i in range(batch_size):
        title, body, net_votes, y = unwrap_single_post(data[(ind + i) % len(data)])
        x = one_hot_encode_post(title, body, char2ind, MAX_SEQ_LEN, EMBEDDING_SIZE)

        if OUTPUT_SIZE == 2:
            y_mse = np.zeros(2)
            y_mse[y] = 1
            y = y_mse

        # append to training data
        batch_x[i] = x
        batch_y[i] = y
        batch_net_votes[i, 0] = min(max(net_votes / 2000, 0), 1)

    input_dic = {"main_input": batch_x}
    output_dic = {"classification": batch_y, "regression": batch_net_votes}
    return input_dic, output_dic


def create_data(data, start, limit, training_config, training, period=1):
    TR_CONFIG = training_config['TRAINING']
    BATCH_SIZE = TR_CONFIG['BATCH_SIZE']

    while True:
        if training:
            rands = np.random.randint(start, limit - BATCH_SIZE, period)

            # Shuffle samples
            # print("\n...shuffling data after full data pass...")
            shuffle_indexes = np.arange(limit - start)
            np.random.shuffle(shuffle_indexes)
            data[start:limit] = [data[shuffle_indexes[i]] for i in range(len(shuffle_indexes))]
        else:
            BATCH_SIZE = TR_CONFIG['TEST_SAMPLES']
            if limit - BATCH_SIZE > start:
                rands = list(range(start, limit - BATCH_SIZE, BATCH_SIZE))
            else:
                rands = [0]

        for ind in rands:
            input_dic, output_dic = get_batch(data[start:limit], ind, training_config, BATCH_SIZE)
            yield input_dic, output_dic
