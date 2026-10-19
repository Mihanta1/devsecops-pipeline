# Choix techniques

Ce document explique **pourquoi** chaque outil a été retenu, **quelles alternatives** existent et **quelles limites** subsistent. Le contexte : un pipeline DevSecOps (sujet 1) pour une petite application API + base de données, réalisé seul, en trois semaines, sur Windows (WSL2).

## 1. Application et base de données

| | |
|---|---|
| **Choix** | FastAPI (Python 3.14), PostgreSQL 16, driver `psycopg` 3 avec requêtes SQL écrites à la main |
| **Pourquoi** | L'application n'est pas le sujet : il fallait quelque chose de réel (API + base, deux services) mais très court à écrire. FastAPI fournit validation des données et documentation `/docs` sans code supplémentaire. Les requêtes sont **paramétrées** (`%s`), ce qui supprime le risque d'injection SQL. |
| **Alternatives** | Flask ou Express pour le framework ; SQLAlchemy pour l'accès aux données |
| **Limites** | Pas d'authentification, pas de migrations de schéma (la table est créée au démarrage), pas de pool de connexions : une connexion par requête. Suffisant pour la démonstration, pas pour de la production. |

Les routes sont séparées en `APIRouter` (un fichier par ressource) et l'accès à la base est isolé dans `storage.py` : changer de stockage ne touche pas aux routes (c'est ce qui a permis de passer d'une liste en mémoire à PostgreSQL sans réécrire l'API).

## 2. Docker

| | |
|---|---|
| **Choix** | Image de base `python:3.14.4-slim` à version précise, utilisateur non-root, dépendances installées avant la copie du code, `.dockerignore`, mise à jour ciblée de `perl-base` |
| **Pourquoi** | La variante `slim` réduit la surface d'attaque ; la version précise rend le build reproductible ; l'ordre des instructions profite du cache Docker ; l'utilisateur non-root limite les dégâts en cas de faille. L'image finale pèse environ 49 Mo de contenu. |
| **Alternatives** | `alpine` (plus petit, mais incompatibilités possibles avec certaines bibliothèques), images « distroless » (encore plus minimales), build multi-stage |
| **Limites** | Pas de multi-stage : l'application n'a rien à compiler, donc il n'apporterait rien ici. L'image de base reste un système Debian complet avec ses paquets : de nouvelles failles peuvent y apparaître, d'où le scan à chaque build. |

## 3. Docker Compose

Utilisé uniquement pour le **développement local** : API + PostgreSQL avec un volume, un healthcheck sur la base et un `depends_on` conditionnel pour que l'API attende que la base soit prête. Les variables viennent d'un `.env` non versionné. Le port de la base n'est publié que sur `127.0.0.1` (pour les tests locaux), jamais sur le réseau.

## 4. GitHub Actions

| | |
|---|---|
| **Choix** | Un seul workflow avec six jobs ; contrôles en parallèle, puis build, puis déploiement |
| **Pourquoi** | Le code est déjà sur GitHub : pas de serveur CI à installer ni à maintenir. Les permissions sont déclarées **job par job** (moindre privilège) : le job de déploiement n'a que `contents: read`. Les runners sont fixés à `ubuntu-24.04` pour éviter qu'un changement de version de `ubuntu-latest` casse le pipeline. |
| **Alternatives** | GitLab CI, Jenkins, Drone |
| **Limites** | La plupart des actions sont référencées par **tag de version** (`@v4`, `@v3`...), qui peut être déplacé par leur auteur. Seule l'action Trivy est épinglée sur une version précise. Épingler **toutes** les actions sur le SHA de leur commit serait plus sûr. |

## 5. Sécurité de la chaîne

### 5.1 Gitleaks : détection de secrets

- **Pourquoi** : un secret commit une fois reste dans l'historique Git même supprimé ensuite. Gitleaks scanne **tout l'historique** (`fetch-depth: 0`), pas seulement le dernier commit.
- **Alternatives** : TruffleHog, la protection de push native de GitHub (secret scanning).
- **Limites** : il repose sur des motifs et de l'entropie ; un secret au format inhabituel peut passer. Il ignore volontairement certaines clés d'exemple connues (par exemple la clé AWS de la documentation), ce qui a obligé à fabriquer un faux secret réaliste pour la démonstration. Aucun secret réel n'a jamais été utilisé.

### 5.2 Trivy : dépendances, image et infrastructure

Un seul outil, trois modes, ce qui garde le pipeline cohérent :

| Mode | Cible | Seuil de blocage |
|---|---|---|
| `fs` | dépendances Python de `app/` | HIGH et CRITICAL (failles corrigeables seulement) |
| `image` | l'image construite, **avant** publication | CRITICAL (failles corrigeables seulement) |
| `config` | Dockerfile, `k8s/`, `terraform/` | HIGH et CRITICAL |

