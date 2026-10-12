# Registre des risques acceptés

Source : SPEC §13 (gates de sécurité, exposition, sorties réseau des moteurs). Un constat de sécurité accepté plutôt que corrigé est consigné ici, jamais sans décision de l'opérateur.

## Mode d'emploi

1. Une ligne par constat, ajoutée seulement après une décision explicite de l'opérateur. Un agent ne peut pas accepter un risque à sa place.
2. Colonnes : constat (outil et identifiant, ou identifiant du `threat-model.md`), justification, propriétaire (une personne), date d'acceptation, date d'expiration (obligatoire).
3. À l'expiration, le risque est corrigé ou ré-accepté par une nouvelle décision datée.
4. Cas prévus par le SPEC : exposition publique du dashboard (§13) ; absence de liste blanche des sorties réseau des moteurs en live (§13, M7) ; constat d'outil de CI accepté (§13).
5. À M7, ce fichier doit être à jour (§14).

## Registre

| Constat | Justification | Propriétaire | Date d'acceptation | Date d'expiration |
| --- | --- | --- | --- | --- |
| *(aucun risque accepté au 2026-10-10)* | | | | |
| X9 : socket proxy filtrant méthode et chemin, pas le corps (un worker compromis pourrait créer un conteneur privilégié) | Aucun live à M2 ; risque borné au paper et au dry-run. Durcissement prévu à M7 (plugin d'autorisation Docker ou démon sans privilèges dédié). ADR 0009, point 14 | Opérateur (nom à inscrire) | **Proposé le 2026-10-12, décision de l'opérateur en attente** | Avant toute promotion en live (M7) |
| X20 : frontière de déchiffrement (I12) tenue par le code et un test d'import, pas par la cryptographie ; rotation de la clé maître impossible | Aucune clé de venue n'est remise à M2. Chiffrement à clé publique et rotation à faire avant le live. ADR 0009, point 13 | Opérateur (nom à inscrire) | **Proposé le 2026-10-12, décision de l'opérateur en attente** | Avant toute promotion en live (M7) |
