import os

import sound_helper


def denoise_dir(src_dir, target_dir, file_name_append=''):
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)

    dirty_files = [x for x in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, x))]
    for dirty_file in dirty_files:
        full_src_file_path = os.path.join(src_dir, dirty_file)
        out_filename = dirty_file
        if len(file_name_append) > 0:
            out_filename = out_filename.replace('.mp3', '') + file_name_append + '.mp3'
        dst_file_path = os.path.join(target_dir, out_filename)
        audio_helper.denoise_file_sox(full_src_file_path, dst_file_path)


def split_long_false_files():
    # split long false files to parts with 10 sec length
    false_chunk_length = 10
    false_long_files = os.listdir(os.path.join(false_src_files_dir, 'long'))
    i = 1
    chunk_length = 10
    for long_false_file in false_long_files:
        long_false_file_path = os.path.join(false_src_files_dir, 'long', long_false_file)
        long_dur = audio_helper.get_duration_seconds(long_false_file_path)

        for chunk_num in range(0, int(int(long_dur) / 10)):
            chunk_path = os.path.join(false_src_files_dir, f'{i}_chunk_{chunk_num + 1}.mp3')
            start_sec = chunk_num * chunk_length
            end_sec = (chunk_num + 1) * chunk_length
            if not os.path.isfile(chunk_path):
                audio_helper.get_audio_part(long_false_file_path, chunk_path, '', '', start_sec, end_sec)

        i += 1


audio_helper = sound_helper.LiveCorpusHelper()

# Denoise true files
# Total duration of cashier sounds is 649s
true_src_files_dir = '/home/dmzubr/gpn/emotions-analyzer/data/true/initial'
false_src_files_dir = '/home/dmzubr/gpn/emotions-analyzer/data/false/initial/'

true_denoised_dir = '/home/dmzubr/gpn/emotions-analyzer/data/true/denosied/'
false_denoised_files_dir = '/home/dmzubr/gpn/emotions-analyzer/data/false/denoised/'

denoise_dir(true_src_files_dir, true_denoised_dir, '_TARGET_')
denoise_dir(false_src_files_dir, false_denoised_files_dir)

print('Done')
