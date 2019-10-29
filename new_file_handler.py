# coding=utf-8

import time
import datetime
import os
import argparse
import logging
import ntpath
import yaml
import shutil

from pydub import AudioSegment

from cnn_aggression_analyzer import CNNAgressionAnalyzer
from vad_extract import CNNNetVAD
from transcribe_service import TranscribeService, WordsComparator, TranscribeServiceConfig


def get_file_name(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


class ChunksGenerator:
    @staticmethod
    def get_chunks_stamps(vad_labels):
        res = []

        admission = 0.3
        cur_window_start = 0
        cur_window_end = 0

        i = 0
        while i < len(vad_labels):
            el = vad_labels[i]
            if el:
                cur_window_start = i

                j = i
                while j < len(vad_labels) and vad_labels[j]:
                    j += 1

                cur_window_end = j
                if cur_window_end < len(vad_labels):
                    cur_window_end += admission

                if cur_window_start > 0:
                    cur_window_start -= admission

                res.append((cur_window_start, cur_window_end))
                i = j

            i += 1

        return res


class Handler:
    ALLOWED_EXTENSIONS = ['.wav', '.mp3']
    MARKER_CNN_FILE_FRAME_RATE = 22050
    VAD_FILE_FRAME_RATE = 44100
    WORK_DIR = 'temp'
    POSITIVE_OUT_DIR = ''

    __tmp_files = []

    def __init__(self, config_file_path, out_dir, logger):
        self.__logger = logger
        self.__config_file_path = config_file_path
        self.POSITIVE_OUT_DIR = out_dir
        if not os.path.isdir(self.POSITIVE_OUT_DIR):
            os.makedirs(self.POSITIVE_OUT_DIR)

        if not os.path.isdir(self.WORK_DIR):
            os.makedirs(self.WORK_DIR)

        self.__init_services()

        # file_to_asses = 'temp/neutral_3_to_transcribe.mp3'
        # # res = self.cnn_agression_analyzer.check_is_file_aggressive(file_to_asses)
        # res = self.transcribe_service.get_transcribe(file_to_asses)
        # print(f'---------------------------------{res}---------------------------------')
        # exit(0)

    def __init_services(self):
        self.__logger.info(f'TRY: Initialise configuration from file "{self.__config_file_path}"')
        with open(self.__config_file_path, 'r') as stream:
            try:
                config = yaml.safe_load((stream))
            except yaml.YAMLError as exc:
                self.__logger.error(f"Can't parse config file")
                self.__logger.error(exc)

        transcriber_config = TranscribeServiceConfig(
            config['transcriber_config']['backend_root'],
            config['transcriber_config']['user'],
            config['transcriber_config']['password'],
        )
        vad_model_path = config['vad_model_path']  # 'vad_models/vad/model.ckpt-200106'
        aggression_cnn_model_path = config['aggression_cnn_model_path']  # 'agression_cnn_model.h5'
        self.__aggr_activation_threshold = config['aggression_activation_threshold']

        self.__logger.debug('TRY: Initialise CNN for aggresion assessment')
        self.cnn_agression_analyzer = CNNAgressionAnalyzer(aggression_cnn_model_path, self.__logger)
        self.__logger.debug('SUCCESS: Initialise CNN for aggresion assessment')

        self.__logger.debug('TRY: Initialise VAD CNN')
        self.vad = CNNNetVAD(256, vad_model_path)
        self.__logger.debug('SUCCESS: Initialise VAD CNN')

        self.__logger.debug('TRY: Initialise Transcribe service')
        self.transcribe_service = TranscribeService(transcriber_config)
        self.__logger.debug('SUCCESS:  Initialise Transcribe service')

        bad_words_file_path = 'bad_words_list.txt'
        self.__logger.debug(f'TRY: Initialise Transcribe comparator. Bad words file is: {bad_words_file_path}')
        self.bad_words_checker = WordsComparator(bad_words_file_path)
        self.__logger.debug('SUCCESS: Initialise Transcribe comparator')

    def on_any_event(self, event):
        self.__logger.info(f'Catch monitored directory event: "{event}"')
        if event.is_directory:
            return None
        elif event.event_type == 'created':
            self.__new_file_handler(event.src_path)

    def new_file_handler(self, file_path):
        self.__logger.info(f'Start processing of file "{file_path}"')
        self.__tmp_files = []

        _, ext = os.path.splitext(file_path)
        file_name = get_file_name(file_path).replace(ext, '')

        if ext not in self.ALLOWED_EXTENSIONS:
            logging.warning(f'File has not supported extension ({ext})')

        # First - convert file to wav
        if 'wav' in ext:
            segm_obj = AudioSegment.from_wav(file_path)
        else:
            segm_obj = AudioSegment.from_mp3(file_path)

        segm_obj.set_channels(1)

        self.__logger.info(f'Convert file to VAD service compatible format (Frame rate={self.VAD_FILE_FRAME_RATE})')
        segm_obj.set_frame_rate(self.VAD_FILE_FRAME_RATE)
        vad_full_path = os.path.join(self.WORK_DIR, f'{file_name}.wav')
        segm_obj.export(vad_full_path, format='wav')
        self.__tmp_files.append(vad_full_path)

        # Split file with VAD
        vad_reponse = self.vad.extract_voice(vad_full_path)
        self.__logger.debug(f'Vad CNN response is {vad_reponse}')

        # Create chunks according to ad response
        chunks_stamps = ChunksGenerator.get_chunks_stamps(vad_reponse)

        # Asses file aggression with CNN
        # Concatenate voiced chunks together - in new file
        self.__logger.info(f'Chunks_stamps is: {chunks_stamps}')
        obj_to_asses_aggr = AudioSegment.empty()
        for chunk_stamp in chunks_stamps:
            obj_to_asses_aggr += segm_obj[chunk_stamp[0]*1000: chunk_stamp[1]*1000]

        file_to_asses_aggr_path = os.path.join(self.WORK_DIR, file_name + '_voice' + '.wav')
        segm_obj.set_frame_rate(self.MARKER_CNN_FILE_FRAME_RATE)
        obj_to_asses_aggr.export(file_to_asses_aggr_path, format='wav')
        self.__tmp_files.append(file_to_asses_aggr_path)

        self.__logger.info(f'TRY: Call CNN for aggressiveness assesment for file {file_to_asses_aggr_path}')
        is_aggressive = self.cnn_agression_analyzer.check_is_file_aggressive(file_to_asses_aggr_path, self.__aggr_activation_threshold)
        self.__logger.info(f'SUCCESS: ------------------------ Is aggressive: {is_aggressive} ------------------------')

        bad_words_entries = []
        USE_TRANSCRIBE = False
        if not is_aggressive and USE_TRANSCRIBE:
            file_to_transcribe_path = os.path.join(self.WORK_DIR, file_name + '_to_transcribe.mp3')
            obj_to_asses_aggr.export(file_to_transcribe_path, format='mp3')
            self.__logger.info(f'TRY: Call transcribe service for file {file_to_transcribe_path}')
            transcribe = self.transcribe_service.get_transcribe(file_to_transcribe_path)
            # self.__logger.info(f'SUCCESS: File transcribe is: {transcribe}')
            if transcribe is not None and len(transcribe) > 0:
                bad_words_entries = self.bad_words_checker.get_text_bad_words_entries(transcribe)
                if len(bad_words_entries) > 0:
                    self.__logger.warning(f'File contains bad words: {bad_words_entries}')
                else:
                    self.__logger.debug(f'File does not contain any bad words')

        self.__tmp_files.append(file_path)

        if is_aggressive or len(bad_words_entries) > 0:
            # File is marked - create a copy to output directory
            dst_file_path = os.path.join(self.POSITIVE_OUT_DIR, file_name + ext)
            shutil.copy(file_path, dst_file_path)
            self.__logger.info(f'Initial file marked as aggressive - so create a copy to output dir: {dst_file_path}')

        for tmp_file in self.__tmp_files:
            os.remove(tmp_file)
