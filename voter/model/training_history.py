import logging

import numpy as np
np.random.seed(1337)  # for reproducibility, needs to be before importing keras

import keras
from sklearn.metrics import confusion_matrix
from steevebase.model.utils import print_2d

logger = logging.getLogger(__name__)


def save_training_history(training_data, outfile):
    np.savez(outfile,
             training=training_data['training'],
             metrics_names=np.array(training_data['metrics_names']),
             min_loss=np.array(training_data['min_loss']),
             net_votes=training_data['net_votes'],
             predictions=training_data['predictions'],
             conf_mats=training_data['conf_mats'],
             label_categorical=training_data['label_categorical'],
             )


class TrainingHistory(keras.callbacks.Callback):
    def __init__(self, test_set, model_instance, training_config):
        self.test_set = test_set
        self.model_instance = model_instance

        TR_CONFIG = training_config['TRAINING']
        self.output_size = training_config['MODEL']['OUTPUT_SIZE']

        self.save_best_only = TR_CONFIG['SAVE_BEST_ONLY']
        self.epochs = TR_CONFIG['EPOCHS']
        self.steps_per_epoch = TR_CONFIG['STEPS_PER_EPOCH']
        self.batch_size = TR_CONFIG['BATCH_SIZE']

        self.training_stats = None
        self.training_stats_name = training_config['DATA']['TRAINING_STATS_NAME']

    def alloc_training_stats(self, metrics_names, test_set):
        training_stats = {}

        training_stats['training'] = np.empty(shape=[0, len(metrics_names)])
        if self.save_best_only:
            training_stats['validation'] = np.empty(shape=[0, len(metrics_names)])

        training_stats['metrics_names'] = metrics_names
        training_stats['min_loss'] = 1000

        training_stats['net_votes'] = test_set[1]['regression'][:, -1]
        training_stats['predictions'] = np.empty(shape=[0, test_set[1]['classification'].shape[0], self.output_size])

        training_stats['conf_mats'] = np.empty(shape=[0, self.output_size, self.output_size + 1])

        training_stats['label_categorical'] = np.argmax(test_set[1]['classification'], axis=1)

        return training_stats


    def on_train_begin(self, logs={}):
        self.training_stats = self.alloc_training_stats(self.model_instance.metrics_names, self.test_set)


    def on_batch_end(self, batch, logs={}):
        self.training_stats['training'] = np.concatenate([self.training_stats['training'], np.array(
            [logs[k] for k in self.model_instance.metrics_names]).reshape((1,len(self.model_instance.metrics_names)))])


    def on_epoch_end(self, batch, logs={}):
        if self.save_best_only:
            self.training_stats['validation'] = np.concatenate([self.training_stats['validation'],
               np.array([logs["val_" + k] for k in self.model_instance.metrics_names]).reshape((1,len(self.model_instance.metrics_names)))])

        predictions = self.model_instance.predict(self.test_set[0], batch_size=self.batch_size)
        self.training_stats['predictions'] = np.concatenate((self.training_stats['predictions'], predictions.reshape(1, self.test_set[1]['classification'].shape[0], self.output_size)))

        res = np.rint(predictions[:, 1]).astype(int)

        conf_mat = np.empty([1, self.output_size, self.output_size+1])
        conf_mat[0, :self.output_size, :self.output_size] = confusion_matrix(
            self.training_stats['label_categorical'], res, [0, 1])
        conf_mat[0, 0, -1] = conf_mat[0, 0, 0] / conf_mat[0, 0, :self.output_size].sum()
        conf_mat[0, 1, -1] = conf_mat[0, 1, 1] / conf_mat[0, 1, :self.output_size].sum()
        self.training_stats['conf_mats'] = np.concatenate((self.training_stats['conf_mats'], conf_mat))

        print()
        print_2d(self.training_stats['conf_mats'][batch], self.output_size, self.output_size + 1)
        print()

        save_training_history(self.training_stats, self.training_stats_name)
