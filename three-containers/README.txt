MedGuard - 3 containers
frontend\  nginx image serving the web page, proxies /resolve and /lists
resolver\  Flask name-resolver microservice (exact, alias, RxNorm, difflib)
k8s\medguard-all.yaml  3 Deployments, 3 Services, 1 Secret
The lists container reuses the existing image medguard-lists:1 (build it from the earlier container folder if it is missing).
