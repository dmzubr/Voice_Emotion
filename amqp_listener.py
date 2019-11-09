import ntpath
import os
import requests
import tempfile
from datetime import datetime
import logging
import pika
import json
import yaml

from pydub import AudioSegment

from asses_aggression_service import AggressionAssessorService
from yandex_cloud_service import YaCloudService


def get_file_name_from_url(url):
    res = url.rsplit('/', 1)[1]
    return res


def get_file_extension_from_url(url):
    file_name = get_file_name_from_url(url)
    res = file_name.rsplit('.', 1)[1]
    return res


def get_file_name_from_path(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


def get_dir_path_from_file_path(path):
    head, tail = ntpath.split(path)
    return head


def upload_and_save_file(file_url, out_file_path):
    r = requests.get(file_url, allow_redirects=True)
    open(out_file_path, 'wb').write(r.content)


class AssesAggressionAMQPService:
    def __init__(self, config_file_path):
        self.__init_logger()

        if not os.path.isfile(config_file_path):
            self.__logger.error(f'Config file not found: {config_file_path}')
            raise FileNotFoundError

        with open(config_file_path, 'r') as stream:
            try:
                config = yaml.safe_load((stream))
            except yaml.YAMLError as exc:
                self.__logger.error(f"Can't parse config file")
                self.__logger.error(exc)

        self.__channel = None
        self.__in_queue_name = 'Loyalty.Audio.EmotionsAssesorService.Logic.Messages.AssesAggressionRequest, Loyalty.Audio.EmotionsAssesorService.Logic'
        self.__exchange_name = config['amqp']['exchange_name']  # 'easy_net_q_rpc'
        self.__amqp_host = config['amqp']['amqp_host']
        self.__user_name = config['amqp']['user_name']
        self.__password = config['amqp']['password']
        self.__aggr_threshold = config['aggression_cnn']['aggression_activation_threshold']

        # Init Ya cloud storage service
        ya_bucket_name = config['ya_cloud_storage']['bucket_name']
        ya_creds_obj = config['ya_cloud_storage']
        self.__cloud_storage = YaCloudService(ya_bucket_name, ya_creds_obj)

        # Init aggression assessment service
        self.__aggression_assessor_service = AggressionAssessorService(config_file_path=config_file_path,
                                                                       logger=self.__logger)

    def __init_logger(self):
        logging.getLogger('pika').setLevel(logging.WARNING)

        self.__logger = logging.getLogger()
        self.__logger.setLevel(logging.DEBUG)
        now = datetime.now()
        logs_dir = './logs'
        os.makedirs(logs_dir, exist_ok=True)

        fh = logging.FileHandler(f'./logs/segan_denoiser-{now.strftime("%Y%m%d")}.log')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        self.__logger.addHandler(fh)
        self.__logger.addHandler(ch)

    def __assess_aggression(self, file_urls_list, file_local_paths_list, chunk_length,
                            save_aggr_chunks_to_cloud:bool = True):
        res_list = []
        temp_files = []

        for file_url in file_urls_list:
            # Load file from url
            initial_file_name = get_file_name_from_url(file_url)
            question_mark_index = initial_file_name.find('?')
            if question_mark_index > -1:
                initial_file_name = initial_file_name[0:question_mark_index]
            initial_file_path = os.path.join(tempfile.gettempdir(), initial_file_name)
            if not os.path.exists(initial_file_path):
                self.__logger.debug(f'TRY: Save initial file to {initial_file_path}')
                upload_and_save_file(file_url, initial_file_path)
                self.__logger.debug(f'SUCCESS: Initial file saved to {initial_file_path}')

            # Not need to convert file to WAV extension
            # Converting is performed in aggression assessment service itself
            aggressive_chunks = self.__aggression_assessor_service.assess_aggression(file_path=initial_file_path,
                                                                                     aggr_threshold=self.__aggr_threshold,
                                                                                     chunk_length=chunk_length,
                                                                                     use_local_vad=True)
            aggressive_chunks_urls_list = []
            aggression_seconds_stamps = []
            self.__logger.debug(f'Got {len(aggressive_chunks)} aggressive chunks')
            for aggressive_chunk in aggressive_chunks:
                aggression_seconds_stamps.append((aggressive_chunk['from'], aggressive_chunk['to']))
                if save_aggr_chunks_to_cloud:
                    # Save file to cloud
                    chunk_path = aggressive_chunk['path']
                    temp_files.append(chunk_path)
                    if '.wav' in aggressive_chunk['path']:
                        # Resave file in mp3 format before save to cloud (to optimize storage size)
                        self.__logger.debug(f"Convert chunk to MP3 format to optimize storage space")
                        chunk_obj = AudioSegment.from_wav(chunk_path)
                        chunk_path = chunk_path.replace('.wav', '.mp3')
                        chunk_obj.export(chunk_path, format='mp3')
                        assert os.path.exists(chunk_path)
                        temp_files.append(chunk_path)
                        self.__logger.debug(f"Chunk MP3 file p[ath is {chunk_path}")

                    self.__logger.debug(f"Save file {chunk_path} to cloud")
                    chunk_file_name = get_file_name_from_path(chunk_path)
                    chunk_url = self.__cloud_storage.save_object_to_storage(file_to_save=chunk_path,
                                                                            save_file_name=chunk_file_name)
                    self.__logger.debug(f"Saved chunk url is {chunk_url}")
                    aggressive_chunks_urls_list.append(chunk_url)
            res_item = {
                'SrcFileUrl': file_url,
                'SrcFilePath': initial_file_path,
                'SavedAggressiveChunkUrl': aggressive_chunks_urls_list,
                'AggressionParts': aggression_seconds_stamps
            }

            res_list.append(res_item)

        res = {}
        res['Files'] = res_list
        return res

    def __handle_delivery(self, channel, method_frame, header_frame, body):
        body_str = body.decode('utf-8')
        self.__logger.info('New assess aggression request: ', body_str)
        req = json.loads(body_str)
        self.__channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        try:
            save_res_chunks_to_cloud = str(req['SaveChunksToCloud']).lower() == 'true'
            res_obj = self.__assess_aggression(file_urls_list=req['FileUrlsList'],
                                               file_local_paths_list=req['FilePathsList'],
                                               save_aggr_chunks_to_cloud=save_res_chunks_to_cloud)
            self.__push_message(header_frame.reply_to, header_frame.correlation_id, res_obj)
        except Exception as exc:
            self.__logger.error(exc)
            res_obj = {'ErrorMessage': str(exc)}
            self.__push_message(header_frame.reply_to, header_frame.correlation_id, res_obj)

    def __push_message(self, reply_to_key, correlation_id, res_obj):
        res = res_obj
        body = json.dumps(res)
        msg_type = 'Loyalty.Audio.DenoiserSegan.SeganDenoisingResponse, Loyalty.Audio.DenoiserSegan'
        props = pika.BasicProperties(correlation_id=correlation_id, type=msg_type)
        self.__logger.debug(f'Publish message to queue {reply_to_key}. Body: {body}')
        self.__channel.basic_publish(exchange=self.__exchange_name, routing_key=reply_to_key, body=body, properties=props)

    def run_listener(self):
        try:
            self.__logger.debug(f'Connecting to AMQP server with username {self.__user_name}')
            credentials = pika.PlainCredentials(self.__user_name, self.__password)
            parameters = pika.ConnectionParameters(host=self.__amqp_host, credentials=credentials)
            connection = pika.BlockingConnection(parameters)

            self.__channel = connection.channel()
            self.__logger.debug(f'Channel created top host {self.__amqp_host}')

            self.__channel.queue_declare(queue=self.__in_queue_name, durable=True, exclusive=False, auto_delete=False)
            self.__channel.queue_bind(queue=self.__in_queue_name, exchange=self.__exchange_name, routing_key=self.__in_queue_name)
            self.__logger.debug(f'Exchange is "{self.__exchange_name}". Queue is "{self.__in_queue_name}'"")
            self.__channel.basic_consume(queue=self.__in_queue_name, on_message_callback=self.__handle_delivery)

            self.__logger.debug(f'Activate blocking listening for queue {self.__in_queue_name}')
            self.__channel.start_consuming()
        except KeyboardInterrupt:
            self.__channel.stop_consuming()
            connection.close()
            connection.ioloop.stop()
        except Exception as e:
            self.__logger.error(e)
            self.run_listener()


def main():
    config_file_path = 'config.yml'
    listener = AssesAggressionAMQPService(config_file_path)
    listener.run_listener()


if __name__ == "__main__":
    main()
