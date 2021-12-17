#!/bin/sh

helm repo add bitnami https://charts.bitnami.com/bitnami
kubectl create namespace monitoring || true