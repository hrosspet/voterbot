import logging
import math

import numpy as np
np.random.seed(1337)  # for reproducibility, needs to be before importing keras

from keras.callbacks import ModelCheckpoint

from datetime import datetime, timedelta

from steevebase.io import load_sequence, load_data, save_sequence
from steevebase.model import generator, models
from steevebase.model.training_history import TrainingHistory

logger = logging.getLogger(__name__)


def get_generators(training_config):
    TR_CONFIG = training_config['TRAINING']

    TEST2TRAIN_RATIO = TR_CONFIG['TEST2TRAIN_RATIO']
    BATCH_SIZE = TR_CONFIG['BATCH_SIZE']
    STEPS_PER_EPOCH = TR_CONFIG['STEPS_PER_EPOCH']
    TEST_SAMPLES = TR_CONFIG['TEST_SAMPLES']

    data_bin = load_sequence(training_config['DATA']['INPUT_DATA_NAME'])

    training_set_size = int(math.floor(len(data_bin) * (1 - TEST2TRAIN_RATIO)))
    logger.info("Training set size: %d", training_set_size)

    start = 0
    limit = BATCH_SIZE * int(training_set_size / BATCH_SIZE)  # round to be divisible by batch_size

    train_generator = generator.create_data(data_bin, start, limit, training_config, training=True,
                                            period=STEPS_PER_EPOCH)

    start = training_set_size
    limit = len(data_bin)

    if TEST_SAMPLES:
        test_samples = TEST_SAMPLES
    else:
        test_samples = BATCH_SIZE * int((limit - start) / BATCH_SIZE)  # round to be divisible by batch_size

    logger.info("Test set size: %d", test_samples)

    test_generator = generator.create_data(data_bin, start, limit, training_config, training=False)

    return train_generator, test_generator


def get_callbacks(test_set, model_instance, save_model_name, training_config):
    SAVE_BEST_ONLY = training_config['TRAINING']['SAVE_BEST_ONLY']

    callbacks = []

    history = TrainingHistory(test_set, model_instance, training_config)

    callbacks.append(history)

    if SAVE_BEST_ONLY:
        filepath = "min_" + save_model_name + ".hdf5"
    else:
        filepath = save_model_name + "_{epoch:03d}.hdf5"

    logger.info("Model will be saved to %s", filepath)

    checkpointer = ModelCheckpoint(
        save_best_only=SAVE_BEST_ONLY,
        filepath=filepath,
        monitor='val_loss',
        verbose=0,
        save_weights_only=True,
        mode='min')

    callbacks.append(checkpointer)
    return callbacks


def sort_test(test_generator):
    test_set = next(test_generator)

    sorted_indexes = np.argsort(test_set[1]['regression'][:, 0])[::-1]
    test_set[0]['main_input'] = test_set[0]['main_input'][sorted_indexes, :]
    test_set[1]['classification'] = test_set[1]['classification'][sorted_indexes, :]
    test_set[1]['regression'] = test_set[1]['regression'][sorted_indexes, :]
    return test_set


def training(load_model_name, save_model_name, training_config):
    TR_CONFIG = training_config['TRAINING']

    LOSS = TR_CONFIG['LOSS']
    STEPS_PER_EPOCH = TR_CONFIG['STEPS_PER_EPOCH']
    EPOCHS = TR_CONFIG['EPOCHS']
    CLASS_WEIGHT = TR_CONFIG['CLASS_WEIGHT']

    model_instance = models.create_cnn_class(training_config)

    if load_model_name:
        model_instance.load_weights(load_model_name)
        logger.info("Model %s loaded...", load_model_name)

    logger.info("Training objective: %s", LOSS)
    logger.info("Class_weight:")
    logger.info(CLASS_WEIGHT)

    train_generator, test_generator = get_generators(training_config)
    test_set = sort_test(test_generator)

    callbacks = get_callbacks(test_set, model_instance, save_model_name, training_config)

    logger.info('Train...')
    model_instance.fit_generator(
        train_generator,
        steps_per_epoch=STEPS_PER_EPOCH,
        epochs=EPOCHS,
        callbacks=callbacks,
        validation_data=test_set if TR_CONFIG['SAVE_BEST_ONLY'] else None,
        class_weight=CLASS_WEIGHT,
        max_q_size=STEPS_PER_EPOCH,
        workers=4,
        pickle_safe=True)


def fetch_training_data(mongo_address, clean_posts_col_name, start_time):
    query = {'created': {'$gte': start_time}}
    return load_data(mongo_address, clean_posts_col_name, query)


def check_and_fetch_data(training_config):
    import os.path
    from voter.config import CONFIG

    BLOCK_STEP = CONFIG['BLOCK_STEP']

    posts_count = 0

    data_name = training_config['DATA']['INPUT_DATA_NAME']
    if not os.path.isfile(data_name):

        TRAINING_DATA_AGE = training_config['DATA']['TRAINING_DATA_PERIOD'] # days
        MONGO_ADDRESS = CONFIG['DATABASE']['ADDRESS']
        CLEAN_POSTS_COL_NAME = CONFIG['DATABASE']['CLEAN_POSTS_COLLECTION_NAME']

        logger.info('data not found -> fetching data from DB (max %d days old)' % TRAINING_DATA_AGE)

        start_time = datetime.utcnow() - timedelta(days=TRAINING_DATA_AGE)
        cursor, count = fetch_training_data(MONGO_ADDRESS, CLEAN_POSTS_COL_NAME, start_time)

        logger.info('fetching %d posts' % count)

        num_batches = math.ceil(count / BLOCK_STEP)

        for batch in range(num_batches):
            step = min(BLOCK_STEP, count - BLOCK_STEP * batch)
            posts = [next(cursor) for i in range(step)]
            posts_count += len(posts)

            logger.info("Number of posts fetched: %d / %d", posts_count, count)

            save_sequence(data_name, posts)

        logger.info('Finished. Data stored at %s', data_name)


def run(args):
    from steevebase.io import load_training_config

    training_config = load_training_config(args.training_config_name)
    check_and_fetch_data(training_config)
    training(args.load_model_name, args.save_model_name, training_config)

    logger.info("Training finished")
