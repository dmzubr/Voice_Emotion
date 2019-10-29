# coding=utf-8

import os
import requests
import tqdm
import shutil
import random
from pydub import AudioSegment


class OutRecordDefinition:
    def __init__(self, id, dataset_name, file_full_path, actor_id, emotion_name, duration, male, output_type=''):
        self.id = id
        self.dataset_name = dataset_name
        self.file_full_path = file_full_path
        self.actor_id = actor_id
        self.emotion_name = emotion_name
        self.duration = duration
        self.male = male
        self.output_type = output_type


TARGET_SAMPLES_FRAME_RATE = 22050
TARGET_CHANNELS = 1
VALID_DATA_PERCENT = 15


def get_records_from_dir(dir_path, emotion_name):
    global i

    target_files = [os.path.join(dir_path, x) for x in os.listdir(dir_path)]
    this_dir_files = []

    for target_file in tqdm.tqdm(target_files):
        out_file_name = '{:04d}.wav'.format(i)
        out_file_path = os.path.join(output_dir, out_file_name)

        file_obj = AudioSegment.from_mp3(target_file)
        file_obj = file_obj.set_frame_rate(TARGET_SAMPLES_FRAME_RATE)
        file_obj = file_obj.set_channels(TARGET_CHANNELS)
        file_obj.export(out_file_path, format='wav')

        rec = OutRecordDefinition(i, dataset_name, out_file_path, actor_id, emotion_name,
                                  file_obj.duration_seconds, male_field_val, 'train')
        this_dir_files.append(rec)

        i += 1

    sum_duration = sum([x.duration for x in this_dir_files])
    target_valid_dur = sum_duration * VALID_DATA_PERCENT / 100

    current_valud_dur = 0
    used_elems_indexes = []

    while current_valud_dur < target_valid_dur:
        el_index = random.randint(0, len(this_dir_files)-1)
        while el_index in used_elems_indexes:
            el_index = random.randint(0, len(this_dir_files)-1)
        this_dir_files[el_index].output_type = 'test'
        used_elems_indexes.append(el_index)
        current_valud_dur += this_dir_files[el_index].duration

    return this_dir_files


def write_csv_meta_file(path_replace_FROM_part, path_replace_TO_part):
    txt = ''
    for rec in res_files:
        changed_file_path = rec.file_full_path.replace(path_replace_FROM_part, path_replace_TO_part)
        txt += f'{rec.id},{rec.dataset_name},{changed_file_path},{rec.actor_id},{rec.emotion_name},{rec.duration},{rec.male},{rec.output_type}\n'

    csv_header_line = ',dataset,filename,actor,emotion,length,gender,set\n'
    with open(out_meta_file_path, 'w', encoding='utf-8') as handle:
        handle.write(csv_header_line)
        handle.write(txt)


def create_valid_data():
    valid_data_dir = 'cashier_data/validation'
    count_of_samples_per_type = 10

    # First - cleanup validation dir
    files_to_clean = [os.path.join(valid_data_dir, x) for x in os.listdir(valid_data_dir)]
    for file_to_clean in files_to_clean:
        os.remove(file_to_clean)

    rigla_corpus_files = get_rigla_files_list()
    cashbox_files = [os.path.join(initial_cashbox_sounds_dir, x) for x in os.listdir(initial_cashbox_sounds_dir)]

    random.seed()

    for i in range(count_of_samples_per_type):
        ind = random.randint(0, len(rigla_corpus_files) - 1)

        file_path_to_convert = rigla_corpus_files[ind]
        file_name_to_convert = file_path_to_convert.split('/')[-1]
        out_file_path = os.path.join(valid_data_dir, 'false_' + f'{i}.wav')

        file_obj = AudioSegment.from_mp3(file_path_to_convert)
        file_obj = file_obj.set_frame_rate(TARGET_SAMPLES_FRAME_RATE)
        file_obj = file_obj.set_channels(TARGET_CHANNELS)
        file_obj.export(out_file_path, format='wav')

    used_true_indexes = []
    for i in range(count_of_samples_per_type):
        ind = random.randint(0, len(cashbox_files) - 1)
        while used_true_indexes in used_true_indexes:
            ind = random.randint(0, len(cashbox_files) - 1)

        used_true_indexes.append(ind)
        file_path_to_convert = cashbox_files[ind]
        file_name_to_convert = file_path_to_convert.split('/')[-1]
        out_file_path = os.path.join(valid_data_dir, 'true_' + f'{i}.wav')

        file_obj = AudioSegment.from_mp3(file_path_to_convert)
        file_obj = file_obj.set_frame_rate(TARGET_SAMPLES_FRAME_RATE)
        file_obj = file_obj.set_channels(TARGET_CHANNELS)
        file_obj.export(out_file_path, format='wav')


def get_rigla_files_list():
    rigla_top_dir = '/media/dmzubr/Dat/audio/rigla_corpus/uploaded2/'

    archives_dirs = [x for x in os.listdir(rigla_top_dir) if os.path.isdir(os.path.join(rigla_top_dir, x))]
    mp3_files = []

    for dir in archives_dirs:
        dir_path = os.path.join(rigla_top_dir, dir)
        mp3_files = mp3_files + [os.path.join(dir_path, x).replace('\\', '/')
                                 for x in os.listdir(dir_path) if '.mp3' in x]

    return mp3_files


def copy_from_rigla_corpus_to_false_initial_dir():
    target_dur = 7200
    current_dur = 0

    out_dir = '/home/dmzubr/gpn/Voice_emotion_zdy/cashier_data/false/initial_rigla_recs/'
    mp3_files = get_rigla_files_list()

    used_indexes = []

    while current_dur < target_dur:
        file_index = random.randint(0, len(mp3_files))-1
        while file_index in used_indexes:
            file_index = random.randint(0, len(mp3_files)) - 1

        in_file_path = mp3_files[file_index]
        spl = in_file_path.split('/')
        in_file_name = spl[-1]
        dir = spl[-2]

        # in_file_path = mp3_files[file_index]
        out_file_name = dir + '_' + in_file_name
        out_file_path = os.path.join(out_dir, out_file_name)

        file_obj = AudioSegment.from_mp3(in_file_path)
        current_dur += file_obj.duration_seconds

        shutil.copy(in_file_path, out_file_path)


initial_cashbox_sounds_dir = 'cashier_data/true/initial'
initial_false_sounds_dir = 'cashier_data/false/initial_rigla_recs'

output_dir = 'cashier_data/res'
out_meta_file_path = 'cashier_data/data_index.csv'

# copy_from_rigla_corpus_to_false_initial_dir()
create_valid_data()
exit(0)

dataset_name = 'd'
actor_id = 1
true_emotion_name = 'cashier'
false_emotion_name = 'neutral'
male_field_val = 'male'

res_files = []

i = 1

files_recs = get_records_from_dir(initial_cashbox_sounds_dir, true_emotion_name)
res_files = res_files + files_recs
files_recs = get_records_from_dir(initial_false_sounds_dir, false_emotion_name)
res_files = res_files + files_recs

total_duration = sum([x.duration for x in res_files])

write_csv_meta_file('', '')
print(f'---------------- Done. Got total {len(res_files)} files with total duration: {total_duration}s ----------------')
