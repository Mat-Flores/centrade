# ADR-0006 : Écarts acceptés à M1

## Statut
Acceptée

## Date
2026-10-11

## Contexte
Des choix faits à M1 s'écartent du SPEC ou en restreignent la lettre. Chacun a été relu dans le code à la clôture du jalon. Cette ADR les consigne avec leur raison (§0.14).

## Décision
1. **Clé d'idempotence unique par `(acteur, clé)`**, pas globale (contrainte `uq_commands_actor_idempotency_key`, migration 0004). Deux opérateurs peuvent choisir la même clé sans se bloquer ni se lire.
2. **La table `commands` sert de file** : pas de stream `commands` dans le bus (seul `events` existe). Cela évite la double écriture base et bus, qui peut diverger.
3. **`GET /system/health` répond toujours 200**, avec `status: ok|degraded`. Un composant en panne ne doit pas faire redémarrer l'API ; l'état de chaque composant est observé et daté.
4. **Les étapes `dispatched` et `acknowledged` ne sont pas auditées** ; les états terminaux le sont (`command.verified`, `command.failed`, `command.timed_out`).
5. **Les commandes en échec « vues » sont mémorisées dans le `localStorage`** du navigateur (`apps/web/src/lib/seen.ts`), faute d'acquittement côté serveur. Sans stockage, elles restent à voir.
6. **Moteur injoignable : `unknown` immédiatement**, plus strict que les 30 s du §13 (sens sûr : rien n'est supposé).
7. **Relevé complet de chaque instance à chaque tour du worker.** À espacer à M2, quand les moteurs seront réels.
8. **Une étape du tour en échec supprime le battement du worker** : l'interface passe en mode dégradé. Sens sûr, à affiner à M2.
9. **Le déclencheur de l'âge d'une valeur est un `span` focalisable (`tabIndex=0`), pas un bouton** (`observed-value.tsx`).
10. **`resume_entries` et `start` sont ouverts à `operator` sur le paper seulement** ; hors paper, `admin` est exigé (`instances.py`).

## Alternatives écartées
- Clé d'idempotence globale : un opérateur pourrait en deviner ou en bloquer une autre.
- Stream `commands` : double écriture à réconcilier, sans gain à M1.
- Santé en 503 : redémarrages en boucle du conteneur pour une panne qui n'est pas la sienne.

## Conséquences
- Points 7 et 8 à revoir à M2 ; point 5 à remplacer par un acquittement serveur si le besoin se confirme.
- Le point 9 reste ouvert : la taille de cible de 44 px n'a pas été revérifiée dans le code pour ce `span`.
