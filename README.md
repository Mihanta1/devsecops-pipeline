# DevSecOps Pipeline : une chaîne logicielle sécurisée de bout en bout

Projet individuel DevOps M2, **Sujet 1 : Pipeline DevSecOps**.

Le dépôt contient une petite application (API de liste de tâches + base PostgreSQL) et, surtout, la chaîne qui la livre : à chaque push, le code est contrôlé, l'image est scannée, inventoriée (SBOM), signée, puis déployée sur Kubernetes **uniquement si sa signature est vérifiée**. Un secret ou une faille CRITICAL bloque le pipeline.

Choix techniques, alternatives et limites : [`docs/CHOIX_TECHNIQUES.md`](docs/CHOIX_TECHNIQUES.md)

## Sommaire

1. Application support
2. Architecture
3. Structure du dépôt
4. Prérequis
5. Relancer le projet de A à Z
6. Le pipeline CI/CD
7. Démonstrations des objectifs du sujet
8. Mesures de sécurité en bref

## 1. Application support

Une API REST de gestion de tâches, volontairement simple : le sujet est la chaîne de livraison, pas l'application.

| Élément | Détail |
|---|---|
| Langage / framework | Python 3.14, FastAPI |
| Base de données | PostgreSQL 16 (driver `psycopg` 3, requêtes paramétrées) |
| Routes | `GET /health`, `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `DELETE /tasks/{id}` |
| Documentation interactive | `/docs` (générée par FastAPI) |
| Configuration | uniquement par variables d'environnement (`DATABASE_URL`) |
| Tests | Pytest (routes, validation, erreurs 404), lint avec Ruff |

## 2. Architecture

```text
Développeuse
    │  git push / Pull Request
    ▼
GitHub (dépôt + Actions)
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│ CI : contrôles en parallèle                                    │
│ • secrets-scan      Gitleaks : secrets (historique complet)    │
│ • dependency-scan   Trivy fs : dépendances Python              │
│ • iac-scan          Trivy config : Dockerfile, k8s, Terraform  │
│ • test-backend      Ruff + Pytest avec PostgreSQL              │
└────────────────────────────────────────────────────────────────┘
                                │ tous verts
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ CI : build-and-push                                            │
│ 1. Build de l'image (sans publication)                         │
│ 2. Trivy image : bloque si faille CRITICAL                     │
│ 3. SBOM Syft  ──►  artefacts : rapport Trivy + SBOM            │
│ 4. Push sur GHCR (tag = SHA du commit)                         │
│ 5. Signature Cosign par digest (sans clé)                      │
└────────────────────────────────────────────────────────────────┘
                                │ sur main uniquement
                                ▼
┌────────────────────────────────────────────────────────────────┐
│ CD : deploy-cd                                                 │
│ 1. cosign verify (identité exacte du workflow)                 │
│ 2. Cluster kind éphémère                                       │
│ 3. kubectl apply avec image@digest vérifié                     │
│ 4. Test de /health                                             │
└────────────────────────────────────────────────────────────────┘

Infrastructure as Code (lancée à la main) :
    Terraform  →  réseau, volume et conteneurs Docker
    Ansible    →  paquets, utilisateur de déploiement, pare-feu
