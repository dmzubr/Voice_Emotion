# coding=utf-8

import os
import logging
import ntpath
import yaml

from pydub import AudioSegment

from cnn_aggression_analyzer import CNNAgressionAnalyzer
from vad_extract import CNNNetVAD
from transcribe_service import TranscribeService, WordsComparator, TranscribeServiceConfig


def get_file_name(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


class AggressionAssessorService:
    ALLOWED_EXTENSIONS = ['.wav', '.mp3']
    MARKER_CNN_FILE_FRAME_RATE = 22050
    VAD_FILE_FRAME_RATE = 44100
    WORK_DIR = 'temp'

    __tmp_files = []

    def __init__(self, config_file_path, logger):
        self.__logger = logger
        self.__config_file_path = config_file_path

        if not os.path.isdir(self.WORK_DIR):
            os.makedirs(self.WORK_DIR)

        self.__init_services()

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
        vad_model_path = config['vad']['model_path']  # 'vad_models/vad/model.ckpt-200106'
        vad_batch_size = config['vad']['batch_size']
        aggr_conf_obj = config['aggression_cnn']
        aggression_cnn_model_path = aggr_conf_obj['cnn_model_path']
        self.__aggr_activation_threshold = aggr_conf_obj['aggression_activation_threshold']

        self.__logger.debug('TRY: Initialise CNN for aggresion assessment')
        self.cnn_agression_analyzer = CNNAgressionAnalyzer(aggression_cnn_model_path, self.__logger)
        self.__logger.debug('SUCCESS: Initialise CNN for aggresion assessment')

        self.__logger.debug('TRY: Initialise VAD CNN')
        self.vad = CNNNetVAD(vad_batch_size, vad_model_path)
        self.__logger.debug('SUCCESS: Initialise VAD CNN')

        self.__logger.debug('TRY: Initialise Transcribe service')
        self.transcribe_service = TranscribeService(transcriber_config)
        self.__logger.debug('SUCCESS:  Initialise Transcribe service')

        bad_words_file_path = 'bad_words_list.txt'
        self.__logger.debug(f'TRY: Initialise Transcribe comparator. Bad words file is: {bad_words_file_path}')
        self.bad_words_checker = WordsComparator(bad_words_file_path)
        self.__logger.debug('SUCCESS: Initialise Transcribe comparator')

    def assess_aggression(self, file_path, aggr_threshold, chunk_length, use_local_vad: bool = True):
        # Returns path to chunks with aggression
        res = []

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
        initial_file_duration = segm_obj.duration_seconds

        if use_local_vad:
            self.__logger.info(f'Convert file to VAD service compatible format (Frame rate={self.VAD_FILE_FRAME_RATE})')
            segm_obj.set_frame_rate(self.VAD_FILE_FRAME_RATE)
            vad_full_path = os.path.join(self.WORK_DIR, f'{file_name}.wav')
            if 'wav' not in ext:
                segm_obj.export(vad_full_path, format='wav')
            self.__tmp_files.append(vad_full_path)

            # Create pure voice part with local VAD
            voice_fle_name = file_name + '_voice.wav'
            voice_wav_file_path = os.path.join(self.WORK_DIR, voice_fle_name)

            vad_reponse = self.vad.extract_voice(vad_full_path, voice_out_path=voice_wav_file_path)
            self.__logger.debug(f'Vad CNN response is {vad_reponse}')
            assert os.path.exists(voice_wav_file_path)

        # Create chunks of entered length from voice file to asses aggression in them
        segm_obj = AudioSegment.from_wav(voice_wav_file_path)
        chunk_start = 0
        chunk_end = chunk_length * 1000
        chunk_iter = 1
        if chunk_end > segm_obj.duration_seconds * 1000:
            chunk_end = segm_obj.duration_seconds * 1000

        while chunk_end <= segm_obj.duration_seconds * 1000:
            if (chunk_end - chunk_start) < 1000:
                break

            self.__logger.debug(f'Chunk from {chunk_start} to {chunk_end}. Assess for aggression threshold {aggr_threshold}')
            chunk_obj = segm_obj[chunk_start:chunk_end]
            chunk_file_name = file_name + '_voice' + f'_part_{chunk_iter}.wav'
            chunk_path = os.path.join(self.WORK_DIR, chunk_file_name)
            chunk_obj.export(chunk_path, format='wav')
            assert os.path.isfile(chunk_path)

            chunk_aggression_level = self.cnn_agression_analyzer.get_aggression(chunk_path)
            self.__logger.debug(f'Chunk {chunk_path} aggression is: {chunk_aggression_level}')
            chunk_descrpition = {
                'from': chunk_start / 1000,
                'to': chunk_end / 1000,
                'path': chunk_path.replace('\\', '/'),
                'aggression_level': chunk_aggression_level
            }
            res.append(chunk_descrpition)

            if chunk_aggression_level < aggr_threshold:
                USE_TRANSCRIBE = False
                if USE_TRANSCRIBE:
                    self.__tmp_files.append(chunk_path)
                    chunk_path_to_transcribe = chunk_path.replace('.wav', '') + '_to_transcribe.mp3'
                    chunk_obj.export(chunk_path_to_transcribe, format='mp3')
                    self.__logger.info(f'TRY: Call transcribe service for file {chunk_path_to_transcribe}')
                    transcribe = self.transcribe_service.get_transcribe(chunk_path_to_transcribe)
                    self.__logger.info(f'SUCCESS: File transcribe is: {transcribe}')
                    if transcribe is not None and len(transcribe) > 0:
                        bad_words_entries = self.bad_words_checker.get_text_bad_words_entries(transcribe)
                        if len(bad_words_entries) > 0:
                            self.__logger.warning(f'File contains bad words: {bad_words_entries}')
                            res.append(chunk_descrpition)
                        else:
                            self.__logger.debug(f'File does not contain any bad words')

            chunk_start = chunk_end
            chunk_end += chunk_length * 1000
            if chunk_end > segm_obj.duration_seconds * 1000:
                chunk_end = segm_obj.duration_seconds * 1000
            chunk_iter += 1

        for tmp_file in self.__tmp_files:
            os.remove(tmp_file)

        return {'chunks': res, 'initial_file_duration': initial_file_duration}
