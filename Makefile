# Makefile for local development

.PHONY: down clean nuke

ifdef TAG
export TAG := $(TAG)
else
export TAG := dev
endif


# Builds core locally and sets to correct tag. This should take priority over DockerHub images
build-core:
	@docker-compose build


# Builds core locally and then runs pgrest in daemon mode
local-deploy: build-core
	@docker-compose run api python manage.py makemigrations
	@docker-compose run api python manage.py migrate
	@docker-compose up -d api


# Running the pgrest/test.py file
test:
	@docker-compose run api python manage.py test


# Pulls all Docker images not yet available but needed to run pgrest
pull:
	@docker-compose pull


# Ends all active Docker containers needed for pgrest
down:
	@docker-compose down

# Ends all active Docker containers needed for pgrest and clears all volumes
# If this is not used the postgres container will restart with data
down-volumes:
	@docker-compose down
	@docker volume prune -f


# Does a clean and also deletes all images needed for abaco
clean:
	@docker-compose down --remove-orphans -v --rmi all 


# Deletes ALL images, containers, and volumes forcefully
nuke:
	@docker rm -f `docker ps -aq`
	@docker rmi -f `docker images -aq`
	@docker container prune -f
	@docker volume prune -f
