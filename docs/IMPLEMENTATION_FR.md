# Comprendre l’implémentation du projet AgentOps

## Point de départ et objectif

Le starter Udacity est un notebook : un modèle choisit parmi des outils CRM, deux outils internes trop permissifs et un outil d’envoi fictif. L’objectif du projet est de rendre ce parcours reproductible, contrôlable et observable, sans construire une infrastructure cloud complète.

Le projet précédent Production LLM FAQ servait à vérifier une réponse RAG et son exploitation. Ici, le risque supplémentaire vient des **actions** : le modèle peut proposer une lecture de données ou un envoi. Il faut donc vérifier la proposition avant l’exécution et vérifier l’effet réellement produit.

Le répertoire `starter/` conserve le support d’origine. Les commandes de rendu s’exécutent depuis la racine du dépôt, avec le code de `src/salesops/`.

## Ce qui a changé

| Dans le prototype | Dans le projet |
|---|---|
| Prompt dans une cellule | `resources/system.v1.txt`, chargé à chaque création d’agent |
| Dépendances implicites | Python 3.13, `pyproject.toml` et `uv.lock` |
| Lecture de toutes les données internes | Six jeux CRM autorisés, avec projection des colonnes |
| Recherche approximative pouvant choisir le mauvais compte | Nom normalisé exact ou identifiant ; échec explicite sinon |
| Outils HR et stratégie disponibles | Aucun outil interne exposé ; un appel forcé est bloqué par le code |
| Total de pipeline incluant les dossiers clôturés | Agrégats limités aux opportunités ouvertes |
| Envoi avec destinataire et texte libres | Brouillon stocké, destinataire issu du CRM, décision externe |
| Pas de point d’arrêt | Statut `awaiting_approval`, puis commande `resume` |
| Pas de preuves d’exécution | Événements par étape, log JSONL et trace par run |
| Quelques questions de démonstration | 18 scénarios reproductibles et tests de régression |

## Lire un parcours complet

Prenons « Summarize the account risk for TechStart Inc. ».

1. `cli.py` lit la question et les options. Il construit un objet `Settings`, comparable à un objet de configuration Spring injecté dans un service.
2. `agent.ask()` crée un `Run`, puis appelle `input_reason()`. Si la question porte sur des données interdites, il enregistre un blocage et s’arrête avant le chargement CRM et avant le modèle.
3. `ToolSurface` charge uniquement les sources CRM prévues par `config.v1.json`. Les deux fichiers internes du starter ne sont jamais chargés par l’application.
4. `create_agent()` construit le graphe LangChain. Le modèle reçoit le prompt versionné et les descriptions des outils. Il propose, par exemple, `lookup_account_context` avec `account_name_or_id="TechStart Inc."`.
5. Le middleware `enforce_tools` intercepte cette proposition. `ToolSurface.invoke()` vérifie le nom de l’outil, le budget d’appels et le schéma Pydantic. C’est comparable à une validation de DTO suivie d’un contrôle dans une couche de service Java.
6. L’outil résout le compte A003 et rassemble ses opportunités, contacts, activités, tickets et usages. Les notes suspectes sont masquées avant de revenir au modèle.
7. Le modèle construit une réponse. L’application applique le contrôle de sortie, puis écrit le résumé dans `logs/runs.jsonl` et les événements dans `traces/<run_id>.json`.

La donnée TechStart est volontairement piégeuse : le score de santé est élevé, mais le contrat se termine le 28 mai 2026. Avec la date de référence du 6 novembre 2026, cette échéance est passée. Le prompt indique cette date de référence pour éviter de reprendre littéralement une ancienne note disant « dans moins de 10 jours ». Une évaluation avec le vrai modèle reste nécessaire pour vérifier qu’il raisonne correctement sur cette chronologie.

## Pourquoi le modèle ne décide pas de l’autorisation

Un prompt demandant de respecter les règles peut être ignoré ou mal interprété. Le contrôle d’entrée, les schémas et la sélection des sources sont des fonctions Python exécutées par l’application. Le modèle ne possède pas d’outil pour modifier la configuration ou charger un fichier arbitraire.

La suite impose même une proposition d’outil interdit avec un modèle de test. Le test vérifie que le middleware la bloque, que le statut final reste bloqué et qu’aucune ligne n’apparaît dans l’outbox. Une phrase du modèle disant « action terminée » ne suffit donc pas à établir une réussite.

Le filtrage de sortie complète cette protection. Il cherche les catégories interdites, certains champs sensibles du starter et les formats de clés. Les traces gardent les codes de diagnostic, mais masquent le contenu sensible. Ce filtrage reste limité : les expressions régulières ne constituent pas une garantie générale contre toutes les formulations.

