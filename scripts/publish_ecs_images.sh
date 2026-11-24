#!/usr/bin/env bash
# Publish the exact checked-out commit to the existing immutable Sydney ECR repositories.
set -euo pipefail

[[ $# == 1 && "$1" =~ ^[0-9a-f]{40}$ && "$(git rev-parse HEAD)" == "$1" ]]
readonly REGISTRY=299952487175.dkr.ecr.ap-southeast-2.amazonaws.com
readonly IMAGE_TAG="sha-$1"
error=$(mktemp)
trap 'rm -f -- "$error"' EXIT

for component in frontend backend; do
  repository="mediroute-$component"
  image="$REGISTRY/$repository:$IMAGE_TAG"
  if aws ecr describe-images --repository-name "$repository" \
      --image-ids "imageTag=$IMAGE_TAG" >/dev/null 2>"$error"; then
    echo "Existing immutable image: $image"
    continue
  fi
  if ! grep -q ImageNotFoundException "$error"; then
    cat "$error" >&2
    exit 1
  fi
  docker build --platform linux/amd64 -f "infra/Dockerfile.$component" -t "$image" .
  docker push "$image"
  echo "PASS: Published $image"
done
