# ros2_3dcv — one-command launcher.
#
#   make start     build everything and run the app   (this is the one step)
#   make stop      stop the app
#   make logs      tail the logs
#   make rebuild   force a clean rebuild of the api/web images
#   make grade MODULE=module-8 [SOLUTION=path.py]   grade without the web app
#
# `make start` is all you need: it builds the ROS 2 sandbox image (once),
# rebuilds the api/web images (so the api has the docker CLI + latest code),
# and starts the stack. Open http://localhost:5173 when it's up.

DISTRO ?= humble
SANDBOX_IMAGE := ros2-3dcv-sandbox:$(DISTRO)

.PHONY: start stop logs rebuild sandbox grade

start: sandbox
	docker compose up --build

# Build the (large, ~few GB) ROS 2 sandbox image only if it doesn't exist yet.
sandbox:
	@if docker image inspect $(SANDBOX_IMAGE) >/dev/null 2>&1; then \
		echo "✓ sandbox image $(SANDBOX_IMAGE) already built"; \
	else \
		echo "building sandbox image $(SANDBOX_IMAGE) (one-time, downloads ROS 2)…"; \
		$(MAKE) -C backend/sandbox_image build DISTRO=$(DISTRO); \
	fi

stop:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache

grade:
	python3 backend/sandbox_image/grade.py $(MODULE) $(SOLUTION) --distro $(DISTRO)
