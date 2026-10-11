# Modèle de menaces (STRIDE)

Source : SPEC §13 (Sécurité), §3, §11, §12, §17.5. Créé à M0 (2026-10-10), mis à jour à chaque jalon (§17.3 étape 7).

**Lecture de l'état.** `prévu` = la parade est décrite par le SPEC mais n'existe pas encore. `livré (M0)` ou `livré (M1)` = présent dans le dépôt et vérifié à la clôture du jalon (tests, pile démarrée, revues indépendantes). `politique seule` = règle écrite (SPEC, `CLAUDE.md`), sans contrôle technique dans le dépôt. Rien d'autre n'est présenté comme fait. Le SPEC ne décrit pas d'autre parade que celles citées ; les manques sont en section 4.

## 1. Actifs

| Actif | Pourquoi il compte | Référence |
| --- | --- | --- |
| Clés API de trading et de lecture des venues | Elles permettent d'ordonner sur des fonds réels | F6, I12 |
| Clé maître du SecretStore, `N8N_ENCRYPTION_KEY` | Perdues, les clés d'exchange sont irrécupérables ; volées, elles sont lisibles | §13 Fiabilité |
| Positions et capital sur les venues | Perte financière directe | I4 à I7, F4 |
| Intégrité de l'état affiché et du journal d'audit | L'opérateur décide d'après eux | I1, I14 |
| Comptes opérateur (mot de passe, TOTP, sessions, jetons de service) | Accès à toutes les commandes | §13 Identifiants |
| Configuration et empreinte des moteurs, images épinglées | Détermine ce qui trade réellement | I2, I10 |
| Dépôt, CI, poste de développement | Point d'entrée de code malveillant | §17.5 |
| Sauvegardes | Contiennent l'état et, chiffrées, les secrets | §13 Fiabilité |
| Clé de l'autorité interne de Caddy (volume `caddy_data`) | Qui la détient peut usurper le dashboard auprès d'un appareil qui l'a approuvée | §5 Reverse proxy |

## 2. Frontières de confiance

| Frontière | Franchie par | Réseau / composant (§13, §3) |
| --- | --- | --- |
| F-a VPN vers la plateforme | Opérateur, navigateur | `edge` : Caddy, web, API. Rien n'écoute sur Internet par défaut |
| F-b API vers données | Requêtes SQL, bus | `data` : Postgres, Redis (API, Risk service, worker seulement) |
| F-c Plateforme vers moteurs | Commandes, relevés d'état | Worker uniquement, via `engines` ; moteur vers Risk service et récepteur d'événements seulement |
| F-d Worker vers Docker | Création de conteneurs | `docker` : worker, socket proxy |
| F-e Moteurs vers venues | Ordres | Sorties Internet : venues seules (liste blanche, M7) |
| F-f Plateforme vers n8n et retour | Webhooks signés HMAC, jetons de service | `automation` : n8n n'atteint que l'API |
| F-g Serveur MCP vers agents Claude | Appels d'outils | `app` ; outils bornés (§12) |
| F-h Contenu externe vers agents et n8n | News, flux, pages, issues | Données non fiables (§12, §17.5) |
| F-i Dépôt et dépendances vers build | Paquets, images, actions CI | Chaîne d'approvisionnement (§13) |
| F-j Poste de développement agentique vers dépôt | Agents de construction | `CLAUDE.md`, `.claude/`, hooks (§17.5) |
| F-k Plateforme vers observabilité et surveillance externe | Métriques, battement | `obs` (lecture) ; battement vers un service hors serveur |

## 3. Menaces

Jalon = jalon où la parade est livrée, d'après la ligne du §14 qui livre le composant. « (déduit) » = le SPEC ne rattache pas la parade à un jalon.