```

### Rôle de chaque brique

| Brique | Rôle | Où |
|---|---|---|
| **Docker** | Emballer l'application dans une image légère, sans droits root | `app/Dockerfile` |
| **Docker Compose** | Lancer l'API et PostgreSQL en une commande (usage local) | `docker-compose.yml` |
| **GitHub Actions (CI)** | Exécuter tests, contrôles de sécurité, build et signature | `.github/workflows/ci.yaml` |
| **Gitleaks** | Chercher des secrets dans tout l'historique Git | job `secrets-scan` |
| **Trivy** | Scanner les dépendances, l'image et les fichiers d'infrastructure | jobs `dependency-scan`, `iac-scan`, `build-and-push` |
| **Syft** | Générer le SBOM (inventaire des composants de l'image) | job `build-and-push` |
| **Cosign** | Signer l'image (sans clé, via l'identité GitHub), puis vérifier la signature | `build-and-push`, `deploy-cd` |
| **GHCR** | Publier l'image (tag = SHA du commit) | `ghcr.io/mihanta1/devsecops-pipeline` |
| **CD** | Vérifier la signature, déployer sur un cluster kind jetable, tester l'application | job `deploy-cd` |
| **Kubernetes** | Exécuter l'API et la base avec des contextes de sécurité stricts | `k8s/` |
| **Terraform** | Décrire réseau, volume et conteneurs Docker en code | `terraform/` |
| **Ansible** | Préparer un hôte (paquets, utilisateur de déploiement, pare-feu) | `ansible/` |

## 3. Structure du dépôt

```text
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
├── docs/                     CHOIX_TECHNIQUES.md
├── .github/workflows/        ci.yaml
├── docker-compose.yml
├── .env.example              modèle de configuration (sans vrais secrets)
└── README.md
```

## 4. Prérequis

Utiliser Windows 11 avec **WSL2 (Ubuntu)** et Docker Desktop (intégration WSL activée). Lancer toutes les commandes ci-dessous **dans le terminal Ubuntu**.

| Outil | Version utilisée |
|---|---|
| Docker | 29.6.1 |
| Git | 2.53 |
| kind | 0.33.0 |
| kubectl | 1.37.1 |
| Terraform | 1.16.5 |
| Ansible (core) | 2.20.1 (avec la collection `community.general`) |
| Python | 3.14.4 |
| Cosign | pour vérifier une signature à la main |

Ne configurer aucun secret GitHub : le push vers GHCR utilise le `GITHUB_TOKEN` du workflow, et le mot de passe de la base est généré à la volée pendant le déploiement.

Rendre le paquet GHCR de l'image **public**, afin qu'un cluster sans identifiants puisse la télécharger.

## 5. Relancer le projet de A à Z

### 5.1 Récupérer le projet et configurer l'environnement

```bash
git clone https://github.com/Mihanta1/devsecops-pipeline.git
cd devsecops-pipeline
cp .env.example .env
```

Éditer `.env` et choisir des valeurs pour `POSTGRES_USER`, `POSTGRES_PASSWORD` et `POSTGRES_DB`. Éviter les caractères spéciaux dans le mot de passe, car il est placé dans une URL. Enregistrer le fichier avec des fins de ligne **LF**. Ne jamais versionner `.env` : il est ignoré par Git.

### 5.2 Lancer l'application avec Docker Compose

```bash
docker compose up --build
```

Dans un autre terminal, vérifier que l'API répond :

```bash
curl http://localhost:8000/health        # {"status":"ok"}
```

Ouvrir `http://localhost:8000/docs` pour tester les routes. Arrêter l'application avec `docker compose down` : les données restent dans le volume, et `docker compose down -v` les supprime.

### 5.3 Lancer le lint et les tests

Démarrer d'abord la base : Compose la publie sur `127.0.0.1:5433` uniquement.

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

Créer le Secret par commande : il n'est jamais écrit dans Git. Dans le pipeline, l'image du manifest est remplacée par le **digest vérifié** avant l'application. Supprimer le cluster en fin de test avec `kind delete cluster --name devsecops`.

### 5.5 Provisionner avec Terraform

Terraform décrit un réseau Docker, un volume et deux conteneurs (base et API). Arrêter Compose avant (`docker compose down`) pour libérer les ressources. Noter que l'API est publiée sur le port **8001**.

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

Le playbook installe quelques paquets, installe Docker **seulement s'il est absent** (tâche ignorée quand Docker Desktop le fournit déjà), crée l'utilisateur `deploy` et le dossier `/opt/devsecops`, puis configure le pare-feu (SSH et port 8000 autorisés, reste refusé en entrée). Il s'exécute ici sur la machine locale (WSL2).

```bash
cd ansible
sudo ansible-playbook -i inventory.ini playbook.yml     # 1er passage : des tâches « changed »
sudo ansible-playbook -i inventory.ini playbook.yml     # 2e passage : changed=0 (idempotence)
```

Lancer le playbook avec `sudo` et non avec `--ask-become-pass` : sur Ubuntu récent, `sudo-rs` est incompatible avec le mécanisme `become` d'Ansible. Désactiver le pare-feu après les tests avec `sudo ufw disable`.

### 5.7 Déclencher le pipeline CI/CD

```bash
git checkout -b ma-modification
# modifier un fichier
git add . && git commit -m "feat: ma modification" && git push origin ma-modification
```

Ouvrir une Pull Request vers `main` : les contrôles s'exécutent sans publier d'image. Fusionner dans `main` : le pipeline construit, scanne, signe, publie puis déploie.

