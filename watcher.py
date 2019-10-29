# coding=utf-8

import time
import datetime
import os
import argparse
import logging
import traceback

from new_file_handler import Handler


today = datetime.date.today()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler(f'./logs/watcher-{today.strftime("%Y%m%d")}.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


class MyWatcher:
    dir_state = []
    INTERVAL = 3

    def __init__(self, dir_to_watch, new_file_hadler):
        logger.debug(f'TRY: Activating watcher on directory "{dir_to_watch}"')
        self.__dir_to_watch = dir_to_watch
        self.__new_file_hadler = new_file_hadler
        logger.debug(f'SUCCESS: Activating watcher on directory "{dir_to_watch}"')

    def run(self):
        while True:
            dir_files = [os.path.join(self.__dir_to_watch, x) for x in os.listdir(self.__dir_to_watch)
                         if (os.path.isfile(os.path.join(self.__dir_to_watch, x)))
                         and (x[-4:] == '.mp3' or x[-4:] == '.wav')]
            if dir_files != self.dir_state:
                files_to_process = [x for x in dir_files if x not in self.dir_state]
                self.dir_state = dir_files
                for i in range(0, len(files_to_process)):
                    # Create inprogress tempfile
                    progress_file_path = files_to_process[i] + '._in_progress'
                    with open(progress_file_path, 'w', encoding='utf-8') as handle:
                        handle.write('File is under processing')

                    try:
                        self.__new_file_hadler(files_to_process[i])
                        if os.path.isfile(progress_file_path):
                            os.remove(progress_file_path)
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error on processing of file: {files_to_process[i]}')
                        logger.error(tb)
                        error_file_path = files_to_process[i] + '._error'
                        with open(error_file_path, 'w', encoding='utf-8') as handle:
                            handle.write(tb)
                        self.dir_state.append(files_to_process[i])

                try:
                    for i in range(0, len(files_to_process)):
                        files_to_process.remove(files_to_process[i])
                except Exception as exc:
                    logger.debug('pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # Docker environment dir name is: /in_audio
    # Host os environment dir name is: /srv/samba/share/test/
    parser.add_argument('--in_dir',
                        default=r'/in_audio',
                        help='Directory for monitoring for new received files')

    # Docker environment dir name is: /out_audio
    # Host os environment dir name is: /srv/samba/share/test/
    parser.add_argument('--out',
                        default=r'/out_audio',
                        help='Directory to output filtered files')

    args = parser.parse_args()

    if not os.path.isdir(args.in_dir):
        print(f'Input directory not found: "{args.in_dir}"')
        exit(-1)

    if not os.path.isdir(args.out):
        os.makedirs(args.out)

    config_file_path = 'config.yml'
    new_file_handler = Handler(config_file_path, args.out, logger)
    watcher = MyWatcher(args.in_dir, new_file_handler.new_file_handler)
    watcher.run()
