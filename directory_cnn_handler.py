# coding=utf-8

import datetime
import os
import shutil
import logging
import ntpath
import yaml
import tqdm

from pydub import AudioSegment

# from cnn_aggression_analyzer import CNNAgressionAnalyzer


def get_file_name(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


today = datetime.date.today()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# create file handler which logs even debug messages
fh = logging.FileHandler(f'./logs/gpn_prod_check1-{today.strftime("%Y%m%d")}.log')
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


ALLOWED_EXTENSIONS = ['.wav', '.mp3']
MARKER_CNN_FILE_FRAME_RATE = 22050
ACTIVATION_THRESHOLD = 0.67
SAVE_FREQ = 10
MINIMAL_IN_DURATION = 5
MINIMAL_CHUNK_DURATION = 5
CHUNK_LENGTH_SECONDS = 15
WORK_DIR = '/home/gpn/Voice_emotion_zdy/tmp'
WORK_DIR = '/home/dmzubr/gpn/Voice_emotion_zdy/tmp'
ITER_NAME = f'20191017_aggr_true_activation_{str(ACTIVATION_THRESHOLD).replace(".", "")}'
ITER_NAME = f'20191017_aggr_true_activation_075'
out_aggr_dir = f'/home/dmzubr/gpn/Voice_emotion_zdy/{ITER_NAME}'
if not os.path.isdir(out_aggr_dir):
    os.makedirs(out_aggr_dir)
aggr_data_csv = f'/home/dmzubr/gpn/Voice_emotion_zdy/{ITER_NAME}.csv'


def save_aggr_data(data_list):
    logger.debug(f'TRY: Save analyzed meta to {aggr_data_csv}')
    with open(aggr_data_csv, 'w', encoding='utf-8') as out_f:
        header_line = f'path;chunks\n'
        out_f.write(header_line)
        for item in data_list:
            line = f"{item['path']};{str(item['chunks'])}\n"
            out_f.write(line)
    logger.info(f'SUCCESS: Save analyzed meta to {aggr_data_csv}')


def asses_aggr_src_files():
    src_files_dir = '/home/gpn/Voice_emotion_zdy/gpn_prod_check'
    src_files_list = [os.path.join(src_files_dir, x) for x in os.listdir(src_files_dir)]

    with open('config.yml', 'r') as stream:
        try:
            config = yaml.safe_load((stream))
        except yaml.YAMLError as exc:
            print(exc)
            exit(0)

    aggression_cnn_model_path = config['aggression_cnn_model_path']  # 'agression_cnn_model.h5'
    cnn_aggression_analyzer = CNNAgressionAnalyzer(aggression_cnn_model_path, logger)
    handled_files_count = 1
    current_save_counter = 0
    handled_files_meta = []

    # src_files_list = src_files_list[0:1]

    for src_file_path in src_files_list:
        try:
            _, ext = os.path.splitext(src_file_path)
            file_name = get_file_name(src_file_path).replace(ext, '')

            # First - convert file to wav
            if 'wav' in ext:
                segm_obj = AudioSegment.from_wav(src_file_path)
            else:
                segm_obj = AudioSegment.from_mp3(src_file_path)

            if segm_obj.duration_seconds < MINIMAL_IN_DURATION:
                logger.warning(f'Too short file: {src_file_path}:{segm_obj.duration_seconds}s')
                continue

            segm_obj = segm_obj.set_channels(1)
            segm_obj = segm_obj.set_frame_rate(MARKER_CNN_FILE_FRAME_RATE)

            files_to_cleanup = []

            chunk_start = 0
            chunk_end = CHUNK_LENGTH_SECONDS*1000
            chunk_iter = 1
            cur_file_chunks = []
            if chunk_end > segm_obj.duration_seconds*1000:
                chunk_end = segm_obj.duration_seconds * 1000

            while chunk_end < segm_obj.duration_seconds*1000 \
                    and (chunk_end - chunk_start)/1000 < MINIMAL_CHUNK_DURATION * 1000:
                logger.debug(f'Chunk from {chunk_start} to {chunk_end}')
                chunk_obj = segm_obj[chunk_start:chunk_end]
                chunk_file_name = file_name + f'_part_{chunk_iter}.wav'
                chunk_path = os.path.join(WORK_DIR, chunk_file_name)
                chunk_obj.export(chunk_path, format='wav')
                assert os.path.isfile(chunk_path)

                aggr_level = cnn_aggression_analyzer.get_aggressive_prediction_level(chunk_path)
                logger.debug(f'AGGR: {aggr_level}')

                if aggr_level > ACTIVATION_THRESHOLD:
                    logger.info(f'---------------- AGGR: {aggr_level} ----------------')

                cur_file_chunk_meta = {
                    'from': chunk_start,
                    'to': chunk_end,
                    'aggr_level': aggr_level,
                    'number': chunk_iter
                }
                cur_file_chunks.append(cur_file_chunk_meta)

                files_to_cleanup.append(chunk_path)
                chunk_start = chunk_end
                chunk_end += CHUNK_LENGTH_SECONDS*1000
                chunk_iter += 1

            handled_file_meta = {'path': src_file_path, 'chunks': cur_file_chunks}
            handled_files_meta.append(handled_file_meta)

            # file_to_asses_aggr_path = os.path.join(WORK_DIR, file_name + '.wav')
            # segm_obj.export(file_to_asses_aggr_path, format='wav')
            #assert os.path.isfile(file_to_asses_aggr_path)

            # logger.info(f'Check file "{src_file_path}":-------------- {handled_files_count} OUT OF {len(src_files_list)}')
            # aggr_level = cnn_agression_analyzer.get_aggressive_prediction_level(file_to_asses_aggr_path)
            # logger.info(f'AGGR: {aggr_level}. File "{src_file_path}":-------------- {handled_files_count} OUT OF {len(src_files_list)}')
            # is_aggressive = cnn_agression_analyzer.check_is_file_aggressive(file_to_asses_aggr_path, ACTIVATION_THRESHOLD)
            # is_aggressive = aggr_level > ACTIVATION_THRESHOLD
            # handled_files_meta.append({'path': src_file_path, 'aggr_level': aggr_level})

            aggressive_chunks = [x for x in cur_file_chunks if x['aggr_level'] > ACTIVATION_THRESHOLD]
            if len(aggressive_chunks) > 0:
                logger.info(f'--------------------------- AGGRESSIVE {src_file_path} ---------------------')
                logger.info(f'--------------------------- Chunk {aggressive_chunks[0]} --------------------')

                # Copy src file itself
                dst_file_name = os.path.join(out_aggr_dir, file_name + ext)
                shutil.copy(src_file_path, dst_file_name)

                # Copy target chunk
                target_chunk_num_str = f"_part_{aggressive_chunks[0]['number']}.wav"
                target_chunk_file_name = [x for x in os.listdir(WORK_DIR) if target_chunk_num_str in x][0]
                chunk_src_path = os.path.join(WORK_DIR, target_chunk_file_name)
                chunk_dst_path = os.path.join(out_aggr_dir, target_chunk_file_name)
                shutil.copy(chunk_src_path, chunk_dst_path)

            for file_to_cleanup in files_to_cleanup:
                os.remove(file_to_cleanup)
        except Exception as exc:
            logger.error(exc)

        if current_save_counter >= SAVE_FREQ:
            save_aggr_data(handled_files_meta)
            current_save_counter = 0

        handled_files_count += 1
        current_save_counter += 1

    logger.info('Handled files are: ')
    logger.info(handled_files_meta)


def init_list_from_file():
    res = []

    with open(aggr_data_csv, 'r', encoding='utf-8') as csv_f:
        txt = csv_f.read()
    lines = txt.split('\n')

    line_iterator = 0
    for line in lines:
        if line_iterator == 0:
            line_iterator = 1
            continue
        top_spl = line.split(';')
        fiLe_path = top_spl[0]

        file_chunks = []
        if len(top_spl) > 1:
            chunks_arr_str = top_spl[1]
            chunks_spl = chunks_arr_str.split('},')
            fiile_def = {'path': fiLe_path}
            for chunks_str in chunks_spl:
                chunk_def = {}
                props = chunks_str.split(',')
                if len(props) > 1:
                    for i in range(len(props)):
                        prop_val_str = props[i].split(':')[1]
                        cleaned_prop_val = prop_val_str.replace('[', '').replace('{', '').replace('\'', '').replace(']', '').replace('}', '')
                        if i == 0:
                            chunk_def['from'] = int(cleaned_prop_val)
                        elif i == 1:
                            chunk_def['to'] = int(cleaned_prop_val)
                        elif i == 2:
                            chunk_def['aggr_level'] = float(cleaned_prop_val)
                        elif i == 3:
                            chunk_def['number'] = int(cleaned_prop_val)
                    file_chunks.append(chunk_def)

            fiile_def['chunks'] = file_chunks
            res.append(fiile_def)

    return res


def create_out_aggr_chunks_by_threshold(file, out_dir):
    aggressive_chunks = [x for x in file['chunks'] if x['aggr_level'] > ACTIVATION_THRESHOLD]
    if len(aggressive_chunks) > 0:
        _, ext = os.path.splitext(file['path'])
        src_file_name = get_file_name(file['path']).replace(ext, '')
        target_chunk_num_str = f"_part_{aggressive_chunks[0]['number']}.wav"
        target_chunk_file_name = src_file_name + '_' + target_chunk_num_str
        chunk_dst_path = os.path.join(out_dir, target_chunk_file_name)

        src_file_path = file['path'].replace('/home/gpn/', '/home/dmzubr/gpn/')
        src_file_obj = AudioSegment.from_mp3(src_file_path)
        chunk_obj = src_file_obj[aggressive_chunks[0]['from']:aggressive_chunks[0]['to']]
        chunk_obj.export(chunk_dst_path, format='mp3')
        assert os.path.isfile(chunk_dst_path)


existed_meta_list = init_list_from_file()
out_dir = '20191017_aggr_true_activation_067'
for file_meta in tqdm.tqdm(existed_meta_list):
    try:
        create_out_aggr_chunks_by_threshold(file_meta, out_dir)
    except Exception as exc:
        logger.error(exc)

print(existed_meta_list[0:2])
