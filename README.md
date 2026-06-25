# Kubernetes Observability GitOps Lab

Kubernetes, OpenTelemetry, Argo CD를 한 번에 연습하기 위한 작은 실습 repo입니다.

최종 흐름은 다음과 같습니다.

1. FastAPI 앱을 Docker 이미지로 빌드합니다.
2. kind 로컬 Kubernetes 클러스터에 앱을 배포합니다.
3. OpenTelemetry Collector와 Jaeger를 붙여 trace를 확인합니다.
4. Argo CD가 Git 변경사항을 Kubernetes에 반영하게 만듭니다.

## 0. 로컬 클러스터

```powershell
kind create cluster --config infra/kind/cluster.yaml
kubectl get nodes
```

이미 만들었다면 현재 컨텍스트만 확인합니다.

```powershell
kubectl config current-context
```

정상 값은 `kind-k8s-lab`입니다.

## 1. 앱 이미지 빌드

```powershell
docker build -t k8s-lab-api:dev ./app
kind load docker-image k8s-lab-api:dev --name k8s-lab
```

## 2. Kubernetes에 직접 배포

```powershell
kubectl apply -k k8s/base
kubectl -n k8s-lab rollout status deployment/orders-api
kubectl -n k8s-lab get pods,svc
```

로컬에서 API를 호출합니다.

```powershell
kubectl -n k8s-lab port-forward svc/orders-api 8081:80
```

다른 터미널에서 확인합니다.

```powershell
curl http://localhost:8081/healthz
curl http://localhost:8081/api/orders
curl http://localhost:8081/api/orders/1
curl http://localhost:8081/api/error
```

로그와 trace 출력도 확인합니다.

```powershell
kubectl -n k8s-lab logs deploy/orders-api
```

## 3. 다음 단계

OpenTelemetry Collector와 Jaeger를 배포합니다.

```powershell
kubectl apply -k observability
kubectl -n observability rollout status deployment/jaeger
kubectl -n observability rollout status deployment/otel-collector
```

앱이 Collector로 trace를 보내도록 overlay를 적용합니다.

```powershell
kubectl apply -k k8s/overlays/otel
kubectl -n k8s-lab rollout status deployment/orders-api
```

트래픽을 만들고 Jaeger UI를 엽니다.

```powershell
kubectl -n k8s-lab port-forward svc/orders-api 18081:80
kubectl -n observability port-forward svc/jaeger 16687:16686
```

다른 터미널에서 요청을 보냅니다.

```powershell
curl http://localhost:18081/api/orders/1
curl http://localhost:18081/api/error
```

브라우저에서 `http://localhost:16687`로 열고 service를 `orders-api`로 선택합니다.

## 4. Argo CD

Argo CD는 클러스터 안에서 Git 저장소를 읽어 Kubernetes에 적용합니다.
따라서 이 로컬 repo를 GitHub 같은 원격 저장소에 push한 뒤 `argocd/orders-api-application.yaml`의 `repoURL`을 바꿔야 합니다.

Argo CD 설치:

```powershell
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-server
```

초기 admin 비밀번호:

```powershell
$encoded = kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}"
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))
```

UI 열기:

```powershell
kubectl -n argocd port-forward svc/argocd-server 8088:443
```

브라우저에서 `https://localhost:8088`로 접속합니다.

GitHub에 push한 뒤 Application을 적용합니다.

```powershell
kubectl apply -f argocd/orders-api-application.yaml
```

연습할 변경:

- `k8s/overlays/otel/deployment-otel-patch.yaml`에서 replica 수 변경
- `app/main.py`에서 응답 필드 하나 추가
- 이미지 태그를 새로 빌드하고 manifest에 반영
- 일부러 잘못된 manifest를 push해서 Argo CD sync failure 확인
- 이전 commit으로 되돌려 rollback 확인
