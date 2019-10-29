# coding=utf-8

import re
import requests
import json
import logging


class TranscribeServiceConfig:
    def __init__(self, backend_root, user, password):
        self.backend_root = backend_root
        self.user = user
        self.password = password


class WordsComparator:
    def __init__(self, words_file_path):
        self.__init_words_list(words_file_path)

    def __init_words_list(self, words_file_path):
        self.__words = []

        with open(words_file_path, 'r', encoding='utf=8') as handle:
            txt = handle.read()
        lines = txt.split('\n')
        for line in lines:
            cleaned_word = line.replace('\r', '')
            self.__words.append(cleaned_word)

    def get_text_bad_words_entries(self, text_to_check):
        res = []
        delimiters = ['\n', ' ', ',', '.', '?', '!', ':', '‒', '–', '—', '/']
        delimiters_s = ' | '.join(delimiters)
        words = re.split(delimiters_s, text_to_check)
        for word in words:
            if word in self.__words:
                res.append(word)
        return res


class TranscribeService:
    def __init__(self, config: TranscribeServiceConfig):
        self.__BACKEND_ROOT = config.backend_root
        self.__transcribe_url = self.__BACKEND_ROOT + '/OutTranscribe/TranscribeFile'
        self.__auth_url  = self.__BACKEND_ROOT + '/Account/GenerateToken'

        self.__login = config.user
        self.__pass = config.password
        self.__headers = {}

        self.__initialise_auth()

    def __initialise_auth(self):
        logging.info(f'TRY: authenticate on transcribe service with account {self.__login}')
        post_data = {
            'Login': self.__login,
            'Password': self.__pass
        }
        req = requests.post(self.__auth_url, json=post_data)
        json_resp = json.loads(req.text)
        auth_token = json_resp['token']
        auth_header = f"bearer {auth_token}"
        logging.info(f'SUCCESS: Received auth token is {auth_token}')
        self.__headers = {'Authorization': auth_header}

    def get_transcribe(self, audio_file_path):
        files = {
            'audio_file': open(audio_file_path, 'rb')
        }
        timeout = 180
        req = requests.post(self.__transcribe_url, headers=self.__headers, timeout=timeout, files=files)

        return  req.text


if __name__ == '__main__':
    words_file_path = './check_words_list.txt'
    text_comparer = WordsComparator(words_file_path)

    login = 'support'
    password = '8364Veakjybot@69$1'
    transcribe_service = TranscribeService(login, password)

    test_file_path = 'E:/proj/cashee/Loyalty.AudioProcessingService.tests/artifacts/e2e_chunks/1.mp3'
    transcribe_service.get_transcribe(test_file_path)


