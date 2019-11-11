# ==================================================================
# module list
# ------------------------------------------------------------------
# ffmpeg libsndfile1 sox libsox-fmt-all              	(apt)
# librosa pyyaml pika requests pydub              	(pip)
# ==================================================================

FROM tensorflow/tensorflow:latest-gpu-py3

RUN apt update && apt install -y libsndfile1 ffmpeg sox libsox-fmt-all
RUN pip install pandas librosa tqdm keras seaborn watchdog pyyaml requests pydub pika boto3

RUN mkdir /root/app
COPY . /root/app

# ENTRYPOINT ["jupyter", "notebook", "--notebook-dir", "/home/gpn", "--ip=0.0.0.0"]