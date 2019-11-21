repo_name=gpn-emotions-prod:latest
sudo docker run --gpus=all -it --name gpn_emotions --restart always \
	-v /home/dmzubr/gpn/Voice_emotion_zdy/:/app_debug \
	docker-repo.rwad-tech.com/$repo_name
