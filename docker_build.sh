repo_name=gpn-emotions-prod:latest
#sudo docker build -t docker-repo.rwad-tech.com/$repo_name -f ./Dockerfile .
#sudo docker push docker-repo.rwad-tech.com/$repo_name
sudo docker build -t $repo_name -f ./Dockerfile .
