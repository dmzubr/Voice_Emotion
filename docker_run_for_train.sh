repo_name=gpn-emotions-train:latest
sudo docker run --gpus=all -it --name gpn_emotions_train \
	-v /home/dmzubr/gpn:/home/gpn \
	-p 8888:8888 \
	$repo_name
#sudo docker run --gpus=all -it --name vad_service --restart always -v /srv/samba.share/in_audio:/in_audio -v /srv/samba.share/out_audio:/out_audio docker-repo.rwad-tech.com/$repo_name