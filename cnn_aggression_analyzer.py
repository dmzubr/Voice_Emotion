# coding=utf-8

import os

import numpy as np
import pandas as pd
import librosa
from keras.models import Sequential
from keras.layers import Conv2D, MaxPool2D, Flatten, Dropout, Dense
import tensorflow as tf


global graph
graph = tf.get_default_graph()


class CNNConfig:
    def __init__(self, n_mfcc=26, n_feat=13, n_fft=552, sr=22050, window=0.4, test_shift=0.1):
        self.n_mfcc = n_mfcc
        self.n_feat = n_feat
        self.n_fft = n_fft
        self.sr = sr
        self.window = window
        self.step = int(sr * window)
        self.test_shift = test_shift
        self.shift = int(sr * test_shift)


class CNNAgressionAnalyzer:
    CLASSES = pd.DataFrame({'emotion': ['neutral', 'angry']})
    INPUT_SHAPE = (13, 16, 1)

    def __init__(self, model_path, logger):
        self.__logger = logger

        # Check that model file is existed and accessible
        if not os.path.isfile(model_path):
            raise Exception(f'CNN model ({model_path}) file is not existed or is not available')

        self.__model_path = model_path

        # Initialise CNN model
        self.__logger.info('TRY: Initialise CNN model')
        self.cnn_model = self.__create_cnn()
        self.cnn_model.load_weights(model_path)
        self.__logger.info(self.cnn_model.summary())
        self.__logger.info('SUCCESS: Model is initialised')

        pass

    def check_is_file_aggressive(self, file_path, activation_line=0.5):
        prediction = self.__get_file_prediction(file_path)

        # if prediction[1] > prediction[0]:
        if prediction[1] >= activation_line:
            return True

        return False

    def get_aggressive_prediction_level(self, file_path):
        prediction = self.__get_file_prediction(file_path)
        return prediction[1]

    # Function to define CNN
    def __create_cnn(self):
        self.__cnn_config = CNNConfig()

        model = Sequential()
        model.add(Conv2D(16, (3, 3), activation='relu', strides=(1, 1), padding='same', input_shape=self.INPUT_SHAPE))
        model.add(Conv2D(32, (3, 3), activation='relu', strides=(1, 1), padding='same'))
        model.add(Conv2D(64, (3, 3), activation='relu', strides=(1, 1), padding='same'))
        model.add(Conv2D(128, (3, 3), activation='relu', strides=(1, 1), padding='same'))
        model.add(MaxPool2D((2, 2)))
        model.add(Dropout(0.5))
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dense(64, activation='relu'))
        model.add(Dense(len(self.CLASSES), activation='softmax'))
        model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['acc'])
        return model

    def __get_file_prediction(self, file_path):
        # Initialize a local results list
        res = []

        # Initialize min and max values for each file for scaling
        _min, _max = float('inf'), -float('inf')

        # Get the numerical label for the emotion of the file
        wav, sr = librosa.load(file_path)

        # Create an array to hold features for each window
        X = []

        cfg = self.__cnn_config

        # Iterate over sliding 0.4s windows of the audio file
        for i in range(int((wav.shape[0] / sr - cfg.window) / cfg.test_shift)):
            X_sample = wav[i * cfg.shift: i * cfg.shift + cfg.step]  # slice out 0.4s window
            X_mfccs = librosa.feature.mfcc(X_sample, sr, n_mfcc=cfg.n_mfcc, n_fft=cfg.n_fft,
                                           hop_length=cfg.n_fft)[1:cfg.n_feat + 1]  # generate mfccs from sample

            _min = min(np.amin(X_mfccs), _min)
            _max = max(np.amax(X_mfccs), _max)  # check min and max values
            X.append(X_mfccs)  # add features of window to X

        # Put window data into array, scale, then reshape
        X = np.array(X)
        X = (X - _min) / (_max - _min)
        X = X.reshape(X.shape[0], X.shape[1], X.shape[2], 1)

        # Feed data for each window into model for prediction
        for i in range(X.shape[0]):
            window = X[i].reshape(1, X.shape[1], X.shape[2], 1)
            res.append(self.cnn_model.predict(window))

        # Aggregate predictions for file into one then append to all_results
        res = (np.sum(np.array(res), axis=0) / len(res))[0]
        res = list(res)

        return res
