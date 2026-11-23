# DuckDNS HTTPS for the Fargate demo

This is an optional endpoint for **MediRoute CD - ECS Control**. Use a DuckDNS
name you control, such as `mediroute-demo.duckdns.org` if available. Each new
DuckDNS task publishes its public IPv4 to the same name. Traffic goes directly
to Nginx on port 443, and the API and frontend stay in the same Fargate task.
The hostname remains stable when the task stops, and the app comes back after
the next task starts and DNS resolves to it. Cached DNS can briefly retain the
previous task's address.

This uses the existing public subnet with a route through the internet gateway.
It uses the task's existing public IPv4 allocation. A separately allocated
Elastic IP, EC2 VM, load balancer, and port 80 are unnecessary. The existing
AWS charges for task runtime and public IPv4 still apply. The DuckDNS option
does not use Cloudflare's proxy protections. The educational demo serves
`/admin.html` and its trace API without authentication. Use only synthetic
demo data. Accounts and saved searches are stored in task-local SQLite and
reset when the task is replaced. Nginx allows 32 MiB at the proxy to fit the API's 30 MiB combined PDF limit plus
multipart overhead.

## 1. Reserve a name and issue a certificate

Sign into [DuckDNS](https://www.duckdns.org/) and create the label. Use a new
label without an existing IPv6 record. Keep the account token private.

Run in WSL, with Certbot and `dig` installed. Substitute the label you reserved.

```bash
export DUCKDNS_LABEL=mediroute-demo
sudo certbot certonly --manual --preferred-challenges dns --key-type ecdsa \
  -d "$DUCKDNS_LABEL.duckdns.org"
```

Leave Certbot open at its TXT challenge prompt. In another WSL terminal, set
the same label, enter the DuckDNS token through the hidden prompt, and paste
the **challenge value** from Certbot.

```bash
export DUCKDNS_LABEL=mediroute-demo
read -rs -p 'DuckDNS account token: ' DUCKDNS_TOKEN; printf '\n'
read -r -p 'Certbot TXT challenge value: ' ACME_TXT
printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&txt=%s"\n' \
  "$DUCKDNS_LABEL" "$DUCKDNS_TOKEN" "$ACME_TXT" |
  curl --config - --fail --silent --max-time 15
printf '\n'
dig +short TXT "_acme-challenge.$DUCKDNS_LABEL.duckdns.org" @1.1.1.1
unset ACME_TXT
```

Expect `OK` and wait until the TXT record matches the challenge before
continuing in Certbot. Note the issued full-chain and private-key file paths.
Renew this certificate manually before it expires and replace the PEM
parameters below. Newly started tasks pick up the replacement. Keep the
same label when renewing so the public URL stays the same.

## 2. Create a dedicated security group and upload the secrets

In the Sydney AWS console, create a security group in the same VPC as subnet
`subnet-0838d819c31bb2b38`. Keep the normal outbound internet access and add
only inbound TCP 443. For a public demo use `0.0.0.0/0`. For an audience with
known source IPs, restrict ingress to those CIDRs and verify HTTPS from one
of those networks. In that case the GitHub runner's public health probe may
report pending. Leave ports 80, 8000 and 8080 closed. Keep the existing Quick
Tunnel group separate.

In WSL, verify the account is `299952487175`. If you opened a new terminal,
set the label again and enter the DuckDNS token at the hidden prompt.

```bash
cd ~/projects/MediRoute
export AWS_PROFILE=mediroute-local AWS_REGION=ap-southeast-2
aws sts get-caller-identity --query Account --output text
```

Upload the three standard SecureString parameters using the default SSM key.
The commands read the values from stdin and avoid printing the token or key.
If this is a renewal, use the certificate paths printed by Certbot. The standard
tier supports values up to 4 KiB. Stop and review if a PEM exceeds that limit.

```bash
(
  set -euo pipefail
  : "${DUCKDNS_LABEL:?Set the reserved DuckDNS label first}"
  if [[ -z "${DUCKDNS_TOKEN:-}" ]]; then
    read -rs -p 'DuckDNS account token: ' DUCKDNS_TOKEN; printf '\n'
  fi
  CERT_DIR="/etc/letsencrypt/live/$DUCKDNS_LABEL.duckdns.org"

  put_duckdns_parameter() {
    jq -Rs --arg name "/mediroute/dev/duckdns/$1" \
      '{Name:$name, Type:"SecureString", Tier:"Standard", Value:., Overwrite:true}' |
      aws ssm put-parameter --cli-input-json file:///dev/stdin
  }

  printf '%s' "$DUCKDNS_TOKEN" | put_duckdns_parameter token
  sudo cat "$CERT_DIR/fullchain.pem" | put_duckdns_parameter fullchain
  sudo cat "$CERT_DIR/privkey.pem" | put_duckdns_parameter privkey
)
unset DUCKDNS_TOKEN

aws iam put-role-policy \
  --role-name mediroute-demo-task-execution \
  --policy-name MediRouteReadDuckDNSParameters \
  --policy-document file://infra/iam/ecs-duckdns-parameters-read.json
```

The policy grants the ECS task **execution role** read access to only those
three parameters. The frontend is the only container that receives the
values. If GitHub's current ECS permissions restrict security groups, have
the AWS operator review the exact new security group for the deployment role.

## 3. Deploy and verify

1. In GitHub **Settings → Secrets and variables → Actions → Variables**,
   set `MEDIROUTE_DUCKDNS_LABEL` to the reserved label and
   `MEDIROUTE_DUCKDNS_SECURITY_GROUP` to the dedicated group's ID.
2. Commit/push the repository changes, wait for CI, and manually publish
   images for the exact passing commit.
3. Confirm the current demo task has stopped. In **MediRoute CD - ECS
   Control**, select the branch with these changes, choose `deploy`, and
   set **public_endpoint** to **duckdns**. Keep `auto_deploy: false`. The
workflow reads the runtime limit from `main` and schedules the stop for 24
hours after launch. It uses the shorter limit if the selected commit specifies
one. The one-time stop schedule remains enabled throughout the testing window.
4. Open the job summary and check for the URL and health result. For a
   direct check, request `https://<label>.duckdns.org/api/health` over HTTPS,
   open `/patient.html` and `/admin.html`, and confirm `/api/admin/requests`
   returns JSON. Test signup and login with a synthetic account.
   Use the task ARN and stop controls as usual.

If health shows pending, check the frontend stream in `/ecs/mediroute-demo`
for acceptance of the IPv4 update. Compare the DuckDNS A record with the
task's public IPv4 in the ECS console, inspect the 443 rule, and verify the
certificate's hostname and expiry. If frontend initialization fails, inspect
the ECS stopped reason and the three SSM paths before trying again. Select
`quick-tunnel` on the next manual run to return to the existing Cloudflare
endpoint.

References: [DuckDNS API](https://www.duckdns.org/spec.jsp),
[Certbot DNS challenge](https://eff-certbot.readthedocs.io/en/stable/using.html),
[Fargate networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/networking-outbound.html),
[AWS IPv4 pricing](https://aws.amazon.com/vpc/pricing/).