### 3.1 Abus par un agent IA

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Un agent d'exécution passe ou modifie un ordre | Serveur MCP | E | `place_order`, `raise_limit`, accès aux secrets, levée du kill switch absents du serveur (§12) ; test d'absence (§14 M5) ; I11 | M5 (test), M7 (I11) | prévu |
| A2 | Un agent fait approuver une action qui augmente le risque | Propositions (F5) | E | Approbation dans le dashboard avec 2FA uniquement ; test (§14 M6) ; mode shadow par défaut (§12) | M6 | prévu |
| A3 | Un agent présente une donnée périmée ou paper comme réelle | Outils de lecture MCP | I | Outils renvoyant l'état avec son âge ; cas dans les évals (§12, I1) | M5 | prévu |
| A4 | Un agent de construction écrit une clé live ou active le live | Poste de dev, dépôt | E, I | Aucune clé live en développement (§0.10, §17.5) ; hook bloquant toute écriture qui active un mode live (§17.5) ; aucun skill ni MCP d'ordres (§17.7). Limite : le hook ne voit que les outils Write et Edit (une écriture par le shell lui échappe) et exempte `docs/`, `tests/` et `*.md` | M0 | livré (M0) |
| A5 | Un agent de construction modifie ses propres garde-fous (`.claude/settings.json`, hooks) | `.claude/` | T, E | Interdit sans demande de l'opérateur (§0.9). Aucune règle de refus ni hook ne protège ces fichiers : la parade est la relecture du diff par l'opérateur | M0 | politique seule |
| A6 | Un agent épuise le budget (boucle d'outils) | Agents | D | Plafonds de coût journaliers, timeouts, sorties validées par schéma (§12) | M5 (déduit) | prévu |
| A7 | Action d'agent non attribuée | API | R | I14 : audit inaltérable avec auteur | M1 | prévu |

### 3.2 Exfiltration de clés

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| K1 | Relecture d'une clé via l'API ou l'interface | SecretStore, API | I | Saisie en écriture seule, jamais relue (F6, I12) ; test que l'API ne renvoie jamais la valeur (§14 M2) | M2 | prévu |
| K2 | Clé dans les logs | Journalisation | I | Processeur structlog de masquage, test à valeurs sentinelles (§13) | M1 (avancé de M2 par l'opérateur le 2026-10-10) | livré (M1). Limite : un message du pilote de base peut encore citer une valeur liée ; `hide_parameters=True` est en place |
| K3 | Clé dans une image, un fichier Compose, une variable d'environnement ou un volume persistant | Runner, moteurs | I | Fichier en lecture seule monté en mémoire, supprimé à l'arrêt (F6, §13) | M2 | prévu |
| K4 | Secrets de la plateforme dans l'environnement ou le dépôt | Compose, dépôt | I | Docker secrets (§13) ; gitleaks en pre-commit et en CI ; `.env.example` sans valeur (§0.5) | M0 | livré (M0) |
| K5 | Sauvegarde volée donnant accès aux clés | Sauvegardes | I | Sauvegardes chiffrées ; clé maître et `N8N_ENCRYPTION_KEY` sauvegardées à part, hors serveur (§13) | M7 (déduit) | prévu |
| K6 | Clé volée utilisée depuis une autre adresse ou pour retirer des fonds | Venue | S, E | Test de connexion : trading autorisé, retrait interdit, sinon refus ; avertissement bloquant pour le live sans restriction d'IP (F6) | M2 | prévu |
| K7 | Moteur compromis tente de lire d'autres clés ou d'atteindre la base | Moteurs | I, E | Réseau `engines` restreint ; gabarit de conteneur durci ; clé transmise à une seule instance (§13, I12) ; plafond de capital par sous-compte (F6) | M2 | prévu |
| K8 | Sortie réseau d'un moteur vers un domaine non prévu | Moteurs | I | Liste blanche de domaines (§13) ; à défaut risque accepté et consigné | M7 | prévu |
| K9 | Secret dans le contexte d'un agent | Agents | I | Aucun secret ni référence dans le contexte ; alias opaques (§12) | M5 | prévu |

### 3.3 Rejeu et falsification de webhooks

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | Faux webhook vers n8n | n8n | S | Signature HMAC vérifiée par chaque workflow ; `make n8n-lint` échoue sans vérification ; webhooks joignables depuis l'API seulement (§11) | M4 | prévu |
| W2 | Rejeu d'un webhook | n8n | R, T | Déduplication sur `X-Event-Id` (§11) | M4 | prévu |
| W3 | Rejeu d'une écriture n8n vers l'API | API | T | `Idempotency-Key` sur les écritures (§11) | M4 | prévu |
| W4 | n8n compromis escalade vers les ordres, limites, secrets, kill switch | API | E | Compte `automation` sans scope `orders:*`, `limits:write`, `secrets:*`, `kill-switch:release` ; `n8n-lint` ; réseau `automation` (§11, §13) | M4 | prévu |
| W5 | Faux clic Telegram approuve une proposition | WF-05 | S, E | Liste blanche d'identités revérifiée côté plateforme ; approbation limitée à `reduces` ; pas d'entrée publique par défaut (§11) | M5 | prévu |
| W6 | Jeton de service volé | API | S | Jetons hachés, à scopes ; ceux des moteurs liés à une instance et renouvelés à chaque déploiement (§13) | M1 (déduit), reporté à M2 | prévu. Rien n'est livré à M1 : aucun jeton de service n'existe encore ; les jetons liés aux instances et remis aux moteurs viennent à M2 |

### 3.4 Injection de prompt

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | Instruction cachée dans une news ou un flux | WF-04, agents | T, E | Données externes jamais traitées comme instructions (§12) ; corpus dans `tests/agents/injection/`, aucun appel d'outil imprévu (§12, §14 M5) | M5 | prévu |
| P2 | Classement LLM de WF-04 détourné | WF-04 | T | Même corpus ; le flux n'écrit que `POST /events/external`, sans scope d'ordre (§11) | M5 | prévu |
| P3 | Décision de risque confiée à un modèle | Risk service | E | Décision de risque déterministe, jamais déléguée à un LLM (§1 principe 6) | M3 | prévu |
| P4 | Agent de construction qui lit une page, une issue ou un document piégé | Poste de dev | T, E | Contenus externes = données ; action confirmée par l'opérateur (§17.5, `CLAUDE.md`) | M0 | livré (M0) |

### 3.5 Compromission de la chaîne d'approvisionnement

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Dépendance vulnérable ou malveillante | Python, npm | T | Dépendances épinglées par fichier de verrouillage ; pip-audit, `pnpm audit` et Trivy en CI (§13) ; audit `supply-chain` (versions, mainteneurs, scripts d'installation) passé à la main à chaque ajout de dépendance, pas en CI ; ADR pour toute dépendance hors §5 (§0.2) | M0 | livré (M0) |
| C2 | Image de base ou de moteur altérée | Docker | T | Tags exacts, jamais `latest` ; image de moteur vérifiée par digest ; Trivy et SBOM en CI (§13) | M0 (images core), M2 (moteurs) | livré (M0) |
| C3 | Secret ou faille introduite dans le code | Dépôt | I | gitleaks, semgrep, CodeQL en CI (§13) | M0 | livré (M0) |
| C4 | Workflow GitHub Actions injectable | CI | T, E | zizmor et actionlint sans constat (§13) | M0 | livré (M0) |
| C5 | Moteur modifié hors plateforme | Moteurs | T | Empreinte de déploiement (I10) ; dérive de configuration détectée en 60 s (S8) | M2 | prévu |
| C6 | Plugin, skill ou MCP tiers malveillant ou capable d'ordres | Poste de dev | T, E | Relus avant installation, épinglés à une version, hooks téléchargeant des binaires désactivés (§17.5) ; interdits d'exécution d'ordres (§17.7). `claude-mem` 13.35.0 (Apache-2.0, commit `fa8ab09`), ajouté par l'opérateur : ses hooks s'exécutent à chaque appel d'outil et en gardent une trace hors du dépôt ; ses scripts n'ont pas été relus en entier | M0 | politique seule |
| C8 | Outil de CI exécuté à la volée (`uvx`, `npx`, image Docker) remplacé en amont | CI | T, E | Versions exactes ; images de la CI épinglées par digest ; jeton en lecture seule et aucun secret dans les workflows (§13). Les dépendances transitives de ces outils ne sont pas verrouillées par empreinte : voir section 4 | M0 | livré (M0) |
| C7 | Faille résiduelle non vue par l'auteur du code | Dépôt | T, I | Revue de sécurité indépendante à chaque jalon (§13) ; revue complète finale et recherche de secrets dans l'historique (§14 M7) | M7 | prévu |

### 3.6 Poste de développement agentique (§17.5)

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Lecture de `.env`, `secrets/`, clés SSH, identifiants cloud | Poste | I | Règles de refus de lecture et d'écriture dans `.claude/settings.json` ; aucun secret réel (§17.5). Le bac à sable `/sandbox` s'active sur le poste : rien dans le dépôt ne le prouve | M0 | livré (M0) (règles de refus) ; politique seule (bac à sable) |
| D2 | Commande destructrice (suppression récursive, poussée forcée ou sur la branche principale, destruction de volumes Docker, `curl \| sh`) | Poste | T, D | Hooks bloquants (§17.5) | M0 | livré (M0) |
| D3 | `--dangerously-skip-permissions` hors conteneur jetable | Poste | E | Interdit (§17.5) ; devcontainer recommandé (§15) | M0 | politique seule |
| D4 | Serveur MCP de projet approuvé automatiquement | Poste | E | Non approuvé automatiquement ; n8n-mcp sans identifiants de production (§17.5) | M0 | livré (M0) |
| D5 | Mode live activé par une édition de fichier | Config | E | Hook bloquant `dry_run` à `false` et variable live (§17.5) ; promotion par la seule procédure F1 (§0.3). Même limite du hook que pour A4 | M0 (hook), M7 (promotion) | livré (M0) |

### 3.7 Plateforme : autres menaces STRIDE

| ID | Menace | Composant | STRIDE | Parade prévue (SPEC) | Jalon | État |
| --- | --- | --- | --- | --- | --- | --- |
| X1 | Usurpation d'un opérateur (force brute, vol de session) | API, dashboard | S | TOTP à codes de récupération à usage unique ; verrouillage progressif ; sessions 12 h / 30 min ; cookie `__Host-` et `Secure` ; aucun identifiant par défaut (§13) | M1 | livré (M1). Limites : le compteur d'échecs ne décroît pas et il n'existe pas de commande de déblocage depuis l'hôte, donc un pair du VPN peut maintenir verrouillé l'administrateur unique (à traiter à M7, durcissement) ; limiteur de débit en mémoire |
| X2 | Élévation de rôle | API | E | Rôles `viewer`, `operator`, `admin` (§13). Règle retenue : `operator` peut rouvrir les entrées et démarrer une instance `paper` seulement ; hors paper, `admin` est exigé | M1 | livré (M1) |
| X3 | CSRF, XSS, injection | Dashboard, API | T, E | En-têtes de sécurité, CSRF, validation stricte des entrées (§13). Livré : contrôle d'origine sur toute requête qui change un état, `SameSite=Strict`, CSP stricte (une fenêtre Radix qui injectait une balise `<style>` a été remplacée par un `<dialog>` natif), validation des entrées, `params` borné | M1 | livré (M1) |
| X4 | Falsification ou effacement de l'audit | Journal | T, R | I14 : journal inaltérable. Livré : trigger, rôle applicatif `centrade_app` sans `UPDATE`, `DELETE` ni `TRUNCATE` sur `audit_log`, chaîne d'empreintes. Limites : la chaîne n'a pas de clé et n'est vérifiée que par les tests ; la troncature des dernières lignes par le propriétaire de la base n'est pas détectée (ancrage hors base et vérification périodique : M4, avec le panneau « Garanties ») | M1 | livré (M1) |
| X5 | Moteur hors de contrôle ouvre une position sans décision | Moteurs | E | I6 ; S6 : alerte, pause, arrêt du conteneur en cas de récidive | M3 | prévu |
| X6 | Affichage trompeur d'un état supposé ou périmé | Dashboard | I | I1 : état observé, daté, périmé ou « inconnu » | M1 | prévu |
| X7 | Panne de la plateforme non remarquée | Noyau | D | Battement toutes les 60 s vers une surveillance externe, alerte en 5 min (§13) | M4 | prévu |
| X8 | Panne du Risk service ou du hook | Risk service | D | Entrée refusée (I5), sortie jamais bloquée (I4) ; S11, S12 | M3 | prévu |
| X9 | Évasion de conteneur ou abus du socket Docker | Runner, worker | E | Socket proxy limité aux opérations de conteneurs ; gabarit durci (non-root, lecture seule, capacités retirées, `no-new-privileges`) (§13) | M2 | prévu |
| X10 | Interception réseau | Caddy | I | TLS hors réseau Docker interne (livré) ; accès par VPN (§13, §15) : la liaison à l'interface du VPN se règle au déploiement, M0 ne lie que `127.0.0.1` | M0 | livré (M0), VPN au déploiement |
| X12 | Conteneur du noyau compromis qui lit ou falsifie le bus et la base | Postgres, Redis | T, I, E | Réseau `data` interne, joignable par l'API, le Risk service et le worker seulement (§13) ; secrets par Docker secrets ; conteneurs non-root, en lecture seule, sans capacités. Les événements sont des indices, les relevés font foi (§7) | M0 (réseau, durcissement), M1 (événements) | livré (M0) pour le réseau et le durcissement ; livré (M1) pour les événements : les relevés font foi |
| X11 | Exposition publique du dashboard | Caddy | I | Rien n'écoute sur Internet ; exposer = décision consignée dans `accepted-risks.md` (§13) | M0 | livré (M0) |
| X13 | Injection de pannes du FakeEngine par `params.failures` depuis l'API | API, FakeEngine | T | Refusée par défaut : réglage `engine_failure_injection`, faux en production | M1 | livré (M1) |
| X14 | Commande de réduction du risque qui n'atteint pas le moteur (worker en retard, bus en panne) | Worker | D | Envoi prioritaire, échéance comptée depuis l'envoi, étapes du tour isolées (I4). Reste : appels moteur séquentiels, à paralléliser à M2 avant Freqtrade | M1 | livré (M1) |
| X15 | Réouverture des entrées sur un état devenu périmé | Worker, commandes | E | Règle rejouée par le worker juste avant l'envoi (I5) | M1 | livré (M1) |
| X16 | `make bootstrap-admin` affiche l'URI TOTP et les codes de récupération dans la sortie d'un conteneur, donc dans le pilote de journaux Docker | Compose, journaux | I | Consigne à l'opérateur dans le README (noter hors ligne, ne pas laisser dans un journal). Aucun contrôle technique | M2 | ouvert, à traiter à M2 |
| X17 | Flux SSE sans plafond par session : épuisement des connexions | API | D | Aucune | M4 | ouvert, M4 |
| X18 | Le worker lit des secrets dont il n'a pas besoin | Compose, worker | I | Il ne monte que les secrets qu'il emploie (clé maître retirée) | M1 | livré (M1) |

## 4. Menaces sans parade prévue

Le SPEC ne prévoit pas de parade explicite pour :

- **Compromission du VPN ou de l'hôte (VPS)** : le SPEC suppose le VPN (§15) mais ne décrit ni durcissement de l'hôte ni détection d'intrusion.
- **Compromission du poste ou de la session de l'opérateur** (appareil volé, session ouverte) au-delà des durées de session et du TOTP.
- **Falsification du battement vers la surveillance externe** : le SPEC n'exige pas d'authentifier le battement.
- **Compromission de l'API native d'un moteur** par un composant autre que le worker : seule la séparation réseau est prévue.
- **Compromission d'une venue** (hors périmètre).
- **Déni de service volumétrique** au niveau réseau : la limitation de débit de l'API (§8), le verrouillage progressif de l'authentification et l'accès par VPN seul (§13) réduisent la surface ; le SPEC ne prévoit rien de plus.
- **Intégrité des journaux du poste de développement** : non traitée.
- **Dépendances transitives des outils de CI** lancés par `uvx` et `npx` : versions fixées, mais sans verrouillage par empreinte.

## 5. Mises à jour

| Date | Jalon | Changement |
| --- | --- | --- |
| 2026-10-10 | M0 | Création. Toutes les parades sont `prévu`, sauf celles que M0 livre (dépôt, CI, hooks, Compose `core`), marquées `livré (M0)` jusqu'à la vérification de clôture. |
| 2026-10-10 | M0 | Revue de sécurité indépendante : A5, C6 et D3 ramenés à `politique seule` ; limites du hook de mode live (A4, D5) ; C1 corrigé (l'audit `supply-chain` n'est pas en CI) ; ajout de C8, X12 et de la clé de l'autorité de Caddy. |
| 2026-10-10 | M0 | Plugin `claude-mem@thedotmack` ajouté par l'opérateur aux plugins toujours actifs (C6) : manifeste et liste des hooks relus, scripts non relus ; skill `cloud-sync` soumis à l'accord de l'opérateur (§17.7). |
| 2026-10-10 | M0 | Clôture : parades de M0 vérifiées et passées à `livré (M0)`. Caddy recompilé avec Go 1.26.9 et `x/net` 0.60.0 (ADR 0003), non-root et sans capacité. |
| 2026-10-10 | M1 (préparation) | K2 : masquage des secrets dans les logs avancé de M2 à M1, journaux d'uvicorn compris. |
| 2026-10-11 | M1 | Clôture : K2, X1 à X4 et X12 (événements) `livré (M1)`, avec leurs limites ; W6 reporté à M2 ; ajout de X13 à X18. Revue de sécurité indépendante : 0 critique, 0 élevé, 2 moyens corrigés, 6 faibles dont 3 corrigés et 3 reportés. Balayage `insecure-sweep` en repli manuel : 26 candidats, aucun retenu (le périmètre par défaut de la cible omet `packages/`). |
