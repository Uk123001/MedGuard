set -e
R=ap-southeast-2; A=623045222203; REG=$A.dkr.ecr.$R.amazonaws.com
CODE=$(aws lambda get-function-configuration --function-name medguard-lists --region $R --query "Environment.Variables.REVIEWER_CODE" --output text)
ARCH=X86_64; [ "$(uname -m)" = "aarch64" ] && ARCH=ARM64

echo "== roles"
cat > /tmp/t_ecs.json <<'T'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
T
aws iam create-role --role-name medguard-ecs-exec-role --assume-role-policy-document file:///tmp/t_ecs.json >/dev/null 2>&1 || true
aws iam attach-role-policy --role-name medguard-ecs-exec-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam create-role --role-name medguard-ecs-task-role --assume-role-policy-document file:///tmp/t_ecs.json >/dev/null 2>&1 || true
aws iam put-role-policy --role-name medguard-ecs-task-role --policy-name lists-table-only --policy-document file://$HOME/lists/perm.json
aws logs create-log-group --log-group-name /ecs/medguard-lists --region $R >/dev/null 2>&1 || true

echo "== network"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region $R --query "Vpcs[0].VpcId" --output text)
SUBS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC --region $R --query "Subnets[0:2].SubnetId" --output text | tr '\t' ',')
SG=$(aws ec2 create-security-group --group-name medguard-lists-sg --description "MedGuard lists container" --vpc-id $VPC --region $R --query GroupId --output text 2>/dev/null || aws ec2 describe-security-groups --filters Name=group-name,Values=medguard-lists-sg --region $R --query "SecurityGroups[0].GroupId" --output text)
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 8080 --cidr 0.0.0.0/0 --region $R >/dev/null 2>&1 || true
echo "vpc $VPC  subnets $SUBS  sg $SG"
sleep 15

echo "== task definition"
cat > /tmp/td.json <<J
{"family":"medguard-lists","networkMode":"awsvpc","requiresCompatibilities":["FARGATE"],
 "cpu":"256","memory":"512",
 "runtimePlatform":{"cpuArchitecture":"$ARCH","operatingSystemFamily":"LINUX"},
 "executionRoleArn":"arn:aws:iam::$A:role/medguard-ecs-exec-role",
 "taskRoleArn":"arn:aws:iam::$A:role/medguard-ecs-task-role",
 "containerDefinitions":[{"name":"lists","image":"$REG/medguard-lists:1","essential":true,
  "portMappings":[{"containerPort":8080,"protocol":"tcp"}],
  "environment":[{"name":"REVIEWER_CODE","value":"$CODE"},{"name":"AWS_DEFAULT_REGION","value":"$R"}],
  "logConfiguration":{"logDriver":"awslogs","options":{"awslogs-group":"/ecs/medguard-lists","awslogs-region":"$R","awslogs-stream-prefix":"lists"}}}]}
J
aws ecs register-task-definition --cli-input-json file:///tmp/td.json --region $R --query "taskDefinition.taskDefinitionArn" --output text

echo "== service"
aws ecs create-service --cluster medguard --service-name lists --task-definition medguard-lists --desired-count 1 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --region $R --query "service.status" --output text
echo "waiting for the container to start (up to 4 min)..."
aws ecs wait services-stable --cluster medguard --services lists --region $R

TASK=$(aws ecs list-tasks --cluster medguard --service-name lists --region $R --query "taskArns[0]" --output text)
ENI=$(aws ecs describe-tasks --cluster medguard --tasks $TASK --region $R --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI --region $R --query "NetworkInterfaces[0].Association.PublicIp" --output text)
echo "PUBLIC IP: $IP"
sleep 5
curl -s -m 10 http://$IP:8080/health; echo
