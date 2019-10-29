repo_name=gpn-emotions-prod:latest
sudo docker run --gpus=all -it --name gpn_emotions --restart always \
	-v /home/dmzubr/gpn/Voice_emotion_zdy/:/app_debug \
	-v /srv/samba/share/in_audio:/in_audio \
	-v /srv/samba/share/out_audio:/out_audio \
	$repo_name