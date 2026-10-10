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