## 6. Le pipeline CI/CD

Un seul fichier : `.github/workflows/ci.yaml`.

| Job | Déclenché sur | Ce qu'il fait | Bloque si |
|---|---|---|---|
| `secrets-scan` | push, PR | Gitleaks sur tout l'historique | un secret est détecté |
| `dependency-scan` | push, PR | Trivy sur `app/` (dépendances) | faille HIGH ou CRITICAL corrigeable |
| `iac-scan` | push, PR | Trivy `config` sur Dockerfile, `k8s/`, `terraform/` | mauvaise configuration HIGH ou CRITICAL |
| `test-backend` | push, PR | Ruff + Pytest avec un service PostgreSQL | lint ou test en échec |
| `build-and-push` | push, PR (publication sur `main` seulement) | Build local, Trivy image, SBOM, push GHCR (tag SHA), signature Cosign | faille CRITICAL dans l'image |
| `deploy-cd` | `main` seulement | `cosign verify`, cluster kind éphémère, déploiement du digest, test `/health` | signature absente ou invalide, déploiement en échec |

Le job `build-and-push` démarre seulement si les quatre contrôles sont verts, et `deploy-cd` seulement si la publication a réussi.

**Consulter les rapports archivés** : ouvrir un run dans l'onglet *Actions*, puis la section *Artifacts*. L'artefact `security-reports` contient `trivy-image.json` (rapport de scan de l'image) et `sbom.spdx.json` (SBOM au format SPDX).

**Vérifier une signature à la main** : récupérer le digest dans les logs de l'étape « Publier l'image » ou sur la page du paquet, puis lancer :

```bash
cosign verify ghcr.io/mihanta1/devsecops-pipeline@sha256:<digest> \
  --certificate-identity "https://github.com/Mihanta1/devsecops-pipeline/.github/workflows/ci.yaml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

## 7. Démonstrations des objectifs du sujet

| Objectif du sujet | Réalisation | Où le constater |
|---|---|---|
| Détecter les secrets et bloquer le pipeline | Job `secrets-scan` (Gitleaks, historique complet) | PR `demo/secret-leak` : run rouge, `build-and-push` ignoré |
| Scanner dépendances, image et IaC | Trivy `fs`, `image`, `config` | Jobs `dependency-scan`, `build-and-push`, `iac-scan` |
| Bloquer sur une faille CRITICAL | `exit-code: 1` sur l'image | Run rouge listant 3 CVE CRITICAL sur `perl-base`, corrigées par la mise à jour du paquet dans le Dockerfile |
| Générer un SBOM et signer l'image | Syft (SPDX), Cosign sans clé, par digest | Artefact `security-reports`, étape « Signer l'image » |
| Vérifier la signature avant déploiement | `cosign verify` avec l'identité exacte du workflow, en tête de `deploy-cd` | Job `deploy-cd` |
| Archiver le rapport de scan | `actions/upload-artifact` (`if: always()`) | Section *Artifacts* de chaque run |

**Reproduire les blocages :**

- **Secret** : ajouter, sur une branche, un **faux** secret au format reconnu (jamais un vrai), puis ouvrir une Pull Request. Constater que `secrets-scan` passe au rouge.
- **Mauvaise configuration** : retirer le `securityContext` d'un Deployment de `k8s/`. Constater que `iac-scan` signale `KSV-0118`.
- **Image non signée** : lancer `cosign verify python:3.14.4-slim ...` avec la commande ci-dessus. Constater la réponse `no signatures found` : une image qui ne vient pas de ce workflow est refusée.

## 8. Mesures de sécurité en bref

- **Ne stocker aucun secret dans Git** : `.env` ignoré, `.env.example` factice, mot de passe Kubernetes généré au déploiement, variable Terraform `sensitive`.
- **Appliquer le moindre privilège** : déclarer les permissions job par job, et limiter le job de déploiement à `contents: read`.
- **Utiliser une image minimale et non-root** : `python:3.14.4-slim` à version précise, utilisateur `appuser`, paquet système vulnérable mis à jour.
- **Durcir les pods** : `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, capacités retirées, profil `seccomp`, pas de jeton de compte de service monté.
- **Déployer par digest** : déployer l'image dont la signature a été vérifiée, pas un tag modifiable.
- **Épingler les outils de sécurité** : fixer l'action Trivy sur une version précise, après l'incident de chaîne d'approvisionnement de mars 2026.