- **Pourquoi `ignore-unfixed`** : bloquer sur une faille que personne ne sait corriger n'aide pas, et rend le pipeline inutilisable. On bloque seulement ce qui est actionnable.
- **Pourquoi scanner l'image avant de la publier** : rien de vulnérable n'arrive dans le registre.
- **Alternatives** : Grype et Snyk (scan de vulnérabilités), Checkov ou tfsec (IaC), Docker Scout.
- **Limites** : l'image est scannée à son état de build ; une faille découverte plus tard n'est détectée qu'au prochain run. Le seuil de l'image est volontairement plus bas (CRITICAL) que celui des dépendances.
- **Épinglage de l'action** : l'action Trivy est fixée sur `v0.36.0`. En mars 2026, les tags de cette action ont été détournés lors d'une attaque de la chaîne d'approvisionnement, ce qui a conduit le projet à migrer ses tags vers un préfixe `v`. Utiliser `@master` ou un tag flottant aurait exposé le pipeline à ce type d'attaque.

### 5.3 Syft : SBOM

Le SBOM (inventaire des composants de l'image) est généré au format **SPDX JSON** et archivé avec le rapport Trivy. **Pourquoi** : quand une nouvelle faille est annoncée, on peut savoir immédiatement si l'image est concernée. **Alternative** : le format CycloneDX. **Limite** : le SBOM est archivé mais pas encore joint à l'image sous forme d'attestation signée.

### 5.4 Cosign : signature sans clé

- **Choix** : signature « keyless » avec l'identité OIDC de GitHub Actions, par **digest** de l'image.
- **Pourquoi** : aucune clé privée à stocker ni à protéger (donc aucune à voler). La signature prouve qu'elle a été produite par **ce workflow, de ce dépôt, sur `main`**. Signer le digest (et non un tag) garantit qu'on certifie cette image précise, car un tag peut être déplacé vers une autre image.
- **Vérification** : l'identité est vérifiée avec une valeur **exacte** (et non une expression régulière) : sa casse compte (`Mihanta1`), ce qui a d'ailleurs fait échouer une première version du contrôle.
- **Alternatives** : Cosign avec une paire de clés, Notary v2, les attestations de provenance de GitHub.
- **Limites** : le contrôle a lieu dans le pipeline (`cosign verify` dans le job de déploiement), pas dans le cluster. Quelqu'un qui déploierait à la main sur un cluster ne serait pas bloqué (voir « Pistes d'amélioration »).

### 5.5 GHCR

Le registre de GitHub : intégré, sans mot de passe supplémentaire (le `GITHUB_TOKEN` du workflow suffit). Chaque image reçoit un tag égal au **SHA du commit**, ce qui permet de savoir exactement quel code tourne ; le tag `latest` est aussi publié par commodité, mais les déploiements utilisent le **digest**. **Alternative** : Docker Hub.

## 6. Kubernetes

| | |
|---|---|
| **Choix** | Manifests Deployment + Service pour l'API et pour la base, testés sur **kind** |
| **Pourquoi** | kind fonctionne dans Docker Desktop, sans machine virtuelle supplémentaire, et peut être créé et détruit en quelques secondes, y compris dans le pipeline. |
| **Alternatives** | k3s, minikube, un cluster cloud managé |

**Durcissement des pods**, guidé par les résultats de Trivy `config` :

