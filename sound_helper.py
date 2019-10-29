# coding=utf-8

import os
import math
import ntpath
import random
import shutil
import subprocess
from subprocess import Popen, PIPE
from pathlib import Path
from pydub import AudioSegment
import uuid
import tempfile


class LiveCorpusHelper:
    def __init__(self, noise_files_dir=''):
        self.__noise_segments = []
        if len(noise_files_dir) > 0:
            # Initialise noise files pydub segments
            print('AudioHelper: Initialise noise files to pydub segments')
            noise_files = [os.path.join(noise_files_dir, x) for x in os.listdir(noise_files_dir) if '.mp3' in x]
            for noise_file_path in noise_files:
                noise_segment = AudioSegment.from_mp3(noise_file_path)
                self.__noise_segments.append(noise_segment)
            print('AudioHelper: Initialisation of noise files done')


    @staticmethod
    def get_three_formatted_number(number):
        res = "{:03d}".format(number)
        return res

    def inject_noise_to_file(self, target_file_path, noise_file_path='', noise_file_segment=object(),
                             noisered_audio_path=''):
        if type(noise_file_segment) != AudioSegment:
            if len(self.__noise_segments) > 0:
                # Get noise segment object from existed array
                noise_index = random.randint(0, len(self.__noise_segments) - 1)
                noise_file_segment = self.__noise_segments[noise_index]
            else:
                noise_file_segment = AudioSegment.from_mp3(noise_file_path)

        input_file_segment = AudioSegment.from_mp3(target_file_path)
        input_file_duration = input_file_segment.duration_seconds * 1000
        noise_file_duration = noise_file_segment.duration_seconds * 1000
        noise_file_start = random.randint(0, math.floor(noise_file_duration - input_file_duration))
        noise_file_end = noise_file_start + input_file_duration
        target_noise_part = noise_file_segment[noise_file_start:noise_file_end]

        temp_noise_part_file_path = os.path.join(tempfile.gettempdir(), 'noise_{0}.mp3'.format(input_file_segment.duration_seconds))
        target_noise_part.export(temp_noise_part_file_path, format="mp3")

        output_file_path = noisered_audio_path
        if len(noisered_audio_path) == 0:
            file_name = ntpath.basename(target_file_path)
            dir = ntpath.dirname(target_file_path)
            output_file_path = os.path.join(dir, 'noisered_' + file_name)

        self.merge_files_sox(target_file_path, temp_noise_part_file_path, output_file_path)

        # Cleanup temp noise file
        os.remove(temp_noise_part_file_path)

    def inject_noise_dir(self, noise_file_path, target_dir_path):
        noise_files_list = [f for f in os.listdir(target_dir_path) if os.path.isfile(os.path.join(target_dir_path, f))]
        for file_to_noise in noise_files_list:
            file_to_noise_full_path = os.path.join(target_dir_path, file_to_noise)
            self.inject_noise_to_file(noise_file_path, file_to_noise_full_path)

    @staticmethod
    def merge_files_sox(file_1_full_path, file_2_full_path, output_file_path):
        # Example of sox call is
        # sox -m new_input.wav myrecording.wav output_test.aiff
        subprocess.call(["sox",
                        '-m',
                        file_1_full_path,
                        file_2_full_path,
                        output_file_path])

    @staticmethod
    def is_file_stereo(file_full_path):
        # Example of ffmpeg call is
        # ffmpeg -i some_rec.mp3
        process = Popen(["ffmpeg", '-i', file_full_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")
        res = stderr_str.find('stereo') > -1
        return res

    @staticmethod
    def merge_stereo_sox(file_full_path, output_file_path=''):
        # Example of sox call is
        # sox in_file.mp3 out_file.mp3 remix 1,2
        need_to_replace_with_buf = len(output_file_path) == 0

        if need_to_replace_with_buf:
            file_name_with_ext = os.path.basename(file_full_path)
            file_name_without_ext = file_name_with_ext.replace('.mp3', '')
            temp_file_path = os.path.join(os.path.dirname(file_full_path), '{0}_merged.mp3'.format(file_name_without_ext))
            output_file_path = temp_file_path

        subprocess.call(["sox",
                         file_full_path,
                         output_file_path,
                         'remix',
                         '1,2'])

        if need_to_replace_with_buf:
            os.remove(file_full_path)
            shutil.copy(output_file_path, file_full_path)
            os.remove(output_file_path)

    def float_try_parse(self, value):
        try:
            return float(value)
        except ValueError:
            return False

    def get_volume_adjustment(self, file_path):
        # sox somefile.mp3 -n stat
        process = Popen([
            "sox",
            file_path,
            "-n",
            "stat"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")

        volume_adjustment_val = 0

        for line in stderr_str.split('\n'):
            # example of line is: Volume adjustment:    3.585
            if 'Volume adjustment' in line:
                entries = line.split(' ')
                for entry in entries:
                    cleaned_entry = entry.replace('\r', '').replace('\n', '').replace('\t', '')
                    parsed_val = self.float_try_parse(cleaned_entry)
                    if parsed_val != False:
                        volume_adjustment_val = parsed_val

        return volume_adjustment_val


    def get_duration_seconds(self, file_path):
        # sox somefile.mp3 -n stat
        process = Popen(["sox", file_path, "-n", "stat"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")

        duration = 0

        for line in stderr_str.split('\n'):
            # example of line is: Volume adjustment:    3.585
            if 'Length (seconds)' in line:
                entries = line.split(' ')
                for entry in entries:
                    if len(entry) > 0 and 'Length' not in entry and '(seconds)' not in entry:
                        cleaned_entry = entry.replace('\r', '').replace('\n', '').replace('\t', '')
                        parsed_val = self.float_try_parse(cleaned_entry)
                        if parsed_val != False:
                            duration = parsed_val

        return duration


    def normalize_volume(self, file_path, out_file_path='', applied_vol_adjustment=0, initial_va_val=0):
        # Get value of volume adjustment parameter
        if applied_vol_adjustment == 0:
            if initial_va_val == 0:
                initial_va_val = self.get_volume_adjustment(file_path)

            applied_vol_adjustment = initial_va_val
            # Suppose that received value is too hoght for real records - so use fixed deplicator
            va_default_deplictor = 0.5
            applied_vol_adjustment = applied_vol_adjustment * va_default_deplictor

        # sox -v 2.9 somefile.mp3 -
        if len(out_file_path) == 0:
            out_file_path = '-n'
        process = Popen(['sox',
                         '-v',
                         str(applied_vol_adjustment),
                         file_path,
                         out_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stdout_str = stdout.decode("utf-8")
        stderr_str = stderr.decode("utf-8")
        # if len(stdout_str) > 0:
        #     print(stdout_str)
        # if len(stderr_str) > 0:
        #     print(stderr_str)

    def denoise_file_sox(self, in_file_path, out_file_path, noised_trim_length=0, noise_sensitivity=0, noise_prof_file_path=''):
        temp_files = []

        # https://stackoverflow.com/questions/44159621/how-to-denoise-audio-with-sox
        id = str(uuid.uuid4())

        if noised_trim_length == 0:
            noised_trim_length = 1
        if noise_sensitivity == 0:
            noise_sensitivity = 0.21

        if len(noise_prof_file_path) == 0:
            # sox audio.wav noise-audio.wav trim 0 0.900
            src_file_ext = Path(in_file_path).suffix
            noise_file_path = os.path.join(tempfile.gettempdir(), id + src_file_ext)
            subprocess.call(['sox',
                             in_file_path,
                             noise_file_path, 'trim', '0', str(noised_trim_length)])

            assert os.path.isfile(noise_file_path)
            temp_files.append(noise_file_path)

            noise_prof_file_path = os.path.join(tempfile.gettempdir(), f'{id}.prof')
            # sox noise-audio.wav -n noiseprof noise.prof
            subprocess.call(['sox',
                             noise_file_path, '-n', 'noiseprof', noise_prof_file_path])
            assert os.path.isfile(noise_prof_file_path)
            temp_files.append(noise_prof_file_path)

        # sox audio.wav audio-clean.wav noisered noise.prof 0.21
        subprocess.call(['sox',
                         in_file_path, out_file_path, 'noisered', noise_prof_file_path, str(noise_sensitivity)])
        assert os.path.isfile(out_file_path)

        return temp_files

    def denoise_file_ffmpeg(self, in_file_path, out_file_path):
        low_pass = 3000
        high_pass = 200

        # https://superuser.com/questions/733061/reduce-background-noise-and-optimize-the-speech-from-an-audio-clip-using-ffmpeg
        # ffmpeg -i <input_file> -af "highpass=f=200, lowpass=f=3000" <output_file>
        process = Popen(['ffmpeg',
                         '-i', in_file_path,
                         '-af', f'highpass=f={high_pass}, lowpass=f={low_pass}',
                         out_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        assert os.path.isfile(out_file_path)

    def get_audio_part(self, in_audio_path, out_audio_path, start_span='', end_span='', start_sec=0, end_sec=0):
        assert end_sec > 0 or len(end_span) > 0
        # assert end_sec == -1 or end_sec > start_sec

        if os.path.isfile(out_audio_path):
            os.remove(out_audio_path)

        start_position_str = str(start_sec)
        end_position_str = str(end_sec)
        if end_position_str == '-1':
            start_position_str = start_span
            end_position_str = end_span

        # ffmpeg -i file.mkv -ss 20 -to 40 -c copy file-2.mkv
        # ffmpeg -i gajCrgdPPQs.mp4 -acodec libmp3lame -ss 00:00:00 -to 00:00:10 part.mp3
        process = Popen(['ffmpeg',
                         '-i', in_audio_path,
                         '-acodec', 'libmp3lame',
                         '-ss', start_position_str,
                         '-to', end_position_str,
                         out_audio_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        s = stdout.decode('utf-8')
        assert os.path.isfile(out_audio_path)

