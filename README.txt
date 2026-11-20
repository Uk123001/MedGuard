MedGuard final code bundle
==========================
frontend/                 single-page website (index.html is the final pink version; template.html + build.py + assets build it)
lambda_lists/             lists + reviewer Lambda
ml_and_evaluation/        severity model training (train_ddi.py), baselines, 40-pair evaluation scripts and results, estimate Lambda (est/)
ecs_fargate_container/    Docker image for the lists service, ecs.sh, deploy.sh
k8s_lists/                first Kubernetes manifest (lists only)
three-containers/         frontend + resolver + lists on Kubernetes (medguard-all.yaml)
deployed_lambdas/         the exact code running in AWS: orchestrator, retrieval, verification, synthesis, estimate, lists, and the SageMaker resolver package (sagemaker_resolver/code)
                          verification, synthesis, estimate and lists, plus the SageMaker model package


MODELS IN USE (ap-southeast-2): synthesis = au.anthropic.claude-sonnet-4-6 ; estimate (AI hypothesis) = au.anthropic.claude-haiku-4-5-20251001-v1:0.
The evaluation baseline in ml_and_evaluation was run with Claude Sonnet 4.5, which AWS later retired for this account.
Known limitation: resolver fuzzy cutoff 0.8 matches cocaine -> procaine (ratio 0.80).
DEPLOY: for each Lambda folder: zip -qr x.zip . ; aws lambda update-function-code --function-name <name> --zip-file fileb://x.zip ; aws lambda wait function-updated --function-name <name>
Frontend: aws s3 cp frontend/index.html s3://medguard-site-623045222203/index.html ; then CloudFront invalidation (distribution E2LTKC8NP234ZU, path /*).
Docker/Kubernetes: three-containers/ (docker build for frontend, resolver, lists; minikube image load; kubectl apply -f medguard-all.yaml; kubectl port-forward service/frontend 8080:80).
