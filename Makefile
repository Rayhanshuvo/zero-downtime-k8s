# Local setup with kind (your own computer):
#   make cluster build kind-load metrics-server
#   make deploy STEP=1-naive
#   make load NAME=e1-naive        (terminal 1)
#   make rollout-v2                (terminal 2)
#
# Poridhi lab (K3s, single node):
#   make build k3s-load
#   make deploy STEP=1-naive
#   make load NODE=<node-internal-ip> NAME=e1-naive
#
# Remote cluster instead: make build push DOCKERHUB_USER=yourname, then
#   make deploy STEP=1-naive DOCKERHUB_USER=yourname, make load NODE=<node-ip> ...

DOCKERHUB_USER ?= local
IMAGE          := $(DOCKERHUB_USER)/orders-api:1.0.0
STEP           ?= 3-production
NODE           ?= 127.0.0.1
NAME           ?= run
DURATION       ?= 90
EXP_DURATION   ?= 150
LOADARGS       ?=

.PHONY: experiment cluster cluster-delete kind-load k3s-load metrics-server build push deploy rollout-v2 rollout-v1 undo history kill-pod watch hpa load clean

experiment:       ## ONE command per experiment: STEP=<step> NAME=<name> NODE=<ip> [LOADARGS=...]
	@echo ">>> 1/3 deploying $(STEP) with v1"
	sed "s|DOCKERHUB_USER|$(DOCKERHUB_USER)|" k8s/$(STEP)/deployment.yaml | kubectl apply -f -
	kubectl apply -f k8s/service.yaml
	# apply alone won't undo a previous `set env` (three-way merge), so reset v1 explicitly
	kubectl set env deployment/orders-api APP_VERSION=v1
	kubectl rollout status deployment/orders-api --timeout=300s
	@echo ">>> 2/3 waiting 25s so every pod has finished warming up"
	sleep 25
	@echo ">>> 3/3 load test for $(EXP_DURATION)s; rollout to v2 starts automatically at 10s"
	python3 scripts/loadtest.py --url http://$(NODE):30080 --duration $(EXP_DURATION) --name $(NAME) $(LOADARGS) \
	  --event-at 10 \
	  --event-cmd "kubectl set env deployment/orders-api APP_VERSION=v2 && kubectl rollout status deployment/orders-api --timeout=300s" \
	  | tee results/$(NAME).txt

cluster:          ## create a local 3-node kind cluster
	kind create cluster --config kind-config.yaml

cluster-delete:   ## delete the local cluster
	kind delete cluster --name zdd

kind-load:        ## copy the locally built image into the kind nodes (no Docker Hub needed)
	kind load docker-image $(IMAGE) --name zdd

k3s-load:         ## copy the locally built image into K3s's containerd (no Docker Hub needed)
	docker save $(IMAGE) | sudo k3s ctr images import -

metrics-server:   ## install metrics-server (needed for HPA / E6); kind needs --kubelet-insecure-tls
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
	kubectl -n kube-system patch deployment metrics-server --type=json \
	  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
	kubectl -n kube-system rollout status deployment/metrics-server

build:            ## build the image (runs Maven inside Docker)
	docker build -t $(IMAGE) app

push:             ## push the image to Docker Hub (run `docker login` first)
	docker push $(IMAGE)

deploy:           ## apply one experiment step: STEP=1-naive | 2-readiness | 3-production
	sed "s|DOCKERHUB_USER|$(DOCKERHUB_USER)|" k8s/$(STEP)/deployment.yaml | kubectl apply -f -
	kubectl apply -f k8s/service.yaml
	kubectl rollout status deployment/orders-api

rollout-v2:       ## trigger a rolling update by changing the pod template (v1 -> v2)
	kubectl set env deployment/orders-api APP_VERSION=v2
	kubectl annotate deployment/orders-api kubernetes.io/change-cause="APP_VERSION=v2" --overwrite

rollout-v1:       ## roll forward back to v1 (a new rollout, not an undo)
	kubectl set env deployment/orders-api APP_VERSION=v1
	kubectl annotate deployment/orders-api kubernetes.io/change-cause="APP_VERSION=v1" --overwrite

undo:             ## roll back to the previous revision
	kubectl rollout undo deployment/orders-api

history:
	kubectl rollout history deployment/orders-api

kill-pod:         ## delete one pod (E5 self-healing)
	kubectl delete pod $$(kubectl get pods -l app=orders-api -o jsonpath='{.items[0].metadata.name}')

watch:            ## live view of pods and ReplicaSets
	watch -n1 'kubectl get rs,pods -l app=orders-api -o wide'

hpa:              ## E6: enable autoscaling
	kubectl apply -f k8s/hpa.yaml

load:             ## run the load tester: NAME=<result-name> [NODE=127.0.0.1] [DURATION=90]
	python3 scripts/loadtest.py --url http://$(NODE):30080 --duration $(DURATION) --name $(NAME)

clean:
	kubectl delete -f k8s/hpa.yaml --ignore-not-found
	kubectl delete deployment/orders-api service/orders-api --ignore-not-found