## Le mécanisme d’approbation

`draft_email` construit un brouillon à partir du contact principal. Il le stocke dans SQLite avec un identifiant et un périmètre composé de l’utilisateur, de la session et du thread.

`send_email` ne reçoit qu’un identifiant de brouillon. L’approbation ne figure pas dans son schéma : le modèle ne peut donc pas ajouter `approval="approve"` à ses arguments. La décision vient du paramètre CLI, puis passe à la couche de service.

| Décision | État obtenu | Effet dans l’outbox |
|---|---|---|
| Absente | `awaiting_approval` | Aucun |
| `approve` | `sent`, simulation locale | Une ligne |
| `reject` | `rejected` | Aucun |
| Appel répété du même brouillon approuvé | `sent` | Toujours une seule ligne |
| Autre utilisateur/session/thread | `blocked` | Aucun |

L’idempotence repose sur la clé primaire `draft_id` et une transaction SQLite. Une reprise ne recrée pas le brouillon. Le rejet est terminal : un appel ultérieur au même brouillon ne le transforme pas en envoi.

Ces identifiants sont des espaces locaux de démonstration. Dans un service réel, ils devraient venir d’une identité authentifiée, et l’approbation devrait être attachée au contenu exact affiché au réviseur.

## L’analyse de données contrainte

Le barème autorise un outil d’exécution de code **ou d’analyse de données**. La solution choisie accepte uniquement une petite liste d’opérations sur des colonnes autorisées.

Exemple : `dataset="opportunities"`, `operation="group_sum"`, `field="amount_usd"`, `group_by="stage"`.

Le traitement retire les opportunités clôturées, vérifie les limites, additionne les montants par étape et renvoie un dictionnaire JSON. Les fixtures donnent 133 opportunités ouvertes pour un montant total de 26 525 000 USD. Ces valeurs sont calculées sur les données fictives ; elles ne concernent pas une entreprise réelle.

Il n’existe pas de paramètre `code`, d’import dynamique, de `eval`, de `exec` ni de client réseau dans cet outil. Un argument supplémentaire est refusé par le schéma. Le plafond de lignes borne le travail effectué. Ce choix réduit la surface à comprendre et à maintenir, mais il ne remplace pas un véritable environnement isolé si du Python généré est ajouté à l’avenir.

## Tests, évaluations et preuves

Les tests de régression vérifient des propriétés précises : blocage avant lecture, sortie sensible masquée, sources internes jamais chargées, isolation des périmètres, limites d’analyse, décisions d’approbation, idempotence, coûts calculés à partir des tokens et erreurs sans fuite de clé.

Les 18 scénarios d’évaluation parcourent l’application et produisent un rapport. Ils vérifient aussi la mutation réelle de l’outbox. Les traces permettent de retrouver les outils proposés, leurs arguments, leurs résultats filtrés et les décisions prises.

Le mode local utilise un **modèle scripté explicitement nommé**. Il valide le câblage et les contrôles, sans appeler un fournisseur. Ses coûts API sont nuls. Il ne démontre pas la qualité du raisonnement d’un LLM. `evaluate --live` utilise le vrai modèle pour les questions fonctionnelles, tout en gardant des sondes déterministes pour les attaques imposées.

Au moment de la préparation, Udacity affiche « Your Cloud Resource is inactive ». Les résultats joints ne doivent donc pas être présentés comme une validation du vrai modèle.

## Lire le suivi opérationnel

Le rapport de monitoring compte les réponses/actions terminées, les erreurs techniques, les blocages, les rejets et les attentes d’approbation. Un scénario de sécurité peut réussir précisément parce que l’application a bloqué la demande. Le taux de complétion opérationnelle n’est donc pas le taux de réussite des tests.

Un run correspond ici à une question CLI. Un thread est un identifiant de périmètre pour les brouillons. Il n’existe pas de mémoire conversationnelle partagée entre questions. `inspect` relit une trace et ne rejoue aucune action.

Les coûts résultent des tokens effectivement remontés par le modèle et des tarifs configurés. Ces tarifs doivent être vérifiés pour le fournisseur utilisé. L’historique Git, le prompt et la configuration permettent de rattacher le code aux preuves ; une facture réelle demanderait un rapprochement avec le fournisseur.

## Reproduire le rendu

```bash
uv sync --locked
uv run pytest -q
uv run evaluate
uv run generate-monitoring-report --log reports/evidence/runs.jsonl
uv build
```

Le point d’entrée et les commandes détaillées sont dans le README. `WRITEUP.md` relie chaque exigence aux fichiers et aux résultats. `GITLOG.txt` vient du véritable dépôt publié. GitHub Actions répète les contrôles sans clé API.
