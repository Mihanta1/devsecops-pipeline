# DevSecOps Pipeline : une chaîne logicielle sécurisée de bout en bout

**État du pipeline CI :** suivi dans l’onglet GitHub Actions du dépôt.

Projet individuel DevOps M2, **Sujet 1 : Pipeline DevSecOps**.

Le dépôt contient une petite application (API de liste de tâches + base PostgreSQL) et, surtout, la chaîne qui la livre : à chaque push, le code est contrôlé, l'image est scannée, inventoriée (SBOM), signée, puis déployée sur Kubernetes **uniquement si sa signature est vérifiée**. Un secret ou une faille CRITICAL bloque le pipeline.

- Choix techniques, alternatives et limites : [`docs/CHOIX_TECHNIQUES.md`](docs/CHOIX_TECHNIQUES.md)

## Sommaire

1. [Application support](#1-application-support)
2. [Architecture](#2-architecture)
3. [Structure du dépôt](#3-structure-du-dépôt)
4. [Prérequis](#4-prérequis)
5. [Tout relancer de A à Z](#5-tout-relancer-de-a-à-z)
6. [Le pipeline CI/CD](#6-le-pipeline-cicd)
7. [Démonstrations des objectifs du sujet](#7-démonstrations-des-objectifs-du-sujet)
8. [Mesures de sécurité en bref](#8-mesures-de-sécurité-en-bref)

## 1. Application support

Une API REST de gestion de tâches, volontairement simple : le sujet est la chaîne de livraison, pas l'application.

| Élément                   | Détail                                                                              |
| ------------------------- | ----------------------------------------------------------------------------------- |
| Langage / framework       | Python 3.14, FastAPI                                                                |
| Base de données           | PostgreSQL 16 (driver `psycopg` 3, requêtes paramétrées)                            |
| Routes                    | `GET /health`, `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `DELETE /tasks/{id}` |
| Documentation interactive | `/docs` (générée par FastAPI)                                                       |
| Configuration             | uniquement par variables d'environnement (`DATABASE_URL`)                           |
| Tests                     | Pytest (routes, validation, erreurs 404), lint avec Ruff                            |

## 2. Architecture

### Vue d'ensemble du flux

1. **Déclenchement** : un push ou une Pull Request vers GitHub lance les contrôles d'intégration continue.
2. **Contrôles préalables** : Gitleaks recherche les secrets, Trivy analyse les dépendances et les fichiers d'infrastructure, puis Ruff et Pytest vérifient la qualité et le fonctionnement du code avec PostgreSQL.
3. **Construction et analyse** : après validation des contrôles, construction de l'image Docker, analyse de ses vulnérabilités avec Trivy et génération d'un SBOM avec Syft.
4. **Publication et signature** : sur `main`, publication de l'image dans GHCR avec un tag correspondant au SHA du commit, puis signature Cosign par digest.
5. **Déploiement continu** : vérification de la signature et de l'identité du workflow, déploiement du digest vérifié sur un cluster Kubernetes `kind` éphémère, puis test de `/health`.
6. **Archivage** : conservation des rapports de sécurité et du SBOM parmi les artefacts du run GitHub Actions.

**Infrastructure as Code, exécutée séparément :** Terraform décrit le réseau, le volume et les conteneurs Docker ; Ansible prépare l'hôte, notamment les paquets, l'utilisateur de déploiement et le pare-feu.

### Rôle de chaque brique

| Brique                  | Rôle                                                                               | Où                                                   |
| ----------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Docker**              | Emballe l'application dans une image légère, sans droits root                      | `app/Dockerfile`                                     |
| **Docker Compose**      | Lance l'API et PostgreSQL en une commande (usage local)                            | `docker-compose.yml`                                 |
| **GitHub Actions (CI)** | Exécute tests, contrôles de sécurité, build, signature                             | `.github/workflows/ci.yaml`                          |
| **Gitleaks**            | Cherche des secrets dans tout l'historique Git                                     | job `secrets-scan`                                   |
| **Trivy**               | Scanne les dépendances, l'image et les fichiers d'infrastructure                   | jobs `dependency-scan`, `iac-scan`, `build-and-push` |
| **Syft**                | Génère le SBOM (inventaire des composants de l'image)                              | job `build-and-push`                                 |
| **Cosign**              | Signe l'image (sans clé, via l'identité GitHub) puis vérifie la signature          | `build-and-push`, `deploy-cd`                        |
| **GHCR**                | Registre où l'image est publiée (tag = SHA du commit)                              | `ghcr.io/mihanta1/devsecops-pipeline`                |
| **CD**                  | Vérifie la signature, déploie sur un cluster kind jetable, teste l'application     | job `deploy-cd`                                      |
| **Kubernetes**          | Deployments et Services de l'API et de la base, avec contextes de sécurité stricts | `k8s/`                                               |
| **Terraform**           | Décrit réseau, volume et conteneurs Docker en code                                 | `terraform/`                                         |
| **Ansible**             | Prépare un hôte (paquets, utilisateur de déploiement, pare-feu)                    | `ansible/`                                           |

## 3. Structure du dépôt

```
.
├── app/                      API FastAPI, tests, Dockerfile, dépendances
│   ├── main.py
│   ├── routers/              health.py, tasks.py
│   ├── schemas.py            modèles Pydantic
│   ├── storage.py            accès PostgreSQL
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt      dépendances de production (versions figées)
│   └── requirements-dev.txt  tests et lint
├── k8s/                      api.yaml, db.yaml
├── terraform/                main.tf, variables.tf, outputs.tf
├── ansible/                  inventory.ini, playbook.yml
├── .github/workflows/        ci.yaml
├── docker-compose.yml
├── .env.example              modèle de configuration (sans vrais secrets)
└── README.md
```

## 4. Prérequis

Environnement utilisé : Windows 11 avec **WSL2 (Ubuntu)** et Docker Desktop (intégration WSL activée). Toutes les commandes ci-dessous se lancent **dans le terminal Ubuntu**.

| Outil          | Version utilisée                                |
| -------------- | ----------------------------------------------- |
| Docker         | 29.6.1                                          |
| Git            | 2.53                                            |
| kind           | 0.33.0                                          |
| kubectl        | 1.37.1                                          |
| Terraform      | 1.16.5                                          |
| Ansible (core) | 2.20.1 (avec la collection `community.general`) |
| Python         | 3.14.4                                          |
| Cosign         | pour vérifier une signature à la main           |

Aucun secret GitHub n'est nécessaire : le push vers GHCR utilise le `GITHUB_TOKEN` du workflow, et le mot de passe de la base est généré à la volée pendant le déploiement.

> Le paquet GHCR de l'image doit être **public** pour qu'un cluster sans identifiants puisse la télécharger.

## 5. Tout relancer de A à Z

### 5.1 Récupérer le projet et configurer l'environnement

```bash
git clone https://github.com/Mihanta1/devsecops-pipeline.git
cd devsecops-pipeline
cp .env.example .env
```

Configuration de `.env` avec des valeurs pour `POSTGRES_USER`, `POSTGRES_PASSWORD` et `POSTGRES_DB` (évite les caractères spéciaux dans le mot de passe : il est placé dans une URL). Le fichier `.env` est ignoré par Git. Il doit être enregistré avec des fins de ligne **LF**.

### 5.2 Lancer l'application avec Docker Compose

```bash
docker compose up --build
```

Dans un autre terminal :

```bash
curl http://localhost:8000/health        # {"status":"ok"}
```

Accès à `http://localhost:8000/docs` pour tester les routes. Arrêt de l'application : `docker compose down` (les données restent dans le volume ; `down -v` les supprime).

### 5.3 Lancer le lint et les tests

Les tests ont besoin d'une base. Compose publie PostgreSQL sur `127.0.0.1:5433` uniquement.

```bash
docker compose up -d db
set -a; source .env; set +a
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5433/${POSTGRES_DB}"

cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest
cd ..
```

### 5.4 Déployer sur Kubernetes (kind)

```bash
kind create cluster --name devsecops

kubectl create secret generic db-secret \
  --from-literal=POSTGRES_USER=app \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --from-literal=POSTGRES_DB=tasks

kubectl apply -f k8s/
kubectl rollout status deployment/db --timeout=180s
kubectl rollout status deployment/task-api --timeout=180s
kubectl port-forward svc/task-api-service 8000:8000
```

Le Secret est créé par commande et **n'est jamais écrit dans Git**. Dans le pipeline, l'image du manifest est remplacée par le **digest vérifié** avant l'application. Nettoyage : `kind delete cluster --name devsecops`.

### 5.5 Provisionner avec Terraform

Terraform décrit un réseau Docker, un volume et deux conteneurs (base et API). Arrêt de Compose au préalable (`docker compose down`) pour libérer les ports ; Terraform publie l'API sur le port **8001**.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars    # renseigner api_image avec un tag SHA de l'image
export TF_VAR_db_password="<mot de passe de test>"

terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
curl http://localhost:8001/health
terraform destroy
```

Le mot de passe est une variable `sensitive` sans valeur par défaut : il n'est écrit dans aucun fichier versionné.

### 5.6 Préparer un hôte avec Ansible

Le playbook installe quelques paquets, crée l'utilisateur `deploy`, le dossier `/opt/devsecops` et configure le pare-feu (SSH et port 8000 autorisés, refus du reste en entrée). Il est ici exécuté sur la machine locale (WSL2).

```bash
cd ansible
sudo ansible-playbook -i inventory.ini playbook.yml     # 1er passage : des tâches « changed »
sudo ansible-playbook -i inventory.ini playbook.yml     # 2e passage : changed=0 (idempotence)
```

> Sur Ubuntu récent, `sudo-rs` est incompatible avec le mécanisme `become` d'Ansible : le playbook est donc lancé directement avec `sudo`. Le pare-feu `ufw` est activé par le playbook ; `sudo ufw disable` le désactive.

### 5.7 Déclencher le pipeline CI/CD

```bash
git checkout -b ma-modification
# ... modifier un fichier ...
git add . && git commit -m "feat: ma modification" && git push origin ma-modification
```

Ouverture d'une Pull Request vers `main` : les contrôles s'exécutent (sans publication d'image). Au merge sur `main`, le pipeline construit, scanne, signe, publie puis déploie.

## 6. Le pipeline CI/CD

Un seul fichier : `.github/workflows/ci.yaml`.

| Job               | Déclenché sur                               | Ce qu'il fait                                                                 | Bloque si                                           |
| ----------------- | ------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------- |
| `secrets-scan`    | push, PR                                    | Gitleaks sur tout l'historique                                                | un secret est détecté                               |
| `dependency-scan` | push, PR                                    | Trivy sur `app/` (dépendances)                                                | faille HIGH ou CRITICAL corrigeable                 |
| `iac-scan`        | push, PR                                    | Trivy `config` sur Dockerfile, `k8s/`, `terraform/`                           | mauvaise configuration HIGH ou CRITICAL             |
| `test-backend`    | push, PR                                    | Ruff + Pytest avec un service PostgreSQL                                      | lint ou test en échec                               |
| `build-and-push`  | push, PR (publication sur `main` seulement) | Build local, Trivy image, SBOM, push GHCR (tag SHA), signature Cosign         | faille CRITICAL dans l'image                        |
| `deploy-cd`       | `main` seulement                            | `cosign verify`, cluster kind éphémère, déploiement du digest, test `/health` | signature absente ou invalide, déploiement en échec |

`build-and-push` n'est lancé que si les quatre contrôles précédents sont verts, et `deploy-cd` que si la publication a réussi.

**Rapports archivés** : dans l'onglet _Actions_, ouvre un run, puis la section _Artifacts_ : `security-reports` contient `trivy-image.json` (rapport de scan de l'image) et `sbom.spdx.json` (SBOM au format SPDX).

**Vérifier une signature à la main** (le digest est affiché dans les logs de l'étape « Publier l'image » ou sur la page du paquet) :

```bash
cosign verify ghcr.io/mihanta1/devsecops-pipeline@sha256:<digest> \
  --certificate-identity "https://github.com/Mihanta1/devsecops-pipeline/.github/workflows/ci.yaml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

## 7. Démonstrations des objectifs du sujet

| Objectif du sujet                           | Comment c'est réalisé                                                      | Où le voir                                                                                               |
| ------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Détecter les secrets et bloquer le pipeline | Job `secrets-scan` (Gitleaks, historique complet)                          | PR `demo/secret-leak` : run rouge, `build-and-push` ignoré                                               |
| Scanner dépendances, image et IaC           | Trivy `fs`, `image`, `config`                                              | Jobs `dependency-scan`, `build-and-push`, `iac-scan`                                                     |
| Bloquer sur une faille CRITICAL             | `exit-code: 1` sur l'image                                                 | Run rouge listant 3 CVE CRITICAL sur `perl-base`, corrigées par mise à jour du paquet dans le Dockerfile |
| Générer un SBOM et signer l'image           | Syft (SPDX), Cosign keyless par digest                                     | Artefact `security-reports`, étape « Signer l'image »                                                    |
| Vérifier la signature avant déploiement     | `cosign verify` avec l'identité exacte du workflow, en tête de `deploy-cd` | Job `deploy-cd`                                                                                          |
| Rapport de scan archivé                     | `actions/upload-artifact` (`if: always()`)                                 | Section _Artifacts_ de chaque run                                                                        |

**Reproduire les blocages :**

- _Secret_ : sur une branche, ajout d'un **faux** secret au format reconnu (jamais un vrai) puis ouverture d'une Pull Request : `secrets-scan` passe au rouge.
- _Mauvaise configuration_ : retrait du `securityContext` d'un Deployment de `k8s/` : `iac-scan` signale `KSV-0118`.
- _Image non signée_ : `cosign verify python:3.14.4-slim ...` (commande ci-dessus) répond `no signatures found` : une image qui ne vient pas de ce workflow est refusée.

### Éléments de preuve

Les exécutions GitHub Actions permettent de vérifier les résultats suivants, sans dépendre de captures d'écran :

- **Pipeline validé** : run vert lorsque l'ensemble des contrôles et du déploiement aboutit.
- **Secret détecté** : échec du job `secrets-scan` avec Gitleaks et blocage des étapes suivantes.
- **Vulnérabilités CRITICAL détectées** : rapport Trivy identifiant les CVE présentes dans l'image ; dans la démonstration, trois CVE CRITICAL liées à `perl-base` ont été corrigées par la mise à jour du paquet dans le Dockerfile.
- **Signature vérifiée ou refusée** : validation de l'image signée par le workflow attendu et refus d'une image sans signature correspondante.
- **Idempotence Ansible** : deuxième exécution du playbook sans changement (`changed=0`).

Les rapports détaillés sont accessibles dans les artefacts de chaque exécution : `trivy-image.json` et `sbom.spdx.json`.

## 8. Mesures de sécurité en bref

- **Aucun secret dans Git** : `.env` ignoré, `.env.example` factice, mot de passe Kubernetes généré au déploiement, variable Terraform `sensitive`.
- **Moindre privilège** : chaque job du pipeline déclare ses permissions ; le job de déploiement n'a que `contents: read`.
- **Image minimale et non-root** : `python:3.14.4-slim` à version précise, utilisateur `appuser`, paquet système vulnérable mis à jour.
- **Pods durcis** : `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, capacités retirées, profil `seccomp`, pas de jeton de compte de service monté.
- **Déploiement par digest** : l'image déployée est celle dont la signature a été vérifiée, pas un tag modifiable.
- **Outils de sécurité épinglés** : l'action Trivy est fixée à une version précise après l'incident de chaîne d'approvisionnement de mars 2026.
