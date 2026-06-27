DISTRO ?= humble
IMAGE  ?= ros2-3dcv-sandbox:$(DISTRO)
MODULE ?= module-1

.PHONY: build grade grade-all

# Build the sandbox image for a ROS distro (humble or jazzy).
build:
	docker build -f Dockerfile --build-arg DISTRO=$(DISTRO) -t $(IMAGE) .

# Grade one module's reference solution (or pass SOLUTION=path/to/file.py).
grade:
	python3 grade.py $(MODULE) $(SOLUTION) --distro $(DISTRO)

# Grade every reference solution (sanity check the curriculum end-to-end).
grade-all:
	@for n in 1 2 3 4 5 6 7 8 9 10 11 12 13; do \
		echo "==== module-$$n ===="; \
		python3 grade.py module-$$n --distro $(DISTRO) || true; \
	done