- API : `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, toutes les capacités retirées, volume `emptyDir` sur `/tmp`, sondes `readiness` et `liveness` sur `/health`, requêtes et limites de ressources.
- Pods : profil `seccomp` `RuntimeDefault` et `automountServiceAccountToken: false`.
- Base : `readOnlyRootFilesystem` activé avec des volumes `emptyDir` pour `/var/run/postgresql` et `/tmp` (vérifié sur un volume de données vide, là où PostgreSQL écrit le plus). Elle ne peut pas passer en `runAsNonRoot` : son entrypoint démarre en root pour préparer son dossier avant de changer d'utilisateur.
- Secrets : le Secret `db-secret` est créé par commande et référencé par `secretKeyRef` ; `DATABASE_URL` est assemblée par Kubernetes à partir de ces valeurs.

**Limites** : une seule réplique pour chaque service, pas d'Ingress, pas de NetworkPolicy, base sans sauvegarde. Le stockage de la base est un volume local au cluster : détruire le cluster détruit les données.

## 7. Déploiement continu sur un cluster éphémère

- **Choix** : le job `deploy-cd` crée un cluster **kind jetable** dans le runner, vérifie la signature, déploie le digest vérifié, attend que les deux Deployments soient prêts, puis teste `/health`. Le mot de passe de la base est généré aléatoirement à chaque exécution et n'est stocké nulle part.
- **Pourquoi** : un runner GitHub est sur Internet et ne peut pas atteindre un cluster qui tournerait sur un poste local. Un cluster éphémère rend le déploiement **reproductible par n'importe qui** et sans secret.
- **Alternatives** : un runner auto-hébergé relié à un cluster local, un petit serveur avec k3s, un cluster cloud.
- **Limites** : c'est un déploiement de **validation** : rien ne reste en ligne après l'exécution. L'image du manifest est remplacée par le digest **dans le runner seulement**, sans commit : le dépôt ne garde donc pas de digest périmé, mais il n'y a pas non plus de suivi GitOps de l'état déployé.

## 8. Terraform

| | |
|---|---|
| **Choix** | Provider Docker : réseau, volume et deux conteneurs (base, API), mot de passe en variable `sensitive` sans valeur par défaut |
| **Pourquoi** | Décrire l'infrastructure en code la rend reproductible et relue avant chaque changement (`terraform plan`). Le provider Docker ne demande aucun compte cloud ni carte bancaire. |
| **Alternatives** | Provider Kubernetes, un cloud (AWS, Azure), OpenTofu |
| **Limites** | Le state est **local** (jamais versionné) ; en équipe, il faudrait un backend distant avec verrouillage. Le fichier `.terraform.lock.hcl` fige les versions des providers. |

## 9. Ansible

| | |
|---|---|
| **Choix** | Un playbook qui installe quelques paquets, installe Docker s'il est absent, crée l'utilisateur de déploiement et le dossier de l'application, puis configure le pare-feu (`ufw`), avec des modules Ansible plutôt que des commandes shell |
| **Pourquoi** | Les modules rendent le playbook **idempotent** : un second passage ne change rien (`changed=0`), ce qui est vérifié dans la démonstration. Le pare-feu autorise SSH **avant** d'activer le refus par défaut, pour ne pas couper l'accès à un serveur distant. |
| **Alternatives** | Scripts shell, cloud-init, Chef ou Puppet |
| **Limites** | Le playbook est exécuté sur la **machine locale (WSL2)** faute de serveur distant : il est conçu pour un hôte distant avec un utilisateur sudoer. Docker n'est installé que **s'il est absent** : sur WSL2, le moteur vient de Docker Desktop et un second moteur entrerait en conflit, donc cette tâche est ignorée ici (elle s'exécuterait sur un serveur vierge). Sur Ubuntu récent, `sudo-rs` est incompatible avec le mécanisme `become` d'Ansible : le playbook est lancé avec `sudo ansible-playbook`. |

## 10. Difficultés rencontrées et solutions

| Problème | Cause | Solution |
|---|---|---|
| L'action Trivy n'était pas trouvée (`0.24.0`) | Tags renommés après l'attaque de mars 2026 | Version `v0.36.0` épinglée |
| 3 failles CRITICAL dans l'image | Paquet `perl-base` de l'image de base Debian | Mise à jour ciblée dans le Dockerfile ; le pipeline est repassé au vert |
| Push vers GHCR refusé | Permission `packages: write` manquante sur le job | Permissions déclarées par job |
| Vérification de signature refusée | Casse de l'identité (`Mihanta1` et non `mihanta1`) | Identité exacte, sans expression régulière |
| Gitleaks ne détectait pas le faux secret | Clé d'exemple AWS ignorée par défaut, fichier mal encodé | Faux secret réaliste, fichier en UTF-8 |
| Port 5432 déjà utilisé au lancement de Compose | Un ancien conteneur PostgreSQL | Plus de port publié pour la base dans Compose (publication limitée à `127.0.0.1:5433` pour les tests) |
| `KSV-0118` et `KSV-0014` sur les manifests | Contexte de sécurité seulement au niveau conteneur ; base en écriture | Contexte au niveau du pod ; base en lecture seule avec volumes temporaires |
| Ansible échouait à obtenir les droits | `sudo-rs` incompatible avec `become` | Lancement avec `sudo ansible-playbook` |
| L'API inaccessible depuis le navigateur | `0.0.0.0` n'est pas une adresse à visiter | `localhost` côté navigateur, `0.0.0.0` côté serveur dans le conteneur |

## 11. Limites générales et pistes d'amélioration

- **Politique d'admission Kubernetes** (Kyverno) qui refuse toute image non signée *dans le cluster*, pour que même un déploiement manuel soit contrôlé : c'est le bonus du sujet, non réalisé.
- **Épingler toutes les actions GitHub sur leur SHA** et activer Dependabot pour les mettre à jour.
- **Attestation du SBOM** jointe à l'image et signée.
- **Image scannée et image publiée** : ce sont deux builds successifs qui partagent le cache, donc très proches, mais pas garantis identiques bit à bit. Une amélioration serait de publier exactement l'image déjà scannée.
- **Nom de l'image écrit en dur** (`ghcr.io/mihanta1/devsecops-pipeline`) : pour reproduire le projet dans un autre compte, il faut le remplacer dans le workflow, le manifest et la variable Terraform, ainsi que l'identité de vérification Cosign.
- **Environnement réel** : GitOps, sauvegardes de la base, haute disponibilité, supervision.
