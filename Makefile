# Makefile — common dev and ops commands for swing-bot.
#
# Usage:
#   make up         Start bot + admin UI (build if needed)
#   make down       Stop all containers
#   make logs       Tail bot logs
#   make restart    Restart just the bot container (picks up .env changes)
#   make shell      Open a bash shell inside the bot container
#   make status     Show container health and resource usage
#   make deploy     Run the deploy script (useful on the server itself)
#   make check      Syntax-check all Python source files
#   make clean      Remove stopped containers and dangling images

COMPOSE = docker compose
BOT     = swing-bot
ADMIN   = swing-bot-admin
SERVER  = deploy@167.233.26.185

.PHONY: up down logs logs-admin restart shell status deploy check clean tunnel

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f $(BOT)

logs-admin:
	$(COMPOSE) logs -f $(ADMIN)

restart:
	$(COMPOSE) restart $(BOT)

restart-admin:
	$(COMPOSE) restart $(ADMIN)

shell:
	docker exec -it $(BOT) bash

shell-admin:
	docker exec -it $(ADMIN) bash

status:
	$(COMPOSE) ps
	@echo ""
	docker stats --no-stream $(BOT) $(ADMIN) 2>/dev/null || true

deploy:
	./deploy/deploy.sh

check:
	@echo "==> Checking Python syntax..."
	@python3 -m py_compile bot.py admin_ui.py && \
	find swingbot -name '*.py' | xargs python3 -m py_compile && \
	echo "All files OK."

clean:
	$(COMPOSE) down --remove-orphans
	docker image prune -f

# Open an SSH tunnel to the admin UI on the Hetzner server.
# After running this, browse to http://localhost:1234
tunnel:
	ssh -L 1234:localhost:1234 $(SERVER) -N

# SSH into the Hetzner server
ssh:
	ssh $(SERVER)
