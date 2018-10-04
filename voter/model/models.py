import logging

import numpy as np
np.random.seed(1337)  # for reproducibility, needs to be before importing keras

from keras.layers import (LSTM, AtrousConvolution1D, Convolution1D, Dropout,
                          Input, MaxPooling1D, merge)
from keras.models import Model
from keras.optimizers import Adam

logger = logging.getLogger(__name__)



# from https://github.com/usernaamee/keras-wavenet/blob/master/simple-generative-model-regressor.py
def wavenetBlock(n_atrous_filters, atrous_filter_size, atrous_rate):
    def f(input_):
        residual = input_
        tanh_out = AtrousConvolution1D(n_atrous_filters, atrous_filter_size,
                                       atrous_rate=atrous_rate,
                                       border_mode='same',
                                       activation='tanh')(input_)
        sigmoid_out = AtrousConvolution1D(n_atrous_filters, atrous_filter_size,
                                          atrous_rate=atrous_rate,
                                          border_mode='same',
                                          activation='sigmoid')(input_)
        merged = merge([tanh_out, sigmoid_out], mode='mul')
        skip_out = Convolution1D(69, 1, activation='relu', border_mode='same')(merged)
        out = merge([skip_out, residual], mode='sum')
        return out, skip_out

    return f


def create_cnn(filters, pool_size, pool_strides):
    return [
        Convolution1D(filters=filters,
                      kernel_size=7,
                      padding='valid',
                      activation='relu',
                      strides=1),
        MaxPooling1D(pool_size=pool_size, strides=pool_strides),
        Convolution1D(filters=filters,
                      kernel_size=7,
                      padding='valid',
                      activation='relu',
                      strides=1),
        MaxPooling1D(pool_size=pool_size, strides=pool_strides),
        Convolution1D(filters=filters,
                      kernel_size=3,
                      padding='valid',
                      activation='relu',
                      strides=1),
        Convolution1D(filters=filters,
                      kernel_size=3,
                      padding='valid',
                      activation='relu',
                      strides=1),
        Convolution1D(filters=filters,
                      kernel_size=3,
                      padding='valid',
                      activation='relu',
                      strides=1),
        Convolution1D(filters=filters,
                      kernel_size=3,
                      padding='valid',
                      activation='relu',
                      strides=1),
        MaxPooling1D(pool_size=pool_size, strides=pool_strides)
    ]


def create_lstms_class(lstm_hidden_size, output_size):
    return [
        LSTM(lstm_hidden_size, return_sequences=True),
        Dropout(0.5),
        LSTM(output_size, activation='softmax', name="classification"),
    ]


def create_cnn_core_class(model_config):
    CONV_CONFIG = model_config['CONVOLUTION']

    core = create_cnn(CONV_CONFIG['FILTERS'], CONV_CONFIG['POOL_SIZE'], CONV_CONFIG['POOL_STRIDES'])
    core.extend(create_lstms_class(model_config['LSTM_HIDDEN_SIZE'], model_config['OUTPUT_SIZE']))
    return core


def apply_shared(shared, inp):
    res = inp
    for layer in shared:
        res = layer(res)
    return res


def create_cnn_class(training_config):
    TR_CONFIG = training_config['TRAINING']
    MODEL_CONFIG = training_config['MODEL']
    DATA_CONFIG = training_config['DATA']

    LR = TR_CONFIG['LR']
    LOSS = TR_CONFIG['LOSS']

    MAX_SEQ_LEN = DATA_CONFIG['MAX_SEQ_LEN']
    EMBEDDING_SIZE = len(DATA_CONFIG['ALPHABET']) + 1

    main_input = Input(shape=(MAX_SEQ_LEN, EMBEDDING_SIZE), name="main_input")

    core = create_cnn_core_class(MODEL_CONFIG)

    classification = apply_shared(core, main_input)

    model = Model(inputs=main_input, outputs=classification)

    # optim = SGD(lr=0.01, decay=1e-5, momentum=0.9) # nesterov=True
    # optim = SGD(lr=LR, decay=1e-5, momentum=0.9) # nesterov=True
    optim = Adam(lr=LR)

    model.compile(loss=LOSS,
                  optimizer=optim,
                  metrics=['mean_absolute_error'])
    model.summary()
    logger.info("Learning rate: %f", LR)
    return model


def sample(preds, temperature=1.0):
    # helper function to sample an index from a probability array
    preds = np.asarray(preds).astype('float64')
    preds = np.log(preds) / temperature
    exp_preds = np.exp(preds)
    preds = exp_preds / np.sum(exp_preds)
    probas = np.random.multinomial(1, preds, 1)
    return np.argmax(probas)
