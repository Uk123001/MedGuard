set -e
R=ap-southeast-2; A=623045222203
REG=$A.dkr.ecr.$R.amazonaws.com
CODE=$(aws lambda get-function-configuration --function-name medguard-lists --region $R --query "Environment.Variables.REVIEWER_CODE" --output text)

echo "== push image to ECR"
aws ecr create-repository --repository-name medguard-lists --region $R >/dev/null 2>&1 || true
aws ecr get-login-password --region $R | docker login --username AWS --password-stdin $REG >/dev/null
docker tag medguard-lists:1 $REG/medguard-lists:1
docker push $REG/medguard-lists:1 | tail -2

echo "== roles"
cat > /tmp/t_build.json <<'T'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
T
cat > /tmp/t_task.json <<'T'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
T
aws iam create-role --role-name medguard-apprunner-ecr-role --assume-role-policy-document file:///tmp/t_build.json >/dev/null 2>&1 || true
aws iam attach-role-policy --role-name medguard-apprunner-ecr-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
aws iam create-role --role-name medguard-apprunner-instance-role --assume-role-policy-document file:///tmp/t_task.json >/dev/null 2>&1 || true
aws iam put-role-policy --role-name medguard-apprunner-instance-role --policy-name lists-table-only --policy-document file://$HOME/lists/perm.json
sleep 15

echo "== create App Runner service"
cat > /tmp/svc.json <<J
{"ServiceName":"medguard-lists",
 "SourceConfiguration":{
  "AuthenticationConfiguration":{"AccessRoleArn":"arn:aws:iam::$A:role/medguard-apprunner-ecr-role"},
  "AutoDeploymentsEnabled":false,
  "ImageRepository":{"ImageIdentifier":"$REG/medguard-lists:1","ImageRepositoryType":"ECR",
   "ImageConfiguration":{"Port":"8080","RuntimeEnvironmentVariables":{"REVIEWER_CODE":"$CODE"}}}},
 "InstanceConfiguration":{"Cpu":"256","Memory":"512","InstanceRoleArn":"arn:aws:iam::$A:role/medguard-apprunner-instance-role"},
 "HealthCheckConfiguration":{"Protocol":"HTTP","Path":"/health"}}
J
ARN=$(aws apprunner create-service --cli-input-json file:///tmp/svc.json --region $R --query Service.ServiceArn --output text)
echo "service: $ARN"

for i in $(seq 1 40); do
  S=$(aws apprunner describe-service --service-arn $ARN --region $R --query Service.Status --output text)
  echo "status: $S"
  [ "$S" = "RUNNING" ] && break
  [ "$S" = "CREATE_FAILED" ] && exit 1
  sleep 15
done
U=$(aws apprunner describe-service --service-arn $ARN --region $R --query Service.ServiceUrl --output text)
echo "URL: https://$U"
curl -s https://$U/health; echo
